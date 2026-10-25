import pytest

from swaploop.config import MissingSettingError, load_env_file, load_settings


def test_loads_values_from_environment():
    settings = load_settings({"DISCORD_TOKEN": "t", "GUILD_ID": "42", "SWAPLOOP_DB": "x.db"})
    assert settings.guild_id == 42
    assert settings.db_path == "x.db"
    assert settings.swap_room_channel == "swap-room"


@pytest.mark.parametrize("missing", ["DISCORD_TOKEN", "GUILD_ID"])
def test_missing_variable_is_named(missing):
    env = {"DISCORD_TOKEN": "t", "GUILD_ID": "42"}
    del env[missing]
    with pytest.raises(MissingSettingError, match=missing):
        load_settings(env)


def test_blank_token_counts_as_missing():
    with pytest.raises(MissingSettingError, match="DISCORD_TOKEN"):
        load_settings({"DISCORD_TOKEN": "  ", "GUILD_ID": "42"})


def test_non_numeric_guild_id_is_rejected():
    with pytest.raises(ValueError, match="GUILD_ID"):
        load_settings({"DISCORD_TOKEN": "t", "GUILD_ID": "abc"})


def test_repr_does_not_expose_token():
    settings = load_settings({"DISCORD_TOKEN": "super-secret", "GUILD_ID": "1"})
    assert "super-secret" not in repr(settings)


def test_blank_optional_values_fall_back_to_defaults():
    settings = load_settings(
        {"DISCORD_TOKEN": "t", "GUILD_ID": "1", "SWAPLOOP_DB": "", "SWAP_ROOM_CHANNEL": " "}
    )
    assert settings.db_path == "swaploop.db"
    assert settings.swap_room_channel == "swap-room"


def test_env_file_fills_missing_values_only(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nGUILD_ID=\"123\"\nexport SWAPLOOP_DB=from_file.db\nDISCORD_TOKEN=\nNOT A LINE\n"
    )
    monkeypatch.delenv("GUILD_ID", raising=False)
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("SWAPLOOP_DB", "already_set.db")

    load_env_file(env_file)

    import os
    assert os.environ["GUILD_ID"] == "123"
    assert os.environ["SWAPLOOP_DB"] == "already_set.db"
    assert "DISCORD_TOKEN" not in os.environ
    monkeypatch.delenv("GUILD_ID")


def test_missing_env_file_is_fine(tmp_path):
    load_env_file(tmp_path / "nope.env")
