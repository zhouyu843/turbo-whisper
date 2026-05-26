"""Save and restore the frontmost application focus (macOS)."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class FocusTarget:
    """A running app to re-activate before pasting transcribed text."""

    bundle_id: str = ""
    app_name: str = ""
    pid: int = 0


def capture_focus() -> FocusTarget | None:
    """Remember which app has keyboard focus (call before showing the recording UI)."""
    if sys.platform == "darwin":
        return _capture_macos()
    return None


def restore_focus(target: FocusTarget | None) -> bool:
    """Bring the previously focused app back to the front."""
    if target is None:
        return False
    if sys.platform == "darwin":
        return _restore_macos(target)
    return False


def _capture_macos() -> FocusTarget | None:
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        return FocusTarget(
            bundle_id=app.bundleIdentifier() or "",
            app_name=app.localizedName() or "",
            pid=int(app.processIdentifier()),
        )
    except Exception as exc:
        print(f"Focus capture failed: {exc}")
        return _capture_macos_applescript()


def _restore_macos(target: FocusTarget) -> bool:
    if target.bundle_id:
        try:
            from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication

            apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(
                target.bundle_id
            )
            if apps:
                apps[0].activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                return True
        except Exception as exc:
            print(f"Focus restore failed: {exc}")

    if target.app_name:
        return _restore_macos_applescript(target.app_name)
    return False


def _capture_macos_applescript() -> FocusTarget | None:
    script = (
        'tell application "System Events" to get name of '
        "first application process whose frontmost is true"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    app_name = result.stdout.strip()
    if not app_name:
        return None
    return FocusTarget(app_name=app_name)


def _restore_macos_applescript(app_name: str) -> bool:
    escaped = app_name.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "{escaped}" to activate'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0

