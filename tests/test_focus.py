"""Tests for focus capture/restore helpers."""

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
