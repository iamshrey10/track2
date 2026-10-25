"""Delivers engine messages to Discord, one at a time and in order."""

import asyncio
import logging

import discord

from swaploop.config import Settings
from swaploop.db import Database
from swaploop.discord_app.formatting import render_demo_console, render_dm, render_swap_room
from swaploop.discord_app.views import build_answer_view
from swaploop.messaging import OutgoingMessage
from swaploop.models import Channel, MessageKind

log = logging.getLogger(__name__)


class DiscordMessenger:
    """The engine is synchronous, so messages are queued and a single worker sends them."""

    def __init__(self, client: discord.Client, db: Database, settings: Settings):
        self._client = client
        self._db = db
        self._settings = settings
        self._queue: asyncio.Queue[OutgoingMessage] = asyncio.Queue()

    def send(self, message: OutgoingMessage) -> None:
        self._queue.put_nowait(message)

    def post_swap_room(self, text: str) -> None:
        self.send(OutgoingMessage(Channel.SWAP_ROOM, MessageKind.INFO, text))

    def post_demo_console(self, text: str) -> None:
        self.send(OutgoingMessage(Channel.DEMO_CONSOLE, MessageKind.INFO, text))

    async def run(self) -> None:
        while True:
            message = await self._queue.get()
            try:
                await self._deliver(message)
            except Exception:
                log.exception("Could not deliver a %s message", message.kind.value)
            finally:
                self._queue.task_done()

    async def _deliver(self, message: OutgoingMessage) -> None:
        if message.channel is Channel.SWAP_ROOM:
            await self._post(self._settings.swap_room_channel, render_swap_room(message))
        elif message.channel is Channel.DEMO_CONSOLE:
            await self._post_to_demo_console(message)
        else:
            await self._deliver_dm(message)

    async def _post_to_demo_console(self, message: OutgoingMessage) -> bool:
        view = None
        if message.kind is MessageKind.PROMPT and message.loop_id and message.recipient_id:
            view = build_answer_view(message.loop_id, message.recipient_id, message.recipient_name)
        return await self._post(self._settings.demo_console_channel, render_demo_console(message), view)

    async def _deliver_dm(self, message: OutgoingMessage) -> None:
        student = self._db.get_student(message.recipient_id)
        view = None
        if message.kind is MessageKind.PROMPT and message.loop_id:
            view = build_answer_view(message.loop_id, student.id)
        try:
            user = await self._client.fetch_user(int(student.discord_id))
            await user.send(render_dm(message), view=view if view is not None else discord.utils.MISSING)
        except (discord.Forbidden, discord.HTTPException, TypeError, ValueError):
            log.warning("DM to %s failed; using #%s instead", student.agent_label,
                        self._settings.demo_console_channel)
            await self._post_to_demo_console(message)

    async def _post(self, channel_name: str, text: str, view: discord.ui.View | None = None) -> bool:
        guild = self._client.get_guild(self._settings.guild_id)
        channel = discord.utils.get(guild.text_channels, name=channel_name) if guild else None
        if channel is None:
            log.error("Channel #%s was not found in the guild", channel_name)
            return False
        try:
            await channel.send(text, view=view if view is not None else discord.utils.MISSING)
        except discord.HTTPException as error:
            log.warning("Could not post to #%s (%s)", channel_name, error.status)
            return False
        return True
