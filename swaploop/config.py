"""Runtime settings, read only from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass


class MissingSettingError(RuntimeError):
    def __init__(self, name: str):
        super().__init__(f"Missing required environment variable: {name}")
        self.name = name


@dataclass(frozen=True)
class Settings:
    discord_token: str = ""
    guild_id: int = 0
    db_path: str = "swaploop.db"
    swap_room_channel: str = "swap-room"
    demo_console_channel: str = "demo-console"

    def __repr__(self) -> str:
        return (
            f"Settings(guild_id={self.guild_id}, db_path={self.db_path!r}, "
            f"swap_room_channel={self.swap_room_channel!r}, "
            f"demo_console_channel={self.demo_console_channel!r})"
        )


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ

    token = env.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise MissingSettingError("DISCORD_TOKEN")

    raw_guild_id = env.get("GUILD_ID", "").strip()
    if not raw_guild_id:
        raise MissingSettingError("GUILD_ID")
    try:
        guild_id = int(raw_guild_id)
    except ValueError:
        raise ValueError("GUILD_ID must be a numeric Discord guild id") from None

    return Settings(
        discord_token=token,
        guild_id=guild_id,
        db_path=env.get("SWAPLOOP_DB", "swaploop.db"),
        swap_room_channel=env.get("SWAP_ROOM_CHANNEL", "swap-room"),
        demo_console_channel=env.get("DEMO_CONSOLE_CHANNEL", "demo-console"),
    )
