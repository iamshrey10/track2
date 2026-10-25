"""Bot setup, guild-scoped command sync and the entry point."""

import asyncio
import logging
import sys

import discord
from discord import app_commands

from swaploop.config import MissingSettingError, Settings, load_env_file, load_settings
from swaploop.db import Database
from swaploop.discord_app.commands import register_commands
from swaploop.discord_app.messenger import DiscordMessenger
from swaploop.discord_app.views import AnswerButton
from swaploop.engine import SwapEngine

log = logging.getLogger(__name__)


class RedactingFormatter(logging.Formatter):
    """Last line of defence: no log line may contain the bot token."""

    def __init__(self, secret: str):
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self._secret = secret

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        return text.replace(self._secret, "[redacted]") if self._secret else text


class SwapLoopBot(discord.Client):
    def __init__(self, settings: Settings):
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.db = Database(settings.db_path)
        self.messenger = DiscordMessenger(self, self.db, settings)
        self.engine = SwapEngine(self.db, self.messenger)
        self.tree = app_commands.CommandTree(self)
        self.tree.on_error = self._on_command_error
        register_commands(self.tree)
        self._delivery_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        self.add_dynamic_items(AnswerButton)
        guild = discord.Object(id=self.settings.guild_id)
        # commands are defined globally in code, then copied to the one guild and synced there only
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("Registered %d slash commands to the guild", len(synced))
        self._delivery_task = asyncio.create_task(self.messenger.run())

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            log.error("The bot is not in the guild GUILD_ID points to")
            return
        names = {channel.name for channel in guild.text_channels}
        for wanted in (self.settings.swap_room_channel, self.settings.demo_console_channel):
            if wanted not in names:
                log.error("Create a text channel named #%s in the guild", wanted)

    async def close(self) -> None:
        if self._delivery_task:
            self._delivery_task.cancel()
        await super().close()
        self.db.close()

    async def _on_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        log.error("Command failed: %s", error, exc_info=error)
        message = "Something went wrong. Try again."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_env_file()
    try:
        settings = load_settings()
    except (MissingSettingError, ValueError) as error:
        log.error("%s", error)
        sys.exit(1)

    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter(settings.discord_token))

    bot = SwapLoopBot(settings)
    try:
        bot.run(settings.discord_token, log_handler=None)
    except discord.LoginFailure:
        log.error("Discord rejected the login. Check DISCORD_TOKEN in .env.")
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        log.error("A privileged intent is required that this bot does not request.")
        sys.exit(1)
