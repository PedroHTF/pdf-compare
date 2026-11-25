"""Comparação em lotes, cache em disco e execução em segundo plano (v0.3.0)."""

import os
import time

import fitz
import pytest

from app.services.batch_runner import BatchRunner
from app.services.diff_batches import ALL_PAGES, DiffCache, batch_for_page, format_size, pair_key, plan_batches
from app.services.preferences import NEXT_AUTO, NEXT_ON_CLICK, CompareSettings, Preferences
from app.services.text_diff import ADDED, CHANGED, DiffMark, diff_pair
from app.services.text_index import DocumentIndex


# --- plano de lotes ---------------------------------------------------------------------------
def test_plan_splits_reference_and_follows_alignment():
    batches = plan_batches([12, 14], [0, 2], 5)
    assert [b.ranges for b in batches] == [((0, 5), (0, 7)), ((5, 10), (7, 12)), ((10, 12), (12, 14))]
    assert batches[1].label_pages() == (6, 10)

    # o primeiro lote começa no início e o último vai até o fim de cada PDF
    batches = plan_batches([10, 4, 30], [0, -3, 5], 4)
    assert [b.ranges[1] for b in batches] == [(0, 1), (1, 4), (4, 4)][:2] + [(4, 4)]
    assert batches[0].ranges[2][0] == 0 and batches[-1].ranges[2][1] == 30


@pytest.mark.parametrize("size", [ALL_PAGES, 50, 12])
def test_single_batch_when_small_or_all(size):
    batches = plan_batches([12, 9], [0, 0], size)
    assert len(batches) == 1 and batches[0].ranges == ((0, 12), (0, 9))


def test_batch_for_page():
    batches = plan_batches([12, 12], [0, 0], 5)
    assert [batch_for_page(batches, p) for p in (0, 4, 5, 11, 99, -3)] == [0, 0, 1, 2, 2, 0]


def _index(texts):
    doc = fitz.open()
    for t in texts:
        doc.new_page().insert_text((72, 72), t, fontsize=12)
    index = DocumentIndex.build(doc)
    doc.close()
    return index


def test_diff_pair_with_page_ranges():
    a = _index(["um dois", "tres quatro", "cinco seis"])
    b = _index(["um dois", "tres QUATRO", "cinco seis sete"])
    full_a, full_b = diff_pair(a, b)
    part_a, part_b = diff_pair(a, b, ref_pages=(1, 2), other_pages=(1, 2))
    assert [m.page for m in part_b] == [1] and part_b[0].kind == CHANGED
    assert [m for m in full_b if m.page == 1] == part_b
    _, last = diff_pair(a, b, ref_pages=(2, 3), other_pages=(2, 3))
    assert [(m.page, m.kind) for m in last] == [(2, ADDED)]


# --- cache ----------------------------------------------------------------------------------
def test_cache_roundtrip_purge_and_clear(tmp_path):
    cache = DiffCache(tmp_path / "c")
    assert cache.load("x") is None and cache.count() == 0
    pair = ([DiffMark(0, ((1.0, 2.0, 3.0, 4.0),), "removed")], [DiffMark(3, ((5.0, 6.0, 7.0, 8.0),), "added")])
    cache.save("x", pair)
    cache.save("y", ([], []))
    assert cache.load("x") == pair and cache.count() == 2 and cache.size_bytes() > 0

    old = time.time() - 40 * 86400
    os.utime(tmp_path / "c" / "y.json", (old, old))
    assert cache.purge(0) == 0                     # 0 = nunca apaga
    assert cache.purge(30) == 1 and cache.load("y") is None and cache.load("x") == pair

    (tmp_path / "c" / "z.json").write_text("{quebrado", encoding="utf-8")
    assert cache.load("z") is None
    assert cache.clear() == 2 and cache.count() == 0
    assert format_size(500) == "500 B" and format_size(2048) == "2.0 KB"


def test_pair_key_depends_on_content_pages_and_options():
    base = pair_key("a", "b", (0, 5), (0, 5), "ocr=0")
    assert base == pair_key("a", "b", (0, 5), (0, 5), "ocr=0")
    assert len({base, pair_key("a", "c", (0, 5), (0, 5), "ocr=0"), pair_key("a", "b", (0, 5), (0, 6), "ocr=0"),
                pair_key("a", "b", (0, 5), (0, 5), "ocr=1")}) == 4


def test_compare_settings_roundtrip():
    class S(dict):
        value = lambda self, k, d=None: self.get(k, d)  # noqa: E731
        setValue = dict.__setitem__  # noqa: N815

    prefs = Preferences(S())
    assert prefs.compare_settings() == CompareSettings()
    c = CompareSettings(batch_size=20, next_mode=NEXT_AUTO, lookahead=0, pause_while_busy=False, cache_days=0)
    prefs.set_compare_settings(c)
    assert prefs.compare_settings() == c
    prefs.settings["compare/next_mode"] = "???"
    prefs.settings["compare/batch_size"] = "x"
    assert prefs.compare_settings().next_mode == NEXT_ON_CLICK and prefs.compare_settings().batch_size == 50


# --- execução em segundo plano -------------------------------------------------------------------
def _docs(n=12, changed=(7,)):
    a = _index([f"pagina {p} texto igual" for p in range(n)])
    b = _index([f"pagina {p} texto {'DIFERENTE' if p in changed else 'igual'}" for p in range(n)])
    return a, b


def test_runner_compares_requested_batches_and_reuses_cache(qtbot, tmp_path):
    a, b = _docs()
    cache = DiffCache(tmp_path / "cache")
    runner = BatchRunner(cache)
    runner.configure([a, b], ["fa", "fb"], [0, 0], 5)
    assert len(runner.batches) == 3
    assert runner.request(0) and not runner.request(0)
    qtbot.waitUntil(lambda: not runner.busy, timeout=5000)
    assert runner.is_done(0) and not runner.is_done(1) and runner.marks() == [[], []]

    with qtbot.waitSignal(runner.changed, timeout=5000):
        runner.request(1)
    qtbot.waitUntil(lambda: not runner.busy, timeout=5000)
    assert [m.page for m in runner.marks()[1]] == [7]

    again = BatchRunner(cache)
    again.configure([a, b], ["fa", "fb"], [0, 0], 5)
    again.request(1)
    qtbot.waitUntil(lambda: not again.busy, timeout=5000)
    assert again.from_cache == 1 and again.marks() == runner.marks()
    runner.shutdown()
    again.shutdown()


def test_runner_waits_for_pages_to_be_read(qtbot):
    full_a, full_b = _docs(6, changed=(1,))
    partial = DocumentIndex(6)
    runner = BatchRunner()
    runner.configure([full_a, partial], ["a", "b"], [0, 0], 3)
    runner.request(0)
    qtbot.wait(100)
    assert runner.busy and not runner.is_done(0)   # o PDF b ainda não foi lido
    for page in full_b.pages[:3]:
        partial.add_page(page)
    qtbot.waitUntil(lambda: runner.is_done(0), timeout=5000)
    assert [m.page for m in runner.marks()[1]] == [1]
    runner.shutdown()


def test_background_batches_pause_and_cancel(qtbot):
    a, b = _docs(30)
    runner = BatchRunner()
    runner.configure([a, b], ["a", "b"], [0, 0], 5)
    runner.pause_for(0.4)
    runner.request(3, priority=False)
    runner.request(0, priority=True)
    qtbot.waitUntil(lambda: runner.is_done(0), timeout=5000)
    assert not runner.is_done(3) and runner.background_pending()   # o segundo plano espera a pausa
    qtbot.waitUntil(lambda: runner.is_done(3), timeout=5000)

    for k in (4, 5):
        runner.request(k, priority=False)
    runner.cancel_background()
    assert not runner.background_pending()
    runner.request(4)
    runner.cancel()
    qtbot.wait(100)
    assert not runner.busy and runner.is_done(0) and runner.is_done(3)
    assert runner.done_count() == 2
    runner.shutdown()


# --- interface ---------------------------------------------------------------------------------
@pytest.fixture
def long_pdfs(make_pdf):
    a = make_pdf("longo_v1.pdf", texts=[f"Pagina {p} do contrato texto igual" for p in range(12)])
    b = make_pdf("longo_v2.pdf", texts=[f"Pagina {p} do contrato texto {'ALTERADO' if p in (2, 8) else 'igual'}"
                                        for p in range(12)])
    return a, b


def _open_with(window, qtbot, pdfs, **settings):
    window.set_compare_settings(CompareSettings(**settings))
    window.add_files(pdfs)
    qtbot.waitUntil(lambda: not window.indexer.busy, timeout=10000)


def _idle(qtbot, w):
    qtbot.waitUntil(lambda: not w.runner.busy, timeout=10000)


def test_click_mode_compares_one_batch_at_a_time(window, qtbot, long_pdfs):
    w = window
    _open_with(w, qtbot, long_pdfs, batch_size=5, next_mode=NEXT_ON_CLICK)
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert w.runner.done_count() == 1 and [m.page for m in w.nav.diffs[1]] == [2]
    assert w.batch_bar.isVisibleTo(w) and "Lote 1 de 3" in w.batch_label.text()
    assert "1 de 3 lotes" in w.batch_label.toolTip()

    w.act_batch_next.trigger()                  # compara o lote 2 e vai até ele
    assert w.nav.page_for(0) == 5 and "Lote 2 de 3" in w.batch_label.text()
    _idle(qtbot, w)
    assert w.runner.done_count() == 2 and [m.page for m in w.nav.diffs[1]] == [2, 8]

    w.go_last()                                 # lote 3 ainda não comparado: nada é feito sozinho
    _idle(qtbot, w)
    assert not w.runner.is_done(2) and w.act_batch_next.text() == "Comparar este lote"
    assert "não comparado" in w.batch_label.text() and w.batch_next_btn.text() == "Comparar este lote"
    w.act_batch_next.trigger()
    _idle(qtbot, w)
    assert w.runner.done_count() == 3

    w.act_batch_prev.trigger()
    assert w.nav.page_for(0) == 5


def test_auto_mode_prepares_batches_ahead(window, qtbot, long_pdfs):
    w = window
    _open_with(w, qtbot, long_pdfs, batch_size=5, next_mode=NEXT_AUTO, lookahead=1, pause_while_busy=False)
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert [w.runner.is_done(k) for k in range(3)] == [True, True, False]
    w.go_to_batch(1)
    _idle(qtbot, w)
    assert w.runner.done_count() == 3
    assert (w.nav.page_for(0), w.nav.page_for(1)) == (5, 5)


def test_first_difference_is_shown_when_results_arrive(window, qtbot, long_pdfs):
    w = window
    _open_with(w, qtbot, long_pdfs, batch_size=ALL_PAGES)
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert not w.batch_bar.isVisibleTo(w)        # um lote só: sem barra de lotes
    assert w.nav.page_for(1) == 2 and w.nav.total_diffs == 4


def test_results_come_from_cache_after_reopening(window, qtbot, long_pdfs, tmp_path):
    from PySide6.QtCore import QSettings

    from app.ui.main_window import MainWindow

    w = window
    _open_with(w, qtbot, long_pdfs, batch_size=5, next_mode=NEXT_AUTO, lookahead=0, pause_while_busy=False)
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert w.runner.done_count() == 3 and w.runner.from_cache == 0
    expected = w.nav.diffs

    again = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat), data_dir=w.data_dir)
    again._notify = lambda *a: None
    qtbot.addWidget(again)
    _open_with(again, qtbot, long_pdfs, batch_size=5, next_mode=NEXT_AUTO, lookahead=0, pause_while_busy=False)
    again.act_diff.trigger()
    _idle(qtbot, again)
    assert again.runner.from_cache == 3 and again.nav.diffs == expected
    assert "6 resultado(s)" not in again.cache_summary() and "3 resultado(s)" in again.cache_summary()
    again.clear_diff_cache()
    assert again.diff_cache.count() == 0


def test_settings_change_batch_size_replans(window, qtbot, long_pdfs):
    from app.ui.settings_dialog import SettingsDialog, SettingsValues

    w = window
    _open_with(w, qtbot, long_pdfs, batch_size=5)
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert len(w.runner.batches) == 3

    values = SettingsValues("pt", w.ocr_language(), w.prefs.diff_colors(), w.mark_style, w.compare)
    dialog = SettingsDialog(values, cache_info=w.cache_summary, clear_cache=w.clear_diff_cache)
    assert not dialog.lookahead_combo.isEnabled()          # só no modo automático
    assert dialog.realign_combo.currentData() == "click"
    dialog.next_combo.setCurrentIndex(dialog.next_combo.findData(NEXT_AUTO))
    assert dialog.lookahead_combo.isEnabled()
    dialog.batch_spin.setValue(0)
    assert dialog.batch_spin.text() == "Tudo de uma vez" and not dialog.next_combo.isEnabled()
    assert not dialog.realign_combo.isEnabled()
    dialog.cache_days_spin.setValue(0)
    assert dialog.cache_days_spin.text() == "Nunca"
    w.apply_settings(dialog.values())
    _idle(qtbot, w)
    assert len(w.runner.batches) == 1 and w.runner.done_count() == 1
    assert w.nav.total_diffs == 4 and Preferences(w.settings).compare_settings().cache_days == 0


def _settle(qtbot, w):
    """Espera a pausa depois do ajuste de alinhamento (encurtada nos testes)."""
    qtbot.waitUntil(lambda: not w._realign_timer.isActive(), timeout=3000)


def test_realigning_waits_for_click_by_default(window, qtbot, long_pdfs):
    w = window
    w._realign_timer.setInterval(30)
    _open_with(w, qtbot, long_pdfs, batch_size=5, next_mode=NEXT_AUTO, lookahead=0, pause_while_busy=False)
    w.act_diff.trigger()
    _idle(qtbot, w)
    before = w.nav.diffs
    for _ in range(3):                           # vários ajustes seguidos: nada é refeito ainda
        w._on_pane_step(1, +1)
    assert w._realign_timer.isActive() and not w.recompare_btn.isVisibleTo(w)
    _settle(qtbot, w)
    assert w.runner.batches[0].ranges[1] == (0, 5)            # o plano antigo continua valendo
    assert w.nav.diffs == before and w.runner.done_count() == 3
    assert w.recompare_btn.isVisibleTo(w) and "alinhamento mudou" in w.batch_label.text()

    w.recompare_btn.click()
    assert w.runner.batches[0].ranges[1] == (0, 8) and not w.recompare_btn.isVisibleTo(w)
    _idle(qtbot, w)
    assert w.runner.done_count() == 3

    for _ in range(3):
        w._on_pane_step(1, -1)                   # voltou ao alinhamento: "Recomparar" some sozinho
    _settle(qtbot, w)
    assert w.recompare_btn.isVisibleTo(w)
    w._on_pane_step(1, +3)
    _settle(qtbot, w)
    assert not w.recompare_btn.isVisibleTo(w) and not w._realign_pending


def test_realigning_recompares_automatically_when_chosen(window, qtbot, long_pdfs):
    w = window
    w._realign_timer.setInterval(30)
    _open_with(w, qtbot, long_pdfs, batch_size=5, next_mode=NEXT_AUTO, lookahead=0, pause_while_busy=False,
               realign_mode="auto")
    w.act_diff.trigger()
    _idle(qtbot, w)
    w._on_pane_step(1, +1)
    w._on_pane_step(1, +1)
    assert w.runner.batches[0].ranges[1] == (0, 5)            # ainda dentro da pausa
    _settle(qtbot, w)
    assert w.runner.batches[0].ranges[1] == (0, 7) and not w.recompare_btn.isVisibleTo(w)
    _idle(qtbot, w)

    w.realign()                                  # volta ao alinhamento original: lotes vêm do cache
    _settle(qtbot, w)
    _idle(qtbot, w)
    assert w.runner.batches[0].ranges[1] == (0, 5) and w.runner.from_cache == 3


def test_diff_navigation_never_replans(window, qtbot, long_pdfs):
    w = window
    w._realign_timer.setInterval(30)
    _open_with(w, qtbot, long_pdfs, batch_size=5, next_mode=NEXT_AUTO, lookahead=0, pause_while_busy=False)
    w.act_diff.trigger()
    _idle(qtbot, w)
    plan = w.runner.batches
    for _ in range(4):
        w.act_diff_next.trigger()                # F7 move cada PDF, mas não é ajuste de alinhamento
    qtbot.wait(80)
    assert w.runner.batches is plan and not w._realign_pending


def test_turning_diff_off_stops_and_hides(window, qtbot, long_pdfs):
    w = window
    _open_with(w, qtbot, long_pdfs, batch_size=5)
    w.act_diff.trigger()
    w.act_diff.trigger()
    assert not w.runner.busy and not w.runner.batches
    assert not w.batch_bar.isVisibleTo(w) and not w.diff_label.isVisibleTo(w)
