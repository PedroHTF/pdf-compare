"""Janela principal: menus, barras de ferramentas, grade de PDFs e pesquisa."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

from PySide6.QtCore import QByteArray, QMimeData, QSettings, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
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
from app.services.indexer import IndexScheduler
from app.services.navigation import NavigationController
from app.services.search import SearchOptions, search_index
from app.ui.pane import FIT_PAGE, FIT_WIDTH, PdfPane, ZoomMode
from app.ui.resources import app_icon, logo_pixmap
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


class MainWindow(QMainWindow):
    def __init__(self, settings: Optional[QSettings] = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings()
        self.sessions: List[DocumentSession] = []
        self.panes: List[PdfPane] = []
        self.nav = NavigationController()
        self.indexer = IndexScheduler(self)
        self.indexer.progress.connect(self._on_index_progress)
        self.indexer.document_indexed.connect(self._on_document_indexed)
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
        self._create_status_bar()
        self._sync_zoom_combo()
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
        m.addActions([self.act_add, self.act_close_all])
        m.addSeparator()
        m.addAction(self.act_quit)

        m = bar.addMenu("&Navegar")
        m.addActions([self.act_prev, self.act_next, self.act_first, self.act_last])
        m.addSeparator()
        m.addAction(self.act_realign)
        m.addSeparator()
        m.addActions([self.act_find, self.act_hit_next, self.act_hit_prev])

        m = bar.addMenu("&Exibir")
        m.addActions([self.act_fit_width, self.act_fit_page, self.act_zoom_in, self.act_zoom_out])
        m.addSeparator()
        m.addAction(self.act_linked_scroll)

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

    def _create_status_bar(self) -> None:
        self.hint_label = QLabel()
        self.hint_label.setObjectName("muted")
        self.statusBar().addWidget(self.hint_label, 1)
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
        session.close()
        self.nav.set_sessions(self.sessions, keep_position=True)
        self._rebuild_grid()
        self.run_search()
        self._update_ui_state()

    def close_all(self) -> None:
        self.indexer.clear()
        for session in self.sessions:
            session.close()
        self.sessions = []
        self.nav.set_sessions([])
        self._rebuild_grid()
        self.run_search()
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
            pane.render(page, self.nav.raw_page(i), self.nav.page_hits(i, page), current, self.zoom_mode)
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

    def _on_document_indexed(self, _session: DocumentSession) -> None:
        if self._query:
            self.run_search()

    def _on_index_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress.hide()
            if self._query:
                self.run_search()
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
        value = str(self.settings.value("view/zoom", FIT_WIDTH))
        if value in (FIT_WIDTH, FIT_PAGE):
            return value
        try:
            zoom = float(value)
        except ValueError:
            return FIT_WIDTH
        return zoom if zoom in ZOOM_PRESETS else FIT_WIDTH

    # ======================================================================
    # Estado da interface
    # ======================================================================
    def _update_ui_state(self) -> None:
        n = len(self.sessions)
        has = n > 0
        self.stack.setCurrentIndex(1 if has else 0)

        for action in (self.act_close_all, self.act_fit_width, self.act_fit_page,
                       self.act_zoom_in, self.act_zoom_out, self.act_find):
            action.setEnabled(has)
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
            ("→ / Page Down", "Próxima página em todos os PDFs"),
            ("← / Page Up", "Página anterior em todos os PDFs"),
            ("Ctrl+Home / Ctrl+End", "Início / fim de todos os PDFs"),
            ("Ctrl+L", "Realinhar: todos na mesma página"),
            ("Ctrl+F", "Pesquisar em todos os PDFs"),
            ("Enter / F3", "Próxima ocorrência em cada PDF"),
            ("Shift+Enter / Shift+F3", "Ocorrência anterior em cada PDF"),
            ("Esc", "Limpar a pesquisa (com o cursor na caixa de pesquisa)"),
            ("Ctrl + roda do mouse", "Zoom"),
            ("Ctrl++ / Ctrl+-", "Aumentar / diminuir zoom"),
            ("Ctrl+0 / Ctrl+9", "Ajustar à largura / página inteira"),
        ]
        table = "".join(f"<tr><td style='padding:2px 16px 2px 0'><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows)
        extra = ("<p>Em cada painel: <b>◀ ▶</b> mudam só aquele PDF, <b>▲ ▼</b> navegam pelas "
                 "ocorrências dele e o campo de página permite digitar o número.</p>")
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

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.setValue("window/geometry", self.saveGeometry())
        self._save_view_settings()
        self.indexer.clear()
        for session in self.sessions:
            session.close()
        super().closeEvent(event)
