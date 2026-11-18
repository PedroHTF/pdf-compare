"""Janela "Licença e créditos": o que se pode fazer, componentes e textos completos."""

from __future__ import annotations

from app.i18n import ENGLISH, language, tr

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
        source_line = tr("O código-fonte completo desta versão está no arquivo <b>{zip}</b>, na pasta do "
                         "programa (botão <i>Abrir pasta do programa</i>, abaixo).", zip=html.escape(zip_path.name))
    else:
        source_line = tr("Na versão executável, o código-fonte completo acompanha o programa no arquivo "
                         "<b>{zip}</b>.", zip=SOURCE_ZIP_NAME)
    template = _SUMMARY_EN if language() == ENGLISH else _SUMMARY_PT
    return template.format(version=__version__, copyright=html.escape(__copyright__), source_line=source_line,
                           url=__url__, url_text=html.escape(__url__))


_SUMMARY_PT = """
<h3 style="margin-bottom:2px">PDF Compare {version}</h3>
<p style="margin-top:0">{copyright}</p>

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
<a href="{url}">{url_text}</a>.</p>

<h4>Sem garantia</h4>
<p>O programa é fornecido "no estado em que se encontra", sem garantias de qualquer tipo.</p>

<p style="color:gray">Este resumo é informativo e não substitui o texto da licença
(aba <i>Textos das licenças</i>).</p>
"""

_SUMMARY_EN = """
<h3 style="margin-bottom:2px">PDF Compare {version}</h3>
<p style="margin-top:0">{copyright}</p>

<p>This program is <b>free software</b>, distributed under the
<b>GNU Affero General Public License, version 3 or later (AGPL-3.0)</b>.
This license is required because the program uses PyMuPDF/MuPDF, which is also AGPL.</p>

<h4>What you can do</h4>
<ul>
<li><b>Use</b> it for any purpose: personal, professional or inside companies.</li>
<li><b>Study and modify</b> the program as you wish.</li>
<li><b>Copy and distribute</b> it to others, free of charge or for a fee, with or without changes.</li>
</ul>
<p>Using the program — including in a company — <b>without distributing it</b> to others creates no obligations.</p>

<h4>What is required when distributing (copies or modified versions)</h4>
<ul>
<li>Provide or make available the <b>complete source code</b> to whoever receives the program.</li>
<li>Keep the copyright notices and this license; provide a copy of the license text.</li>
<li>Modified versions must stay under the <b>same license (AGPL-3.0)</b> and state what was changed.</li>
<li>Do not impose extra restrictions on recipients (for example, forbidding redistribution).</li>
<li>If a <b>modified</b> version is offered for use over a network (as an online service),
the source code must also be offered to those users.</li>
</ul>

<h4>Source code</h4>
<p>{source_line}</p>
<p>The source code is also published at
<a href="{url}">{url_text}</a>.</p>

<h4>No warranty</h4>
<p>The program is provided "as is", without warranties of any kind.</p>

<p style="color:gray">This summary is informative and does not replace the license text
(<i>License texts</i> tab).</p>
"""


class LicenseDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Licença e créditos"))
        self.resize(780, 600)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._summary_tab(), tr("Resumo"))
        self.tabs.addTab(self._components_tab(), tr("Componentes"))
        self.tabs.addTab(self._texts_tab(), tr("Textos das licenças"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.btn_folder = QPushButton(tr("Abrir pasta do programa"))
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
        self.table.setHorizontalHeaderLabels([tr("Componente"), tr("Versão"), tr("Licença"), tr("Responsável")])
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
            tr("As bibliotecas do Qt (LGPL) ficam como arquivos separados na pasta <i>_internal</i> "
            "e podem ser substituídas por versões compatíveis. "
            "Dê dois cliques em um componente para ver o texto da licença dele.")
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
            self.license_combo.addItem(tr(item.title), item.file)
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
