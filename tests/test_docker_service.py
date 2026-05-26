import subprocess

from turbo_whisper.config import Config
from turbo_whisper.docker_service import DockerService


def completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)


def docker_config(**overrides):
    values = {
        "docker_autostart": True,
        "docker_container_name": "turbo-whisper-faster-whisper",
        "docker_run_command": (
            "docker run -d --name turbo-whisper-faster-whisper -p 8000:8000 "
            "-e WHISPER__MODEL=Systran/faster-whisper-base "
            "fedirz/faster-whisper-server:latest-cpu"
        ),
        "api_url": "http://localhost:8000/v1/audio/transcriptions",
    }
    values.update(overrides)
    return Config(**values)


def fail_if_called(*args, **kwargs):
    raise AssertionError("subprocess.run should not be called")


def test_docker_disabled_does_nothing(monkeypatch):
    service = DockerService(docker_config(docker_autostart=False))

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    result = service.start()

    assert result.ok is True
    assert result.skipped is True
    assert service.started_by_app is False


def test_existing_running_container_is_not_restarted(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["docker", "--version"]:
            return completed(args, stdout="Docker version 1\n")
        if args[:3] == ["docker", "inspect", "-f"]:
            return completed(args, stdout="true\n")
        raise AssertionError(f"unexpected command: {args}")

    service = DockerService(docker_config())
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(service, "_wait_for_api", lambda: True)

    result = service.start()

    assert result.ok is True
    assert result.started_by_app is False
    assert service.started_by_app is False
    assert calls == [
        ["docker", "--version"],
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            "turbo-whisper-faster-whisper",
        ],
    ]


def test_existing_stopped_container_uses_docker_start(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["docker", "--version"]:
            return completed(args)
        if args[:3] == ["docker", "inspect", "-f"]:
            return completed(args, stdout="false\n")
        if args == ["docker", "start", "turbo-whisper-faster-whisper"]:
            return completed(args, stdout="turbo-whisper-faster-whisper\n")
        raise AssertionError(f"unexpected command: {args}")

    service = DockerService(docker_config())
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(service, "_wait_for_api", lambda: True)

    result = service.start()

    assert result.ok is True
    assert result.started_by_app is True
    assert service.started_by_app is True
    assert ["docker", "start", "turbo-whisper-faster-whisper"] in calls


def test_missing_container_uses_configured_docker_run(monkeypatch):
    calls = []
    configured_command = [
        "docker",
        "run",
        "-d",
        "--name",
        "turbo-whisper-faster-whisper",
        "-p",
        "8000:8000",
        "-e",
        "WHISPER__MODEL=Systran/faster-whisper-base",
        "fedirz/faster-whisper-server:latest-cpu",
    ]

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["docker", "--version"]:
            return completed(args)
        if args[:3] == ["docker", "inspect", "-f"]:
            return completed(args, returncode=1, stderr="No such object")
        if args == configured_command:
            return completed(args, stdout="container-id\n")
        raise AssertionError(f"unexpected command: {args}")

    service = DockerService(docker_config())
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(service, "_wait_for_api", lambda: True)

    result = service.start()

    assert result.ok is True
    assert result.started_by_app is True
    assert configured_command in calls


def test_missing_container_rejects_mismatched_docker_run_name(monkeypatch):
    calls = []
    config = docker_config(
        docker_run_command=(
            "docker run -d --name other-name -p 8000:8000 "
            "fedirz/faster-whisper-server:latest-cpu"
        )
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["docker", "--version"]:
            return completed(args)
        if args[:3] == ["docker", "inspect", "-f"]:
            return completed(args, returncode=1, stderr="No such object")
        raise AssertionError(f"unexpected command: {args}")

    service = DockerService(config)
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = service.start()

    assert result.ok is False
    assert result.message == (
        'Docker command --name must match configured container name '
        '"turbo-whisper-faster-whisper"'
    )
    assert service.started_by_app is False
    assert calls == [
        ["docker", "--version"],
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            "turbo-whisper-faster-whisper",
        ],
    ]


def test_docker_start_timeout_reports_clean_error(monkeypatch):
    def fake_run(args, **kwargs):
        if args == ["docker", "--version"]:
            raise subprocess.TimeoutExpired(args, timeout=10)
        raise AssertionError(f"unexpected command: {args}")

    service = DockerService(docker_config())
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = service.start()

    assert result.ok is False
    assert result.message == "Docker command timed out: docker --version"
    assert service.started_by_app is False


def test_missing_docker_cli_reports_clean_error(monkeypatch):
    def fake_run(args, **kwargs):
        if args == ["docker", "--version"]:
            raise FileNotFoundError
        raise AssertionError(f"unexpected command: {args}")

    service = DockerService(docker_config())
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = service.start()

    assert result.ok is False
    assert result.message == "Docker CLI is not available"
    assert service.started_by_app is False


def test_started_by_app_container_is_stopped_on_quit(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return completed(args)

    service = DockerService(docker_config())
    service.started_by_app = True
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert service.stop() is True
    assert service.started_by_app is False
    assert calls == [["docker", "stop", "turbo-whisper-faster-whisper"]]


def test_stop_timeout_returns_false(monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, timeout=10)

    service = DockerService(docker_config())
    service.started_by_app = True
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert service.stop() is False
    assert service.started_by_app is True


def test_pre_existing_running_container_is_not_stopped_on_quit(monkeypatch):
    service = DockerService(docker_config())
    service.started_by_app = False

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    assert service.stop() is False
