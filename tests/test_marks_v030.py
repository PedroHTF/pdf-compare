"""Marcações da v0.3.0 (formas, texto, carimbos, edição, desfazer) e Configurações."""

import json

import fitz
import pytest
from PySide6.QtCore import QPoint, Qt

from app.services import annotations as am
from app.services.annotations import Annotation, AnnotationStore, annotated_copy, file_fingerprint
from app.services.preferences import DEFAULT_DIFF_COLORS, DEFAULT_STYLE, MarkStyle, Preferences, from_hex, to_hex
from app.services.text_diff import ADDED
from app.ui.pane import DIFF_STYLE, TOOL_NONE


class DictSettings:
    def __init__(self):
        self.data = {}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):  # noqa: N802
        self.data[key] = value


def all_kinds():
    return [
        Annotation(am.HIGHLIGHT, 0, [(72, 60, 150, 75)]),
        Annotation(am.UNDERLINE, 0, [(72, 60, 150, 75)]),
        Annotation(am.STRIKEOUT, 0, [(72, 60, 150, 75)]),
        Annotation(am.SQUIGGLY, 0, [(72, 60, 150, 75)]),
        Annotation(am.NOTE, 0, [am.note_rect(300, 60)], "nota"),
        Annotation(am.RECT, 0, [(50, 100, 200, 180)], fill=(1, 1, 0), opacity=0.5),
        Annotation(am.ELLIPSE, 0, [(250, 100, 400, 180)]),
        Annotation(am.LINE, 0, [], points=[(50, 200), (200, 230)]),
        Annotation(am.ARROW, 0, [], points=[(250, 200), (400, 230)]),
        Annotation(am.POLYGON, 0, [], points=[(50, 300), (150, 320), (100, 400)], fill=(0, 1, 0)),
        Annotation(am.INK, 0, [], strokes=[[(250, 300), (270, 320), (300, 290)]]),
        Annotation(am.TEXTBOX, 0, [(50, 450, 250, 500)], "caixa", fill=(1, 1, 1)),
        Annotation(am.CALLOUT, 0, [(300, 450, 450, 500)], "balão", points=[(260, 560)]),
        Annotation(am.STAMP, 0, [am.stamp_rect(150, 620, "Aprovado")], "Aprovado"),
    ]


# --- modelo -----------------------------------------------------------------------------------
def test_every_kind_roundtrips_and_exports_as_real_pdf_annotation():
    items = all_kinds()
    again = [Annotation.from_dict(json.loads(json.dumps(a.to_dict()))) for a in items]
    assert again == items

    doc = fitz.open()
    doc.new_page()
    out = annotated_copy(doc, items)
    types = [a.type[1] for a in out[0].annots()]
    assert types == ["Highlight", "Underline", "StrikeOut", "Squiggly", "Text", "Square", "Circle", "Line",
                     "Line", "Polygon", "Ink", "FreeText", "FreeText", "FreeText"]
    texts = " ".join(page.get_text() for page in annotated_copy(doc, items, bake=True))
    assert "caixa" in texts and "APROVADO" in texts


def test_version_1_files_still_load(tmp_path):
    store_dir = tmp_path / "anotacoes"
    store_dir.mkdir()
    (store_dir / "abc.json").write_text(json.dumps({"version": 1, "annotations": [
        {"kind": "highlight", "page": 0, "rects": [[1, 2, 3, 4]], "text": "", "id": "x"},
        {"kind": "note", "page": 1, "rects": [[5, 5, 23, 23]], "text": "oi", "id": "y"},
        {"kind": "desconhecido", "page": 0, "rects": [[1, 1, 2, 2]]},
    ]}), encoding="utf-8")
    items = AnnotationStore(store_dir).load("abc")
    assert [(a.kind, a.text, a.color) for a in items] == [("highlight", "", None), ("note", "oi", None)]
    assert items[0].stroke_color == am.HIGHLIGHT_COLOR


def test_move_resize_and_hit_testing():
    line = Annotation(am.LINE, 0, [], points=[(0, 0), (100, 100)])
    assert line.rects == [(0, 0, 100, 100)]
    assert line.contains(50, 51) and not line.contains(90, 10)

    moved = am.moved(line, 10, 5)
    assert moved.points == [(10, 5), (110, 105)] and moved.id == line.id
    resized = am.resized(line, (0, 0, 50, 200))
    assert resized.points == [(0, 0), (50, 200)]

    callout = Annotation(am.CALLOUT, 0, [(100, 100, 200, 140)], "x", points=[(50, 200)])
    big = am.resized(callout, (100, 100, 300, 180))
    assert big.rects == [(100, 100, 300, 180)] and big.points == [(50, 200)]   # a ponta fica no lugar
    assert callout.contains(50, 200)

    ink = Annotation(am.INK, 0, [], strokes=[[(0, 0), (10, 0)]])
    assert ink.contains(5, 1) and not ink.contains(5, 30)
    tiny = am.resized(Annotation(am.RECT, 0, [(0, 0, 10, 10)]), (5, 5, 5, 5))
    assert tiny.rects[0][2] - tiny.rects[0][0] >= am.MIN_SIZE


def test_store_update_snapshot_restore(tmp_path):
    store = AnnotationStore(tmp_path)
    a = Annotation(am.RECT, 0, [(0, 0, 10, 10)])
    store.add("k", a)
    before = store.snapshot("k")
    store.update("k", am.moved(a, 5, 5))
    assert AnnotationStore(tmp_path).load("k")[0].rects == [(5, 5, 15, 15)]
    store.restore("k", before)
    assert AnnotationStore(tmp_path).load("k")[0].rects == [(0, 0, 10, 10)]


# --- preferências --------------------------------------------------------------------------
def test_preferences_defaults_roundtrip_and_bad_values():
    settings = DictSettings()
    prefs = Preferences(settings)
    assert prefs.diff_colors() == DEFAULT_DIFF_COLORS
    assert prefs.mark_style() == DEFAULT_STYLE

    style = MarkStyle(color=(0, 0, 1), highlight=(0, 1, 0), fill=(1, 0, 0), width=3, opacity=0.4, font_size=20)
    prefs.set_mark_style(style)
    prefs.set_diff_colors({ADDED: (0, 0, 0)})
    again = Preferences(settings)
    assert again.mark_style() == style
    assert again.diff_colors()[ADDED] == (0, 0, 0)

    settings.setValue("marks/width", "abc")
    settings.setValue("marks/opacity", 9)
    settings.setValue("colors/added", "#zz")
    assert again.mark_style().width == DEFAULT_STYLE.width and again.mark_style().opacity == 1.0
    assert again.diff_colors()[ADDED] == DEFAULT_DIFF_COLORS[ADDED]
    assert from_hex(to_hex((0.2, 0.4, 0.6))) == pytest.approx((0.2, 0.4, 0.6), abs=0.003)


# --- interface ------------------------------------------------------------------------------
@pytest.fixture
def opened(window, make_pdf):
    a = make_pdf("a.pdf", texts=["Primeira pagina do contrato", "Segunda"])
    b = make_pdf("b.pdf", texts=["Primeira pagina do contrato", "Segunda"])
    window.add_files([a, b])
    window.set_zoom(1.0)
    return window


def widget_pos(pane, x, y):
    """Ponto da página (sem rotação) -> posição no QLabel da imagem."""
    pix = pane.image.pixmap()
    w = pix.width() / pane._dpr
    h = pix.height() / pane._dpr
    ox = (pane.image.width() - w) / 2
    oy = (pane.image.height() - h) / 2
    return QPoint(round(ox + x * pane._scale), round(oy + y * pane._scale))


def drag(qtbot, pane, start, end, steps=3):
    qtbot.mousePress(pane.image, Qt.MouseButton.LeftButton, pos=widget_pos(pane, *start))
    for i in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * i / steps
        y = start[1] + (end[1] - start[1]) * i / steps
        qtbot.mouseMove(pane.image, widget_pos(pane, x, y))
    qtbot.mouseRelease(pane.image, Qt.MouseButton.LeftButton, pos=widget_pos(pane, *end))


def marks(window, index=0):
    return window.document_annotations(index)


def test_draw_rectangle_select_move_resize_undo_redo(opened, qtbot):
    w = opened
    pane = w.panes[0]
    w.set_tool(am.RECT)
    assert w.tool_actions[am.RECT].isChecked() and not w.act_select.isChecked()
    drag(qtbot, pane, (100, 200), (200, 260))
    [rect] = marks(w)
    assert rect.kind == am.RECT
    assert rect.rects[0] == pytest.approx((100, 200, 200, 260), abs=1.5)
    assert rect.color == w.mark_style.color
    assert w._selection == (0, rect.id)   # a forma recém-desenhada fica selecionada

    w.set_tool(TOOL_NONE)
    drag(qtbot, pane, (150, 230), (180, 250))                        # mover
    assert marks(w)[0].rects[0] == pytest.approx((130, 220, 230, 280), abs=2)
    drag(qtbot, pane, (233, 283), (300, 330))                        # alça inferior direita
    assert marks(w)[0].rects[0] == pytest.approx((130, 220, 297, 327), abs=3)

    w.act_undo.trigger()
    assert marks(w)[0].rects[0] == pytest.approx((130, 220, 230, 280), abs=2)
    w.act_undo.trigger()
    w.act_undo.trigger()
    assert marks(w) == [] and not w.act_undo.isEnabled()
    w.act_redo.trigger()
    assert len(marks(w)) == 1
    # o desfazer também vale depois de reabrir: as marcações estão gravadas
    assert AnnotationStore(w.data_dir / "anotacoes").load(w.annotation_key(0))[0].kind == am.RECT


def test_click_on_empty_area_deselects_and_esc_returns_to_select(opened, qtbot):
    w = opened
    pane = w.panes[0]
    w.set_tool(am.ELLIPSE)
    drag(qtbot, pane, (300, 300), (380, 360))
    assert w._selection is not None
    w.escape()
    assert w._selection is None and w.tool == am.ELLIPSE
    w.escape()
    assert w.tool == TOOL_NONE and w.act_select.isChecked()
    w._select((0, marks(w)[0].id))
    qtbot.mousePress(pane.image, Qt.MouseButton.LeftButton, pos=widget_pos(pane, 500, 700))
    assert w._selection is None


def test_lines_arrows_ink_and_tiny_drags(opened, qtbot):
    w = opened
    pane = w.panes[1]
    w.set_tool(am.ARROW)
    drag(qtbot, pane, (100, 100), (200, 150))
    w.set_tool(am.LINE)
    drag(qtbot, pane, (100, 300), (101, 301))       # arraste mínimo: nada é criado
    w.set_tool(am.INK)
    drag(qtbot, pane, (300, 300), (400, 380), steps=6)
    kinds = [a.kind for a in marks(w, 1)]
    assert kinds == [am.ARROW, am.INK]
    arrow, ink = marks(w, 1)
    assert arrow.points[0] == pytest.approx((100, 100), abs=1.5)
    assert len(ink.strokes[0]) >= 5


def test_polygon_by_clicks_and_double_click(opened, qtbot):
    w = opened
    pane = w.panes[0]
    w.set_tool(am.POLYGON)
    for p in [(100, 400), (200, 420), (150, 500)]:
        qtbot.mouseClick(pane.image, Qt.MouseButton.LeftButton, pos=widget_pos(pane, *p))
    assert pane._preview is not None and marks(w) == []
    qtbot.mouseDClick(pane.image, Qt.MouseButton.LeftButton, pos=widget_pos(pane, 150, 500))
    [poly] = marks(w)
    assert poly.kind == am.POLYGON and len(poly.points) == 3

    qtbot.mouseClick(pane.image, Qt.MouseButton.LeftButton, pos=widget_pos(pane, 300, 400))
    w.escape()   # cancela o polígono em andamento
    assert pane._polygon == [] and pane._preview is None and len(marks(w)) == 1


def test_textbox_callout_and_stamp(opened, qtbot):
    w = opened
    pane = w.panes[0]
    answers = iter(["Texto da caixa", None, "Atenção aqui"])
    w._ask_mark_text = lambda title, initial: next(answers)
    w.set_tool(am.TEXTBOX)
    drag(qtbot, pane, (100, 100), (300, 160))
    drag(qtbot, pane, (100, 300), (300, 360))      # cancelou o texto: nada é criado
    w.set_tool(am.CALLOUT)
    drag(qtbot, pane, (400, 400), (300, 300))
    w.choose_stamp("Revisar")
    assert w.tool == am.STAMP
    qtbot.mouseClick(pane.image, Qt.MouseButton.LeftButton, pos=widget_pos(pane, 300, 600))

    box, callout, stamp = marks(w)
    assert (box.kind, box.text) == (am.TEXTBOX, "Texto da caixa")
    assert callout.kind == am.CALLOUT and callout.points[0] == pytest.approx((400, 400), abs=1.5)
    assert (stamp.kind, stamp.text) == (am.STAMP, "Revisar")
    assert stamp.bounds[0] < 300 < stamp.bounds[2]

    # editar com duplo clique
    w.set_tool(TOOL_NONE)
    w._ask_mark_text = lambda title, initial: initial + " (editado)"
    qtbot.mouseDClick(pane.image, Qt.MouseButton.LeftButton, pos=widget_pos(pane, 200, 130))
    assert marks(w)[0].text == "Texto da caixa (editado)"


def test_markups_snap_to_words(opened):
    w = opened
    doc = w.sessions[0].doc
    word = doc[0].get_text("words")[0]
    for kind in (am.UNDERLINE, am.STRIKEOUT, am.SQUIGGLY):
        w.panes[0].markup_requested.emit(0, 0, kind, (word[0] + 1, word[1] + 1, word[2] - 1, word[3] - 1))
    assert [a.kind for a in marks(w)] == [am.UNDERLINE, am.STRIKEOUT, am.SQUIGGLY]
    assert all(a.rects == [tuple(word[:4])] for a in marks(w))


def test_style_bar_applies_to_new_and_selected_marks(opened, qtbot):
    w = opened
    w.panes[0].shape_drawn.emit(0, Annotation(am.RECT, 0, [(10, 10, 50, 50)]))
    w._select((0, marks(w)[0].id))
    w.style_bar.width_spin.setValue(4.0)
    w.style_bar.color_btn.set_color((0.0, 0.0, 1.0), emit=True)
    w.style_bar.fill_btn.set_color((1.0, 1.0, 0.0), emit=True)
    rect = marks(w)[0]
    assert (rect.width, rect.color, rect.fill) == (4.0, (0.0, 0.0, 1.0), (1.0, 1.0, 0.0))
    assert w.mark_style.width == 4.0
    assert Preferences(w.settings).mark_style().color == (0.0, 0.0, 1.0)

    w._select(None)
    w.set_tool(am.ELLIPSE)
    drag(qtbot, w.panes[0], (200, 200), (260, 260))
    assert marks(w)[1].width == 4.0 and marks(w)[1].fill == (1.0, 1.0, 0.0)
    w.act_undo.trigger()
    w.act_undo.trigger()
    assert marks(w)[0].fill is None   # desfaz a troca de preenchimento


def test_copy_paste_delete(opened):
    w = opened
    w.panes[0].shape_drawn.emit(0, Annotation(am.RECT, 0, [(10, 10, 50, 50)]))
    w._select((0, marks(w)[0].id))
    w.act_copy_mark.trigger()
    w.act_paste_mark.trigger()                     # mesmo painel e página: desloca um pouco
    assert marks(w)[1].rects[0] == (22, 22, 62, 62)
    assert marks(w)[1].id != marks(w)[0].id

    w._last_pane = 1
    w.paste_mark()
    assert marks(w, 1)[0].rects[0] == (22, 22, 62, 62) and marks(w, 1)[0].page == 0

    w._select((0, marks(w)[0].id))
    w.act_delete_mark.trigger()
    assert len(marks(w)) == 1 and w._selection is None


def test_marks_panel_lists_filters_and_jumps(opened):
    w = opened
    w.panes[0].shape_drawn.emit(0, Annotation(am.RECT, 1, [(10, 10, 50, 50)], color=(1, 0, 0)))
    w.panes[1].shape_drawn.emit(1, Annotation(am.ARROW, 0, [], points=[(0, 0), (9, 9)], color=(0, 0, 1)))
    panel = w.marks_panel
    assert len(panel.item_ids()) == 2
    panel.kind_filter.setCurrentIndex(panel.kind_filter.findData(am.ARROW))
    assert panel.item_ids() == [marks(w, 1)[0].id]
    panel.kind_filter.setCurrentIndex(0)
    panel.color_filter.setCurrentIndex(panel.color_filter.findData("#ff0000"))
    assert panel.item_ids() == [marks(w)[0].id]

    panel.mark_activated.emit(0, marks(w)[0].id)
    assert w.nav.page_for(0) == 1 and w._selection == (0, marks(w)[0].id)
    assert w.panes[0].selected_id == marks(w)[0].id


def test_every_kind_renders_in_the_pane(opened):
    w = opened
    for a in all_kinds():
        w.add_annotation(0, a)
    w._select((0, marks(w)[5].id))
    image = w.panes[0].image.pixmap().toImage()
    assert not image.isNull() and image.width() > 100


def test_settings_change_colors_style_and_persist(opened, tmp_path):
    from app.ui.settings_dialog import SettingsDialog, SettingsValues

    w = opened
    values = SettingsValues("pt", "eng", w.prefs.diff_colors(), w.mark_style)
    dialog = SettingsDialog(values)
    dialog.diff_buttons[ADDED].set_color((0.5, 0.0, 0.5))
    dialog.mark_width.setValue(6)
    dialog.ocr_edit.setText("por")
    new = dialog.values()
    w._ocr_calls = []
    w.set_ocr_language = lambda lang: w._ocr_calls.append(lang)
    w.apply_settings(new)

    assert DIFF_STYLE[ADDED][0].red() == 128 and DIFF_STYLE[ADDED][0].alpha() == 70
    assert w.mark_style.width == 6 and w.style_bar.width_spin.value() == 6
    assert w._ocr_calls == ["por"]
    assert Preferences(w.settings).diff_colors()[ADDED] == pytest.approx((0.5, 0.0, 0.5), abs=0.003)

    dialog.reset_diff_colors()
    assert dialog.values().diff_colors == DEFAULT_DIFF_COLORS
    w.apply_settings(SettingsValues("pt", "por", DEFAULT_DIFF_COLORS, DEFAULT_STYLE))


def test_original_pdf_never_changes(opened, make_pdf):
    w = opened
    path = w.sessions[0].path
    before = path.read_bytes()
    for a in all_kinds():
        w.add_annotation(0, a)
    assert path.read_bytes() == before and file_fingerprint(path) == w.annotation_key(0)


def test_selection_is_cleared_when_the_page_changes(opened):
    w = opened
    w.panes[0].shape_drawn.emit(0, Annotation(am.RECT, 0, [(10, 10, 50, 50)]))
    assert w._selection is not None
    w.step(+1)
    assert w._selection is None and w.panes[0].selected_id == ""
    assert not w.act_delete_mark.isEnabled()
