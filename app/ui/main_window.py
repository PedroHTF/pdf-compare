"""Janela principal: menus, barras de ferramentas, grade de PDFs, pesquisa,
anotações, comparação de texto, exportação, sessões e OCR."""

from __future__ import annotations

from app.i18n import LANGUAGES, language, tr

import os

import fitz
from pathlib import Path
from collections import OrderedDict
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
from app.services.compare_scope import (
    IgnoredPagesStore,
    format_pages,
    page_geometry,
    parse_pages,
    scoped_index,
)
from app.services.content_align import (
    AlignmentStore,
    PairMatch,
    align_pages,
    build_rows,
    combined_anchors,
    document_lines,
    match_lines,
    rows_key,
)
from app.services.report import PairReport, make_report, write_report
from app.services.strip_layout import StripLayout, compute_layouts
from app.services.updates import ReleaseInfo, due, fetch_latest, is_newer
from app.services.visual_diff import VISUAL, page_difference
from app.services.diff_batches import ALL_PAGES, Batch, DiffCache, batch_for_page, format_size, plan_batches_from_rows
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
from app.services.text_diff import ADDED, CHANGED, REMOVED, DiffMark, count_by_kind, report_entries
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
        self.align_store = AlignmentStore(self.data_dir / "alinhamentos")
        self._matches: Dict[tuple, PairMatch] = {}   # comparação de linhas por par de PDFs (em memória)
        self.ignored_pages = IgnoredPagesStore(self.data_dir / "paginas_ignoradas.json")
        self._scoped: Dict[tuple, object] = {}       # índices sem cabeçalho/rodapé/páginas ignoradas
        self._geometry: Dict[int, list] = {}         # geometria das páginas por PDF (uid)
        self._page_only_pages: Optional[tuple] = None   # páginas comparadas em "só a página atual"
        self._align_version = 0                     # muda a cada ajuste manual (espaços, trechos)
        self._layouts_key: Optional[tuple] = None
        self._layouts: List[StripLayout] = []
        self._heights: Dict[int, List[float]] = {}  # alturas das páginas por PDF (uid)
        self._strip_position: Optional[int] = None  # posição já mostrada na rolagem contínua
        self._pick: Optional[Tuple[int, int, float]] = None   # 1º ponto de "Alinhar este trecho com…"
        self._region_pick: Optional[tuple] = None   # 1º trecho de "Alinhar seleções": (painel, início, fim)
        self._visual_cache: "OrderedDict[tuple, tuple]" = OrderedDict()   # diferença visual por par de páginas
        self.reference_uid: Optional[int] = None   # PDF de referência (None = o primeiro)
        self.chain_mode = False                    # cada PDF comparado com o anterior
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
        self._init_updates()

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
        self.act_report = self._action(tr("&Relatório de diferenças…"), self.export_report, ["Ctrl+Shift+R"],
                                       tr("Salvar a lista de mudanças entre os PDFs (página, texto antes e depois) "
                                          "em PDF, HTML ou CSV"))
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
        self.act_content_align = self._action(
            tr("Alinhar por &conteúdo"), self.toggle_content_align, ["Ctrl+Shift+L"],
            tr("Mostrar lado a lado as páginas com o mesmo conteúdo, compensando páginas incluídas ou removidas"),
            checkable=True)
        self.act_content_align.setIconText(tr("Alinhar por conteúdo"))
        self.act_content_align.setChecked(self._bool_setting("view/content_align", False))
        self.act_realign = self._action(tr("Realinhar"), self.realign, ["Ctrl+L"],
                                        tr("Desfazer ajustes individuais: todos voltam a mostrar a mesma página"),
                                        S.SP_BrowserReload)
        self._realign_tip = self.act_realign.toolTip()
        self.act_align_regions = self._action(
            tr("Alinhar &seleções"), self.toggle_align_regions, ["Ctrl+Shift+A"],
            tr("Arraste sobre um trecho em um PDF e depois sobre o trecho correspondente em outro: "
               "os dois ficam alinhados na rolagem contínua"), checkable=True)
        self.act_align_regions.setIconText(tr("Alinhar seleções"))
        self.act_unlock_gaps = self._action(tr("Destravar todos os espaços"), self.unlock_all_gaps, [],
                                            tr("Os espaços travados voltam a poder ser ajustados e "
                                               "“Realinhar” passa a desfazê-los"))

        self.act_find = self._action(tr("&Pesquisar"), self.focus_search, ["Ctrl+F"], tr("Pesquisar em todos os PDFs"))
        self.act_hit_next = self._action(tr("Próxima ocorrência"), lambda: self.next_hit_all(+1), ["F3"],
                                         tr("Ir para a próxima ocorrência em cada PDF"))
        self.act_hit_prev = self._action(tr("Ocorrência anterior"), lambda: self.next_hit_all(-1), ["Shift+F3"],
                                         tr("Ir para a ocorrência anterior em cada PDF"))

        self.act_diff = self._action(tr("Comparar &texto"), self.toggle_diff, ["Ctrl+D"],
                                     tr("Destacar as diferenças de texto em relação à referência"),
                                     checkable=True)
        self.act_diff_whole = self._action(tr("Comparar o documento inteiro"), lambda: self.set_page_only(False),
                                           [], tr("Comparar todas as páginas (em lotes, conforme as Configurações)"),
                                           checkable=True)
        self.act_diff_page = self._action(tr("Comparar só a página atual"), lambda: self.set_page_only(True),
                                          [], tr("Comparar apenas as páginas à vista; a comparação acompanha "
                                                 "quando você muda de página"), checkable=True)
        from PySide6.QtGui import QActionGroup

        self._diff_scope_group = QActionGroup(self)
        for action in (self.act_diff_whole, self.act_diff_page):
            self._diff_scope_group.addAction(action)
        self.act_diff_page.setChecked(self.compare.page_only)
        self.act_diff_whole.setChecked(not self.compare.page_only)
        self.act_ignore_pages = self._action(tr("Páginas &ignoradas na comparação…"), self.edit_ignored_pages, [],
                                             tr("Escolher páginas de cada PDF que ficam fora da comparação "
                                                "(ex.: capa, índice)"))
        self.act_visual_diff = self._action(
            tr("Diferença &visual"), self.toggle_visual_diff, ["Ctrl+Shift+V"],
            tr("Destacar áreas com aparência diferente, pixel a pixel (imagens, assinaturas, carimbos, "
               "páginas escaneadas). Funciona com ou sem a comparação de texto."), checkable=True)
        self.act_visual_diff.setIconText(tr("Visual"))
        self.act_visual_diff.setChecked(self._bool_setting("view/visual_diff", False))
        self.act_diff_next = self._action(tr("Próxima diferença"), lambda: self.next_diff_all(+1), ["F7"],
                                          tr("Ir para a próxima diferença de texto em cada PDF"))
        self.act_diff_prev = self._action(tr("Diferença anterior"), lambda: self.next_diff_all(-1), ["Shift+F7"],
                                          tr("Ir para a diferença de texto anterior em cada PDF"))
        self.act_batch_next = self._action(tr("Comparar próximo lote"), self.compare_next_batch, ["F8"],
                                           tr("Comparar o próximo lote de páginas e ir até ele"))
        self.act_chain = self._action(tr("Em &cadeia (cada PDF com o anterior)"), self.set_chain_mode, [],
                                      tr("Comparar o 2º PDF com o 1º, o 3º com o 2º, e assim por diante"),
                                      checkable=True)
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
        self.act_continuous = self._action(
            tr("Rolagem &contínua"), self.toggle_continuous, ["Ctrl+Shift+C"],
            tr("Mostrar todas as páginas em sequência, em vez de uma de cada vez"), checkable=True)
        self.act_continuous.setIconText(tr("Contínua"))
        self.act_continuous.setChecked(self._bool_setting("view/continuous", False))
        self.act_wheel_flip = self._action(
            tr("Rolar para a &próxima página"), self._save_wheel_flip, [],
            tr("Uma página por vez: rolar além do fim da página abre a seguinte (e além do início, a anterior)"),
            checkable=True)
        self.act_wheel_flip.setChecked(self._bool_setting("view/wheel_flip", True))

        self.act_shortcuts = self._action(tr("&Atalhos de teclado"), self.show_shortcuts, ["F1"])
        self.act_license = self._action(tr("&Licença e créditos…"), self.show_license,
                                        tip=tr("O que você pode fazer com este programa e licenças dos componentes"))
        self.act_about = self._action(tr("&Sobre"), self.show_about)
        self.act_check_updates = self._action(tr("&Verificar atualizações agora"),
                                              lambda: self.check_updates(manual=True), [],
                                              tr("Consultar no GitHub se há uma versão mais nova do PDF Compare"))

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
        m.addAction(self.act_report)
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
        m.addAction(self.act_content_align)
        m.addAction(self.act_align_regions)
        m.addAction(self.act_unlock_gaps)
        m.addSeparator()
        m.addActions([self.act_find, self.act_hit_next, self.act_hit_prev])
        m.addSeparator()
        m.addActions([self.act_diff_next, self.act_diff_prev])
        m.addActions([self.act_batch_next, self.act_batch_prev, self.act_recompare])

        m = bar.addMenu(tr("&Exibir"))
        m.addActions([self.act_fit_width, self.act_fit_page, self.act_zoom_in, self.act_zoom_out])
        m.addSeparator()
        m.addAction(self.act_linked_scroll)
        m.addAction(self.act_continuous)
        m.addAction(self.act_wheel_flip)
        self.view_menu = m

        m = bar.addMenu(tr("&Ferramentas"))
        marks = m.addMenu(tr("&Marcações"))
        marks.addAction(self.act_select)
        marks.addSeparator()
        marks.addActions([self.tool_actions[k] for k in MARK_KINDS])
        marks.addAction(self.act_stamp)
        m.addSeparator()
        m.addAction(self.act_diff)
        self.diff_scope_menu = m.addMenu(tr("Abrangência da &comparação"))
        self.diff_scope_menu.addActions([self.act_diff_whole, self.act_diff_page])
        m.addAction(self.act_ignore_pages)
        m.addAction(self.act_visual_diff)
        self.reference_menu = m.addMenu(tr("&Referência da comparação"))
        self.reference_menu.aboutToShow.connect(self._fill_reference_menu)
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
        m.addActions([self.act_shortcuts, self.act_license])
        m.addSeparator()
        m.addAction(self.act_check_updates)
        m.addAction(self.act_about)

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
        tb.addAction(self.act_content_align)
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
        tb.addAction(self.act_continuous)
        tb.addSeparator()
        tb.addAction(self.act_diff)
        from PySide6.QtWidgets import QToolButton

        diff_button = tb.widgetForAction(self.act_diff)
        if isinstance(diff_button, QToolButton):   # ▾ ao lado: documento inteiro / só a página atual
            diff_button.setMenu(self.diff_scope_menu)
            diff_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        tb.addAction(self.act_visual_diff)
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
        self.statusBar().addPermanentWidget(self.batch_bar)

    def _create_status_bar(self) -> None:
        self._hint_text = ""
        self.hint_label = QLabel()
        self.hint_label.setObjectName("muted")
        self.statusBar().addWidget(self.hint_label, 1)
        self.diff_label = QLabel()
        self.diff_label.setObjectName("diffSummary")
        self.diff_label.hide()
        self.statusBar().addPermanentWidget(self.diff_label)
        self.visual_label = QLabel()
        self.visual_label.setObjectName("diffSummary")
        self.visual_label.hide()
        self.statusBar().addPermanentWidget(self.visual_label)
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
            pane.visual_provider = lambda page, i=i: self.visual_marks(i, page)
            pane.strip_scrolled.connect(self._on_strip_scrolled)
            pane.gap_resized.connect(self._on_gap_resized)
            pane.point_picked.connect(self._on_point_picked)
            pane.region_picked.connect(self._on_region_picked)
            pane.relayout_requested.connect(self._on_relayout)
            pane.page_flip.connect(self._on_page_flip)
            pane.scope_provider = lambda page, i=i: self.scope_marks(i, page)
            pane.wheel_flip = self.act_wheel_flip.isChecked()
            pane.set_view_mode(self.act_continuous.isChecked())
            pane.mark_style = self.mark_style
            pane.scroll.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            pane.set_tool(self.tool)
            pane.region_mode = self.act_align_regions.isChecked()
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
        self._strip_position = None
        self._layouts_key = None
        self._pick = None
        self._region_pick = None
        if self.reference_uid is not None and all(s.uid != self.reference_uid for s in self.sessions):
            self.reference_uid = None      # a referência foi fechada: volta a ser o 1º PDF
        self._update_roles()
        self.update_alignment()
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
        if self.sessions and self.nav.by_rows:
            primary = self.reference_index()
            for j in range(len(self.sessions)):
                if self._align_key(primary, j):
                    self.align_store.clear(self._align_key(primary, j))
            self._align_version += 1
            self._strip_position = None
            self.update_alignment()
            self.refresh()
            if self._has_locked_gaps():
                self.statusBar().showMessage(tr("Ajustes manuais do alinhamento desfeitos (os espaços travados "
                                                "foram mantidos)."), 4000)
            else:
                self.statusBar().showMessage(tr("Ajustes manuais do alinhamento desfeitos."), 3000)
            return
        if self.sessions:
            self.nav.realign()
            self.refresh()
            self.statusBar().showMessage(tr("Todos os PDFs realinhados na mesma página."), 3000)

    def _on_pane_step(self, index: int, delta: int) -> None:
        self._user_busy()
        if self.act_continuous.isChecked() and self.nav.by_rows:
            page = self.panes[index].top_page() if index < len(self.panes) else None
            self._continuous_go(index, (page or 0) + delta)
            return
        self._alignment_touched = True
        self._strip_position = None
        if self.nav.by_rows:
            self.nudge_alignment(index, delta=delta)
            return
        self.nav.step_pane(index, delta)
        self.refresh()

    def _on_pane_jump(self, index: int, page: int) -> None:
        self._user_busy()
        if self.act_continuous.isChecked() and self.nav.by_rows:
            self._continuous_go(index, page)
            return
        self._alignment_touched = True
        self._strip_position = None
        if self.nav.by_rows:
            self.nudge_alignment(index, target=page)
            return
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
        if (self.act_diff.isChecked() and self.compare.page_only and len(self.sessions) >= 2
                and self._shown_pages() != self._page_only_pages):
            self.update_diff()        # mudou de página: compara as novas (update_diff chama refresh)
            return
        if self.act_diff.isChecked() and self.runner.batches:
            self._ensure_batches()
        if self.act_continuous.isChecked() and self.panes:
            self._refresh_continuous(active)
            return
        selected = self.selected_annotation()
        if self._selection is not None and (selected is None or self.nav.page_for(self._selection[0]) != selected.page):
            self._selection = None   # a marcação selecionada saiu de vista
            for pane in self.panes:
                pane.selected_id = ""
        visual_total = 0
        for i, pane in enumerate(self.panes):
            page = self.nav.page_for(i)
            current = self.nav.current_hit(i)
            if current is not None and current.page != page:
                current = None   # o usuário saiu da página da ocorrência
            diff = self.nav.current_diff(i)
            if diff is not None and diff.page != page:
                diff = None
            blank = ""
            if page is None and self.nav.by_rows:
                blank = tr("Sem página correspondente neste PDF.\nO conteúdo dos outros PDFs nesta posição "
                           "foi incluído neles ou removido deste.")
            visual = self.visual_marks(i, page)
            visual_total += len(visual)
            pane.render(page, self.nav.raw_page(i), self.nav.page_hits(i, page), current, self.zoom_mode,
                        self.nav.page_diffs(i, page), diff, self.page_annotations(i, page), blank, visual)
            position = self.nav.hit_index[i] if current is not None else -1
            pane.set_hit_status(active, self.nav.hit_count(i), position)
        self._update_visual_label(visual_total)
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
            self.update_alignment()
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
        self._strip_position = None   # rolagem contínua: volta à posição atual na nova escala
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
        self.act_visual_diff.setEnabled(n >= 2)
        self.act_report.setEnabled(n >= 2)
        has_diffs = n >= 2 and self.act_diff.isChecked() and self.nav.total_diffs > 0
        self.act_diff_next.setEnabled(has_diffs)
        self.act_diff_prev.setEnabled(has_diffs)
        self.act_open_folder.setEnabled(n < MAX_DOCUMENTS)
        self.act_add.setEnabled(n < MAX_DOCUMENTS)
        self.act_prev.setEnabled(has and not self.nav.at_start)
        self.act_first.setEnabled(has and not self.nav.at_start)
        self.act_next.setEnabled(has and not self.nav.at_end)
        self.act_last.setEnabled(has and not self.nav.at_end)
        self.act_align_regions.setEnabled(n >= 2)
        if self.act_align_regions.isChecked() and (n < 2 or not self.act_continuous.isChecked()
                                                   or not self.act_content_align.isChecked()):
            self._set_region_mode(False)
        self.act_unlock_gaps.setEnabled(has and self._has_locked_gaps())
        if self.nav.by_rows:
            self.act_realign.setEnabled(has and self._has_manual_alignment())
            self.act_realign.setToolTip(tr("Desfazer os ajustes manuais do alinhamento por conteúdo (Ctrl+L)"))
        else:
            self.act_realign.setEnabled(has and not self.nav.is_aligned)
            self.act_realign.setToolTip(self._realign_tip)
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
        elif self.act_continuous.isChecked() and self.nav.by_rows:
            hint = tr("Role qualquer PDF: os outros acompanham  ·  botão direito: inserir, remover ou travar "
                      "espaço  ·  Ctrl+Shift+A: alinhar seleções  ·  arraste a alça de um espaço para ajustar")
        elif self.nav.by_rows:
            hint = tr("◀ ▶ ou setas do teclado: avançam todos juntos  ·  ◀ ▶ de um painel: escolhem qual "
                      "página dele fica ao lado da referência")
        else:
            hint = (tr("◀ ▶ ou setas do teclado: avançam todos juntos  ·  "
                    "botões de cada painel: ajustam só aquele PDF  ·  Ctrl+F: pesquisar em todos"))
        self._hint_text = hint
        self.hint_label.setText("" if self.batch_bar.isVisibleTo(self) else hint)

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
            ("Ctrl+Shift+L", tr("Alinhar por conteúdo")),
            ("Ctrl+Shift+A", tr("Alinhar seleções: arraste sobre um trecho em cada PDF")),
            ("Ctrl+Shift+C", tr("Rolagem contínua")),
            ("Ctrl+Shift+V", tr("Diferença visual")),
            ("Ctrl+Shift+R", tr("Relatório de diferenças")),
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

    # ======================================================================
    # Aviso de nova versão
    # ======================================================================
    def _init_updates(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        self.fetch_release = fetch_latest          # substituído nos testes
        self._update_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdfcompare-updates")
        self._update_future = None
        self._update_manual = False
        self.available_release: Optional[ReleaseInfo] = None
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(200)
        self._update_timer.timeout.connect(self._poll_update)
        self._create_update_bar()
        if not os.environ.get("PDFCOMPARE_NO_UPDATE_CHECK"):
            QTimer.singleShot(4000, self._auto_check_updates)   # depois de abrir, sem atrasar a janela

    def _create_update_bar(self) -> None:
        from PySide6.QtWidgets import QHBoxLayout, QToolButton

        self.update_bar = QWidget()
        self.update_bar.setObjectName("updateBar")
        row = QHBoxLayout(self.update_bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.update_label = QLabel()
        self.update_label.setObjectName("updateLabel")
        self.update_download_btn = QToolButton()
        self.update_download_btn.setText(tr("Baixar"))
        self.update_download_btn.setToolTip(tr("Abrir a página da nova versão no navegador (downloads e novidades)"))
        self.update_download_btn.clicked.connect(self.open_release_page)
        self.update_skip_btn = QToolButton()
        self.update_skip_btn.setText(tr("Ignorar esta versão"))
        self.update_skip_btn.clicked.connect(self.skip_release)
        self.update_close_btn = QToolButton()
        self.update_close_btn.setText("✕")
        self.update_close_btn.setToolTip(tr("Esconder até a próxima vez que o programa abrir"))
        self.update_close_btn.clicked.connect(lambda: self.update_bar.hide())
        for w in (self.update_label, self.update_download_btn, self.update_skip_btn, self.update_close_btn):
            row.addWidget(w)
        self.update_bar.hide()
        self.statusBar().addPermanentWidget(self.update_bar)

    def updates_enabled(self) -> bool:
        return self._bool_setting("updates/check", True)

    def _auto_check_updates(self) -> None:
        try:
            last = float(self.settings.value("updates/last_check", 0) or 0)
        except (TypeError, ValueError):
            last = 0.0
        if self.updates_enabled() and due(last):
            self.check_updates(manual=False)

    def check_updates(self, manual: bool = False) -> None:
        """Consulta a última versão em segundo plano (manual: também avisa se já está atualizado)."""
        self._update_manual = self._update_manual or manual
        if self._update_future is not None:
            return
        if manual:
            self.statusBar().showMessage(tr("Verificando atualizações…"), 3000)
        self._update_future = self._update_executor.submit(self.fetch_release)
        self._update_timer.start()

    def _poll_update(self) -> None:
        future = self._update_future
        if future is None or not future.done():
            return
        self._update_timer.stop()
        self._update_future = None
        manual, self._update_manual = self._update_manual, False
        try:
            release = future.result()
        except Exception:
            release = None
        import time as _time

        self.settings.setValue("updates/last_check", _time.time())
        self.on_release_info(release, manual)

    def on_release_info(self, release: Optional[ReleaseInfo], manual: bool) -> None:
        from app import __version__

        if release is None:
            if manual:
                self._notify("warning", tr("Verificar atualizações"),
                             tr("Não foi possível consultar o GitHub agora. Verifique a conexão e tente de novo."))
            return
        if not is_newer(release.version, __version__):
            self.available_release = None
            self.update_bar.hide()
            if manual:
                self._notify("info", tr("Verificar atualizações"),
                             tr("Você já tem a versão mais recente ({version}).", version=__version__))
            return
        self.available_release = release
        skipped = str(self.settings.value("updates/skip", "")) == release.version
        if skipped and not manual:
            return
        self.update_label.setText(tr("PDF Compare {version} disponível", version=release.version))
        self.update_label.setToolTip(release.notes[:600] or release.url)
        self.update_bar.show()
        if manual:
            box = QMessageBox(self)
            box.setWindowTitle(tr("Nova versão disponível"))
            box.setText(tr("O PDF Compare {new} está disponível (você tem a {current}).",
                           new=release.version, current=__version__))
            box.setInformativeText(tr("A página da versão tem o instalador, a versão portátil e as novidades."))
            open_button = box.addButton(tr("Abrir página da versão"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(tr("Agora não"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is open_button:
                self.open_release_page()

    def open_release_page(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if self.available_release is not None:
            QDesktopServices.openUrl(QUrl(self.available_release.url))

    def skip_release(self) -> None:
        if self.available_release is not None:
            self.settings.setValue("updates/skip", self.available_release.version)
            self.statusBar().showMessage(tr("Você não será avisado da versão {version} de novo. Ajuda › "
                                            "Verificar atualizações agora continua mostrando.",
                                            version=self.available_release.version), 6000)
        self.update_bar.hide()

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
        if tool != TOOL_NONE and self.act_align_regions.isChecked():
            self._set_region_mode(False)
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
        if self._pick is not None:
            self._end_pick(tr("Alinhamento de trecho cancelado."))
            return
        if any([pane.cancel_region() for pane in self.panes]):
            return
        if self._region_pick is not None:
            self._region_pick = None
            self._refresh_region_marks()
            self.statusBar().showMessage(tr("Seleção cancelada. Arraste sobre um trecho para começar de novo."), 4000)
            return
        if self.act_align_regions.isChecked():
            self._set_region_mode(False)
            return
        if any([pane.cancel_drawing() for pane in self.panes]):
            return
        if self._selection is not None:
            self._select(None)
        elif self.tool != TOOL_NONE:
            self.set_tool(TOOL_NONE)

    def _on_annotation_menu(self, index: int, page: int, x: float, y: float, global_pos: QPoint) -> None:
        found = find_at(self.document_annotations(index), page, x, y)
        if found is None:
            self._pane_menu(index, global_pos, page, y)
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
                                self.prefs.diff_colors(), self.mark_style, self.compare, self.updates_enabled())
        dialog = SettingsDialog(values, tr("Idiomas instalados: {langs}. Use + para combinar (ex.: eng+por).",
                                           langs=langs), self,
                                cache_info=self.cache_summary, clear_cache=self.clear_diff_cache)
        if dialog.exec():
            self.apply_settings(dialog.values())

    def apply_settings(self, values) -> None:
        self.settings.setValue("updates/check", bool(getattr(values, "check_updates", True)))
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
        if compare.visual_sensitivity != old.visual_sensitivity:
            self._visual_cache.clear()
            for pane in self.panes:
                pane.invalidate()
                pane.canvas.invalidate()
        if compare.batch_size != old.batch_size:
            self._batch_signature = None        # novo tamanho de lote: replaneja
            self._realign_pending = False
        if compare.next_mode != NEXT_AUTO and old.next_mode == NEXT_AUTO:
            self.runner.cancel_background()
        self.act_diff_page.setChecked(compare.page_only)
        self.act_diff_whole.setChecked(not compare.page_only)
        if compare.scope != old.scope:
            self._after_scope_change()
            return
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
        offsets = self._alignment_key()
        return (tuple(s.uid for s in self.sessions), tuple(id(i) for i in indexes),
                self.compare.batch_size, offsets, self.indexer.ocr_enabled, self.indexer.ocr_language,
                self.chain_mode, self.reference_index(), self.compare.scope.key(),
                tuple(self._ignored(i) for i in range(len(self.sessions))), repr(self._sync_points()),
                self._shown_pages() if self.compare.page_only else None)

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
        indexes = [self.compare_index(i) for i in range(len(self.sessions))]
        keys = [self._compare_fingerprint(i) for i in range(len(self.sessions))]
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
            primary = self.reference_index()
            ref_offset = self.sessions[primary].offset
            offsets = [ref_offset - s.offset for s in self.sessions]   # página do PDF i = página da principal + isto
            options = f"ocr={int(self.indexer.ocr_enabled)}:{self.indexer.ocr_language}"
            if self.compare.scope.active:
                options += ":" + self.compare.scope.key()
            plan = None
            self._page_only_pages = None
            if self.compare.page_only:
                self._page_only_pages = self._shown_pages()
                plan = [Batch(0, tuple((p, p + 1) if p is not None else (0, 0) for p in self._page_only_pages),
                              primary)]
            elif self.nav.by_rows:
                plan = plan_batches_from_rows(self.nav.rows, [s.page_count for s in self.sessions],
                                              self.compare.batch_size, primary)
            self.runner.configure(indexes, keys, offsets, self.compare.batch_size, options,
                                  pairs=self.comparison_pairs(), primary=primary, batches=plan,
                                  sync=self._sync_points())
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
        primary = self.reference_index()
        ref = self.sessions[primary]
        page = min(max(self.nav.raw_page(primary), 0), max(ref.page_count - 1, 0))
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

    def _alignment_key(self) -> tuple:
        """O que define as páginas de cada lote: os deslocamentos ou o alinhamento por conteúdo."""
        if self.nav.by_rows:
            return ("rows", rows_key(self.nav.rows))
        return tuple(s.offset for s in self.sessions)

    def _plan_offsets_differ(self) -> bool:
        if self._batch_signature is None:
            return False
        return self._alignment_key() != self._batch_signature[3]

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
        primary = self.reference_index()
        if self.nav.by_rows:
            self.nav.go_to(self.nav.row_of(primary, start) or 0)
        else:
            self.nav.go_to(start + self.sessions[primary].offset)
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
        # dá espaço à barra de lotes (sem mostrar a dica por cima de uma mensagem temporária)
        self.hint_label.setText("" if self.batch_bar.isVisibleTo(self) else self._hint_text)
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
        ref = self.reference_index()
        if self.nav.total_diffs == 0:
            if self.chain_mode:
                return tr("Texto idêntico em todos os PDFs") + self._scope_suffix()
            return tr("Texto idêntico ao da referência ({name})", name=self.sessions[ref].name) + self._scope_suffix()
        parts = []
        for a, b in self.comparison_pairs():
            c = count_by_kind(self.nav.diffs[b])
            parts.append(f"{self.sessions[b].name}: +{c[ADDED]} −{c[REMOVED]} ~{c[CHANGED]}")
        if self.chain_mode:
            text = tr("Em cadeia (cada PDF com o anterior) — {parts}", parts=" · ".join(parts))
        else:
            text = tr("Diferenças em relação a {name} — {parts}", name=self.sessions[ref].name, parts=" · ".join(parts))
        return text + self._scope_suffix()

    # --- o que entra na comparação -------------------------------------------------------
    def _ignored(self, index: int) -> frozenset:
        return self.ignored_pages.pages(self.annotation_key(index))

    def _geometry_for(self, index: int) -> list:
        session = self.sessions[index]
        if session.uid not in self._geometry and session.doc is not None:
            self._geometry[session.uid] = page_geometry(session.doc)
        return self._geometry.get(session.uid, [])

    def compare_index(self, index: int):
        """Texto do PDF como a comparação e o alinhamento o veem (sem o que o usuário ignorou)."""
        session = self.sessions[index]
        base = self.indexer.index_for(session)
        scope, ignored = self.compare.scope, self._ignored(index)
        if base is None or (not scope.active and not ignored):
            return base
        key = (session.uid, id(base), scope, ignored)
        if key not in self._scoped:
            if len(self._scoped) > 40:
                self._scoped.clear()
            geometry = self._geometry_for(index) if scope.active else []
            self._scoped[key] = scoped_index(base, scope, geometry, ignored)
        return self._scoped[key]

    def _compare_fingerprint(self, index: int) -> Optional[str]:
        """Identifica o PDF no cache da comparação (muda se mudam as páginas ignoradas)."""
        key = self.annotation_key(index)
        ignored = self._ignored(index)
        return f"{key}|ign={format_pages(ignored)}" if key and ignored else key

    def _sync_points(self) -> Dict[Tuple[int, int], list]:
        """Pontos alinhados à mão que a comparação segue: trechos, linhas e páginas fixadas."""
        if not self.compare.follow_alignment or self.chain_mode or not self.act_content_align.isChecked():
            return {}
        primary = self.reference_index()
        out = {}
        for j in range(len(self.sessions)):
            key = self._gap_key(j) if j != primary else None
            if not key:
                continue
            points = list(self.align_store.forced_anchors(key))
            points += [(pa, 0.0, pb, 0.0) for pa, pb in self.align_store.manual_pages(key)]
            if points:
                out[(primary, j)] = sorted(set(points))
        return out

    def _shown_pages(self) -> tuple:
        return tuple(self.nav.page_for(i) for i in range(len(self.sessions)))

    def _scope_suffix(self) -> str:
        parts = []
        if self.compare.page_only:
            parts.append(tr("só a página atual"))
        scope = self.compare.scope
        if scope.header and scope.footer:
            parts.append(tr("sem cabeçalho e rodapé"))
        elif scope.header:
            parts.append(tr("sem cabeçalho"))
        elif scope.footer:
            parts.append(tr("sem rodapé"))
        ignored = sum(len(self._ignored(i)) for i in range(len(self.sessions)))
        if ignored:
            parts.append(_plural(ignored, "{n} página ignorada", "{n} páginas ignoradas"))
        return "".join(" · " + p for p in parts)

    def _in_scope(self, index: int, page: int, rect) -> bool:
        scope = self.compare.scope
        if not scope.active:
            return True
        geometry = self._geometry_for(index)
        if page >= len(geometry):
            return True
        matrix, height = geometry[page]
        top, bottom = scope.band(height)
        x0, y0, x1, y1 = rect
        y = (fitz.Point((x0 + x1) / 2, (y0 + y1) / 2) * fitz.Matrix(*matrix)).y
        return top <= y <= bottom

    def scope_marks(self, index: int, page: int):
        """O que desenhar como "fora da comparação" na página: (ignorada, % cabeçalho, % rodapé) ou None."""
        if len(self.sessions) < 2 or not (self.act_diff.isChecked() or self.act_visual_diff.isChecked()
                                          or self.act_content_align.isChecked()):
            return None
        ignored = index < len(self.sessions) and page in self._ignored(index)
        scope = self.compare.scope
        if not ignored and not scope.active:
            return None
        return (ignored, scope.header, scope.footer)

    def _after_scope_change(self, message: str = "") -> None:
        """Mudou o que entra na comparação: refaz o alinhamento, a comparação e o desenho."""
        self._align_version += 1
        self._layouts_key = None
        self._batch_signature = None
        for pane in self.panes:
            pane.invalidate()
            pane.canvas.invalidate()
        self.update_alignment()
        if self.act_diff.isChecked():
            self.update_diff()
        else:
            self.refresh()
        if message:
            self.statusBar().showMessage(message, 5000)

    def toggle_ignored_page(self, index: int, page: int) -> None:
        key = self.annotation_key(index)
        if not key:
            return
        now = self.ignored_pages.toggle(key, page)
        self._after_scope_change(
            tr("Página {page} de {name} ignorada na comparação.", page=page + 1, name=self.sessions[index].name)
            if now else tr("Página {page} de {name} voltou a ser comparada.", page=page + 1,
                           name=self.sessions[index].name))

    def edit_ignored_pages(self) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout

        if not self.sessions:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Páginas ignoradas na comparação"))
        form = QFormLayout(dialog)
        intro = QLabel(tr("Páginas de cada PDF que ficam fora da comparação de texto, do relatório e do "
                          "alinhamento por conteúdo (ex.: capa, índice). Exemplo: 1-3, 7"))
        intro.setWordWrap(True)
        form.addRow(intro)
        edits = []
        for i, session in enumerate(self.sessions):
            edit = QLineEdit(format_pages(self._ignored(i)))
            edit.setPlaceholderText(tr("nenhuma"))
            edit.setEnabled(bool(self.annotation_key(i)))
            form.addRow(tr("{name} ({n} págs.)", name=session.name, n=session.page_count), edit)
            edits.append(edit)
        error = QLabel()
        error.setObjectName("error")
        error.setStyleSheet("color: #c0392b")
        form.addRow(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        parsed: Dict[int, set] = {}

        def accept() -> None:
            parsed.clear()
            for i, edit in enumerate(edits):
                try:
                    parsed[i] = parse_pages(edit.text(), self.sessions[i].page_count)
                except ValueError as exc:
                    error.setText(tr("Páginas inválidas em {name}: “{part}”", name=self.sessions[i].name,
                                     part=str(exc)))
                    edit.setFocus()
                    return
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        self._ignored_dialog = dialog          # (testes)
        self._ignored_edits = edits
        if not dialog.exec():
            return
        changed = False
        for i, pages in parsed.items():
            key = self.annotation_key(i)
            if key and frozenset(pages) != self._ignored(i):
                self.ignored_pages.set_pages(key, pages)
                changed = True
        if changed:
            self._after_scope_change(tr("Páginas ignoradas atualizadas."))

    def set_page_only(self, on: bool) -> None:
        if on == self.compare.page_only:
            return
        from dataclasses import replace

        self.compare = replace(self.compare, page_only=on)
        self.prefs.set_compare_settings(self.compare)
        self.act_diff_page.setChecked(on)
        self.act_diff_whole.setChecked(not on)
        self._batch_signature = None
        if not self.act_diff.isChecked() and len(self.sessions) >= 2:
            self.act_diff.setChecked(True)      # escolher a abrangência já liga a comparação
            self.toggle_diff()
        else:
            self.update_diff()
        self.statusBar().showMessage(tr("Comparando só a página atual: a comparação acompanha a navegação.")
                                     if on else tr("Comparando o documento inteiro."), 5000)

    # --- uma página por vez: rolar para a próxima ------------------------------------------
    def _save_wheel_flip(self) -> None:
        on = self.act_wheel_flip.isChecked()
        self.settings.setValue("view/wheel_flip", on)
        for pane in self.panes:
            pane.wheel_flip = on

    def _on_page_flip(self, index: int, delta: int) -> None:
        """Rolou além da borda da página: vai para a seguinte (todos juntos, se a rolagem é vinculada)."""
        linked = self.act_linked_scroll.isChecked()
        for pane in self.panes:
            if linked or pane.index == index:
                pane.land_at_bottom = delta < 0
        if linked:
            self.step(delta)
        else:
            self._on_pane_step(index, delta)

    # --- alinhamento por conteúdo -------------------------------------------------------
    def _align_key(self, a: int, b: int) -> Optional[str]:
        fa, fb = self.annotation_key(a), self.annotation_key(b)
        return AlignmentStore.key(fa, fb) if fa and fb else None

    def _has_manual_alignment(self) -> bool:
        primary = self.reference_index()
        return any(self.align_store.has_manual(k) for j in range(len(self.sessions))
                   if (k := self._align_key(primary, j)))

    def _pair_match(self, a: int, b: int) -> Optional[PairMatch]:
        ia, ib = self.compare_index(a), self.compare_index(b)
        if ia is None or ib is None or not ia.complete or not ib.complete:
            return None
        key = (self._compare_fingerprint(a), self._compare_fingerprint(b), self.indexer.ocr_enabled,
               self.indexer.ocr_language, self.compare.scope.key())
        if key not in self._matches:
            if len(self._matches) > 30:
                self._matches.clear()
            self._matches[key] = match_lines(ia, ib)
        return self._matches[key]

    def toggle_content_align(self) -> None:
        self.settings.setValue("view/content_align", self.act_content_align.isChecked())
        self.update_alignment(announce=True)
        self.refresh()

    def update_alignment(self, announce: bool = False) -> None:
        """Liga, desliga ou recalcula o alinhamento por conteúdo (páginas lado a lado)."""
        primary = self.reference_index()
        if not self.act_content_align.isChecked() or len(self.sessions) < 2:
            if self.nav.by_rows:
                self.nav.set_rows(None, follow=primary)
            return
        pairs = {}
        for j in range(len(self.sessions)):
            if j == primary:
                continue
            match = self._pair_match(primary, j)
            key = self._align_key(primary, j)
            if match is None or key is None:
                if announce:
                    self.statusBar().showMessage(tr("Alinhando por conteúdo… aguardando a leitura dos PDFs."), 4000)
                return   # tenta de novo quando a leitura terminar
            pairs[j] = align_pages(match, self.align_store.manual_pages(key))
        rows = build_rows([s.page_count for s in self.sessions], primary, pairs)
        if rows != self.nav.rows:
            self.nav.set_rows(rows, follow=primary)
        if announce:
            extra = sum(1 for row in rows if row[primary] is None)
            missing = sum(1 for row in rows if row[primary] is not None and None in row)
            self.statusBar().showMessage(
                tr("Alinhado por conteúdo: {extra} posição(ões) com páginas incluídas e {missing} com páginas "
                   "removidas em relação a {name}.", extra=extra, missing=missing, name=self.sessions[primary].name),
                6000)

    def nudge_alignment(self, index: int, delta: int = 0, target: Optional[int] = None) -> None:
        """◀ ▶ ou página digitada em um painel, com o alinhamento por conteúdo ligado.

        Fixa à mão qual página deste PDF fica ao lado da página atual da referência.
        """
        primary = self.reference_index()
        rows = self.nav.rows
        if not rows:
            return
        ref_page = self.nav.page_for(primary)
        if ref_page is None:   # posição sem página da referência: usa a próxima (ou a anterior)
            ref_page = next((row[primary] for row in rows[self.nav.current:] if row[primary] is not None),
                            max(self.nav.raw_page(primary), 0))
        if index == primary:
            new_ref = ref_page + delta if target is None else target
            new_ref = max(0, min(new_ref, self.sessions[primary].page_count - 1))
            for j in range(len(self.sessions)):
                shown = self.nav.page_for(j) if j != primary else None
                key = self._align_key(primary, j) if j != primary else None
                if key and shown is not None:
                    self.align_store.fix_pages(key, new_ref, shown)
            ref_page, other_page = new_ref, None
        else:
            current = self.nav.page_for(index)
            base = current if current is not None else self.nav.raw_page(index)
            other_page = base + delta if target is None else target
            other_page = max(0, min(other_page, self.sessions[index].page_count - 1))
            key = self._align_key(primary, index)
            if key:
                self.align_store.fix_pages(key, ref_page, other_page)
        self.update_alignment()
        row = self.nav.row_of(primary, ref_page)
        if row is not None:
            self.nav.go_to(row)
        self.refresh()
        if other_page is not None:
            self.statusBar().showMessage(
                tr("Página {page} de {name} fixada ao lado da página {ref} de {ref_name}. Realinhar desfaz.",
                   page=other_page + 1, name=self.sessions[index].name, ref=ref_page + 1,
                   ref_name=self.sessions[primary].name), 5000)

    # --- rolagem contínua --------------------------------------------------------------
    def toggle_continuous(self) -> None:
        on = self.act_continuous.isChecked()
        self.settings.setValue("view/continuous", on)
        self._end_pick()
        for pane in self.panes:
            pane.set_view_mode(on)
        self._strip_position = None
        self._layouts_key = None
        self.refresh()

    def _page_heights(self, index: int) -> List[float]:
        session = self.sessions[index]
        if session.uid not in self._heights:
            self._heights[session.uid] = self.panes[index].page_heights()
        return self._heights[session.uid]

    def _gap_key(self, index: int) -> Optional[str]:
        """Onde ficam os espaços manuais deste PDF (por par com a referência)."""
        return self._align_key(self.reference_index(), index)

    def strip_layouts(self) -> List[StripLayout]:
        primary = self.reference_index()
        scales = [round(p.continuous_scale(self.zoom_mode), 4) for p in self.panes]
        aligned = self.nav.by_rows
        key = (tuple(s.uid for s in self.sessions), tuple(scales), aligned, primary, self._align_version,
               rows_key(self.nav.rows) if aligned else "", self.indexer.ocr_enabled)
        if key == self._layouts_key:
            return self._layouts
        anchors, manual, forced = {}, {}, {}
        if aligned:
            for j in range(len(self.sessions)):
                gap_key = self._gap_key(j)
                if gap_key:
                    manual[j] = self.align_store.manual_gaps(gap_key)
                if j == primary:
                    continue
                match = self._pair_match(primary, j)
                if match is not None and gap_key:
                    forced[j] = self.align_store.forced_anchors(gap_key)
                    anchors[j] = combined_anchors(match, forced[j])
        heights = [self._page_heights(i) for i in range(len(self.sessions))]
        self._layouts = compute_layouts(heights, scales, primary, anchors, manual, aligned, forced)
        self._layouts_key = key
        return self._layouts

    def _refresh_continuous(self, active: bool) -> None:
        layouts = self.strip_layouts()
        focused = None
        self._refresh_region_marks(update=False)
        for i, pane in enumerate(self.panes):
            scrolled = pane.render_continuous(layouts[i], self.nav.hits[i], self.nav.current_hit(i),
                                              self.nav.diffs[i], self.nav.current_diff(i),
                                              self.document_annotations(i))
            if scrolled and focused is None:
                focused = i
            position = self.nav.hit_index[i] if self.nav.current_hit(i) is not None else -1
            pane.set_hit_status(active, self.nav.hit_count(i), position)
        self._update_visual_label(None)
        if focused is not None:
            if self.nav.by_rows and self.act_linked_scroll.isChecked():
                value = self.panes[focused].strip_value()
                for pane in self.panes:
                    if pane.index != focused:
                        pane.scroll_to_strip(value)
            self._strip_position = self.nav.current
        elif self._strip_position != self.nav.current:
            self._scroll_to_position(layouts)
            self._strip_position = self.nav.current
        self._update_ui_state()

    def _scroll_to_position(self, layouts: List[StripLayout]) -> None:
        if self.nav.by_rows and self.nav.rows:
            row = self.nav.rows[self.nav.current]
            primary = self.reference_index()
            doc = primary if row[primary] is not None else next((d for d, p in enumerate(row) if p is not None), None)
            if doc is None:
                return
            value = layouts[doc].page_top[row[doc]]
            for pane in self.panes:
                pane.scroll_to_strip(value)
            return
        for i, pane in enumerate(self.panes):
            page = self.nav.page_for(i)
            if page is not None:
                pane.scroll_to_strip(layouts[i].page_top[page])

    def _continuous_go(self, index: int, page: int) -> None:
        page = max(0, min(page, self.sessions[index].page_count - 1))
        row = self.nav.row_of(index, page)
        if row is not None:
            self.nav.go_to(row)
        self._strip_position = None
        self.refresh()

    def _on_strip_scrolled(self, index: int, value: float) -> None:
        """O usuário rolou um PDF na rolagem contínua: os outros acompanham."""
        self._user_busy()
        layouts = self._layouts
        if index >= len(layouts) or index >= len(self.panes):
            return
        if self.act_linked_scroll.isChecked():
            if self.nav.by_rows:   # alinhados: a mesma altura mostra o mesmo conteúdo
                for pane in self.panes:
                    if pane.index != index:
                        pane.scroll_to_strip(value)
            else:                  # sem alinhamento: mesma página (com os deslocamentos) e mesma fração
                page = layouts[index].page_at(value + 4)
                into = (value - layouts[index].page_top[page]) / max(layouts[index].scale, 1e-6)
                logical = page + self.sessions[index].offset
                for j, pane in enumerate(self.panes):
                    if j == index:
                        continue
                    pj = logical - self.sessions[j].offset
                    if 0 <= pj < self.sessions[j].page_count:
                        pane.scroll_to_strip(layouts[j].page_top[pj] + into * layouts[j].scale)
        page = self.panes[index].top_page()
        if page is not None:
            if self.nav.by_rows:
                row = self.nav.row_of(index, page)
                if row is not None:
                    self.nav.go_to(row)
            else:
                self.nav.go_to(page + self.sessions[index].offset)
            self._strip_position = self.nav.current
        if self.act_diff.isChecked() and self.runner.batches:
            self._ensure_batches()
            self._update_batch_status()
        self._update_ui_state()

    def _on_relayout(self, _index: int) -> None:
        """O painel mudou de tamanho (ajustar à largura): recalcula e volta à posição atual."""
        if self.act_continuous.isChecked():
            self._strip_position = None
            self.refresh()

    def _manual_gap_at(self, index: int, page: int, y: float) -> float:
        key = self._gap_key(index)
        entry = self.align_store.gap_entry(key, page, y) if key else None
        return entry[2] if entry else 0.0

    def _gap_scale(self, index: int) -> float:
        return max(self._layouts[index].scale if index < len(self._layouts) else 1.0, 1e-6)

    def _has_locked_gaps(self) -> bool:
        primary = self.reference_index()
        return any(self.align_store.has_locked(k) for j in range(len(self.sessions))
                   if (k := self._align_key(primary, j)))

    def _on_gap_resized(self, index: int, page: int, y: float, manual_points: float) -> None:
        key = self._gap_key(index)
        if key is None:
            return
        self.align_store.set_gap(key, page, y, manual_points)
        self._after_alignment_edit(tr("Espaço ajustado. Realinhar desfaz os ajustes manuais."))

    def insert_gap(self, index: int, page: int, y: float, points: float = 30.0) -> None:
        key = self._gap_key(index)
        if key is None:
            return
        self.align_store.set_gap(key, page, y, self._manual_gap_at(index, page, y) + points)
        self._after_alignment_edit(tr("Espaço inserido. Arraste a alça embaixo dele para ajustar a altura."))

    def remove_gap(self, index: int, gap, lock: bool = False) -> None:
        """Remove o espaço: ele some e o alinhamento não o recria logo abaixo."""
        key = self._gap_key(index)
        if key is None or gap is None:
            return
        self.align_store.remove_gap(key, gap.page, gap.y, locked=True if lock else None)
        if lock or gap.locked:
            message = tr("Espaço removido e travado: o alinhamento automático não o recria.")
        else:
            message = tr("Espaço removido. Realinhar desfaz os ajustes manuais.")
        self._after_alignment_edit(message)

    def lock_gap(self, index: int, gap, locked: bool = True) -> None:
        """Trava (ou destrava) o espaço com a altura que ele tem agora."""
        key = self._gap_key(index)
        if key is None or gap is None:
            return
        self.align_store.lock_gap(key, gap.page, gap.y, gap.height / self._gap_scale(index), locked)
        self._after_alignment_edit(
            tr("Espaço travado: o alinhamento automático não muda nem recria este espaço, e Realinhar o mantém.")
            if locked else tr("Espaço destravado."))

    def unlock_all_gaps(self) -> None:
        primary = self.reference_index()
        for j in range(len(self.sessions)):
            key = self._align_key(primary, j)
            if key:
                self.align_store.unlock_all(key)
        self._after_alignment_edit(tr("Todos os espaços foram destravados."))

    # --- alinhar seleções ----------------------------------------------------------------------
    def toggle_align_regions(self) -> None:
        self._set_region_mode(self.act_align_regions.isChecked(), announce=True)

    def _set_region_mode(self, on: bool, announce: bool = False) -> None:
        if on and len(self.sessions) < 2:
            on = False
        self.act_align_regions.setChecked(False)   # liga só depois da rolagem contínua e do alinhamento
        self._region_pick = None
        if on:
            self._end_pick()
            if self.tool != TOOL_NONE:
                self.set_tool(TOOL_NONE)
            if not self.act_content_align.isChecked():
                self.act_content_align.setChecked(True)
                self.toggle_content_align()
            if not self.act_continuous.isChecked():
                self.act_continuous.setChecked(True)
                self.toggle_continuous()
        self.act_align_regions.setChecked(on)
        for pane in self.panes:
            pane.region_mode = on
            pane.cancel_region()
        self._apply_region_cursor()
        self._refresh_region_marks()
        if announce:
            self.statusBar().showMessage(
                tr("Alinhar seleções: arraste sobre um trecho em um PDF e depois sobre o trecho "
                   "correspondente em outro. Esc para sair.") if on else tr("Alinhar seleções desligado."), 8000)

    def _apply_region_cursor(self) -> None:
        if self.act_align_regions.isChecked() and self._pick is None:
            for pane in self.panes:
                pane.canvas.setCursor(Qt.CursorShape.CrossCursor)

    def _snap_region(self, index: int, p0: int, y0: float, p1: int, y1: float):
        """Ajusta o trecho arrastado às linhas de texto que ele cobre: (início, fim), cada um (página, y)."""
        if (p1, y1) < (p0, y0):
            (p0, y0), (p1, y1) = (p1, y1), (p0, y0)
        index_doc = self.indexer.index_for(self.sessions[index])
        lines = document_lines(index_doc) if index_doc is not None and index_doc.complete else []
        chosen = [k for k, line in enumerate(lines) if (line.page, line.bottom) > (p0, y0)
                  and (line.page, line.y) < (p1, y1)]
        if not chosen:
            if p0 == p1 and y1 - y0 < 3:
                return (p0, y0), (p0, y0)
            return (p0, y0), (p1, y1)
        first, last = lines[chosen[0]], lines[chosen[-1]]
        nxt = lines[chosen[-1] + 1] if chosen[-1] + 1 < len(lines) else None
        if nxt is not None and nxt.page == last.page:
            end = (nxt.page, nxt.cut)
        else:
            height = self._page_heights(index)[last.page] if last.page < len(self._page_heights(index)) else last.bottom
            end = (last.page, min(last.bottom + 2.0, height))
        return (first.page, first.cut), end

    def _region_marks(self, index: int) -> list:
        primary = self.reference_index()
        marks = []
        if index == primary:
            for j in range(len(self.sessions)):
                key = self._gap_key(j) if j != primary else None
                for b in self.align_store.manual_blocks(key) if key else []:
                    marks.append((b[0], b[1], b[2], b[3], "block", (j, b)))
        else:
            key = self._gap_key(index)
            for b in self.align_store.manual_blocks(key) if key else []:
                marks.append((b[4], b[5], b[6], b[7], "block", (index, b)))
        if self._region_pick is not None and self._region_pick[0] == index:
            _, (sp, sy), (ep, ey) = self._region_pick
            marks.append((sp, sy, ep, ey, "pending", None))
        return marks

    def _refresh_region_marks(self, update: bool = True) -> None:
        for i, pane in enumerate(self.panes):
            pane.region_marks = self._region_marks(i) if self.act_continuous.isChecked() else []
            if update:
                pane.canvas.update()

    def _on_region_picked(self, index: int, p0: int, y0: float, p1: int, y1: float) -> None:
        start, end = self._snap_region(index, p0, y0, p1, y1)
        if self._region_pick is None or self._region_pick[0] == index:
            self._region_pick = (index, start, end)
            self._refresh_region_marks()
            self.statusBar().showMessage(tr("Trecho escolhido. Agora arraste sobre o trecho correspondente em "
                                            "outro PDF (Esc cancela)."), 10000)
            return
        first, s1, e1 = self._region_pick
        self._region_pick = None
        primary = self.reference_index()
        layouts = self.strip_layouts()

        def on_primary(doc: int, point: Tuple[int, float]) -> Tuple[int, float]:
            return layouts[primary].from_strip(layouts[doc].to_strip(*point))

        if first == primary:
            other, block = index, (s1, e1, start, end)
        elif index == primary:
            other, block = first, (start, end, s1, e1)
        else:   # dois PDFs que não são a referência: liga pelo trecho da referência ao lado do 2º
            other, block = first, (on_primary(index, start), on_primary(index, end), s1, e1)
        key = self._gap_key(other)
        if key is None:
            self._refresh_region_marks()
            return
        self.align_store.add_block(key, *block)
        self._after_alignment_edit(tr("Trechos alinhados: o início e o fim ficam na mesma altura. "
                                      "Botão direito na barra verde desfaz."))

    def remove_block(self, ref) -> None:
        doc, block = ref
        key = self._gap_key(doc)
        if key is None:
            return
        self.align_store.remove_block(key, block)
        self._after_alignment_edit(tr("Alinhamento do trecho desfeito."))

    def start_pick(self, index: int, page: int, y: float) -> None:
        self._pick = (index, page, y)
        for pane in self.panes:
            pane.pick_mode = pane.index != index
            pane.canvas.setCursor(Qt.CursorShape.CrossCursor if pane.pick_mode else Qt.CursorShape.ForbiddenCursor)
        self.statusBar().showMessage(tr("Agora clique no trecho correspondente em outro PDF (Esc cancela)."), 10000)

    def _end_pick(self, message: str = "") -> None:
        self._pick = None
        for pane in self.panes:
            pane.pick_mode = False
            pane.set_tool(self.tool)
        self._apply_region_cursor()
        if message:
            self.statusBar().showMessage(message, 4000)

    def _on_point_picked(self, index: int, page: int, y: float) -> None:
        if self._pick is None or index == self._pick[0]:
            return
        first, page_a, y_a = self._pick
        primary = self.reference_index()
        layouts = self.strip_layouts()

        def on_primary(doc: int, p: int, yy: float) -> Tuple[int, float]:
            if doc == primary:
                return p, yy
            return layouts[primary].from_strip(layouts[doc].to_strip(p, yy))

        if first == primary:
            other, anchor = index, (page_a, y_a, page, y)
        elif index == primary:
            other, anchor = first, (page, y, page_a, y_a)
        else:   # dois PDFs que não são a referência: liga pelo ponto da referência ao lado do 2º
            pp, py = on_primary(index, page, y)
            other, anchor = first, (pp, py, page_a, y_a)
        key = self._gap_key(other)
        self._end_pick()
        if key is None:
            return
        self.align_store.add_line(key, anchor)
        self._after_alignment_edit(tr("Trechos alinhados. Realinhar desfaz os ajustes manuais."))

    def _after_alignment_edit(self, message: str) -> None:
        self._align_version += 1
        self.refresh()
        self.statusBar().showMessage(message, 5000)

    # --- diferença visual -----------------------------------------------------------------
    def toggle_visual_diff(self) -> None:
        on = self.act_visual_diff.isChecked()
        self.settings.setValue("view/visual_diff", on)
        for pane in self.panes:
            pane.invalidate()
        self.refresh()
        if on:
            self.statusBar().showMessage(
                tr("Diferença visual ligada: áreas diferentes aparecem com contorno tracejado. "
                   "A sensibilidade fica em Configurações › Comparação."), 6000)

    def _partner_page(self, index: int, page: int, other: int) -> Optional[int]:
        """Página do PDF `other` que fica ao lado da página `page` do PDF `index`."""
        if self.nav.by_rows:
            row = self.nav.row_of(index, page)
            return self.nav.rows[row][other] if row is not None else None
        partner = page + self.sessions[index].offset - self.sessions[other].offset
        return partner if 0 <= partner < self.sessions[other].page_count else None

    def visual_marks(self, index: int, page: Optional[int]) -> List[DiffMark]:
        """Áreas da diferença visual na página `page` do PDF `index` (comparada com o par dela)."""
        if not self.act_visual_diff.isChecked() or page is None or len(self.sessions) < 2:
            return []
        if page in self._ignored(index):
            return []
        out: List[DiffMark] = []
        for a, b in self.comparison_pairs():
            if index not in (a, b):
                continue
            other = b if index == a else a
            partner = self._partner_page(index, page, other)
            if partner is None:
                continue
            pa, pb = (page, partner) if index == a else (partner, page)
            boxes = self._visual_pair(a, pa, b, pb)
            mine = boxes[0] if index == a else boxes[1]
            out += [DiffMark(page, (rect,), VISUAL) for rect in mine if self._in_scope(index, page, rect)]
        return out

    def _visual_pair(self, a: int, page_a: int, b: int, page_b: int) -> tuple:
        sa, sb = self.sessions[a], self.sessions[b]
        key = (self.annotation_key(a) or sa.uid, page_a, self.annotation_key(b) or sb.uid, page_b,
               self.compare.visual_sensitivity)
        if key in self._visual_cache:
            self._visual_cache.move_to_end(key)
            return self._visual_cache[key]
        try:
            result = page_difference(sa.doc[page_a], sb.doc[page_b], self.compare.visual_sensitivity)
        except (RuntimeError, ValueError, IndexError):
            result = ([], [])
        self._visual_cache[key] = result
        while len(self._visual_cache) > 300:
            self._visual_cache.popitem(last=False)
        return result

    def _update_visual_label(self, count: Optional[int]) -> None:
        on = self.act_visual_diff.isChecked() and len(self.sessions) >= 2
        self.visual_label.setVisible(on)
        if not on:
            return
        if count is None:
            self.visual_label.setText(tr("Diferença visual ligada"))
        else:
            self.visual_label.setText(tr("Diferença visual: {n} área(s) nas páginas à vista", n=count))
        self.visual_label.setToolTip(tr("Áreas com aparência diferente (imagens, assinaturas, carimbos, "
                                        "páginas escaneadas), com contorno tracejado."))

    # --- relatório de diferenças -------------------------------------------------------------
    REPORT_FILTERS = {"pdf": "PDF (*.pdf)", "html": "HTML (*.html)", "csv": "CSV (*.csv)"}

    def export_report(self) -> None:
        if len(self.sessions) < 2:
            return
        indexes = [self.indexer.index_for(s) for s in self.sessions]
        if any(i is None or not i.complete for i in indexes):
            self.statusBar().showMessage(tr("Aguarde terminar a leitura dos PDFs para gerar o relatório."), 5000)
            return
        start_dir = str(self.settings.value("files/export_dir", self.settings.value("files/last_dir", "")))
        default = Path(start_dir) / tr("relatorio_de_diferencas.pdf")
        filters = ";;".join(self.REPORT_FILTERS.values())
        path, chosen = QFileDialog.getSaveFileName(self, tr("Salvar relatório de diferenças"), str(default), filters)
        if not path:
            return
        if Path(path).suffix.lower() not in (".pdf", ".html", ".htm", ".csv"):
            ext = next((k for k, v in self.REPORT_FILTERS.items() if v == chosen), "pdf")
            path += f".{ext}"
        self.settings.setValue("files/export_dir", str(Path(path).parent))
        self.save_report(path)

    def build_report(self):
        from datetime import datetime

        pairs = []
        for a, b in self.comparison_pairs():
            ia, ib = self.compare_index(a), self.compare_index(b)
            pairs.append(PairReport(self.sessions[a].name, self.sessions[b].name,
                                    report_entries(ia, ib, sync=self._sync_points().get((a, b)))))
        if self.chain_mode:
            mode = tr("Em cadeia (cada PDF com o anterior)")
        else:
            mode = tr("Referência: {name}", name=self.sessions[self.reference_index()].name)
        created = datetime.now().strftime("%d/%m/%Y %H:%M" if language() == "pt" else "%Y-%m-%d %H:%M")
        return make_report(created, mode, [s.name for s in self.sessions], pairs)

    def save_report(self, path: str) -> bool:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = self.build_report()
            write_report(path, report)
        except (OSError, RuntimeError, ValueError) as exc:
            QApplication.restoreOverrideCursor()
            self._notify("warning", tr("Relatório não salvo"), tr("Não foi possível salvar o relatório: {error}",
                                                                  error=exc))
            return False
        QApplication.restoreOverrideCursor()
        total = sum(len(p.entries) for p in report.pairs)
        self.statusBar().showMessage(tr("Relatório salvo ({n} mudança(s)): {path}", n=total, path=path), 8000)
        return True

    # --- referência / cadeia ----------------------------------------------------------
    def reference_index(self) -> int:
        """Índice do PDF de referência (no modo em cadeia, o primeiro)."""
        if not self.chain_mode and self.reference_uid is not None:
            for i, s in enumerate(self.sessions):
                if s.uid == self.reference_uid:
                    return i
        return 0

    def comparison_pairs(self) -> List[Tuple[int, int]]:
        n = len(self.sessions)
        if self.chain_mode:
            return [(i - 1, i) for i in range(1, n)]
        ref = self.reference_index()
        return [(ref, i) for i in range(n) if i != ref]

    def set_reference(self, index: int) -> None:
        if not (0 <= index < len(self.sessions)):
            return
        self.reference_uid = self.sessions[index].uid
        self.chain_mode = False
        self._comparison_changed(tr("Referência da comparação: {name}", name=self.sessions[index].name))

    def set_chain_mode(self, on: Optional[bool] = None) -> None:
        self.chain_mode = self.act_chain.isChecked() if on is None else bool(on)
        self._comparison_changed(tr("Comparação em cadeia: cada PDF com o anterior.") if self.chain_mode
                                 else tr("Comparação com a referência."))

    def _comparison_changed(self, message: str) -> None:
        self.act_chain.setChecked(self.chain_mode)
        self._batch_signature = None
        self._update_roles()
        self.update_alignment()
        if self.act_diff.isChecked():
            self.update_diff()
        self.statusBar().showMessage(message, 4000)

    def _update_roles(self) -> None:
        ref = self.reference_index()
        for i, pane in enumerate(self.panes):
            if len(self.panes) < 2:
                pane.set_role("")
            elif self.chain_mode:
                pane.set_role(tr("{n}º", n=i + 1),
                              tr("Comparação em cadeia: este PDF é comparado com o anterior") if i else
                              tr("Comparação em cadeia: início"))
            else:
                pane.set_role(tr("Referência") if i == ref else "",
                              tr("Os outros PDFs são comparados com este. Clique com o botão direito em outro "
                                 "PDF para mudar a referência."))

    def _fill_reference_menu(self) -> None:
        from PySide6.QtGui import QActionGroup

        menu = self.reference_menu
        menu.clear()
        group = QActionGroup(menu)
        ref = self.reference_index()
        for i, s in enumerate(self.sessions):
            action = menu.addAction(s.name, lambda i=i: self.set_reference(i))
            action.setCheckable(True)
            action.setChecked(not self.chain_mode and i == ref)
            group.addAction(action)
        if self.sessions:
            menu.addSeparator()
        menu.addAction(self.act_chain)
        group.addAction(self.act_chain)
        self.act_chain.setChecked(self.chain_mode)
        self.act_chain.setEnabled(len(self.sessions) >= 3 or self.chain_mode)

    def _pane_menu(self, index: int, global_pos: QPoint, page: Optional[int] = None,
                   y: Optional[float] = None) -> None:
        if len(self.sessions) < 2:
            return
        menu = QMenu(self)
        gap_actions = {}
        gap = None
        if self.act_continuous.isChecked() and self.nav.by_rows and page is not None:
            gap = self.panes[index].last_context_gap
            block = self.panes[index].last_context_block
            if gap is not None:
                page, y = gap.page, gap.y
            insert = menu.addAction(tr("Inserir espaço aqui"))
            insert.setEnabled(gap is None or not gap.locked)
            gap_actions[insert] = lambda: self.insert_gap(index, page, y)
            if gap is not None:
                if not gap.removed:
                    remove = menu.addAction(tr("Remover este espaço"))
                    gap_actions[remove] = lambda: self.remove_gap(index, gap)
                if gap.locked:
                    unlock = menu.addAction(tr("Destravar este espaço"))
                    gap_actions[unlock] = lambda: self.lock_gap(index, gap, False)
                else:
                    lock = menu.addAction(tr("Travar este espaço"))
                    lock.setToolTip(tr("O alinhamento automático não muda nem recria este espaço"))
                    gap_actions[lock] = lambda: self.lock_gap(index, gap, True)
                    if not gap.removed:
                        remove_lock = menu.addAction(tr("Remover e travar este espaço"))
                        gap_actions[remove_lock] = lambda: self.remove_gap(index, gap, lock=True)
            pick = menu.addAction(tr("Alinhar este trecho com…"))
            pick.setToolTip(tr("Depois, clique no trecho correspondente em outro PDF"))
            gap_actions[pick] = lambda: self.start_pick(index, page, y)
            menu.addAction(self.act_align_regions)
            if block is not None:
                undo_block = menu.addAction(tr("Desfazer o alinhamento deste trecho"))
                gap_actions[undo_block] = lambda: self.remove_block(block)
            menu.addSeparator()
        ignore = None
        if page is not None and self.annotation_key(index):
            ignored = page in self._ignored(index)
            ignore = menu.addAction(tr("Voltar a comparar esta página") if ignored
                                    else tr("Ignorar esta página na comparação"))
            menu.addAction(self.act_ignore_pages)
            menu.addSeparator()
        use = menu.addAction(tr("Usar como referência da comparação"))
        use.setEnabled(self.chain_mode or index != self.reference_index())
        chain = menu.addAction(tr("Comparar em cadeia (cada PDF com o anterior)"))
        chain.setCheckable(True)
        chain.setChecked(self.chain_mode)
        chain.setEnabled(len(self.sessions) >= 3)
        chosen = menu.exec(global_pos)
        if chosen in gap_actions:
            gap_actions[chosen]()
            return
        if ignore is not None and chosen is ignore:
            self.toggle_ignored_page(index, page)
            return
        if chosen is use:
            self.set_reference(index)
        elif chosen is chain:
            self.set_chain_mode(not self.chain_mode)

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
        self._update_executor.shutdown(wait=False, cancel_futures=True)
        self.settings.setValue("view/mark_toolbar", self.mark_toolbar.isVisible())
        self._save_view_settings()
        self.runner.shutdown()
        self.indexer.clear()
        for session in self.sessions:
            session.close()
        super().closeEvent(event)
