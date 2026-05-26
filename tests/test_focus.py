"""Tests for focus capture/restore helpers."""

import sys
from types import SimpleNamespace

from turbo_whisper.focus import FocusTarget, restore_focus


def test_restore_focus_no_target():
    assert restore_focus(None) is False


def test_restore_focus_non_macos(monkeypatch):
    monkeypatch.setattr("turbo_whisper.focus.sys.platform", "linux")
    target = FocusTarget(app_name="Cursor", bundle_id="com.todesktop.cursor")
    assert restore_focus(target) is False


def test_focus_target_fields():
    target = FocusTarget(bundle_id="com.apple.Terminal", app_name="Terminal", pid=123)
    assert target.bundle_id == "com.apple.Terminal"
    assert target.app_name == "Terminal"
    assert target.pid == 123


def test_restore_focus_prefers_pid_on_macos(monkeypatch):
    activated = []

    class FakeApp:
        def __init__(self, name):
            self.name = name

        def activateWithOptions_(self, _option):
            activated.append(self.name)
            return True

    class FakeRunningApplication:
        @staticmethod
        def runningApplicationWithProcessIdentifier_(_pid):
            return FakeApp("pid-match")

        @staticmethod
        def runningApplicationsWithBundleIdentifier_(_bundle_id):
            return [FakeApp("bundle-match")]

    fake_appkit = SimpleNamespace(
        NSApplicationActivateIgnoringOtherApps=1,
        NSRunningApplication=FakeRunningApplication,
    )

    monkeypatch.setattr("turbo_whisper.focus.sys.platform", "darwin")
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit)

    target = FocusTarget(
        bundle_id="com.example.Editor",
        app_name="Editor",
        pid=123,
    )

    assert restore_focus(target) is True
    assert activated == ["pid-match"]
