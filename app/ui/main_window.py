"""Janela principal: menus, barras de ferramentas, grade de PDFs, pesquisa,
anotações, comparação de texto, exportação, sessões e OCR."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QSettings, QSize, QStandardPaths, Qt
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
from app.services import ocr
from app.services.annotations import (
    HIGHLIGHT,
    NOTE,
    NOTE_SIZE,
    Annotation,
    AnnotationStore,
    file_fingerprint,
    find_at,
    for_page,
    note_rect,
    save_annotated_pdf,
    words_in_rect,
)
from app.services.export import Column, ExportError, export_comparison, export_current_pages, safe_stem
from app.services.indexer import IndexScheduler
from app.services.navigation import NavigationController
from app.services.search import SearchOptions, hit_snippet, search_index
from app.services.text_diff import ADDED, CHANGED, REMOVED, count_by_kind, diff_documents
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
from app.ui.pane import FIT_PAGE, FIT_WIDTH, TOOL_HIGHLIGHT, TOOL_NONE, TOOL_NOTE, PdfPane, ZoomMode
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
    return f"{n} {singular if n == 1 else plural}"


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
        self.act_add = self._action("&Adicionar PDFs…", self.open_dialog, ["Ctrl+O"],
                                    "Adicionar PDFs à comparação", S.SP_DialogOpenButton)
        self.act_open_folder = self._action("Abrir &pasta…", self.open_folder_dialog, ["Ctrl+Shift+O"],
                                            "Abrir os PDFs de uma pasta (até 6, em ordem de nome)")
        self.act_open_session = self._action("Abrir &sessão…", self.open_session_dialog, [],
                                             "Reabrir um conjunto de PDFs salvo, com páginas e zoom")
        self.act_save_session = self._action("&Salvar sessão…", self.save_session_dialog, ["Ctrl+S"],
                                             "Salvar os PDFs abertos, as páginas e o zoom para reabrir depois")
        self.act_export = self._action("&Exportar…", self.export_dialog, ["Ctrl+E"],
                                       "Exportar a comparação ou as páginas atuais como PDF ou PNG")
        self.act_close_all = self._action("&Fechar todos", self.close_all, ["Ctrl+Shift+W"],
                                          "Fechar todos os PDFs", S.SP_DialogCloseButton)
        self.act_quit = self._action("Sai&r", self.close, ["Ctrl+Q"], "Sair do programa")

        self.act_prev = self._action("Anterior", lambda: self.step(-1), ["Left", "PgUp"],
                                     "Página anterior em todos os PDFs", S.SP_ArrowBack)
        self.act_next = self._action("Próxima", lambda: self.step(+1), ["Right", "PgDown"],
                                     "Próxima página em todos os PDFs", S.SP_ArrowForward)
        self.act_first = self._action("Início", self.go_first, ["Ctrl+Home"],
                                      "Ir para o início de todos os PDFs", S.SP_MediaSkipBackward)
        self.act_last = self._action("Fim", self.go_last, ["Ctrl+End"],
                                     "Ir para o fim de todos os PDFs", S.SP_MediaSkipForward)
        self.act_realign = self._action("Realinhar", self.realign, ["Ctrl+L"],
                                        "Desfazer ajustes individuais: todos voltam a mostrar a mesma página",
                                        S.SP_BrowserReload)

        self.act_find = self._action("&Pesquisar", self.focus_search, ["Ctrl+F"], "Pesquisar em todos os PDFs")
        self.act_hit_next = self._action("Próxima ocorrência", lambda: self.next_hit_all(+1), ["F3"],
                                         "Ir para a próxima ocorrência em cada PDF")
        self.act_hit_prev = self._action("Ocorrência anterior", lambda: self.next_hit_all(-1), ["Shift+F3"],
                                         "Ir para a ocorrência anterior em cada PDF")

        self.act_diff = self._action("Comparar &texto", self.toggle_diff, ["Ctrl+D"],
                                     "Destacar as diferenças de texto em relação ao primeiro PDF",
                                     checkable=True)
        self.act_diff_next = self._action("Próxima diferença", lambda: self.next_diff_all(+1), ["F7"],
                                          "Ir para a próxima diferença de texto em cada PDF")
        self.act_diff_prev = self._action("Diferença anterior", lambda: self.next_diff_all(-1), ["Shift+F7"],
                                          "Ir para a diferença de texto anterior em cada PDF")

        self.act_highlight = self._action("&Destacar texto", lambda: self.toggle_tool(TOOL_HIGHLIGHT), ["Ctrl+H"],
                                          "Arraste sobre o texto para destacá-lo", checkable=True)
        self.act_note = self._action("Adicionar &nota", lambda: self.toggle_tool(TOOL_NOTE), ["Ctrl+M"],
                                     "Clique na página para adicionar uma nota", checkable=True)
        self.act_highlight.setIconText("Destacar")
        self.act_note.setIconText("Nota")

        self.act_ocr = self._action("Reconhecer texto em PDFs escaneados (&OCR)", self.toggle_ocr, [],
                                    "Usa o Tesseract OCR, se instalado, para pesquisar e comparar PDFs escaneados",
                                    checkable=True)
        self.act_ocr_language = self._action("&Idioma do OCR…", self.choose_ocr_language)

        self.act_fit_width = self._action("Ajustar à &largura", lambda: self.set_zoom(FIT_WIDTH), ["Ctrl+0"])
        self.act_fit_page = self._action("&Página inteira", lambda: self.set_zoom(FIT_PAGE), ["Ctrl+9"])
        self.act_zoom_in = self._action("&Aumentar zoom", lambda: self.zoom_by(+1), ["Ctrl++", "Ctrl+="])
        self.act_zoom_out = self._action("&Diminuir zoom", lambda: self.zoom_by(-1), ["Ctrl+-"])
        self.act_zoom_in.setIconText("+")
        self.act_zoom_out.setIconText("−")

        self.act_linked_scroll = self._action(
            "Rolagem &vinculada", self._save_view_settings, [],
            "Ao rolar a página de um PDF, os outros acompanham", checkable=True,
        )
        self.act_linked_scroll.setChecked(self._bool_setting("view/linked_scroll", True))

        self.act_shortcuts = self._action("&Atalhos de teclado", self.show_shortcuts, ["F1"])
        self.act_license = self._action("&Licença e créditos…", self.show_license,
                                        tip="O que você pode fazer com este programa e licenças dos componentes")
        self.act_about = self._action("&Sobre", self.show_about)

    def _create_menus(self) -> None:
        bar = self.menuBar()
        m = bar.addMenu("&Arquivo")
        m.addActions([self.act_add, self.act_open_folder])
        self.recent_menu = m.addMenu("Abertos &recentemente")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        m.addActions([self.act_open_session, self.act_save_session])
        m.addSeparator()
        m.addAction(self.act_export)
        m.addSeparator()
        m.addAction(self.act_close_all)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = bar.addMenu("&Navegar")
        m.addActions([self.act_prev, self.act_next, self.act_first, self.act_last])
        m.addSeparator()
        m.addAction(self.act_realign)
        m.addSeparator()
        m.addActions([self.act_find, self.act_hit_next, self.act_hit_prev])
        m.addSeparator()
        m.addActions([self.act_diff_next, self.act_diff_prev])

        m = bar.addMenu("&Exibir")
        m.addActions([self.act_fit_width, self.act_fit_page, self.act_zoom_in, self.act_zoom_out])
        m.addSeparator()
        m.addAction(self.act_linked_scroll)
        self.view_menu = m

        m = bar.addMenu("&Ferramentas")
        m.addActions([self.act_highlight, self.act_note])
        m.addSeparator()
        m.addAction(self.act_diff)
        m.addSeparator()
        m.addActions([self.act_ocr, self.act_ocr_language])

        m = bar.addMenu("A&juda")
        m.addActions([self.act_shortcuts, self.act_license, self.act_about])

    def _create_toolbars(self) -> None:
        tb = QToolBar("Barra principal")
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
        self.zoom_combo.setToolTip("Zoom de todos os PDFs (Ctrl + roda do mouse)")
        self.zoom_combo.setAccessibleName("Zoom")
        self.zoom_combo.addItem("Ajustar à largura", FIT_WIDTH)
        self.zoom_combo.addItem("Página inteira", FIT_PAGE)
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
        tb.addActions([self.act_highlight, self.act_note, self.act_diff])
        tb.addSeparator()
        tb.addAction(self.act_export)

        self.addToolBarBreak()
        stb = QToolBar("Pesquisa")
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

    def _create_central(self) -> None:
        self.empty_view = DropZone(
            "Arraste seus PDFs para cá",
            "Compare de 2 a 6 documentos lado a lado, pesquise em todos ao mesmo tempo\n"
            "e avance página por página — em todos juntos ou em cada um separadamente.",
            pixmap=logo_pixmap(96),
        )
        self.empty_view.open_requested.connect(self.open_dialog)
        empty_host = QWidget()
        empty_layout = QVBoxLayout(empty_host)
        empty_layout.setContentsMargins(60, 40, 60, 40)
        empty_layout.addWidget(self.empty_view)

        self.grid_host = QWidget()
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
        self.results_dock = QDockWidget("Ocorrências", self)
        self.results_dock.setObjectName("resultsDock")
        self.results_dock.setWidget(self.results_panel)
        self.results_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.results_dock)
        self.results_dock.setVisible(self._bool_setting("view/results_panel", False))
        self.act_results = self.results_dock.toggleViewAction()
        self.act_results.setText("Lista de &ocorrências")
        self.act_results.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_results.setToolTip("Mostrar a lista de ocorrências da pesquisa (Ctrl+Shift+F)")
        self.addAction(self.act_results)
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.act_results)
        self.search_bar.layout().insertWidget(5, self._results_button())

    def _results_button(self):
        from PySide6.QtWidgets import QToolButton

        button = QToolButton()
        button.setDefaultAction(self.act_results)
        button.setText("Lista")
        return button

    def _create_status_bar(self) -> None:
        self.hint_label = QLabel()
        self.hint_label.setObjectName("muted")
        self.statusBar().addWidget(self.hint_label, 1)
        self.diff_label = QLabel()
        self.diff_label.setObjectName("diffSummary")
        self.diff_label.hide()
        self.statusBar().addPermanentWidget(self.diff_label)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(240)
        self.progress.setFormat("Preparando pesquisa… %p%")
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

    # ======================================================================
    # Abrir e fechar documentos
    # ======================================================================
    def open_dialog(self) -> None:
        if len(self.sessions) >= MAX_DOCUMENTS:
            self._notify("info", "Limite atingido", f"Já há {MAX_DOCUMENTS} PDFs abertos. Feche um para adicionar outro.")
            return
        start_dir = str(self.settings.value("files/last_dir", ""))
        paths, _ = QFileDialog.getOpenFileNames(self, "Adicionar PDFs", start_dir, "Documentos PDF (*.pdf)")
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
                f"Não aberto (senha não informada): {', '.join(cancelled)}", 6000
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
            problems.append(f"Limite de {MAX_DOCUMENTS} PDFs: não foram abertos — {names}.")
        if ignored_type:
            problems.append(f"{_plural(ignored_type, 'arquivo ignorado', 'arquivos ignorados')} por não ser PDF.")
        if problems:
            self._notify("warning", "Alguns arquivos não foram abertos", "\n\n".join(problems))
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
            f"Senha incorreta para “{path.name}” ({MAX_PASSWORD_ATTEMPTS} tentativas). "
            "Abra o arquivo de novo para tentar outra vez."
        )

    def _ask_password(self, name: str, attempt: int) -> Optional[str]:
        """Pede a senha ao usuário. Devolve None se ele cancelar."""
        if attempt == 1:
            label = f"“{name}” está protegido por senha.\n\nDigite a senha para abri-lo:"
        else:
            label = (f"Senha incorreta. Tente novamente "
                     f"(tentativa {attempt} de {MAX_PASSWORD_ATTEMPTS}).\n\nSenha de “{name}”:")
        dialog = QInputDialog(self)
        dialog.setWindowTitle("PDF protegido")
        dialog.setLabelText(label)
        dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
        dialog.setOkButtonText("Abrir")
        dialog.setCancelButtonText("Pular este arquivo")
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
            pane.set_tool(self.tool)
            self.panes.append(pane)
            self.grid.addWidget(pane, i // cols, i % cols)
        if n == 1:
            add_zone = DropZone("Adicione outro PDF", "para comparar lado a lado", "Adicionar PDF…", compact=True)
            add_zone.open_requested.connect(self.open_dialog)
            self.grid.addWidget(add_zone, 0, 1)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        for r in range(rows):
            self.grid.setRowStretch(r, 1)
        self.refresh()

    # ======================================================================
    # Navegação
    # ======================================================================
    def step(self, delta: int) -> None:
        if self.sessions:
            self.nav.step(delta)
            self.refresh()

    def go_first(self) -> None:
        if self.sessions:
            self.nav.go_first()
            self.refresh()

    def go_last(self) -> None:
        if self.sessions:
            self.nav.go_last()
            self.refresh()

    def realign(self) -> None:
        if self.sessions:
            self.nav.realign()
            self.refresh()
            self.statusBar().showMessage("Todos os PDFs realinhados na mesma página.", 3000)

    def _on_pane_step(self, index: int, delta: int) -> None:
        self.nav.step_pane(index, delta)
        self.refresh()

    def _on_pane_jump(self, index: int, page: int) -> None:
        self.nav.show_page(index, page)
        self.refresh()

    def _on_pane_hit_step(self, index: int, delta: int) -> None:
        self.nav.step_hit(index, delta)
        self.refresh()

    def _on_pane_scrolled(self, index: int, ratio: float) -> None:
        if not self.act_linked_scroll.isChecked():
            return
        for pane in self.panes:
            if pane.index != index:
                pane.set_scroll_ratio(ratio)

    def refresh(self) -> None:
        active = bool(self._query)
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
            text = (f"{_plural(total, 'ocorrência', 'ocorrências')} em {docs} de "
                    f"{_plural(len(self.sessions), 'PDF', 'PDFs')} — Enter vai para a próxima")
            state = "found"
        else:
            text, state = "Nenhuma ocorrência encontrada", "notfound"
        if pending:
            text += " · ainda lendo o texto dos PDFs…"
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
            self.statusBar().showMessage("Nenhuma ocorrência para navegar.", 3000)

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
                       self.act_save_session, self.act_highlight, self.act_note):
            action.setEnabled(has)
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
            hint = "Abra ou arraste de 2 a 6 PDFs para começar  (Ctrl+O)"
        elif n == 1:
            hint = "Adicione pelo menos mais um PDF para comparar."
        else:
            hint = ("◀ ▶ ou setas do teclado: avançam todos juntos  ·  "
                    "botões de cada painel: ajustam só aquele PDF  ·  Ctrl+F: pesquisar em todos")
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
            ("Ctrl+O", "Adicionar PDFs (ou arraste os arquivos para a janela)"),
            ("Ctrl+Shift+O", "Abrir todos os PDFs de uma pasta"),
            ("Ctrl+S", "Salvar sessão (PDFs, páginas e zoom)"),
            ("Ctrl+E", "Exportar comparação ou páginas atuais (PDF/PNG)"),
            ("→ / Page Down", "Próxima página em todos os PDFs"),
            ("← / Page Up", "Página anterior em todos os PDFs"),
            ("Ctrl+Home / Ctrl+End", "Início / fim de todos os PDFs"),
            ("Ctrl+L", "Realinhar: todos na mesma página"),
            ("Ctrl+F", "Pesquisar em todos os PDFs"),
            ("Enter / F3", "Próxima ocorrência em cada PDF"),
            ("Shift+Enter / Shift+F3", "Ocorrência anterior em cada PDF"),
            ("Ctrl+Shift+F", "Mostrar/ocultar a lista de ocorrências"),
            ("Esc", "Limpar a pesquisa (com o cursor na caixa de pesquisa)"),
            ("Ctrl+D", "Comparar texto: destacar diferenças em relação ao 1º PDF"),
            ("F7 / Shift+F7", "Próxima / anterior diferença de texto em cada PDF"),
            ("Ctrl+H", "Destacar texto (arraste sobre o texto)"),
            ("Ctrl+M", "Adicionar nota (clique na página)"),
            ("Botão direito", "Editar ou remover a anotação sob o cursor"),
            ("Ctrl + roda do mouse", "Zoom"),
            ("Ctrl++ / Ctrl+-", "Aumentar / diminuir zoom"),
            ("Ctrl+0 / Ctrl+9", "Ajustar à largura / página inteira"),
        ]
        table = "".join(f"<tr><td style='padding:2px 16px 2px 0'><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows)
        extra = ("<p>Em cada painel: <b>◀ ▶</b> mudam só aquele PDF, <b>▲ ▼</b> navegam pelas "
                 "ocorrências dele e o campo de página permite digitar o número.</p>"
                 "<p>Comparar texto: <span style='background:#cdeccd'>verde</span> = incluído, "
                 "<span style='background:#f6c9c4'>vermelho</span> = removido, "
                 "<span style='background:#cfdffb'>azul</span> = alterado.</p>")
        QMessageBox.information(self, "Atalhos de teclado", f"<table>{table}</table>{extra}")

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(f"Sobre o {APP_NAME}")
        box.setIconPixmap(logo_pixmap(72))
        box.setText(
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Compare de 2 a 6 PDFs lado a lado, com pesquisa simultânea "
            "e navegação página a página.</p>"
            "<p>Os arquivos são processados apenas neste computador.</p>"
            f"<p>{__copyright__}<br>Software livre sob a licença GNU AGPL v3.<br>"
            f'Código-fonte: <a href="{__url__}">{__url__}</a></p>'
        )
        btn_license = box.addButton("Licença e créditos…", QMessageBox.ButtonRole.ActionRole)
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
            self.statusBar().showMessage("Solte para adicionar os PDFs à comparação.")

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
    # Pasta, recentes e sessões
    # ======================================================================
    def open_folder_dialog(self) -> None:
        start_dir = str(self.settings.value("files/last_dir", ""))
        folder = QFileDialog.getExistingDirectory(self, "Abrir os PDFs de uma pasta", start_dir)
        if folder:
            self.settings.setValue("files/last_dir", folder)
            self.open_folder(folder)

    def open_folder(self, folder) -> None:
        pdfs = pdfs_in_folder(folder)
        if not pdfs:
            self._notify("info", "Nenhum PDF", f"Não há arquivos PDF em “{Path(folder).name or folder}”.")
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
            label = Path(path).name + ("  (sessão)" if path.lower().endswith(SESSION_SUFFIX) else "")
            action = self.recent_menu.addAction(label)
            action.setToolTip(path)
            action.setStatusTip(path)
            action.triggered.connect(lambda _c=False, p=path: self.open_recent(p))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Limpar lista", lambda: self.settings.setValue("files/recent", []))

    def open_recent(self, path: str) -> None:
        if not Path(path).exists():
            self._notify("warning", "Arquivo não encontrado", f"“{path}” não existe mais.")
            return
        if path.lower().endswith(SESSION_SUFFIX):
            self.open_session(path)
        else:
            self.add_files([path])

    def save_session_dialog(self) -> None:
        if not self.sessions:
            return
        start = str(Path(str(self.settings.value("files/last_dir", ""))) / f"comparacao{SESSION_SUFFIX}")
        path, _ = QFileDialog.getSaveFileName(self, "Salvar sessão", start,
                                              f"Sessão do PDF Compare (*{SESSION_SUFFIX})")
        if path:
            self.save_session_to(path)

    def save_session_to(self, path) -> Optional[Path]:
        data = SessionData([SessionFile(s.path, s.offset) for s in self.sessions], self.nav.current, self.zoom_mode)
        try:
            saved = save_session(path, data)
        except SessionError as exc:
            self._notify("warning", "Sessão não salva", str(exc))
            return None
        self._remember(saved)
        self.statusBar().showMessage(f"Sessão salva em “{saved.name}”.", 4000)
        return saved

    def open_session_dialog(self) -> None:
        start_dir = str(self.settings.value("files/last_dir", ""))
        path, _ = QFileDialog.getOpenFileName(self, "Abrir sessão", start_dir,
                                              f"Sessão do PDF Compare (*{SESSION_SUFFIX})")
        if path:
            self.open_session(path)

    def open_session(self, path) -> None:
        try:
            data, missing = load_session(path)
        except SessionError as exc:
            self._notify("warning", "Sessão não aberta", str(exc))
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
            self._notify("warning", "Arquivos não encontrados",
                         "Estes PDFs da sessão não foram encontrados:\n" + "\n".join(missing))

    # ======================================================================
    # Anotações
    # ======================================================================
    def toggle_tool(self, tool: str) -> None:
        self.set_tool(TOOL_NONE if self.tool == tool else tool)

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.act_highlight.setChecked(tool == TOOL_HIGHLIGHT)
        self.act_note.setChecked(tool == TOOL_NOTE)
        for pane in self.panes:
            pane.set_tool(tool)
        if tool == TOOL_HIGHLIGHT:
            self.statusBar().showMessage("Destacar: arraste sobre o texto. Ctrl+H de novo para sair.", 5000)
        elif tool == TOOL_NOTE:
            self.statusBar().showMessage("Nota: clique no ponto da página. Ctrl+M de novo para sair.", 5000)

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

    def add_annotation(self, index: int, annotation: Annotation) -> bool:
        key = self.annotation_key(index)
        if key is None:
            self._notify("warning", "Anotação não salva", "Não foi possível ler o arquivo para guardar a anotação.")
            return False
        try:
            self.annotations.add(key, annotation, self.sessions[index].name)
        except OSError as exc:
            self._notify("warning", "Anotação não salva", f"Não foi possível gravar a anotação: {exc}")
            return False
        self.refresh()
        return True

    def _on_highlight(self, index: int, page: int, rect: tuple) -> None:
        session = self.sessions[index]
        rects = words_in_rect(session.doc[page], rect)
        if not rects:
            if abs(rect[2] - rect[0]) < 4 or abs(rect[3] - rect[1]) < 4:
                self.statusBar().showMessage("Arraste sobre o texto que deseja destacar.", 4000)
                return
            rects = [rect]   # área sem texto (imagem, PDF escaneado): destaca a área
        self.add_annotation(index, Annotation(HIGHLIGHT, page, rects))

    def _on_note(self, index: int, page: int, x: float, y: float) -> None:
        text = self._ask_note_text("")
        if text is None:
            return
        half = NOTE_SIZE / 2
        self.add_annotation(index, Annotation(NOTE, page, [note_rect(x - half, y - half)], text))

    def _ask_note_text(self, initial: str) -> Optional[str]:
        text, ok = QInputDialog.getMultiLineText(self, "Nota", "Texto da nota:", initial)
        return text if ok else None

    def _on_annotation_menu(self, index: int, page: int, x: float, y: float, global_pos: QPoint) -> None:
        found = find_at(self.document_annotations(index), page, x, y)
        if found is None:
            return
        menu = QMenu(self)
        edit = menu.addAction("Editar texto da nota…" if found.kind == NOTE else "Adicionar comentário…")
        remove = menu.addAction("Remover anotação")
        chosen = menu.exec(global_pos)
        if chosen is edit:
            self.edit_annotation(index, found.id)
        elif chosen is remove:
            self.remove_annotation(index, found.id)

    def edit_annotation(self, index: int, annotation_id: str) -> None:
        key = self.annotation_key(index)
        current = next((a for a in self.document_annotations(index) if a.id == annotation_id), None)
        if key is None or current is None:
            return
        text = self._ask_note_text(current.text)
        if text is not None:
            self.annotations.update_text(key, annotation_id, text, self.sessions[index].name)
            self.refresh()

    def remove_annotation(self, index: int, annotation_id: str) -> None:
        key = self.annotation_key(index)
        if key and self.annotations.remove(key, annotation_id, self.sessions[index].name):
            self.refresh()

    # ======================================================================
    # Comparação de texto
    # ======================================================================
    def toggle_diff(self) -> None:
        self.update_diff()
        if self.act_diff.isChecked() and self.nav.total_diffs:
            self.next_diff_all(+1)

    def update_diff(self) -> None:
        if not self.act_diff.isChecked() or len(self.sessions) < 2:
            self.nav.clear_diffs()
            self.diff_label.hide()
            self.refresh()
            return
        indexes = [self.indexer.index_for(s) for s in self.sessions]
        if any(i is None or not i.complete for i in indexes):
            self.nav.clear_diffs()
            self.diff_label.setText("Comparando texto… aguardando a leitura dos PDFs")
            self.diff_label.show()
            self.refresh()
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.nav.set_diffs(diff_documents(indexes))
        finally:
            QApplication.restoreOverrideCursor()
        self.diff_label.setText(self.diff_summary())
        self.diff_label.setToolTip("Verde: incluído · Vermelho: removido · Azul: alterado "
                                   "(em relação ao primeiro PDF). F7 vai para a próxima diferença.")
        self.diff_label.show()
        self.refresh()

    def diff_summary(self) -> str:
        if self.nav.total_diffs == 0:
            return "Texto idêntico ao do 1º PDF"
        parts = []
        for i, session in enumerate(self.sessions[1:], start=1):
            c = count_by_kind(self.nav.diffs[i])
            parts.append(f"{session.name}: +{c[ADDED]} −{c[REMOVED]} ~{c[CHANGED]}")
        return "Diferenças em relação a " + self.sessions[0].name + " — " + " · ".join(parts)

    def next_diff_all(self, delta: int) -> None:
        if self.nav.step_diff_all(delta):
            self.refresh()
        elif self.act_diff.isChecked():
            self.statusBar().showMessage("Nenhuma diferença de texto para navegar.", 3000)

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
            target, _ = QFileDialog.getSaveFileName(self, "Exportar comparação", str(Path(start_dir) / f"{name}.{ext}"),
                                                    f"{ext.upper()} (*.{ext})")
            if target and not target.lower().endswith(f".{ext}"):
                target += f".{ext}"
            folder = str(Path(target).parent) if target else ""
        else:
            target = QFileDialog.getExistingDirectory(self, "Pasta de destino", start_dir)
            folder = target
        if not target:
            return
        self.settings.setValue("files/export_dir", folder)
        files = self.export(choice, target)
        if files:
            where = files[0].parent
            self.statusBar().showMessage(f"{_plural(len(files), 'arquivo exportado', 'arquivos exportados')} em {where}", 6000)

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
            self._notify("warning", "Exportação não concluída", str(exc))
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
            self.statusBar().showMessage("OCR desativado: Tesseract OCR não encontrado.", 8000)

    def toggle_ocr(self) -> None:
        if not self.act_ocr.isChecked():
            self.indexer.set_ocr(False)
            self.settings.setValue("ocr/enabled", False)
            return
        status = ocr.check(self.ocr_language())
        if not status.available:
            self.act_ocr.setChecked(False)
            self._notify("warning", "OCR indisponível", status.message)
            return
        self.settings.setValue("ocr/enabled", True)
        self.indexer.set_ocr(True, self.ocr_language(), status.tessdata)
        self._reindex()
        self.statusBar().showMessage("OCR ligado: páginas escaneadas serão reconhecidas (pode levar alguns segundos por página).", 6000)

    def choose_ocr_language(self) -> None:
        tessdata = ocr.find_tessdata()
        langs = ", ".join(ocr.installed_languages(tessdata)) or "nenhum (Tesseract não encontrado)"
        text, ok = QInputDialog.getText(
            self, "Idioma do OCR",
            f"Código do idioma do Tesseract (ex.: por, eng, por+eng).\nInstalados: {langs}",
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
                self._notify("warning", "OCR indisponível", status.message)
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
        self._notify("warning", "OCR desativado", f"{message}\n\n{ocr.INSTALL_HELP}")

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
                f"“{session.name}” parece escaneado (sem texto). Ative Ferramentas › OCR para pesquisar nele.", 10000)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("view/results_panel", self.results_dock.isVisible())
        self._save_view_settings()
        self.indexer.clear()
        for session in self.sessions:
            session.close()
        super().closeEvent(event)
