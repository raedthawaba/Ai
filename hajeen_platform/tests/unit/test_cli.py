import yaml
from typer.testing import CliRunner

from data_engine.channels.registry import ChannelRegistry
from data_engine.cli import app


runner = CliRunner()


def _read_channels(config_path):
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return payload["channels"]


def setup_function():
    ChannelRegistry.clear()


def teardown_function():
    ChannelRegistry.clear()


def test_cli_create_list_and_trigger_channel(tmp_path, monkeypatch):
    config_path = tmp_path / "channels.yaml"
    monkeypatch.setenv("HAJEEN_CHANNELS_CONFIG", str(config_path))

    create_result = runner.invoke(
        app,
        [
            "create-channel",
            "--name",
            "Demo CLI",
            "--type",
            "demo",
            "--url",
            "https://example.com/demo",
        ],
    )

    assert create_result.exit_code == 0
    assert "Created channel" in create_result.output

    stored_channels = _read_channels(config_path)
    assert len(stored_channels) == 1
    assert stored_channels[0]["name"] == "Demo CLI"
    channel_id = stored_channels[0]["id"]

    list_result = runner.invoke(app, ["list-channels"])
    assert list_result.exit_code == 0
    assert "Demo CLI" in list_result.output
    assert channel_id in list_result.output

    trigger_result = runner.invoke(app, ["trigger-channel", channel_id])
    assert trigger_result.exit_code == 0
    assert "Running channel" in trigger_result.output
    assert "Fetch completed" in trigger_result.output
    assert "Pipeline completed" in trigger_result.output


def test_cli_rejects_invalid_schedule(tmp_path, monkeypatch):
    config_path = tmp_path / "channels.yaml"
    monkeypatch.setenv("HAJEEN_CHANNELS_CONFIG", str(config_path))

    result = runner.invoke(
        app,
        [
            "create-channel",
            "--name",
            "Broken Schedule",
            "--type",
            "demo",
            "--url",
            "https://example.com/demo",
            "--schedule",
            "invalid cron",
        ],
    )

    assert result.exit_code == 2
    assert "Invalid cron expression" in result.output


def test_cli_trigger_missing_channel_returns_error(tmp_path, monkeypatch):
    config_path = tmp_path / "channels.yaml"
    monkeypatch.setenv("HAJEEN_CHANNELS_CONFIG", str(config_path))

    result = runner.invoke(app, ["trigger-channel", "ch_missing"])

    assert result.exit_code == 1
    assert "was not found" in result.output
