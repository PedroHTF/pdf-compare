"""Janela principal: menus, barras de ferramentas, grade de PDFs, pesquisa,
anotações, comparação de texto, exportação, sessões e OCR."""

from __future__ import annotations

from app.i18n import LANGUAGES, language, tr

from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QSettings, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app import __copyright__, __url__, __version__
from app.model.session import DocumentSession, PasswordRequired, PdfOpenError, WrongPassword
from app.services import annotations as am
from app.services import ocr
from app.services.annotations import (
    HIGHLIGHT,
    NOTE,
    NOTE_SIZE,
    STAMP_FONT,
    Annotation,
    AnnotationStore,
    file_fingerprint,
    find_at,
    for_page,
    note_rect,
    save_annotated_pdf,
    stamp_rect,
    words_in_rect,
)
from app.services.batch_runner import BatchRunner
from app.services.diff_batches import ALL_PAGES, DiffCache, batch_for_page, format_size
from app.services.preferences import (
    LOOKAHEAD_ALL,
    NEXT_AUTO,
    REALIGN_AUTO,
    CompareSettings,
    MarkStyle,
    Preferences,
    to_hex,
)
from app.services.export import Column, ExportError, export_comparison, export_current_pages, safe_stem
from app.services.indexer import IndexScheduler
from app.services.navigation import NavigationController
from app.services.search import SearchOptions, hit_snippet, search_index
from app.services.text_diff import ADDED, CHANGED, REMOVED, count_by_kind
from app.services.workspace import (
    SESSION_SUFFIX,
    SessionData,
    SessionError,
    SessionFile,
    add_recent,
    existing_recent,
    load_session,
    pdfs_in_folder,
    save_session,
)
from app.ui.export_dialog import ANNOTATED, CURRENT_PAGES, SCOPE_ALL, SIDE_BY_SIDE, ExportChoice, ExportDialog
from app.ui.mark_widgets import MarkStyleBar, kind_label, stamp_label
from app.ui.marks_panel import MarksPanel
from app.ui.pane import (
    FIT_PAGE,
    FIT_WIDTH,
    TOOL_HIGHLIGHT,
    TOOL_NONE,
    TOOL_NOTE,
    PdfPane,
    ZoomMode,
    set_diff_colors,
)
from app.ui.resources import app_icon, logo_pixmap
from app.ui.results_panel import MAX_ITEMS_PER_DOC, ResultsPanel
from app.ui.search_bar import SearchBar
from app.ui.widgets import DropZone

APP_NAME = "PDF Compare"
MAX_DOCUMENTS = 6
MAX_PASSWORD_ATTEMPTS = 3
GRID_SHAPES = {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2), 5: (2, 3), 6: (2, 3)}
ZOOM_PRESETS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
S = QStyle.StandardPixmap


def _plural(n: int, singular: str, plural: str) -> str:
    """Ex.: _plural(3, "{n} arquivo", "{n} arquivos") -> "3 arquivos" (traduzido)."""
    return tr(singular if n == 1 else plural, n=n)


@dataclass
class UndoStep:
    """Estado das marcações de um documento antes e depois de uma alteração."""

    key: str
    name: str
    before: List[Annotation]
    after: List[Annotation]


# Ferramentas de marcação na ordem da barra: (tipo, texto do botão, dica)
MARK_KINDS = [am.HIGHLIGHT, am.UNDERLINE, am.STRIKEOUT, am.SQUIGGLY, am.NOTE, am.RECT, am.ELLIPSE, am.LINE, am.ARROW, am.POLYGON, am.INK, am.TEXTBOX, am.CALLOUT]


def mark_tools() -> List[Tuple[str, str, str]]:
    return [
        (am.HIGHLIGHT, "▌", tr("Destacar texto: arraste sobre o texto")),
        (am.UNDERLINE, "U̲", tr("Sublinhar texto: arraste sobre o texto")),
        (am.STRIKEOUT, "S̶", tr("Tachar texto: arraste sobre o texto")),
        (am.SQUIGGLY, "〰", tr("Sublinhado ondulado: arraste sobre o texto")),
        (am.NOTE, "🗈", tr("Nota: clique no ponto da página")),
        (am.RECT, "▭", tr("Retângulo: arraste na página")),
        (am.ELLIPSE, "◯", tr("Elipse: arraste na página")),
        (am.LINE, "╱", tr("Linha: arraste na página")),
        (am.ARROW, "➚", tr("Seta: arraste do início até a ponta")),
        (am.POLYGON, "⬠", tr("Polígono: clique em cada vértice e dê duplo clique para terminar (Esc cancela)")),
        (am.INK, "✎", tr("Caneta: desenhe à mão livre")),
        (am.TEXTBOX, "T", tr("Caixa de texto: arraste para definir a área (ou clique)")),
        (am.CALLOUT, "💬", tr("Balão: arraste do ponto indicado até onde fica o texto")),
    ]


def default_data_dir() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(location) if location else Path.home() / ".pdfcompare"


class MainWindow(QMainWindow):
    def __init__(self, settings: Optional[QSettings] = None, data_dir: Optional[Path] = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings()
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.annotations = AnnotationStore(self.data_dir / "anotacoes")
        self._annot_keys: Dict[int, Optional[str]] = {}
        self.tool = TOOL_NONE
        self.prefs = Preferences(self.settings)
        set_diff_colors(self.prefs.diff_colors())
        self.mark_style: MarkStyle = self.prefs.mark_style()
        self.stamp = stamp_label(am.STAMPS[0])
        self._undo: List[UndoStep] = []
        self._redo: List[UndoStep] = []
        self._selection: Optional[Tuple[int, str]] = None   # (painel, id da marcação)
        self._clipboard: Optional[Annotation] = None
        self._clipboard_source: Optional[Tuple[int, int]] = None   # (painel, página) de onde foi copiada
        self._last_pane = 0
        self.compare: CompareSettings = self.prefs.compare_settings()
        self.diff_cache = DiffCache(self.data_dir / "comparacoes")
        self.diff_cache.purge(self.compare.cache_days)
        self.runner = BatchRunner(self.diff_cache, self)
        self.runner.changed.connect(self._on_batches_changed)
        self.runner.progress.connect(self._on_batch_progress)
        self._batch_signature: Optional[tuple] = None
        self._current_batch = 0
        self._jump_to_first_diff = False
        self._alignment_touched = False   # o usuário acabou de ajustar o alinhamento de um painel
        self._adopt_offsets = False       # o próximo plano usa o alinhamento atual
        self._realign_pending = False     # alinhamento mudou e o usuário ainda não pediu "Recomparar"
        self._realign_timer = QTimer(self)
        self._realign_timer.setSingleShot(True)
        self._realign_timer.setInterval(self.REALIGN_DELAY_MS)
        self._realign_timer.timeout.connect(self._alignment_settled)
        self.sessions: List[DocumentSession] = []
        self.panes: List[PdfPane] = []
        self.nav = NavigationController()
        self.indexer = IndexScheduler(self)
        self.indexer.progress.connect(self._on_index_progress)
        self.indexer.document_indexed.connect(self._on_document_indexed)
        self.indexer.ocr_failed.connect(self._on_ocr_failed)
        self.zoom_mode: ZoomMode = self._load_zoom()
        self._query = ""

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.resize(1400, 900)
        geometry = self.settings.value("window/geometry")
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)

        self._create_actions()
        self._create_menus()
        self._create_toolbars()
        self._create_central()
        self._create_results_dock()
        self._create_marks_dock()
        self._create_status_bar()
        self._sync_zoom_combo()
        self._restore_ocr()
        self._update_ui_state()

    # ======================================================================
    # Construção da interface
    # ======================================================================
    def _action(
        self,
        text: str,
        slot: Callable[[], None],
        shortcuts: Sequence[str] = (),
        tip: str = "",
        icon: Optional[QStyle.StandardPixmap] = None,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(self.style().standardIcon(icon))
        if shortcuts:
            action.setShortcuts([QKeySequence(s) for s in shortcuts])
            native = QKeySequence(shortcuts[0]).toString(QKeySequence.SequenceFormat.NativeText)
            tip = f"{tip or text.replace('&', '')} ({native})"
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        action.setCheckable(checkable)
        action.triggered.connect(lambda _checked=False: slot())
        self.addAction(action)
        return action

    def _create_actions(self) -> None:
        self.act_add = self._action(tr("&Adicionar PDFs…"), self.open_dialog, ["Ctrl+O"],
                                    tr("Adicionar PDFs à comparação"), S.SP_DialogOpenButton)
        self.act_open_folder = self._action(tr("Abrir &pasta…"), self.open_folder_dialog, ["Ctrl+Shift+O"],
                                            tr("Abrir os PDFs de uma pasta (até 6, em ordem de nome)"))
        self.act_open_session = self._action(tr("Abrir &sessão…"), self.open_session_dialog, [],
                                             tr("Reabrir um conjunto de PDFs salvo, com páginas e zoom"))
        self.act_save_session = self._action(tr("&Salvar sessão…"), self.save_session_dialog, ["Ctrl+S"],
                                             tr("Salvar os PDFs abertos, as páginas e o zoom para reabrir depois"))
        self.act_export = self._action(tr("&Exportar…"), self.export_dialog, ["Ctrl+E"],
                                       tr("Exportar a comparação ou as páginas atuais como PDF ou PNG"))
        self.act_close_all = self._action(tr("&Fechar todos"), self.close_all, ["Ctrl+Shift+W"],
                                          tr("Fechar todos os PDFs"), S.SP_DialogCloseButton)
        self.act_quit = self._action(tr("Sai&r"), self.close, ["Ctrl+Q"], tr("Sair do programa"))

        self.act_prev = self._action(tr("Anterior"), lambda: self.step(-1), ["Left", "PgUp"],
                                     tr("Página anterior em todos os PDFs"), S.SP_ArrowBack)
        self.act_next = self._action(tr("Próxima"), lambda: self.step(+1), ["Right", "PgDown"],
                                     tr("Próxima página em todos os PDFs"), S.SP_ArrowForward)
        self.act_first = self._action(tr("Início"), self.go_first, ["Ctrl+Home"],
                                      tr("Ir para o início de todos os PDFs"), S.SP_MediaSkipBackward)
        self.act_last = self._action(tr("Fim"), self.go_last, ["Ctrl+End"],
                                     tr("Ir para o fim de todos os PDFs"), S.SP_MediaSkipForward)
        self.act_realign = self._action(tr("Realinhar"), self.realign, ["Ctrl+L"],
                                        tr("Desfazer ajustes individuais: todos voltam a mostrar a mesma página"),
                                        S.SP_BrowserReload)

        self.act_find = self._action(tr("&Pesquisar"), self.focus_search, ["Ctrl+F"], tr("Pesquisar em todos os PDFs"))
        self.act_hit_next = self._action(tr("Próxima ocorrência"), lambda: self.next_hit_all(+1), ["F3"],
                                         tr("Ir para a próxima ocorrência em cada PDF"))
        self.act_hit_prev = self._action(tr("Ocorrência anterior"), lambda: self.next_hit_all(-1), ["Shift+F3"],
                                         tr("Ir para a ocorrência anterior em cada PDF"))

        self.act_diff = self._action(tr("Comparar &texto"), self.toggle_diff, ["Ctrl+D"],
                                     tr("Destacar as diferenças de texto em relação ao primeiro PDF"),
                                     checkable=True)
        self.act_diff_next = self._action(tr("Próxima diferença"), lambda: self.next_diff_all(+1), ["F7"],
                                          tr("Ir para a próxima diferença de texto em cada PDF"))
        self.act_diff_prev = self._action(tr("Diferença anterior"), lambda: self.next_diff_all(-1), ["Shift+F7"],
                                          tr("Ir para a diferença de texto anterior em cada PDF"))
        self.act_batch_next = self._action(tr("Comparar próximo lote"), self.compare_next_batch, ["F8"],
                                           tr("Comparar o próximo lote de páginas e ir até ele"))
        self.act_recompare = self._action(tr("Recomparar"), self.recompare, [],
                                          tr("Refazer a comparação em lotes com o alinhamento atual dos PDFs"))
        self.act_batch_prev = self._action(tr("Lote anterior"), self.go_previous_batch, ["Shift+F8"],
                                           tr("Voltar ao lote de páginas anterior"))

        self.act_highlight = self._action(tr("&Destacar texto"), lambda: self.toggle_tool(TOOL_HIGHLIGHT), ["Ctrl+H"],
                                          tr("Arraste sobre o texto para destacá-lo"), checkable=True)
        self.act_note = self._action(tr("Adicionar &nota"), lambda: self.toggle_tool(TOOL_NOTE), ["Ctrl+M"],
                                     tr("Clique na página para adicionar uma nota"), checkable=True)
        self.act_highlight.setIconText(tr("Destacar"))
        self.act_note.setIconText(tr("Nota"))
        self.act_select = self._action(tr("&Selecionar e mover"), lambda: self.set_tool(TOOL_NONE), [],
                                       tr("Selecionar, mover e redimensionar marcações (duplo clique edita o texto)"),
                                       checkable=True)
        self.act_select.setIconText("⬚")
        self.act_select.setChecked(True)
        self.tool_actions: Dict[str, QAction] = {TOOL_NONE: self.act_select, TOOL_HIGHLIGHT: self.act_highlight,
                                                 TOOL_NOTE: self.act_note}
        for kind, glyph, tip in mark_tools():
            if kind not in self.tool_actions:
                self.tool_actions[kind] = self._action(kind_label(kind), lambda k=kind: self.toggle_tool(k), [],
                                                       tip, checkable=True)
            self.tool_actions[kind].setIconText(glyph)
            self.tool_actions[kind].setToolTip(f"{kind_label(kind)} — {tip}")
        self.act_stamp = self._action(tr("Carimbo"), lambda: self.toggle_tool(am.STAMP), [],
                                      tr("Carimbo: escolha o texto e clique na página"), checkable=True)
        self.act_stamp.setIconText("▣")
        self.tool_actions[am.STAMP] = self.act_stamp

        self.act_undo = self._action(tr("&Desfazer"), self.undo, ["Ctrl+Z"], tr("Desfazer a última alteração nas marcações"))
        self.act_redo = self._action(tr("&Refazer"), self.redo, ["Ctrl+Y", "Ctrl+Shift+Z"],
                                     tr("Refazer a alteração desfeita"))
        self.act_undo.setIconText("↶")
        self.act_redo.setIconText("↷")
        self.act_copy_mark = self._action(tr("&Copiar marcação"), self.copy_selected, ["Ctrl+C"])
        self.act_paste_mark = self._action(tr("Co&lar marcação"), self.paste_mark, ["Ctrl+V"],
                                           tr("Colar a marcação copiada na página à vista do painel"))
        self.act_delete_mark = self._action(tr("&Excluir marcação"), self.delete_selected, ["Delete"])
        self.act_escape = self._action(tr("Cancelar"), self.escape, ["Esc"])
        for action in (self.act_copy_mark, self.act_paste_mark, self.act_delete_mark, self.act_escape):
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.removeAction(action)
        self.act_settings = self._action(tr("&Configurações…"), self.open_settings, ["Ctrl+,"],
                                         tr("Idiomas, cores da comparação e estilo das marcações"))

        self.act_ocr = self._action(tr("Reconhecer texto em PDFs escaneados (&OCR)"), self.toggle_ocr, [],
                                    tr("Usa o Tesseract OCR, se instalado, para pesquisar e comparar PDFs escaneados"),
                                    checkable=True)
        self.act_ocr_language = self._action(tr("&Idioma do OCR…"), self.choose_ocr_language)

        self.act_fit_width = self._action(tr("Ajustar à &largura"), lambda: self.set_zoom(FIT_WIDTH), ["Ctrl+0"])
        self.act_fit_page = self._action(tr("&Página inteira"), lambda: self.set_zoom(FIT_PAGE), ["Ctrl+9"])
        self.act_zoom_in = self._action(tr("&Aumentar zoom"), lambda: self.zoom_by(+1), ["Ctrl++", "Ctrl+="])
        self.act_zoom_out = self._action(tr("&Diminuir zoom"), lambda: self.zoom_by(-1), ["Ctrl+-"])
        self.act_zoom_in.setIconText("+")
        self.act_zoom_out.setIconText("−")

        self.act_linked_scroll = self._action(
            tr("Rolagem &vinculada"), self._save_view_settings, [],
            tr("Ao rolar a página de um PDF, os outros acompanham"), checkable=True,
        )
        self.act_linked_scroll.setChecked(self._bool_setting("view/linked_scroll", True))

        self.act_shortcuts = self._action(tr("&Atalhos de teclado"), self.show_shortcuts, ["F1"])
        self.act_license = self._action(tr("&Licença e créditos…"), self.show_license,
                                        tip=tr("O que você pode fazer com este programa e licenças dos componentes"))
        self.act_about = self._action(tr("&Sobre"), self.show_about)

    def _create_menus(self) -> None:
        bar = self.menuBar()
        m = bar.addMenu(tr("&Arquivo"))
        m.addActions([self.act_add, self.act_open_folder])
        self.recent_menu = m.addMenu(tr("Abertos &recentemente"))
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        m.addActions([self.act_open_session, self.act_save_session])
        m.addSeparator()
        m.addAction(self.act_export)
        m.addSeparator()
        m.addAction(self.act_close_all)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = bar.addMenu(tr("E&ditar"))
        m.addActions([self.act_undo, self.act_redo])
        m.addSeparator()
        m.addActions([self.act_copy_mark, self.act_paste_mark, self.act_delete_mark])
        m.addSeparator()
        m.addAction(self.act_settings)

        m = bar.addMenu(tr("&Navegar"))
        m.addActions([self.act_prev, self.act_next, self.act_first, self.act_last])
        m.addSeparator()
        m.addAction(self.act_realign)
        m.addSeparator()
        m.addActions([self.act_find, self.act_hit_next, self.act_hit_prev])
        m.addSeparator()
        m.addActions([self.act_diff_next, self.act_diff_prev])
        m.addActions([self.act_batch_next, self.act_batch_prev, self.act_recompare])

        m = bar.addMenu(tr("&Exibir"))
        m.addActions([self.act_fit_width, self.act_fit_page, self.act_zoom_in, self.act_zoom_out])
        m.addSeparator()
        m.addAction(self.act_linked_scroll)
        self.view_menu = m

        m = bar.addMenu(tr("&Ferramentas"))
        marks = m.addMenu(tr("&Marcações"))
        marks.addAction(self.act_select)
        marks.addSeparator()
        marks.addActions([self.tool_actions[k] for k in MARK_KINDS])
        marks.addAction(self.act_stamp)
        m.addSeparator()
        m.addAction(self.act_diff)
        m.addSeparator()
        m.addActions([self.act_ocr, self.act_ocr_language])
        m.addSeparator()
        m.addAction(self.act_settings)

        self.language_menu = m.addMenu("Idioma / &Language")
        for code, label in LANGUAGES.items():
            action = self.language_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == language())
            action.setData(code)
            action.triggered.connect(lambda _c=False, c=code: self.set_ui_language(c))

        m = bar.addMenu(tr("A&juda"))
        m.addActions([self.act_shortcuts, self.act_license, self.act_about])

    def _create_toolbars(self) -> None:
        tb = QToolBar(tr("Barra principal"))
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        tb.addAction(self.act_add)
        tb.addSeparator()
        tb.addActions([self.act_first, self.act_prev, self.act_next, self.act_last])
        tb.addSeparator()
        tb.addAction(self.act_realign)
        tb.addSeparator()
        tb.addAction(self.act_zoom_out)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setToolTip(tr("Zoom de todos os PDFs (Ctrl + roda do mouse)"))
        self.zoom_combo.setAccessibleName("Zoom")
        self.zoom_combo.addItem(tr("Ajustar à largura"), FIT_WIDTH)
        self.zoom_combo.addItem(tr("Página inteira"), FIT_PAGE)
        for z in ZOOM_PRESETS:
            self.zoom_combo.addItem(f"{round(z * 100)}%", z)
        self.zoom_combo.currentIndexChanged.connect(
            lambda i: self.set_zoom(self.zoom_combo.itemData(i))
        )
        tb.addWidget(self.zoom_combo)
        tb.addAction(self.act_zoom_in)
        tb.addSeparator()
        tb.addAction(self.act_linked_scroll)
        tb.addSeparator()
        tb.addAction(self.act_diff)
        tb.addSeparator()
        tb.addAction(self.act_export)

        self.addToolBarBreak()
        stb = QToolBar(tr("Pesquisa"))
        stb.setObjectName("searchToolbar")
        stb.setMovable(False)
        self.search_bar = SearchBar()
        self.search_bar.set_options(SearchOptions(
            case_sensitive=self._bool_setting("search/case_sensitive", False),
            whole_word=self._bool_setting("search/whole_word", False),
            ignore_accents=self._bool_setting("search/ignore_accents", True),
        ))
        self.search_bar.search_changed.connect(self.run_search)
        self.search_bar.next_requested.connect(lambda: self.next_hit_all(+1))
        self.search_bar.prev_requested.connect(lambda: self.next_hit_all(-1))
        stb.addWidget(self.search_bar)
        self.addToolBar(stb)
        self._create_mark_toolbar()

    def _create_mark_toolbar(self) -> None:
        from PySide6.QtWidgets import QToolButton

        self.addToolBarBreak()
        mtb = QToolBar(tr("Barra de marcação"))
        mtb.setObjectName("markToolbar")
        mtb.setMovable(False)
        mtb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        mtb.addAction(self.act_select)
        mtb.addSeparator()
        for kind in MARK_KINDS:
            mtb.addAction(self.tool_actions[kind])
        self.stamp_menu = QMenu(self)
        for stamp in am.STAMPS:
            label = stamp_label(stamp)
            self.stamp_menu.addAction(label, lambda t=label: self.choose_stamp(t))
        self.stamp_menu.addSeparator()
        self.stamp_menu.addAction(tr("Outro texto…"), self.choose_custom_stamp)
        stamp_button = QToolButton()
        stamp_button.setDefaultAction(self.act_stamp)
        stamp_button.setMenu(self.stamp_menu)
        stamp_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        stamp_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        mtb.addWidget(stamp_button)
        mtb.addSeparator()
        self.style_bar = MarkStyleBar(self.mark_style)
        self.style_bar.style_changed.connect(self.set_mark_style)
        mtb.addWidget(self.style_bar)
        mtb.addSeparator()
        mtb.addActions([self.act_undo, self.act_redo])
        self.addToolBar(mtb)
        self.mark_toolbar = mtb
        self.act_mark_toolbar = mtb.toggleViewAction()
        self.act_mark_toolbar.setText(tr("Barra de &marcação"))
        mtb.setVisible(self._bool_setting("view/mark_toolbar", True))

    def _create_central(self) -> None:
        self.empty_view = DropZone(
            tr("Arraste seus PDFs para cá"),
            tr("Compare de 2 a 6 documentos lado a lado, pesquise em todos ao mesmo tempo\n"
            "e avance página por página — em todos juntos ou em cada um separadamente."),
            pixmap=logo_pixmap(96),
        )
        self.empty_view.open_requested.connect(self.open_dialog)
        empty_host = QWidget()
        empty_layout = QVBoxLayout(empty_host)
        empty_layout.setContentsMargins(60, 40, 60, 40)
        empty_layout.addWidget(self.empty_view)

        self.grid_host = QWidget()
        for action in (self.act_copy_mark, self.act_paste_mark, self.act_delete_mark, self.act_escape):
            self.grid_host.addAction(action)
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.grid.setSpacing(6)

        self.stack = QStackedWidget()
        self.stack.addWidget(empty_host)
        self.stack.addWidget(self.grid_host)
        self.setCentralWidget(self.stack)

    def _create_results_dock(self) -> None:
        self.results_panel = ResultsPanel()
        self.results_panel.hit_activated.connect(self.go_to_hit)
        self.results_dock = QDockWidget(tr("Ocorrências"), self)
        self.results_dock.setObjectName("resultsDock")
        self.results_dock.setWidget(self.results_panel)
        self.results_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.results_dock)
        self.results_dock.setVisible(self._bool_setting("view/results_panel", False))
        self.act_results = self.results_dock.toggleViewAction()
        self.act_results.setText(tr("Lista de &ocorrências"))
        self.act_results.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_results.setToolTip(tr("Mostrar a lista de ocorrências da pesquisa (Ctrl+Shift+F)"))
        self.addAction(self.act_results)
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.act_results)
        self.search_bar.layout().insertWidget(5, self._results_button())

    def _create_marks_dock(self) -> None:
        self.marks_panel = MarksPanel()
        self.marks_panel.mark_activated.connect(self.go_to_mark)
        self.marks_dock = QDockWidget(tr("Marcações"), self)
        self.marks_dock.setObjectName("marksDock")
        self.marks_dock.setWidget(self.marks_panel)
        self.marks_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.marks_dock)
        self.marks_dock.setVisible(self._bool_setting("view/marks_panel", False))
        self.act_marks_panel = self.marks_dock.toggleViewAction()
        self.act_marks_panel.setText(tr("Lista de &marcações"))
        self.act_marks_panel.setShortcut(QKeySequence("Ctrl+Shift+M"))
        self.act_marks_panel.setToolTip(tr("Mostrar a lista de todas as marcações (Ctrl+Shift+M)"))
        self.addAction(self.act_marks_panel)
        self.view_menu.addAction(self.act_marks_panel)
        self.view_menu.addAction(self.act_mark_toolbar)
        self.mark_toolbar.addAction(self.act_marks_panel)

    def _results_button(self):
        from PySide6.QtWidgets import QToolButton

        button = QToolButton()
        button.setDefaultAction(self.act_results)
        button.setText(tr("Lista"))
        return button

    def _create_batch_bar(self) -> None:
        from PySide6.QtWidgets import QHBoxLayout, QToolButton

        self.batch_bar = QWidget()
        self.batch_bar.setObjectName("batchBar")
        row = QHBoxLayout(self.batch_bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.batch_prev_btn = QToolButton()
        self.batch_prev_btn.setText("◀")
        self.batch_prev_btn.setToolTip(self.act_batch_prev.toolTip())
        self.batch_prev_btn.clicked.connect(self.act_batch_prev.trigger)
        self.batch_label = QLabel()
        self.batch_next_btn = QToolButton()
        self.batch_next_btn.clicked.connect(self.act_batch_next.trigger)
        self.batch_next_btn.setToolTip(self.act_batch_next.toolTip())
        self.recompare_btn = QToolButton()
        self.recompare_btn.setText(tr("Recomparar"))
        self.recompare_btn.setToolTip(self.act_recompare.toolTip())
        self.recompare_btn.clicked.connect(self.act_recompare.trigger)
        self.batch_progress = QProgressBar()
        self.batch_progress.setMaximumWidth(120)
        self.batch_progress.setTextVisible(False)
        self.batch_cancel_btn = QToolButton()
        self.batch_cancel_btn.setText(tr("Cancelar"))
        self.batch_cancel_btn.setToolTip(tr("Cancelar a comparação em andamento (os lotes prontos continuam)"))
        self.batch_cancel_btn.clicked.connect(self.cancel_batches)
        for w in (self.batch_prev_btn, self.batch_label, self.batch_next_btn, self.recompare_btn, self.batch_progress,
                  self.batch_cancel_btn):
            row.addWidget(w)
        self.batch_bar.hide()
        self.statusBar().insertPermanentWidget(0, self.batch_bar)

    def _create_status_bar(self) -> None:
        self.hint_label = QLabel()
        self.hint_label.setObjectName("muted")
        self.statusBar().addWidget(self.hint_label, 1)
        self.diff_label = QLabel()
        self.diff_label.setObjectName("diffSummary")
        self.diff_label.hide()
        self.statusBar().addPermanentWidget(self.diff_label)
        self._create_batch_bar()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(240)
        self.progress.setFormat(tr("Preparando pesquisa… %p%"))
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

    # ======================================================================
    # Abrir e fechar documentos
    # ======================================================================
    def open_dialog(self) -> None:
        if len(self.sessions) >= MAX_DOCUMENTS:
            self._notify("info", tr("Limite atingido"), tr("Já há {n} PDFs abertos. Feche um para adicionar outro.", n=MAX_DOCUMENTS))
            return
        start_dir = str(self.settings.value("files/last_dir", ""))
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Adicionar PDFs"), start_dir, tr("Documentos PDF (*.pdf)"))
        if paths:
            self.settings.setValue("files/last_dir", str(Path(paths[0]).parent))
            self.add_files(paths)

    def add_files(self, paths: Iterable) -> None:
        candidates = [Path(p) for p in paths]
        pdfs = [p for p in candidates if p.suffix.lower() == ".pdf"]
        ignored_type = len(candidates) - len(pdfs)
        room = MAX_DOCUMENTS - len(self.sessions)
        accepted, over_limit = pdfs[:room], pdfs[room:]

        errors: List[str] = []
        opened: List[DocumentSession] = []
        cancelled: List[str] = []
        for path in accepted:
            try:
                session = self._open_document(path)
            except PdfOpenError as exc:
                errors.append(str(exc))
                continue
            if session is None:
                cancelled.append(path.name)
            else:
                opened.append(session)
        if cancelled:
            self.statusBar().showMessage(
                tr("Não aberto (senha não informada): {names}", names=", ".join(cancelled)), 6000
            )

        if opened:
            was_empty = not self.sessions
            self.sessions.extend(opened)
            for session in opened:
                self.indexer.add(session)
            self.nav.set_sessions(self.sessions, keep_position=not was_empty)
            self._rebuild_grid()
            self.run_search()
            self.update_diff()
            for session in opened:
                self._remember(session.path)

        problems: List[str] = list(errors)
        if over_limit:
            names = ", ".join(p.name for p in over_limit)
            problems.append(tr("Limite de {n} PDFs: não foram abertos — {names}.", n=MAX_DOCUMENTS, names=names))
        if ignored_type:
            problems.append(_plural(ignored_type, "{n} arquivo ignorado por não ser PDF.", "{n} arquivos ignorados por não serem PDF."))
        if problems:
            self._notify("warning", tr("Alguns arquivos não foram abertos"), "\n\n".join(problems))
        self._update_ui_state()

    def _open_document(self, path: Path) -> Optional[DocumentSession]:
        """Abre um PDF pedindo a senha, se necessário.

        Devolve None se o usuário cancelar. A senha é usada só para desbloquear
        o arquivo e não é guardada em lugar nenhum.
        """
        try:
            return DocumentSession.open(path)
        except PasswordRequired:
            pass
        for attempt in range(1, MAX_PASSWORD_ATTEMPTS + 1):
            password = self._ask_password(path.name, attempt)
            if password is None:
                return None
            try:
                return DocumentSession.open(path, password=password)
            except WrongPassword:
                continue
        raise PdfOpenError(
            tr("Senha incorreta para “{name}” ({n} tentativas). Abra o arquivo de novo para tentar outra vez.",
               name=path.name, n=MAX_PASSWORD_ATTEMPTS)
        )

    def _ask_password(self, name: str, attempt: int) -> Optional[str]:
        """Pede a senha ao usuário. Devolve None se ele cancelar."""
        if attempt == 1:
            label = tr("“{name}” está protegido por senha.\n\nDigite a senha para abri-lo:", name=name)
        else:
            label = tr("Senha incorreta. Tente novamente (tentativa {attempt} de {total}).\n\nSenha de “{name}”:",
                       attempt=attempt, total=MAX_PASSWORD_ATTEMPTS, name=name)
        dialog = QInputDialog(self)
        dialog.setWindowTitle(tr("PDF protegido"))
        dialog.setLabelText(label)
        dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
        dialog.setOkButtonText(tr("Abrir"))
        dialog.setCancelButtonText(tr("Pular este arquivo"))
        dialog.resize(420, dialog.sizeHint().height())
        if dialog.exec() != QInputDialog.DialogCode.Accepted:
            return None
        return dialog.textValue()

    def remove_document(self, index: int) -> None:
        if not 0 <= index < len(self.sessions):
            return
        session = self.sessions.pop(index)
        self.indexer.remove(session)
        self._annot_keys.pop(session.uid, None)
        session.close()
        self.nav.set_sessions(self.sessions, keep_position=True)
        self._rebuild_grid()
        self.run_search()
        self.update_diff()
        self._update_ui_state()

    def close_all(self) -> None:
        self.indexer.clear()
        for session in self.sessions:
            session.close()
        self.sessions = []
        self._annot_keys.clear()
        self.nav.set_sessions([])
        self._rebuild_grid()
        self.run_search()
        self.update_diff()
        self._update_ui_state()

    def _rebuild_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for i in range(3):
            self.grid.setColumnStretch(i, 0)
            self.grid.setRowStretch(i, 0)
        self.panes = []

        n = len(self.sessions)
        if n == 0:
            return
        slots = n + 1 if n == 1 else n   # com 1 PDF, mostra um espaço para adicionar outro
        rows, cols = GRID_SHAPES[slots]
        for i, session in enumerate(self.sessions):
            pane = PdfPane(i, session)
            pane.page_step.connect(self._on_pane_step)
            pane.page_jump.connect(self._on_pane_jump)
            pane.hit_step.connect(self._on_pane_hit_step)
            pane.close_requested.connect(self.remove_document)
            pane.zoom_step.connect(self.zoom_by)
            pane.scrolled.connect(self._on_pane_scrolled)
            pane.highlight_requested.connect(self._on_highlight)
            pane.note_requested.connect(self._on_note)
            pane.annotation_menu.connect(self._on_annotation_menu)
            pane.markup_requested.connect(self._on_markup)
            pane.shape_drawn.connect(self._on_shape)
            pane.stamp_requested.connect(self._on_stamp)
            pane.annotation_changed.connect(self._on_mark_changed)
            pane.selection_changed.connect(self._on_selection)
            pane.edit_requested.connect(self.edit_annotation)
            pane.mark_style = self.mark_style
            pane.scroll.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            pane.set_tool(self.tool)
            self.panes.append(pane)
            self.grid.addWidget(pane, i // cols, i % cols)
        if n == 1:
            add_zone = DropZone(tr("Adicione outro PDF"), tr("para comparar lado a lado"), tr("Adicionar PDF…"), compact=True)
            add_zone.open_requested.connect(self.open_dialog)
            self.grid.addWidget(add_zone, 0, 1)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        for r in range(rows):
            self.grid.setRowStretch(r, 1)
        self._selection = None
        self.refresh()
        self._refresh_marks_panel()

    # ======================================================================
    # Navegação
    # ======================================================================
    def step(self, delta: int) -> None:
        self._user_busy()
        if self.sessions:
            self.nav.step(delta)
            self.refresh()

    def go_first(self) -> None:
        self._user_busy()
        if self.sessions:
            self.nav.go_first()
            self.refresh()

    def go_last(self) -> None:
        self._user_busy()
        if self.sessions:
            self.nav.go_last()
            self.refresh()

    def realign(self) -> None:
        self._alignment_touched = True
        if self.sessions:
            self.nav.realign()
            self.refresh()
            self.statusBar().showMessage(tr("Todos os PDFs realinhados na mesma página."), 3000)

    def _on_pane_step(self, index: int, delta: int) -> None:
        self._user_busy()
        self._alignment_touched = True
        self.nav.step_pane(index, delta)
        self.refresh()

    def _on_pane_jump(self, index: int, page: int) -> None:
        self._user_busy()
        self._alignment_touched = True
        self.nav.show_page(index, page)
        self.refresh()

    def _on_pane_hit_step(self, index: int, delta: int) -> None:
        self.nav.step_hit(index, delta)
        self.refresh()

    def _on_pane_scrolled(self, index: int, ratio: float) -> None:
        self._user_busy()
        if not self.act_linked_scroll.isChecked():
            return
        for pane in self.panes:
            if pane.index != index:
                pane.set_scroll_ratio(ratio)

    def refresh(self) -> None:
        active = bool(self._query)
        if self.act_diff.isChecked() and self.runner.batches:
            self._ensure_batches()
        selected = self.selected_annotation()
        if self._selection is not None and (selected is None or self.nav.page_for(self._selection[0]) != selected.page):
            self._selection = None   # a marcação selecionada saiu de vista
            for pane in self.panes:
                pane.selected_id = ""
        for i, pane in enumerate(self.panes):
            page = self.nav.page_for(i)
            current = self.nav.current_hit(i)
            if current is not None and current.page != page:
                current = None   # o usuário saiu da página da ocorrência
            diff = self.nav.current_diff(i)
            if diff is not None and diff.page != page:
                diff = None
            pane.render(page, self.nav.raw_page(i), self.nav.page_hits(i, page), current, self.zoom_mode,
                        self.nav.page_diffs(i, page), diff, self.page_annotations(i, page))
            position = self.nav.hit_index[i] if current is not None else -1
            pane.set_hit_status(active, self.nav.hit_count(i), position)
        self._update_ui_state()

    # ======================================================================
    # Pesquisa
    # ======================================================================
    def focus_search(self) -> None:
        if self.sessions:
            self.search_bar.focus_search()

    def run_search(self) -> None:
        query = self.search_bar.text()
        options = self.search_bar.options()
        self._save_search_settings(options)
        self._query = query if self.sessions else ""

        if not self._query:
            self.nav.clear_hits()
            self.search_bar.set_summary("")
            self.results_panel.set_results("", [])
            self.refresh()
            return

        results = []
        pending = False
        for session in self.sessions:
            index = self.indexer.index_for(session)
            if index is None or not index.complete:
                pending = True
            results.append(search_index(index, query, options) if index is not None else [])
        self.nav.set_hits(results)
        self._fill_results(query)

        total = self.nav.total_hits
        docs = sum(1 for r in results if r)
        if total:
            text = tr("{hits} em {docs} de {total} — Enter vai para a próxima",
                      hits=_plural(total, "{n} ocorrência", "{n} ocorrências"), docs=docs,
                      total=_plural(len(self.sessions), "{n} PDF", "{n} PDFs"))
            state = "found"
        else:
            text, state = tr("Nenhuma ocorrência encontrada"), "notfound"
        if pending:
            text += tr(" · ainda lendo o texto dos PDFs…")
            state = "found" if total else ""
        self.search_bar.set_summary(text, state)
        self.refresh()

    def next_hit_all(self, delta: int) -> None:
        if not self.sessions:
            return
        if not self._query:
            self.focus_search()
            return
        if self.nav.step_hit_all(delta):
            self.refresh()
        else:
            self.statusBar().showMessage(tr("Nenhuma ocorrência para navegar."), 3000)

    def _fill_results(self, query: str) -> None:
        results = []
        for i, session in enumerate(self.sessions):
            index = self.indexer.index_for(session)
            hits = self.nav.hits[i] if i < len(self.nav.hits) else []
            items = [(h.page, hit_snippet(index, h) if index is not None else "")
                     for h in hits[:MAX_ITEMS_PER_DOC]]
            items += [(h.page, "") for h in hits[MAX_ITEMS_PER_DOC:]]
            results.append((session.name, items))
        self.results_panel.set_results(query, results)

    def go_to_hit(self, doc_index: int, position: int) -> None:
        """Clique na lista de ocorrências: leva aquele PDF até a ocorrência."""
        if self.nav.go_to_hit(doc_index, position):
            self.refresh()

    def _on_document_indexed(self, session: DocumentSession) -> None:
        if self._query:
            self.run_search()
        self._hint_scanned(session)

    def _on_index_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress.hide()
            if self._query:
                self.run_search()
            self.update_diff()
            return
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress.show()

    # ======================================================================
    # Zoom
    # ======================================================================
    def set_zoom(self, mode: ZoomMode) -> None:
        if mode is None:
            return
        self.zoom_mode = mode
        self._sync_zoom_combo()
        self.settings.setValue("view/zoom", str(mode))
        self.refresh()

    def zoom_by(self, direction: int) -> None:
        if not self.panes:
            return
        current = self.panes[0].last_scale
        if direction > 0:
            target = next((z for z in ZOOM_PRESETS if z > current + 0.01), ZOOM_PRESETS[-1])
        else:
            target = next((z for z in reversed(ZOOM_PRESETS) if z < current - 0.01), ZOOM_PRESETS[0])
        self.set_zoom(target)

    def _sync_zoom_combo(self) -> None:
        index = self.zoom_combo.findData(self.zoom_mode)
        self.zoom_combo.blockSignals(True)
        self.zoom_combo.setCurrentIndex(max(index, 0))
        self.zoom_combo.blockSignals(False)

    def _load_zoom(self) -> ZoomMode:
        zoom = self._parse_zoom(self.settings.value("view/zoom", FIT_WIDTH))
        return zoom if zoom is not None else FIT_WIDTH

    @staticmethod
    def _parse_zoom(value) -> Optional[ZoomMode]:
        value = str(value)
        if value in (FIT_WIDTH, FIT_PAGE):
            return value
        try:
            zoom = float(value)
        except ValueError:
            return None
        return zoom if zoom in ZOOM_PRESETS else None

    # ======================================================================
    # Estado da interface
    # ======================================================================
    def _update_ui_state(self) -> None:
        n = len(self.sessions)
        has = n > 0
        self.stack.setCurrentIndex(1 if has else 0)

        for action in (self.act_close_all, self.act_fit_width, self.act_fit_page,
                       self.act_zoom_in, self.act_zoom_out, self.act_find, self.act_export,
                       self.act_save_session, *self.tool_actions.values()):
            action.setEnabled(has)
        self.act_undo.setEnabled(bool(self._undo))
        self.act_redo.setEnabled(bool(self._redo))
        self.act_copy_mark.setEnabled(self._selection is not None)
        self.act_delete_mark.setEnabled(self._selection is not None)
        self.act_paste_mark.setEnabled(has and self._clipboard is not None)
        self.act_diff.setEnabled(n >= 2)
        has_diffs = n >= 2 and self.act_diff.isChecked() and self.nav.total_diffs > 0
        self.act_diff_next.setEnabled(has_diffs)
        self.act_diff_prev.setEnabled(has_diffs)
        self.act_open_folder.setEnabled(n < MAX_DOCUMENTS)
        self.act_add.setEnabled(n < MAX_DOCUMENTS)
        self.act_prev.setEnabled(has and not self.nav.at_start)
        self.act_first.setEnabled(has and not self.nav.at_start)
        self.act_next.setEnabled(has and not self.nav.at_end)
        self.act_last.setEnabled(has and not self.nav.at_end)
        self.act_realign.setEnabled(has and not self.nav.is_aligned)
        has_hits = has and self.nav.total_hits > 0
        self.act_hit_next.setEnabled(has_hits)
        self.act_hit_prev.setEnabled(has_hits)
        self.search_bar.setEnabled(has)
        self.search_bar.btn_next.setEnabled(has_hits)
        self.search_bar.btn_prev.setEnabled(has_hits)
        self.zoom_combo.setEnabled(has)

        names = ", ".join(s.name for s in self.sessions)
        self.setWindowTitle(f"{names} — {APP_NAME}" if names else APP_NAME)

        if not has:
            hint = tr("Abra ou arraste de 2 a 6 PDFs para começar  (Ctrl+O)")
        elif n == 1:
            hint = tr("Adicione pelo menos mais um PDF para comparar.")
        else:
            hint = (tr("◀ ▶ ou setas do teclado: avançam todos juntos  ·  "
                    "botões de cada painel: ajustam só aquele PDF  ·  Ctrl+F: pesquisar em todos"))
        self.hint_label.setText(hint)

    # ======================================================================
    # Diálogos e preferências
    # ======================================================================
    def _notify(self, kind: str, title: str, text: str) -> None:
        if kind == "warning":
            QMessageBox.warning(self, title, text)
        else:
            QMessageBox.information(self, title, text)

    def show_shortcuts(self) -> None:
        rows = [
            ("Ctrl+O", tr("Adicionar PDFs (ou arraste os arquivos para a janela)")),
            ("Ctrl+Shift+O", tr("Abrir todos os PDFs de uma pasta")),
            ("Ctrl+S", tr("Salvar sessão (PDFs, páginas e zoom)")),
            ("Ctrl+E", tr("Exportar comparação ou páginas atuais (PDF/PNG)")),
            ("→ / Page Down", tr("Próxima página em todos os PDFs")),
            ("← / Page Up", tr("Página anterior em todos os PDFs")),
            ("Ctrl+Home / Ctrl+End", tr("Início / fim de todos os PDFs")),
            ("Ctrl+L", tr("Realinhar: todos na mesma página")),
            ("Ctrl+F", tr("Pesquisar em todos os PDFs")),
            ("Enter / F3", tr("Próxima ocorrência em cada PDF")),
            ("Shift+Enter / Shift+F3", tr("Ocorrência anterior em cada PDF")),
            ("Ctrl+Shift+F", tr("Mostrar/ocultar a lista de ocorrências")),
            ("Esc", tr("Limpar a pesquisa (com o cursor na caixa de pesquisa)")),
            ("Ctrl+D", tr("Comparar texto: destacar diferenças em relação ao 1º PDF")),
            ("F7 / Shift+F7", tr("Próxima / anterior diferença de texto em cada PDF")),
            ("Ctrl+H", tr("Destacar texto (arraste sobre o texto)")),
            ("Ctrl+M", tr("Adicionar nota (clique na página)")),
            (tr("Botão direito"), tr("Editar ou remover a anotação sob o cursor")),
            (tr("Duplo clique"), tr("Editar o texto da marcação")),
            ("Ctrl+Z / Ctrl+Y", tr("Desfazer / refazer alterações nas marcações")),
            ("Ctrl+C / Ctrl+V / Delete", tr("Copiar, colar ou excluir a marcação selecionada")),
            ("Esc", tr("Cancelar o desenho, desmarcar ou voltar à seleção")),
            ("Ctrl+Shift+M", tr("Mostrar/ocultar a lista de marcações")),
            ("Ctrl+,", tr("Configurações")),
            (tr("Ctrl + roda do mouse"), "Zoom"),
            ("Ctrl++ / Ctrl+-", tr("Aumentar / diminuir zoom")),
            ("Ctrl+0 / Ctrl+9", tr("Ajustar à largura / página inteira")),
        ]
        table = "".join(f"<tr><td style='padding:2px 16px 2px 0'><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows)
        colors = {k: to_hex(c) for k, c in self.prefs.diff_colors().items()}
        extra = (tr("<p>Em cada painel: <b>◀ ▶</b> mudam só aquele PDF, <b>▲ ▼</b> navegam pelas "
                    "ocorrências dele e o campo de página permite digitar o número.</p>")
                 + tr("<p>Comparar texto: <span style='color:{added}'>■</span> incluído, "
                      "<span style='color:{removed}'>■</span> removido, "
                      "<span style='color:{changed}'>■</span> alterado "
                      "(cores em Ferramentas › Configurações).</p>",
                      added=colors[ADDED], removed=colors[REMOVED], changed=colors[CHANGED]))
        QMessageBox.information(self, tr("Atalhos de teclado"), f"<table>{table}</table>{extra}")

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("Sobre o {app}", app=APP_NAME))
        box.setIconPixmap(logo_pixmap(72))
        box.setText(
            f"<h3>{APP_NAME} {__version__}</h3>" +
            tr("<p>Compare de 2 a 6 PDFs lado a lado, com pesquisa simultânea "
            "e navegação página a página.</p>"
            "<p>Os arquivos são processados apenas neste computador.</p>")
            + tr('<p>{copyright}<br>Software livre sob a licença GNU AGPL v3.<br>'
                 'Código-fonte: <a href="{url}">{url}</a></p>', copyright=__copyright__, url=__url__)
        )
        btn_license = box.addButton(tr("Licença e créditos…"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is btn_license:
            self.show_license()

    def show_license(self) -> None:
        from app.ui.license_dialog import LicenseDialog

        LicenseDialog(self).exec()

    def _bool_setting(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    def _save_view_settings(self) -> None:
        self.settings.setValue("view/linked_scroll", self.act_linked_scroll.isChecked())

    def _save_search_settings(self, options: SearchOptions) -> None:
        self.settings.setValue("search/case_sensitive", options.case_sensitive)
        self.settings.setValue("search/whole_word", options.whole_word)
        self.settings.setValue("search/ignore_accents", options.ignore_accents)

    # ======================================================================
    # Arrastar e soltar / fechamento
    # ======================================================================
    @staticmethod
    def _pdf_paths(mime: QMimeData) -> List[Path]:
        if not mime.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in mime.urls()
                if u.isLocalFile() and u.toLocalFile().lower().endswith(".pdf")]

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._pdf_paths(event.mimeData()):
            event.acceptProposedAction()
            self.statusBar().showMessage(tr("Solte para adicionar os PDFs à comparação."))

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._pdf_paths(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.statusBar().clearMessage()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._pdf_paths(event.mimeData())
        self.statusBar().clearMessage()
        if paths:
            event.acceptProposedAction()
            self.add_files(paths)

    # ======================================================================
    # Idioma da interface
    # ======================================================================
    def set_ui_language(self, code: str) -> None:
        """Guarda o idioma escolhido; ele vale a partir da próxima abertura do programa."""
        for action in self.language_menu.actions():
            action.setChecked(action.data() == code)
        if str(self.settings.value("app/language", language())) == code and code == language():
            return
        self.settings.setValue("app/language", code)
        if code == language():
            return
        self._notify("info", "PDF Compare",
                     "Reinicie o programa para usar o novo idioma."
                     if code == "pt" else "Restart the program to use the new language.")

    # ======================================================================
    # Pasta, recentes e sessões
    # ======================================================================
    def open_folder_dialog(self) -> None:
        start_dir = str(self.settings.value("files/last_dir", ""))
        folder = QFileDialog.getExistingDirectory(self, tr("Abrir os PDFs de uma pasta"), start_dir)
        if folder:
            self.settings.setValue("files/last_dir", folder)
            self.open_folder(folder)

    def open_folder(self, folder) -> None:
        pdfs = pdfs_in_folder(folder)
        if not pdfs:
            self._notify("info", tr("Nenhum PDF"), tr("Não há arquivos PDF em “{name}”.", name=Path(folder).name or folder))
            return
        self.add_files(pdfs)

    def recent_files(self) -> List[str]:
        value = self.settings.value("files/recent", [])
        if isinstance(value, str):
            return [value] if value else []
        return [str(v) for v in (value or [])]

    def _remember(self, path) -> None:
        self.settings.setValue("files/recent", add_recent(self.recent_files(), path))

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        items = existing_recent(self.recent_files())
        if not items:
            empty = self.recent_menu.addAction("(nenhum)")
            empty.setEnabled(False)
            return
        for path in items:
            label = Path(path).name + (tr("  (sessão)") if path.lower().endswith(SESSION_SUFFIX) else "")
            action = self.recent_menu.addAction(label)
            action.setToolTip(path)
            action.setStatusTip(path)
            action.triggered.connect(lambda _c=False, p=path: self.open_recent(p))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction(tr("Limpar lista"), lambda: self.settings.setValue("files/recent", []))

    def open_recent(self, path: str) -> None:
        if not Path(path).exists():
            self._notify("warning", tr("Arquivo não encontrado"), tr("“{path}” não existe mais.", path=path))
            return
        if path.lower().endswith(SESSION_SUFFIX):
            self.open_session(path)
        else:
            self.add_files([path])

    def save_session_dialog(self) -> None:
        if not self.sessions:
            return
        start = str(Path(str(self.settings.value("files/last_dir", ""))) / f"comparacao{SESSION_SUFFIX}")
        path, _ = QFileDialog.getSaveFileName(self, tr("Salvar sessão"), start,
                                              tr("Sessão do PDF Compare (*{suffix})", suffix=SESSION_SUFFIX))
        if path:
            self.save_session_to(path)

    def save_session_to(self, path) -> Optional[Path]:
        data = SessionData([SessionFile(s.path, s.offset) for s in self.sessions], self.nav.current, self.zoom_mode)
        try:
            saved = save_session(path, data)
        except SessionError as exc:
            self._notify("warning", tr("Sessão não salva"), str(exc))
            return None
        self._remember(saved)
        self.statusBar().showMessage(tr("Sessão salva em “{name}”.", name=saved.name), 4000)
        return saved

    def open_session_dialog(self) -> None:
        start_dir = str(self.settings.value("files/last_dir", ""))
        path, _ = QFileDialog.getOpenFileName(self, tr("Abrir sessão"), start_dir,
                                              tr("Sessão do PDF Compare (*{suffix})", suffix=SESSION_SUFFIX))
        if path:
            self.open_session(path)

    def open_session(self, path) -> None:
        try:
            data, missing = load_session(path)
        except SessionError as exc:
            self._notify("warning", tr("Sessão não aberta"), str(exc))
            return
        self.close_all()
        self.add_files([f.path for f in data.files])
        offsets = {str(f.path.resolve()): f.offset for f in data.files}
        for session in self.sessions:
            session.offset = offsets.get(str(session.path.resolve()), 0)
        self.nav.set_sessions(self.sessions, keep_position=True)
        self.nav.go_to(data.current)
        if data.zoom is not None:
            zoom = self._parse_zoom(data.zoom)
            if zoom is not None:
                self.set_zoom(zoom)
        self.run_search()
        self.update_diff()
        self._remember(path)
        if missing:
            self._notify("warning", tr("Arquivos não encontrados"),
                         tr("Estes PDFs da sessão não foram encontrados:\n") + "\n".join(missing))

    # ======================================================================
    # Anotações
    # ======================================================================
    def toggle_tool(self, tool: str) -> None:
        self.set_tool(TOOL_NONE if self.tool == tool else tool)

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        for kind, action in self.tool_actions.items():
            action.setChecked(kind == tool)
        for pane in self.panes:
            pane.set_tool(tool)
        if tool == TOOL_HIGHLIGHT:
            self.statusBar().showMessage(tr("Destacar: arraste sobre o texto. Ctrl+H de novo para sair."), 5000)
        elif tool == TOOL_NOTE:
            self.statusBar().showMessage(tr("Nota: clique no ponto da página. Ctrl+M de novo para sair."), 5000)
        elif tool == am.STAMP:
            self.statusBar().showMessage(tr("Carimbo “{stamp}”: clique na página. Esc para sair.", stamp=self.stamp), 5000)
        elif tool != TOOL_NONE:
            tip = next((t for k, _, t in mark_tools() if k == tool), "")
            self.statusBar().showMessage(tip + "  ·  " + tr("Esc para sair."), 5000)

    def choose_stamp(self, text: str) -> None:
        self.stamp = text
        self.set_tool(am.STAMP)

    def choose_custom_stamp(self) -> None:
        text, ok = QInputDialog.getText(self, tr("Carimbo"), tr("Texto do carimbo:"), QLineEdit.EchoMode.Normal,
                                        self.stamp)
        if ok and text.strip():
            self.choose_stamp(text.strip()[:40])

    def set_mark_style(self, style: MarkStyle) -> None:
        """Estilo das próximas marcações; também é aplicado à marcação selecionada."""
        self.mark_style = style
        self.prefs.set_mark_style(style)
        for pane in self.panes:
            pane.mark_style = style
        selected = self.selected_annotation()
        if selected is not None:
            self._replace_mark(self._selection[0], self._styled_copy(selected, style))

    def _styled_copy(self, a: Annotation, style: MarkStyle) -> Annotation:
        out = a.copy()
        if a.kind == HIGHLIGHT:
            out.color = style.highlight
        elif a.kind != NOTE:
            out.color = style.color
        if a.kind in am.FILLABLE:
            out.fill = style.fill if style.fill is not None or a.kind not in (am.TEXTBOX, am.CALLOUT) else a.fill
        out.width = style.width
        out.opacity = style.opacity
        if a.kind in am.TEXT_KINDS:
            out.font_size = style.font_size
        return out

    def _new_mark(self, kind: str, page: int, rects, **extra) -> Annotation:
        st = self.mark_style
        color = st.highlight if kind == HIGHLIGHT else (None if kind == NOTE else st.color)
        return Annotation(kind, page, list(rects), color=color, width=st.width, opacity=st.opacity,
                          font_size=st.font_size, **extra)

    def annotation_key(self, index: int) -> Optional[str]:
        session = self.sessions[index]
        if session.uid not in self._annot_keys:
            try:
                self._annot_keys[session.uid] = file_fingerprint(session.path)
            except OSError:
                self._annot_keys[session.uid] = None
        return self._annot_keys[session.uid]

    def document_annotations(self, index: int) -> List[Annotation]:
        key = self.annotation_key(index)
        return self.annotations.load(key) if key else []

    def page_annotations(self, index: int, page: Optional[int]) -> List[Annotation]:
        return for_page(self.document_annotations(index), page) if page is not None else []

    def find_annotation(self, index: int, annotation_id: str) -> Optional[Annotation]:
        return next((a for a in self.document_annotations(index) if a.id == annotation_id), None)

    def selected_annotation(self) -> Optional[Annotation]:
        if self._selection is None or self._selection[0] >= len(self.sessions):
            return None
        return self.find_annotation(*self._selection)

    # --- alterações com desfazer -------------------------------------------------------
    def _mutate(self, index: int, change: Callable[[str, str], object]) -> bool:
        """Executa `change(key, nome)` guardando o estado anterior para desfazer."""
        key = self.annotation_key(index)
        if key is None:
            self._notify("warning", tr("Anotação não salva"), tr("Não foi possível ler o arquivo para guardar a anotação."))
            return False
        name = self.sessions[index].name
        before = self.annotations.snapshot(key)
        try:
            change(key, name)
        except OSError as exc:
            self.annotations.restore(key, before, name)
            self._notify("warning", tr("Anotação não salva"), tr("Não foi possível gravar a anotação: {error}", error=exc))
            return False
        self._user_busy()
        self._undo.append(UndoStep(key, name, before, self.annotations.snapshot(key)))
        del self._undo[:-200]
        self._redo.clear()
        self._after_marks_changed()
        return True

    def _after_marks_changed(self) -> None:
        if self._selection is not None and self.selected_annotation() is None:
            self._select(None)
        self.refresh()
        self._refresh_marks_panel()

    def _restore(self, step: UndoStep, items: List[Annotation]) -> None:
        try:
            self.annotations.restore(step.key, items, step.name)
        except OSError as exc:
            self._notify("warning", tr("Anotação não salva"), tr("Não foi possível gravar a anotação: {error}", error=exc))
        self._after_marks_changed()

    def undo(self) -> None:
        if self._undo:
            step = self._undo.pop()
            self._redo.append(step)
            self._restore(step, step.before)

    def redo(self) -> None:
        if self._redo:
            step = self._redo.pop()
            self._undo.append(step)
            self._restore(step, step.after)

    def add_annotation(self, index: int, annotation: Annotation) -> bool:
        return self._mutate(index, lambda key, name: self.annotations.add(key, annotation, name))

    def _replace_mark(self, index: int, annotation: Annotation) -> bool:
        return self._mutate(index, lambda key, name: self.annotations.update(key, annotation, name))

    # --- criação --------------------------------------------------------------------
    def _on_highlight(self, index: int, page: int, rect: tuple) -> None:
        self._on_markup(index, page, HIGHLIGHT, rect)

    def _on_markup(self, index: int, page: int, kind: str, rect: tuple) -> None:
        session = self.sessions[index]
        rects = words_in_rect(session.doc[page], rect)
        if not rects:
            if abs(rect[2] - rect[0]) < 4 or abs(rect[3] - rect[1]) < 4:
                self.statusBar().showMessage(tr("Arraste sobre o texto que deseja destacar."), 4000)
                return
            rects = [rect]   # área sem texto (imagem, PDF escaneado): marca a área
        self._last_pane = index
        self.add_annotation(index, self._new_mark(kind, page, rects))

    def _on_note(self, index: int, page: int, x: float, y: float) -> None:
        text = self._ask_note_text("")
        if text is None:
            return
        half = NOTE_SIZE / 2
        self._last_pane = index
        self.add_annotation(index, Annotation(NOTE, page, [note_rect(x - half, y - half)], text))

    def _on_shape(self, index: int, annotation: Annotation) -> None:
        if annotation.kind in (am.TEXTBOX, am.CALLOUT):
            text = self._ask_mark_text(kind_label(annotation.kind), "")
            if not text:
                return
            annotation.text = text
        self._last_pane = index
        if self.add_annotation(index, annotation):
            self._select((index, annotation.id))

    def _on_stamp(self, index: int, page: int, x: float, y: float) -> None:
        size = max(self.mark_style.font_size, STAMP_FONT)
        mark = self._new_mark(am.STAMP, page, [stamp_rect(x, y, self.stamp, size)], text=self.stamp)
        mark.font_size = size
        self._last_pane = index
        self.add_annotation(index, mark)

    def _ask_note_text(self, initial: str) -> Optional[str]:
        text, ok = QInputDialog.getMultiLineText(self, tr("Nota"), tr("Texto da nota:"), initial)
        return text if ok else None

    def _ask_mark_text(self, title: str, initial: str) -> Optional[str]:
        text, ok = QInputDialog.getMultiLineText(self, title, tr("Texto:"), initial)
        return text if ok else None

    # --- seleção, edição, área de transferência -------------------------------------------
    def _select(self, selection: Optional[Tuple[int, str]]) -> None:
        self._selection = selection
        for pane in self.panes:
            pane.set_selected(selection[1] if selection is not None and selection[0] == pane.index else "")
        if selection is not None:
            self._last_pane = selection[0]
        self._update_ui_state()

    def _on_selection(self, index: int, annotation_id: str) -> None:
        self._last_pane = index
        self._select((index, annotation_id) if annotation_id else None)

    def _on_mark_changed(self, index: int, annotation: Annotation) -> None:
        self._replace_mark(index, annotation)

    def copy_selected(self) -> None:
        selected = self.selected_annotation()
        if selected is not None:
            self._clipboard = selected.copy()
            self._clipboard_source = (self._selection[0], selected.page)
            self.statusBar().showMessage(tr("Marcação copiada. Ctrl+V cola na página à vista."), 3000)
            self._update_ui_state()

    def paste_mark(self, index: Optional[int] = None) -> None:
        if self._clipboard is None or not self.sessions:
            return
        index = self._last_pane if index is None else index
        index = min(max(index, 0), len(self.sessions) - 1)
        page = self.nav.page_for(index)
        if page is None:
            self.statusBar().showMessage(tr("Este painel não tem página nesta posição."), 4000)
            return
        mark = self._clipboard.copy(new_id=True)
        mark.page = page
        if self._clipboard_source == (index, page):
            mark = am.moved(mark, 12, 12)
            self._clipboard = am.moved(self._clipboard, 12, 12)
        if self.add_annotation(index, mark):
            self._select((index, mark.id))

    def delete_selected(self) -> None:
        if self._selection is not None:
            index, annotation_id = self._selection
            self.remove_annotation(index, annotation_id)

    def escape(self) -> None:
        if any([pane.cancel_drawing() for pane in self.panes]):
            return
        if self._selection is not None:
            self._select(None)
        elif self.tool != TOOL_NONE:
            self.set_tool(TOOL_NONE)

    def _on_annotation_menu(self, index: int, page: int, x: float, y: float, global_pos: QPoint) -> None:
        found = find_at(self.document_annotations(index), page, x, y)
        if found is None:
            return
        self._select((index, found.id))
        menu = QMenu(self)
        if found.kind == NOTE:
            edit = menu.addAction(tr("Editar texto da nota…"))
        elif found.kind in am.TEXT_KINDS:
            edit = menu.addAction(tr("Editar texto…"))
        else:
            edit = menu.addAction(tr("Adicionar comentário…"))
        restyle = menu.addAction(tr("Aplicar o estilo atual"))
        copy_action = menu.addAction(tr("Copiar"))
        menu.addSeparator()
        remove = menu.addAction(tr("Remover anotação"))
        chosen = menu.exec(global_pos)
        if chosen is edit:
            self.edit_annotation(index, found.id)
        elif chosen is restyle:
            self._replace_mark(index, self._styled_copy(found, self.mark_style))
        elif chosen is copy_action:
            self.copy_selected()
        elif chosen is remove:
            self.remove_annotation(index, found.id)

    def edit_annotation(self, index: int, annotation_id: str) -> None:
        current = self.find_annotation(index, annotation_id)
        if self.annotation_key(index) is None or current is None:
            return
        if current.kind in am.TEXT_KINDS:
            text = self._ask_mark_text(kind_label(current.kind), current.text)
            if current.kind == am.STAMP and text:
                text = " ".join(text.split())[:40]
        else:
            text = self._ask_note_text(current.text)
        if text is None or (current.kind in am.TEXT_KINDS and not text.strip()) or text == current.text:
            return
        edited = current.copy()
        edited.text = text
        if current.kind == am.STAMP:   # o carimbo acompanha o tamanho do texto
            b = current.rects[0]
            edited.rects = [stamp_rect((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, text, current.font_size)]
        self._replace_mark(index, edited)

    def remove_annotation(self, index: int, annotation_id: str) -> None:
        if self.find_annotation(index, annotation_id) is not None:
            self._mutate(index, lambda key, name: self.annotations.remove(key, annotation_id, name))

    # --- lista de marcações ----------------------------------------------------------------
    def _refresh_marks_panel(self) -> None:
        self.marks_panel.set_documents([(s.name, list(self.document_annotations(i)))
                                        for i, s in enumerate(self.sessions)])

    def go_to_mark(self, index: int, annotation_id: str) -> None:
        mark = self.find_annotation(index, annotation_id)
        if mark is None:
            return
        if self.nav.page_for(index) != mark.page:
            self.nav.show_page(index, mark.page)
            self.refresh()
        self._select((index, annotation_id))

    # --- Configurações -------------------------------------------------------------------
    def open_settings(self) -> None:
        from app.ui.settings_dialog import SettingsDialog, SettingsValues

        tessdata = ocr.find_tessdata()
        langs = ", ".join(ocr.installed_languages(tessdata)) or tr("nenhum (Tesseract não encontrado)")
        values = SettingsValues(str(self.settings.value("app/language", language())), self.ocr_language(),
                                self.prefs.diff_colors(), self.mark_style, self.compare)
        dialog = SettingsDialog(values, tr("Idiomas instalados: {langs}. Use + para combinar (ex.: eng+por).",
                                           langs=langs), self,
                                cache_info=self.cache_summary, clear_cache=self.clear_diff_cache)
        if dialog.exec():
            self.apply_settings(dialog.values())

    def apply_settings(self, values) -> None:
        if values.ocr_language != self.ocr_language():
            self.set_ocr_language(values.ocr_language)
        self.prefs.set_diff_colors(values.diff_colors)
        set_diff_colors(values.diff_colors)
        self.mark_style = values.mark_style
        self.prefs.set_mark_style(values.mark_style)
        self.style_bar.set_style(values.mark_style)
        for pane in self.panes:
            pane.mark_style = values.mark_style
            pane.invalidate()
        self.set_compare_settings(values.compare)
        self.refresh()
        if values.language != str(self.settings.value("app/language", language())):
            self.set_ui_language(values.language)

    def set_compare_settings(self, compare: CompareSettings) -> None:
        old = self.compare
        self.compare = compare
        self.prefs.set_compare_settings(compare)
        if compare.cache_days != old.cache_days:
            self.diff_cache.purge(compare.cache_days)
        if compare.batch_size != old.batch_size:
            self._batch_signature = None        # novo tamanho de lote: replaneja
            self._realign_pending = False
        if compare.next_mode != NEXT_AUTO and old.next_mode == NEXT_AUTO:
            self.runner.cancel_background()
        if self.act_diff.isChecked():
            self.update_diff()

    def cache_summary(self) -> str:
        return tr("{n} resultado(s) salvos · {size}", n=self.diff_cache.count(),
                  size=format_size(self.diff_cache.size_bytes()))

    def clear_diff_cache(self) -> None:
        self.diff_cache.clear()

    # ======================================================================
    # Comparação de texto
    # ======================================================================
    def toggle_diff(self) -> None:
        self._jump_to_first_diff = self.act_diff.isChecked()
        self.update_diff()
        if self.act_diff.isChecked() and self.nav.total_diffs:
            self._jump_to_first_diff = False
            self.next_diff_all(+1)

    def _diff_signature(self, indexes) -> tuple:
        offsets = tuple(s.offset for s in self.sessions)
        return (tuple(s.uid for s in self.sessions), tuple(id(i) for i in indexes),
                self.compare.batch_size, offsets, self.indexer.ocr_enabled, self.indexer.ocr_language)

    def update_diff(self) -> None:
        """(Re)planeja a comparação em lotes e pede os lotes necessários."""
        if not self.act_diff.isChecked() or len(self.sessions) < 2:
            self.runner.reset()
            self._batch_signature = None
            self._realign_timer.stop()
            self._realign_pending = False
            self.nav.clear_diffs()
            self.diff_label.hide()
            self.batch_bar.hide()
            self.refresh()
            return
        indexes = [self.indexer.index_for(s) for s in self.sessions]
        keys = [self.annotation_key(i) for i in range(len(self.sessions))]
        if any(i is None for i in indexes) or any(k is None for k in keys):
            self.nav.clear_diffs()
            self._update_batch_status()
            return
        signature = self._diff_signature(indexes)
        if self._batch_signature is not None and not self._adopt_offsets:
            # ir à próxima diferença/ocorrência também move os PDFs, mas não muda o plano
            signature = signature[:3] + self._batch_signature[3:4] + signature[4:]
        self._adopt_offsets = False
        if not self._same_plan(signature):
            ref_offset = self.sessions[0].offset
            offsets = [ref_offset - s.offset for s in self.sessions]   # página do PDF i = página da referência + isto
            options = f"ocr={int(self.indexer.ocr_enabled)}:{self.indexer.ocr_language}"
            self.runner.configure(indexes, keys, offsets, self.compare.batch_size, options)
            self._batch_signature = signature
            self.nav.clear_diffs()
            if self.compare.next_mode != NEXT_AUTO and self.runner.batches:
                self.runner.request(self._batch_at_view())   # no modo "ao clicar", só o lote à vista
        self._ensure_batches()
        self._update_batch_status()
        self.refresh()

    def _same_plan(self, signature: tuple) -> bool:
        old = self._batch_signature
        if old is None:
            return False
        if len(self.runner.batches) <= 1:   # um lote só: o alinhamento não muda o que é comparado
            return old[:3] == signature[:3] and old[4:] == signature[4:]
        return old == signature

    def _batch_at_view(self) -> int:
        if not self.runner.batches or not self.sessions:
            return 0
        ref = self.sessions[0]
        page = min(max(self.nav.raw_page(0), 0), max(ref.page_count - 1, 0))
        return batch_for_page(self.runner.batches, page)

    def _ensure_batches(self) -> None:
        """Pede o lote à vista e, no modo automático, os seguintes em segundo plano."""
        batches = self.runner.batches
        if not batches:
            return
        if self._alignment_touched:
            self._alignment_touched = False
            if len(batches) > 1:
                self._realign_timer.start()   # espera o usuário terminar de ajustar
        current = self._batch_at_view()
        moved = current != self._current_batch
        self._current_batch = current
        if self.compare.next_mode == NEXT_AUTO or len(batches) == 1:
            self.runner.request(current, priority=True)
            ahead = len(batches) if self.compare.lookahead == LOOKAHEAD_ALL else self.compare.lookahead
            for k in range(current + 1, min(current + 1 + ahead, len(batches))):
                self.runner.request(k, priority=False)
        if moved:
            self._update_batch_status()

    REALIGN_DELAY_MS = 1000

    def _plan_offsets_differ(self) -> bool:
        if self._batch_signature is None:
            return False
        return tuple(s.offset for s in self.sessions) != self._batch_signature[3]

    def _alignment_settled(self) -> None:
        """O usuário parou de ajustar o alinhamento: recompara ou oferece "Recomparar"."""
        if not self.act_diff.isChecked() or len(self.runner.batches) <= 1:
            return
        if not self._plan_offsets_differ():
            self._realign_pending = False     # voltou ao alinhamento da comparação atual
        elif self.compare.realign_mode == REALIGN_AUTO:
            self.recompare()
            return
        else:
            self._realign_pending = True
            self.statusBar().showMessage(tr("O alinhamento mudou. Clique em “Recomparar” para refazer os lotes "
                                            "com o novo alinhamento."), 6000)
        self._update_batch_status()

    def recompare(self) -> None:
        """Refaz o plano de lotes com o alinhamento atual (os lotes iguais vêm do cache)."""
        self._realign_timer.stop()
        self._realign_pending = False
        if not self.act_diff.isChecked():
            return
        self._adopt_offsets = True
        self.update_diff()

    def compare_next_batch(self) -> None:
        """Compara o lote à vista (se ainda não foi) ou o próximo, e vai até ele."""
        if not self.runner.batches:
            return
        current = self._batch_at_view()
        if not self.runner.is_done(current) and not self.runner.is_pending(current):
            self.runner.request(current, priority=True)
        elif current + 1 < len(self.runner.batches):
            self.runner.request(current + 1, priority=True)
            self.go_to_batch(current + 1)
        self._update_batch_status()

    def go_previous_batch(self) -> None:
        current = self._batch_at_view()
        if current > 0:
            self.go_to_batch(current - 1)

    def go_to_batch(self, number: int) -> None:
        if not (0 <= number < len(self.runner.batches)):
            return
        start = self.runner.batches[number].ref_range[0]
        self.nav.go_to(start + self.sessions[0].offset)
        self.refresh()
        self._update_batch_status()

    def cancel_batches(self) -> None:
        self.runner.cancel()
        self.statusBar().showMessage(tr("Comparação cancelada. Os lotes já comparados continuam valendo."), 4000)
        self._update_batch_status()

    def _user_busy(self) -> None:
        if self.compare.pause_while_busy and self.runner.background_pending():
            self.runner.pause_for(1.5)

    def _on_batches_changed(self) -> None:
        self.nav.set_diffs(self.runner.marks())
        if self._jump_to_first_diff and self.nav.total_diffs:
            self._jump_to_first_diff = False
            self.nav.step_diff_all(+1)
        self._update_batch_status()
        self.refresh()

    def _on_batch_progress(self, done: int, total: int) -> None:
        self.batch_progress.setVisible(total > 0)
        self.batch_cancel_btn.setVisible(total > 0)
        if total > 0:
            self.batch_progress.setMaximum(total)
            self.batch_progress.setValue(done)
        self._update_batch_status()

    def _update_batch_status(self) -> None:
        on = self.act_diff.isChecked() and len(self.sessions) >= 2
        batches = self.runner.batches
        multi = on and len(batches) > 1
        current = self._batch_at_view() if batches else 0
        self.batch_bar.setVisible(multi or (on and self.runner.busy))
        self.hint_label.setVisible(not self.batch_bar.isVisibleTo(self))   # dá espaço à barra de lotes
        self.batch_label.setVisible(multi)
        self.batch_prev_btn.setVisible(multi)
        self.batch_next_btn.setVisible(multi)
        busy = self.runner.busy
        self.batch_progress.setVisible(busy)
        self.batch_cancel_btn.setVisible(busy)
        if multi:
            first, last = batches[current].label_pages()
            label = tr("Lote {n} de {total} · páginas {first}–{last}", n=current + 1,
                       total=len(batches), first=first, last=last)
            if not self.runner.is_done(current):
                label += " · " + tr("comparando…") if self.runner.is_pending(current) else " · " + tr("não comparado")
            self.batch_label.setText(label)
            self.batch_label.setToolTip(tr("{done} de {total} lotes comparados", done=self.runner.done_count(),
                                           total=len(batches)))
            pending_here = not self.runner.is_done(current)
            this_one = pending_here and not self.runner.is_pending(current)
            self.act_batch_next.setText(tr("Comparar este lote") if this_one else tr("Comparar próximo lote ▶"))
            self.batch_next_btn.setText(tr("Comparar este lote") if this_one else tr("Próximo lote ▶"))
            self.act_batch_next.setEnabled(this_one or current + 1 < len(batches))
            self.act_batch_prev.setEnabled(current > 0)
        else:
            self.act_batch_next.setEnabled(False)
            self.act_batch_prev.setEnabled(False)
        self.recompare_btn.setVisible(multi and self._realign_pending)
        self.act_recompare.setEnabled(multi and self._plan_offsets_differ())
        if multi and self._realign_pending:
            self.batch_label.setText(self.batch_label.text() + " · " + tr("alinhamento mudou"))
        self.batch_next_btn.setEnabled(self.act_batch_next.isEnabled())
        self.batch_prev_btn.setEnabled(self.act_batch_prev.isEnabled())
        if not on:
            return
        done = self.runner.done_count()
        if done == 0:
            if self.runner.busy:
                text = tr("Comparando texto… aguardando a leitura dos PDFs") if self.indexer.busy \
                    else tr("Comparando texto…")
            else:
                text = tr("Lote ainda não comparado — use “Comparar este lote” (F8)")
            self.diff_label.setText(text)
        else:
            self.diff_label.setText(self.diff_summary())
        self.diff_label.setToolTip(tr("Incluído · removido · alterado, em relação ao primeiro PDF "
                                      "(cores em Ferramentas › Configurações). F7 vai para a próxima diferença."))
        self.diff_label.show()

    def diff_summary(self) -> str:
        if self.nav.total_diffs == 0:
            return tr("Texto idêntico ao do 1º PDF")
        parts = []
        for i, session in enumerate(self.sessions[1:], start=1):
            c = count_by_kind(self.nav.diffs[i])
            parts.append(f"{session.name}: +{c[ADDED]} −{c[REMOVED]} ~{c[CHANGED]}")
        return tr("Diferenças em relação a {name} — {parts}", name=self.sessions[0].name, parts=" · ".join(parts))

    def next_diff_all(self, delta: int) -> None:
        if self.nav.step_diff_all(delta):
            self.refresh()
        elif self.act_diff.isChecked():
            self.statusBar().showMessage(tr("Nenhuma diferença de texto para navegar."), 3000)

    # ======================================================================
    # Exportação
    # ======================================================================
    def export_dialog(self) -> None:
        if not self.sessions:
            return
        has_annotations = any(self.document_annotations(i) for i in range(len(self.sessions)))
        dialog = ExportDialog(has_annotations, self)
        if dialog.exec() != ExportDialog.DialogCode.Accepted:
            return
        choice = dialog.choice()
        start_dir = str(self.settings.value("files/export_dir", self.settings.value("files/last_dir", "")))
        if choice.kind == SIDE_BY_SIDE:
            ext = choice.fmt
            name = "comparacao" if choice.scope == SCOPE_ALL else f"comparacao_posicao_{self.nav.current + 1}"
            target, _ = QFileDialog.getSaveFileName(self, tr("Exportar comparação"), str(Path(start_dir) / f"{name}.{ext}"),
                                                    f"{ext.upper()} (*.{ext})")
            if target and not target.lower().endswith(f".{ext}"):
                target += f".{ext}"
            folder = str(Path(target).parent) if target else ""
        else:
            target = QFileDialog.getExistingDirectory(self, tr("Pasta de destino"), start_dir)
            folder = target
        if not target:
            return
        self.settings.setValue("files/export_dir", folder)
        files = self.export(choice, target)
        if files:
            where = files[0].parent
            self.statusBar().showMessage(_plural(len(files), "{n} arquivo exportado", "{n} arquivos exportados") + tr(" em {folder}", folder=where), 6000)

    def export(self, choice: ExportChoice, target) -> List[Path]:
        """Executa a exportação (sem diálogos). Devolve os arquivos criados."""
        columns = [Column(s.doc, s.name, self.document_annotations(i) if choice.with_annotations else [])
                   for i, s in enumerate(self.sessions)]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if choice.kind == SIDE_BY_SIDE:
                if choice.scope == SCOPE_ALL:
                    rows = [[s.page_at(pos) for s in self.sessions] for pos in range(self.nav.first, self.nav.last + 1)]
                else:
                    rows = [[self.nav.page_for(i) for i in range(len(self.sessions))]]
                return export_comparison(columns, rows, target, choice.fmt, dpi=choice.dpi)
            if choice.kind == CURRENT_PAGES:
                pages = [self.nav.page_for(i) for i in range(len(self.sessions))]
                return export_current_pages(columns, pages, target, choice.fmt, dpi=choice.dpi)
            if choice.kind == ANNOTATED:
                return self._export_annotated(Path(target))
            return []
        except (ExportError, OSError, RuntimeError, ValueError) as exc:
            self._notify("warning", tr("Exportação não concluída"), str(exc))
            return []
        finally:
            QApplication.restoreOverrideCursor()

    def _export_annotated(self, folder: Path) -> List[Path]:
        folder.mkdir(parents=True, exist_ok=True)
        written: List[Path] = []
        for i, session in enumerate(self.sessions):
            target = folder / f"{safe_stem(session.name)}_anotado.pdf"
            k = 2
            while target.resolve() == session.path.resolve() or target in written:
                target = folder / f"{safe_stem(session.name)}_anotado_{k}.pdf"
                k += 1
            save_annotated_pdf(session.doc, self.document_annotations(i), target)
            written.append(target)
        return written

    # ======================================================================
    # OCR
    # ======================================================================
    def ocr_language(self) -> str:
        return str(self.settings.value("ocr/language", ocr.DEFAULT_LANGUAGE)) or ocr.DEFAULT_LANGUAGE

    def _restore_ocr(self) -> None:
        if not self._bool_setting("ocr/enabled", False):
            return
        status = ocr.check(self.ocr_language())
        if status.available:
            self.act_ocr.setChecked(True)
            self.indexer.set_ocr(True, self.ocr_language(), status.tessdata)
        else:
            self.statusBar().showMessage(tr("OCR desativado: Tesseract OCR não encontrado."), 8000)

    def toggle_ocr(self) -> None:
        if not self.act_ocr.isChecked():
            self.indexer.set_ocr(False)
            self.settings.setValue("ocr/enabled", False)
            return
        status = ocr.check(self.ocr_language())
        if not status.available:
            self.act_ocr.setChecked(False)
            self._notify("warning", tr("OCR indisponível"), status.message)
            return
        self.settings.setValue("ocr/enabled", True)
        self.indexer.set_ocr(True, self.ocr_language(), status.tessdata)
        self._reindex()
        self.statusBar().showMessage(tr("OCR ligado: páginas escaneadas serão reconhecidas (pode levar alguns segundos por página)."), 6000)

    def choose_ocr_language(self) -> None:
        tessdata = ocr.find_tessdata()
        langs = ", ".join(ocr.installed_languages(tessdata)) or tr("nenhum (Tesseract não encontrado)")
        text, ok = QInputDialog.getText(
            self, tr("Idioma do OCR"),
            tr("Código do idioma do Tesseract (ex.: eng, por, eng+por).\nInstalados: {langs}", langs=langs),
            QLineEdit.EchoMode.Normal, self.ocr_language())
        if ok and text.strip():
            self.set_ocr_language(text.strip())

    def set_ocr_language(self, language: str) -> None:
        self.settings.setValue("ocr/language", language)
        if self.act_ocr.isChecked():
            status = ocr.check(language)
            if not status.available:
                self.act_ocr.setChecked(False)
                self.indexer.set_ocr(False)
                self.settings.setValue("ocr/enabled", False)
                self._notify("warning", tr("OCR indisponível"), status.message)
                return
            self.indexer.set_ocr(True, language, status.tessdata)
            self._reindex()

    def _reindex(self) -> None:
        for session in self.sessions:
            self.indexer.add(session)
        self.run_search()
        self.update_diff()

    def _on_ocr_failed(self, message: str) -> None:
        self.act_ocr.setChecked(False)
        self.settings.setValue("ocr/enabled", False)
        self._notify("warning", tr("OCR desativado"), f"{message}\n\n{ocr.install_help()}")

    def _hint_scanned(self, session: DocumentSession) -> None:
        if self.indexer.ocr_enabled or session.doc is None:
            return
        index = self.indexer.index_for(session)
        if index is None or any(index.pages):
            return
        try:
            scanned = ocr.page_needs_ocr(session.doc[0])
        except Exception:
            scanned = False
        if scanned:
            self.statusBar().showMessage(
                tr("“{name}” parece escaneado (sem texto). Ative Ferramentas › OCR para pesquisar nele.", name=session.name), 10000)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("view/results_panel", self.results_dock.isVisible())
        self.settings.setValue("view/marks_panel", self.marks_dock.isVisible())
        self.settings.setValue("view/mark_toolbar", self.mark_toolbar.isVisible())
        self._save_view_settings()
        self.runner.shutdown()
        self.indexer.clear()
        for session in self.sessions:
            session.close()
        super().closeEvent(event)
