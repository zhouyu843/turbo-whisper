"""Docker lifecycle helper for local Whisper servers."""

from __future__ import annotations

import shlex
import socket
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

from .config import Config


@dataclass
class DockerStartResult:
    """Result from attempting to start the configured Docker service."""

    ok: bool
    message: str
    started_by_app: bool = False
    skipped: bool = False


class DockerService:
    """Manage an optional local Docker container for self-hosted Whisper."""

    def __init__(self, config: Config):
        self.config = config
        self.started_by_app = False

    def start(self) -> DockerStartResult:
        """Start or attach to the configured Docker container."""
        try:
            return self._start()
        except DockerCommandTimeout as exc:
            return DockerStartResult(ok=False, message=str(exc))

    def _start(self) -> DockerStartResult:
        """Start or attach to the configured Docker container."""
        if not self.config.docker_autostart or not self.config.docker_run_command.strip():
            return DockerStartResult(
                ok=True,
                message="Docker autostart is disabled",
                skipped=True,
            )

        if not self._docker_available():
            return DockerStartResult(ok=False, message="Docker CLI is not available")

        name = self.config.docker_container_name.strip()
        if not name:
            return DockerStartResult(ok=False, message="Docker container name is empty")

        state = self._container_state(name)
        if state == "running":
            ready = self._wait_for_api()
            if ready:
                return DockerStartResult(ok=True, message="Docker container is already running")
            return DockerStartResult(
                ok=False,
                message="Docker container is running, but the Whisper endpoint timed out",
            )

        if state == "stopped":
            result = self._run(["docker", "start", name])
            if result.returncode != 0:
                return DockerStartResult(
                    ok=False,
                    message=self._format_error("Could not start Docker container", result),
                )
            self.started_by_app = True
        else:
            try:
                command = shlex.split(self.config.docker_run_command)
            except ValueError as exc:
                return DockerStartResult(ok=False, message=f"Invalid Docker command: {exc}")

            if len(command) < 2 or command[0] != "docker" or command[1] != "run":
                return DockerStartResult(
                    ok=False,
                    message='Docker command must start with "docker run"',
                )
            command_name = self._get_run_container_name(command)
            if command_name != name:
                return DockerStartResult(
                    ok=False,
                    message=(
                        "Docker command --name must match configured container name "
                        f'"{name}"'
                    ),
                )

            result = self._run(command)
            if result.returncode != 0:
                return DockerStartResult(
                    ok=False,
                    message=self._format_error("Could not run Docker container", result),
                )
            self.started_by_app = True

        if not self._wait_for_api():
            return DockerStartResult(
                ok=False,
                message="Docker started, but the Whisper endpoint timed out",
                started_by_app=self.started_by_app,
            )

        return DockerStartResult(
            ok=True,
            message="Docker Whisper server is ready",
            started_by_app=self.started_by_app,
        )

    def stop(self, *, on_settings_change: bool = False) -> bool:
        """Stop the container only if this app session started it.

        When ``on_settings_change`` is True, stop even if ``docker_autostop`` is
        disabled (user turned off Docker autostart in settings).
        """
        if not self.started_by_app or not self.config.docker_container_name.strip():
            return False

        if not on_settings_change and not self.config.docker_autostop:
            return False

        try:
            result = self._run(["docker", "stop", self.config.docker_container_name.strip()])
        except DockerCommandTimeout:
            return False
        if result.returncode == 0:
            self.started_by_app = False
            return True
        return False

    def _docker_available(self) -> bool:
        try:
            result = self._run(["docker", "--version"])
        except FileNotFoundError:
            return False
        return result.returncode == 0

    def _container_state(self, name: str) -> str:
        result = self._run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
        )
        if result.returncode != 0:
            return "missing"
        if result.stdout.strip().lower() == "true":
            return "running"
        return "stopped"

    def _wait_for_api(self) -> bool:
        parsed = urlparse(self.config.api_url)
        if not parsed.hostname:
            return False

        if parsed.port is not None:
            port = parsed.port
        elif parsed.scheme == "https":
            port = 443
        else:
            port = 80

        deadline = time.monotonic() + self.config.docker_start_timeout_seconds
        while time.monotonic() <= deadline:
            try:
                with socket.create_connection((parsed.hostname, port), timeout=1.0):
                    return True
            except OSError:
                time.sleep(0.25)
        return False

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired as exc:
            command = " ".join(args)
            raise DockerCommandTimeout(f"Docker command timed out: {command}") from exc

    @staticmethod
    def _get_run_container_name(command: Sequence[str]) -> str | None:
        for index, arg in enumerate(command):
            if arg == "--name" and index + 1 < len(command):
                return command[index + 1]
            if arg.startswith("--name="):
                return arg.split("=", 1)[1]
        return None

    @staticmethod
    def _format_error(prefix: str, result: subprocess.CompletedProcess[str]) -> str:
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            return f"{prefix}: {detail}"
        return prefix


class DockerCommandTimeout(Exception):
    """Raised when a Docker CLI command times out."""
