import json

from turbo_whisper.config import Config


def test_load_old_config_without_docker_fields(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "api_url": "http://localhost:8000/v1/audio/transcriptions",
                "api_key": "",
                "history": [],
            }
        )
    )

    monkeypatch.setattr(Config, "get_config_path", classmethod(lambda cls: config_path))

    config = Config.load()

    assert config.docker_autostart is False
    assert config.docker_autostop is True
    assert config.docker_container_name == "turbo-whisper-faster-whisper"
    assert config.docker_run_command == ""
    assert config.docker_start_timeout_seconds == 30.0
