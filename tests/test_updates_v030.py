"""Aviso de nova versão (v0.3.0): nunca acessa a internet nos testes."""

import io
import json

import pytest

from app import __version__
from app.services import updates
from app.services.updates import ReleaseInfo, due, fetch_latest, is_newer, parse_release, parse_version


def test_version_parsing_and_comparison():
    assert parse_version("v0.3.0") == (0, 3, 0) and parse_version("1.2") == (1, 2)
    assert parse_version("0.4.0-beta") == (0, 4, 0) and parse_version("abc") == ()
    assert is_newer("0.3.1", "0.3.0") and is_newer("v1.0", "0.9.9") and is_newer("0.10.0", "0.9.0")
    assert not is_newer("0.3.0", "0.3.0") and not is_newer("0.3", "0.3.0") and not is_newer("x", "0.3.0")
    assert parse_version(__version__) >= (0, 4, 0)


def test_parse_release_rules():
    good = {"tag_name": "v0.4.0", "html_url": "https://github.com/PedroHTF/pdf-compare/releases/tag/v0.4.0",
            "body": "Novidades"}
    assert parse_release(good) == ReleaseInfo("0.4.0", good["html_url"], "Novidades")
    assert parse_release({**good, "draft": True}) is None
    assert parse_release({**good, "prerelease": True}) is None
    assert parse_release({**good, "tag_name": "sem-numero"}) is None
    # nunca abre um endereço fora do GitHub
    assert parse_release({**good, "html_url": "https://exemplo.com/x"}).url.endswith("/releases/latest")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_latest_uses_api_and_never_raises():
    seen = {}

    def opener(request, timeout):
        seen["url"], seen["agent"], seen["timeout"] = request.full_url, request.get_header("User-agent"), timeout
        return FakeResponse(json.dumps({"tag_name": "v9.9.9", "html_url": "https://github.com/x"}).encode())

    assert fetch_latest(opener).version == "9.9.9"
    assert seen["url"] == updates.API_URL and "PDF-Compare" in seen["agent"] and seen["timeout"] > 0

    def offline(request, timeout):
        raise OSError("sem internet")

    assert fetch_latest(offline) is None
    assert fetch_latest(lambda r, timeout: FakeResponse(b"<html>")) is None


def test_due_once_a_day():
    assert due(0, now=1000) and not due(1000, now=1000 + 3600) and due(1000, now=1000 + 86400)
    assert due(5000, now=1000)   # relógio voltou: verifica de novo


# --- interface ---------------------------------------------------------------------------------
NEW = ReleaseInfo("9.9.0", "https://github.com/PedroHTF/pdf-compare/releases/tag/v9.9.0", "Novidades da 9.9.0")


def _check(w, qtbot, release, manual=False):
    w.fetch_release = lambda: release
    w.check_updates(manual=manual)
    qtbot.waitUntil(lambda: w._update_future is None, timeout=3000)


def test_new_version_shows_bar_and_skip(window, qtbot, monkeypatch):
    w = window
    opened = []
    monkeypatch.setattr("PySide6.QtGui.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    _check(w, qtbot, NEW)
    assert w.update_bar.isVisibleTo(w) and "9.9.0" in w.update_label.text()
    assert float(w.settings.value("updates/last_check")) > 0
    w.update_download_btn.click()
    assert opened == [NEW.url]

    w.update_skip_btn.click()
    assert not w.update_bar.isVisibleTo(w) and w.settings.value("updates/skip") == "9.9.0"
    _check(w, qtbot, NEW)                                       # automático: versão ignorada não aparece
    assert not w.update_bar.isVisibleTo(w)


def test_up_to_date_and_offline(window, qtbot):
    w = window
    messages = []
    w._notify = lambda kind, title, text: messages.append((kind, text))
    _check(w, qtbot, ReleaseInfo(__version__, NEW.url))         # automático e atualizado: silêncio
    _check(w, qtbot, None)                                      # automático sem internet: silêncio
    assert messages == [] and not w.update_bar.isVisibleTo(w)
    _check(w, qtbot, ReleaseInfo(__version__, NEW.url), manual=True)
    _check(w, qtbot, None, manual=True)
    assert [k for k, _ in messages] == ["info", "warning"] and __version__ in messages[0][1]


def test_auto_check_respects_setting_and_interval(window, qtbot):
    import time

    w = window
    calls = []
    w.fetch_release = lambda: calls.append(1) or None
    w.settings.setValue("updates/check", False)
    w._auto_check_updates()
    w.settings.setValue("updates/check", True)
    w.settings.setValue("updates/last_check", time.time())
    w._auto_check_updates()
    assert calls == []
    w.settings.setValue("updates/last_check", time.time() - 2 * 86400)
    w._auto_check_updates()
    qtbot.waitUntil(lambda: w._update_future is None, timeout=3000)
    assert calls == [1]


def test_settings_toggle_updates(window):
    from app.ui.settings_dialog import SettingsDialog, SettingsValues

    w = window
    dialog = SettingsDialog(SettingsValues("pt", "eng", w.prefs.diff_colors(), w.mark_style, w.compare,
                                           w.updates_enabled()))
    assert dialog.updates_check.isChecked()
    dialog.updates_check.setChecked(False)
    w.apply_settings(dialog.values())
    assert not w.updates_enabled()
