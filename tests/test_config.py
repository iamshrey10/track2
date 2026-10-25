import pytest

from swaploop.config import MissingSettingError, load_settings


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
