"""Janela "Licença e créditos": o que se pode fazer, componentes e textos completos."""

from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app import __copyright__, __url__, __version__
from app.legal import LICENSE_TEXTS, SOURCE_ZIP_NAME, components, program_dir, read_license, source_zip_path


def summary_html() -> str:
    zip_path = source_zip_path()
    if zip_path is not None:
        source_line = (f"O código-fonte completo desta versão está no arquivo "
                       f"<b>{html.escape(zip_path.name)}</b>, na pasta do programa "
                       f"(botão <i>Abrir pasta do programa</i>, abaixo).")
    else:
        source_line = (f"Na versão executável, o código-fonte completo acompanha o programa "
                       f"no arquivo <b>{SOURCE_ZIP_NAME}</b>.")
    return f"""
<h3 style="margin-bottom:2px">PDF Compare {__version__}</h3>
<p style="margin-top:0">{html.escape(__copyright__)}</p>

<p>Este programa é <b>software livre</b>, distribuído sob a
<b>GNU Affero General Public License, versão 3 ou posterior (AGPL-3.0)</b>.
Essa licença é obrigatória porque o programa usa o PyMuPDF/MuPDF, que também é AGPL.</p>

<h4>O que você pode fazer</h4>
<ul>
<li><b>Usar</b> para qualquer finalidade: pessoal, profissional ou dentro de empresas.</li>
<li><b>Estudar e modificar</b> o programa como quiser.</li>
<li><b>Copiar e distribuir</b> para outras pessoas, de graça ou cobrando, com ou sem modificações.</li>
</ul>
<p>Usar o programa — inclusive em uma empresa — <b>sem distribuí-lo</b> a terceiros não gera nenhuma obrigação.</p>

<h4>O que é obrigatório ao distribuir (cópias ou versões modificadas)</h4>
<ul>
<li>Entregar ou disponibilizar o <b>código-fonte completo</b> a quem receber o programa.</li>
<li>Manter os avisos de copyright e esta licença; entregar uma cópia do texto da licença.</li>
<li>Versões modificadas devem continuar sob a <b>mesma licença (AGPL-3.0)</b> e indicar o que foi alterado.</li>
<li>Não impor restrições extras a quem recebe (por exemplo, proibir que redistribua).</li>
<li>Se uma versão <b>modificada</b> for oferecida para uso pela rede (como serviço on-line),
o código-fonte também deve ser oferecido a esses usuários.</li>
</ul>

<h4>Código-fonte</h4>
<p>{source_line}</p>
<p>O código-fonte também está publicado em
<a href="{__url__}">{html.escape(__url__)}</a>.</p>

<h4>Sem garantia</h4>
<p>O programa é fornecido "no estado em que se encontra", sem garantias de qualquer tipo.</p>

<p style="color:gray">Este resumo é informativo e não substitui o texto da licença
(aba <i>Textos das licenças</i>).</p>
"""


class LicenseDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Licença e créditos")
        self.resize(780, 600)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._summary_tab(), "Resumo")
        self.tabs.addTab(self._components_tab(), "Componentes")
        self.tabs.addTab(self._texts_tab(), "Textos das licenças")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.btn_folder = QPushButton("Abrir pasta do programa")
        self.btn_folder.setToolTip(str(program_dir()))
        self.btn_folder.clicked.connect(self.open_program_folder)
        buttons.addButton(self.btn_folder, QDialogButtonBox.ButtonRole.ActionRole)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)

    def _summary_tab(self) -> QWidget:
        self.summary = QTextBrowser()
        self.summary.setOpenExternalLinks(True)
        self.summary.setHtml(summary_html())
        return self.summary

    def _components_tab(self) -> QWidget:
        items = components()
        self.table = QTableWidget(len(items), 4)
        self.table.setHorizontalHeaderLabels(["Componente", "Versão", "Licença", "Responsável"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for row, comp in enumerate(items):
            for col, value in enumerate((comp.name, comp.version, comp.license, comp.owner)):
                cell = QTableWidgetItem(value)
                if comp.url:
                    cell.setToolTip(comp.url)
                self.table.setItem(row, col, cell)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda row, _col: self._show_license_of(items[row].license_file))

        note = QLabel(
            "As bibliotecas do Qt (LGPL) ficam como arquivos separados na pasta <i>_internal</i> "
            "e podem ser substituídas por versões compatíveis. "
            "Dê dois cliques em um componente para ver o texto da licença dele."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.table, 1)
        layout.addWidget(note)
        return page

    def _texts_tab(self) -> QWidget:
        self.license_combo = QComboBox()
        for item in LICENSE_TEXTS:
            self.license_combo.addItem(item.title, item.file)
        self.license_view = QPlainTextEdit()
        self.license_view.setReadOnly(True)
        self.license_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.license_combo.currentIndexChanged.connect(self._load_license)
        self._load_license(0)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.license_combo)
        layout.addWidget(self.license_view, 1)
        return page

    def _load_license(self, index: int) -> None:
        self.license_view.setPlainText(read_license(self.license_combo.itemData(index)))
        self.license_view.moveCursor(self.license_view.textCursor().MoveOperation.Start)

    def _show_license_of(self, file_name: str) -> None:
        index = self.license_combo.findData(file_name)
        if index >= 0:
            self.license_combo.setCurrentIndex(index)
            self.tabs.setCurrentIndex(2)

    def open_program_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(program_dir())))
