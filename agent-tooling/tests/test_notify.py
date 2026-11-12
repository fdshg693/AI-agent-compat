"""agent_tooling/notify/: OS ごとの振り分けと Windows／macOS バックエンドの分岐。

実際の音・ウィンドウ・通知は出さない（winsound・subprocess を差し替える）。
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest

from agent_tooling import notify
from agent_tooling.notify import macos as notify_macos
from agent_tooling.notify import project as notify_project
from agent_tooling.notify import windows as notify_windows

# ---------------------------------------------------------------------------
# 振り分け
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("platform", ["linux", "freebsd", "cygwin"])
def test_unsupported_platform_returns_unsupported(monkeypatch, platform):
    monkeypatch.setattr(notify.sys, "platform", platform)
    expected = {"ok": False, "mode": "unsupported", "detail": f"platform={platform}"}
    assert notify.notify_sound(None) == expected
    assert (
        notify.notify_popup("t", 1, "p", entry_script=Path("x.py"), popup_flag="--popup")
        == expected
    )
    assert notify.run_notify_popup("t", 1, "p", "App") is None


def test_unsupported_wins_over_disabled(monkeypatch):
    monkeypatch.setattr(notify.sys, "platform", "linux")
    assert notify.notify_sound(None, enabled=False)["mode"] == "unsupported"


def test_disabled_on_supported_platform(monkeypatch):
    monkeypatch.setattr(notify.sys, "platform", "win32")
    assert notify.notify_sound(None, enabled=False) == {"ok": False, "mode": "disabled"}
    popup = notify.notify_popup(
        "t", 1, "p", entry_script=Path("x.py"), popup_flag="--popup", enabled=False
    )
    assert popup == {"ok": False, "mode": "disabled"}


def test_dispatch_selects_backend_by_platform(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.sys, "platform", "win32")
    monkeypatch.setitem(
        notify._SOUND_BACKENDS, "win32", lambda path: calls.append(path) or {"ok": True}
    )
    assert notify.notify_sound(Path("a.wav")) == {"ok": True}
    assert calls == [Path("a.wav")]


def test_backend_exception_does_not_escape(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(notify.sys, "platform", "win32")
    monkeypatch.setitem(notify._SOUND_BACKENDS, "win32", boom)
    monkeypatch.setitem(notify._POPUP_SPAWNERS, "win32", boom)
    assert notify.notify_sound(None) == {"ok": False, "mode": "error", "detail": "boom"}
    popup = notify.notify_popup("t", 1, "p", entry_script=Path("x.py"), popup_flag="--popup")
    assert popup == {"ok": False, "mode": "spawn_failed", "detail": "boom"}


def test_backend_tables_cover_the_same_platforms():
    assert set(notify._SOUND_BACKENDS) == set(notify._POPUP_SPAWNERS) == {"win32", "darwin"}
    # 子プロセスで描くのは Windows だけ
    assert set(notify._POPUP_WINDOWS) <= set(notify._POPUP_SPAWNERS)


def test_darwin_dispatches_popup_to_mac_backend(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(notify.sys, "platform", "darwin")
    monkeypatch.setitem(
        notify._POPUP_SPAWNERS, "darwin", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    notify.notify_popup(
        "t",
        1,
        "p",
        entry_script=Path("x.py"),
        popup_flag="--popup",
        subtitle="~/w",
        notification_id="sid",
        helper_app=tmp_path / "X.app",
    )
    ((args, kwargs),) = calls
    assert args == ("t", 1, "p", Path("x.py"), "--popup")
    assert kwargs == {"subtitle": "~/w", "notification_id": "sid", "helper_app": tmp_path / "X.app"}


# ---------------------------------------------------------------------------
# Windows バックエンド（winsound を偽物に差し替える）
# ---------------------------------------------------------------------------


class FakeWinsound(types.ModuleType):
    SND_FILENAME = 0x1
    SND_SYNC = 0x2
    MB_ICONASTERISK = 0x40

    def __init__(self, *, play_fails=False, message_beep_fails=False, beep_fails=False):
        super().__init__("winsound")
        self.calls: list[tuple] = []
        self._play_fails = play_fails
        self._message_beep_fails = message_beep_fails
        self._beep_fails = beep_fails

    def PlaySound(self, path, flags):  # noqa: N802 - winsound の名前に合わせる
        self.calls.append(("PlaySound", path, flags))
        if self._play_fails:
            raise RuntimeError("bad wav")

    def MessageBeep(self, kind):  # noqa: N802
        self.calls.append(("MessageBeep", kind))
        if self._message_beep_fails:
            raise RuntimeError("no beep")

    def Beep(self, freq, dur):  # noqa: N802
        self.calls.append(("Beep", freq, dur))
        if self._beep_fails:
            raise RuntimeError("no tone")


@pytest.fixture
def fake_winsound(monkeypatch):
    def install(**kwargs):
        fake = FakeWinsound(**kwargs)
        monkeypatch.setitem(sys.modules, "winsound", fake)
        return fake

    return install


def test_win_plays_file_when_given(fake_winsound, tmp_path):
    fake = fake_winsound()
    wav = tmp_path / "a.wav"
    result = notify_windows._win_play_sound(wav)
    assert result == {"ok": True, "mode": "file", "path": str(wav)}
    assert fake.calls == [("PlaySound", str(wav), 0x3)]


def test_win_falls_back_to_beep_when_file_fails(fake_winsound, monkeypatch, tmp_path):
    fake_winsound(play_fails=True)
    monkeypatch.setattr(notify_windows, "_win_asterisk_sound_configured", lambda: True)
    result = notify_windows._win_play_sound(tmp_path / "a.wav")
    assert result["mode"] == "beep"
    assert result["ok"] is True
    assert result["detail"] == "bad wav"
    assert result["path"] == str(tmp_path / "a.wav")


def test_win_beeps_without_file(fake_winsound, monkeypatch):
    fake = fake_winsound()
    monkeypatch.setattr(notify_windows, "_win_asterisk_sound_configured", lambda: True)
    assert notify_windows._win_play_sound(None) == {"ok": True, "mode": "beep", "path": None}
    assert fake.calls == [("MessageBeep", 0x40)]


def test_win_tone_when_asterisk_unassigned(fake_winsound, monkeypatch):
    fake = fake_winsound()
    monkeypatch.setattr(notify_windows, "_win_asterisk_sound_configured", lambda: False)
    assert notify_windows._win_play_sound(None) == {"ok": True, "mode": "tone", "path": None}
    assert fake.calls == [("Beep", 880, 300)]


def test_win_tone_fallback_when_message_beep_fails(fake_winsound, monkeypatch):
    fake_winsound(message_beep_fails=True)
    monkeypatch.setattr(notify_windows, "_win_asterisk_sound_configured", lambda: True)
    result = notify_windows._win_play_sound(None)
    assert result["mode"] == "tone_fallback"
    assert result["ok"] is True


def test_win_beep_failed_when_everything_fails(fake_winsound, monkeypatch):
    fake_winsound(message_beep_fails=True, beep_fails=True)
    monkeypatch.setattr(notify_windows, "_win_asterisk_sound_configured", lambda: True)
    result = notify_windows._win_play_sound(None)
    assert result == {"ok": False, "mode": "beep_failed", "detail": "no beep; no tone"}


def test_win_spawn_popup_reruns_entry_script(monkeypatch):
    spawned = []
    monkeypatch.setattr(notify_windows.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(notify_windows.subprocess, "CREATE_NEW_PROCESS_GROUP", 0, raising=False)
    monkeypatch.setattr(
        notify_windows.subprocess, "Popen", lambda argv, **kwargs: spawned.append(argv)
    )
    result = notify_windows._win_spawn_popup("hi", 5.0, "proj", Path("hooks/x.py"), "--popup")
    assert result == {
        "ok": True,
        "mode": "spawned",
        "text": "hi",
        "seconds": 5.0,
        "project": "proj",
    }
    (argv,) = spawned
    assert argv == [
        sys.executable,
        str(Path("hooks/x.py").resolve()),
        "--popup",
        "hi",
        "5.0",
        "proj",
    ]


# ---------------------------------------------------------------------------
# macOS バックエンド（subprocess を差し替え、渡る引数だけを見る）
# ---------------------------------------------------------------------------


class FakeRun:
    """`subprocess.run` の代わり。argv を記録し、プログラム名ごとの終了コードを返す。"""

    def __init__(self, codes: dict[str, int] | None = None):
        self.calls: list[list[str]] = []
        self.codes = codes or {}

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        code = self.codes.get(Path(argv[0]).name, 0)
        return subprocess.CompletedProcess(argv, code, stdout="", stderr="err" if code else "")


@pytest.fixture
def helper_app(tmp_path):
    app = tmp_path / "ClaudeNotify.app"
    binary = app / "Contents" / "MacOS" / "ClaudeNotify"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    return app


@pytest.fixture
def fake_run(monkeypatch):
    def install(**codes):
        fake = FakeRun(codes)
        monkeypatch.setattr(notify_macos.subprocess, "run", fake)
        return fake

    return install


def test_mac_post_uses_helper_with_id(fake_run, helper_app):
    fake = fake_run()
    result = notify_macos._mac_post(
        "T", "~/w", "B", sound="Glass", notification_id="sid", helper_app=helper_app
    )
    assert result == {"ok": True, "mode": "helper"}
    (argv,) = fake.calls
    assert argv == [
        str(helper_app / "Contents" / "MacOS" / "ClaudeNotify"),
        *("post", "--id", "sid", "--title", "T", "--subtitle", "~/w", "--body", "B"),
        *("--sound", "Glass"),
    ]


def test_mac_post_falls_back_to_osascript_without_helper(fake_run, tmp_path):
    fake = fake_run()
    result = notify_macos._mac_post(
        "T", "S", "B", notification_id="sid", helper_app=tmp_path / "Missing.app"
    )
    assert result["mode"] == "osascript"
    assert result["helper"]["mode"] == "helper_missing"
    (argv,) = fake.calls
    assert argv[:2] == ["osascript", "-e"]
    # 値は argv で渡す（スクリプトに埋め込まない）
    assert argv[3:] == ["T", "S", "B", ""]


@pytest.mark.parametrize("code", [1, 2])
def test_mac_post_falls_back_when_helper_fails(fake_run, helper_app, code):
    fake = fake_run(ClaudeNotify=code)
    result = notify_macos._mac_post("T", "S", "B", notification_id="sid", helper_app=helper_app)
    assert result["mode"] == "osascript"
    assert result["helper"]["mode"] == "helper_failed"
    assert [Path(argv[0]).name for argv in fake.calls] == ["ClaudeNotify", "osascript"]


def test_mac_post_does_nothing_when_denied(fake_run, helper_app):
    fake = fake_run(ClaudeNotify=3)
    result = notify_macos._mac_post("T", "S", "B", notification_id="sid", helper_app=helper_app)
    assert result["mode"] == "helper_denied"
    assert result["ok"] is False
    assert len(fake.calls) == 1


def test_mac_post_without_id_skips_helper(fake_run, helper_app):
    fake = fake_run()
    assert notify_macos._mac_post("T", "S", "B", helper_app=helper_app)["mode"] == "osascript"
    assert [argv[0] for argv in fake.calls] == ["osascript"]


def test_mac_post_reports_osascript_failure(fake_run):
    fake_run(osascript=1)
    result = notify_macos._mac_post("T", "S", "B")
    assert result["ok"] is False
    assert result["mode"] == "osascript_failed"


def test_mac_helper_timeout_is_reported(monkeypatch, helper_app):
    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(notify_macos.subprocess, "run", slow)
    result = notify_macos._mac_remove("sid", helper_app=helper_app, timeout=2)
    assert result == {"ok": False, "mode": "helper_timeout", "detail": "2s"}


def test_mac_remove(fake_run, helper_app):
    fake = fake_run()
    assert notify_macos._mac_remove("", helper_app=helper_app) == {"ok": False, "mode": "no_id"}
    assert notify_macos._mac_remove("sid", helper_app=helper_app) == {"ok": True, "mode": "helper"}
    assert fake.calls[0][1:] == ["remove", "--id", "sid"]


def test_mac_play_sound_detaches_afplay(monkeypatch, tmp_path):
    spawned = []
    monkeypatch.setattr(
        notify_macos.subprocess, "Popen", lambda argv, **kwargs: spawned.append((argv, kwargs))
    )
    wav = tmp_path / "alert.wav"
    assert notify_macos._mac_play_sound(wav) == {"ok": True, "mode": "afplay", "path": str(wav)}
    assert notify_macos._mac_play_sound(None)["path"] == str(notify_macos._MAC_DEFAULT_SOUND)
    (argv, kwargs), _ = spawned
    assert argv == ["afplay", str(wav)]
    assert kwargs["start_new_session"] is True


def test_mac_spawn_popup_posts_without_sound(monkeypatch, helper_app):
    posted = []
    monkeypatch.setattr(
        notify_macos, "_mac_post", lambda *args, **kwargs: posted.append((args, kwargs)) or {}
    )
    notify_macos._mac_spawn_popup(
        "line1\n  line2",
        300,
        "proj",
        Path("x.py"),
        "--popup",
        subtitle="~/w",
        notification_id="sid",
        helper_app=helper_app,
    )
    ((args, kwargs),) = posted
    assert args == ("proj", "~/w", "line1 line2")
    assert kwargs == {"notification_id": "sid", "helper_app": helper_app}


def test_mac_helper_app_default_location():
    app = notify.mac_helper_app("ClaudeNotify")
    assert app.name == "ClaudeNotify.app"
    assert app.is_absolute()


# ---------------------------------------------------------------------------
# 文字列の整形
# ---------------------------------------------------------------------------


def test_truncate_body_collapses_whitespace_and_limits_length():
    assert notify.truncate_body("a\n  b\tc") == "a b c"
    assert notify.truncate_body("x" * 130) == "x" * 120 + "…"
    assert notify.truncate_body("x" * 120) == "x" * 120


def test_shorten_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert notify.shorten_home(str(tmp_path / "w")) == "~/w"
    assert notify.shorten_home(str(tmp_path)) == "~"
    assert notify.shorten_home(str(tmp_path) + "x") == str(tmp_path) + "x"
    assert notify.shorten_home("") == ""


# ---------------------------------------------------------------------------
# プロジェクト名
# ---------------------------------------------------------------------------


def test_project_title_prefers_given_dir():
    assert notify.resolve_project_title("/work/my-project") == "my-project"


def test_project_title_falls_back_to_git(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.chdir(repo / "sub")
    assert notify.resolve_project_title("  ") == "repo"


def test_project_title_falls_back_to_marker_then_unknown(tmp_path, monkeypatch):
    def no_git(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(notify_project.subprocess, "run", no_git)
    hooks = tmp_path / "proj" / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    anchor = hooks / "stop_alert.py"
    assert notify.resolve_project_title(None, anchor=anchor, marker=".claude") == "proj"
    assert notify.resolve_project_title(None, anchor=anchor) == notify.UNKNOWN_PROJECT_TITLE
