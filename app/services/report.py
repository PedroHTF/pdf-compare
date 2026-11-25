"""Relatório de diferenças: lista das mudanças entre os PDFs, em PDF, HTML ou CSV.

Para cada comparação (base → comparado) há uma tabela com o tipo da mudança,
as páginas e o texto antes e depois. O HTML é uma página única, sem arquivos
externos; o PDF é gerado a partir do mesmo HTML pelo PyMuPDF (fitz.Story); o
CSV abre no Excel (UTF-8 com BOM; separador ";" em português, "," em inglês).
"""

from __future__ import annotations

import csv
import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence

import fitz

from app.i18n import language, tr
from app.services.text_diff import ADDED, CHANGED, REMOVED, ReportEntry

FORMATS = ("pdf", "html", "csv")


@dataclass
class PairReport:
    base: str            # nome do PDF base (referência ou anterior na cadeia)
    other: str           # nome do PDF comparado
    entries: List[ReportEntry] = field(default_factory=list)

    def counts(self) -> dict:
        out = {ADDED: 0, REMOVED: 0, CHANGED: 0}
        for e in self.entries:
            out[e.kind] += 1
        return out


@dataclass
class Report:
    created: str          # data e hora, já formatadas
    mode: str             # "Referência: v1.pdf" ou "Em cadeia"
    documents: List[str]
    pairs: List[PairReport]


def kind_label(kind: str) -> str:
    return {ADDED: tr("Incluído"), REMOVED: tr("Removido"), CHANGED: tr("Alterado")}.get(kind, kind)


def _page(value) -> str:
    return "" if value is None else str(value + 1)


def write_csv(path: Path | str, report: Report) -> None:
    delimiter = ";" if language() == "pt" else ","
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow([tr("Base"), tr("Comparado"), tr("Tipo"), tr("Página (base)"), tr("Texto (base)"),
                         tr("Página (comparado)"), tr("Texto (comparado)")])
        for pair in report.pairs:
            for e in pair.entries:
                writer.writerow([pair.base, pair.other, kind_label(e.kind),
                                 _page(e.page_a) if e.kind != ADDED else "", e.text_a,
                                 _page(e.page_b) if e.kind != REMOVED else "", e.text_b])


CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #202124; }
h1 { font-size: 16pt; margin: 0 0 4pt 0; }
h2 { font-size: 12pt; margin: 14pt 0 4pt 0; }
p.meta { color: #5f6368; margin: 0 0 2pt 0; }
table { border-collapse: collapse; width: 100%; }
th { background: #e8eaed; text-align: left; padding: 3pt 4pt; font-size: 9pt; }
td { border-top: 1px solid #dadce0; padding: 3pt 4pt; vertical-align: top; font-size: 9pt; }
td.page { text-align: right; white-space: nowrap; color: #5f6368; }
td.added { color: #137333; font-weight: bold; }
td.removed { color: #c5221f; font-weight: bold; }
td.changed { color: #1967d2; font-weight: bold; }
span.old { color: #c5221f; text-decoration: line-through; }
span.new { color: #137333; }
p.none { color: #5f6368; font-style: italic; }
"""


def to_html(report: Report, standalone: bool = True) -> str:
    e = html.escape
    parts = [f"<h1>{e(tr('Relatório de diferenças'))}</h1>",
             f"<p class='meta'>{e(report.mode)}</p>",
             f"<p class='meta'>{e(tr('PDFs'))}: {e(', '.join(report.documents))}</p>",
             f"<p class='meta'>{e(tr('Gerado em {date} pelo PDF Compare', date=report.created))}</p>"]
    for pair in report.pairs:
        c = pair.counts()
        parts.append(f"<h2>{e(pair.base)} &gt; {e(pair.other)}</h2>")
        parts.append("<p class='meta'>" + e(tr("{added} incluído(s) · {removed} removido(s) · {changed} alterado(s)",
                                               added=c[ADDED], removed=c[REMOVED], changed=c[CHANGED])) + "</p>")
        if not pair.entries:
            parts.append(f"<p class='none'>{e(tr('Texto idêntico.'))}</p>")
            continue
        parts.append("<table><tr>"
                     f"<th>{e(tr('Tipo'))}</th><th>{e(tr('Pág.'))}</th><th>{e(tr('Antes'))}</th>"
                     f"<th>{e(tr('Pág.'))}</th><th>{e(tr('Depois'))}</th></tr>")
        for entry in pair.entries:
            before = f"<span class='old'>{e(entry.text_a)}</span>" if entry.text_a else ""
            after = f"<span class='new'>{e(entry.text_b)}</span>" if entry.text_b else ""
            parts.append(
                f"<tr><td class='{entry.kind}'>{e(kind_label(entry.kind))}</td>"
                f"<td class='page'>{_page(entry.page_a) if entry.kind != ADDED else ''}</td><td>{before}</td>"
                f"<td class='page'>{_page(entry.page_b) if entry.kind != REMOVED else ''}</td><td>{after}</td></tr>")
        parts.append("</table>")
    body = "\n".join(parts)
    if not standalone:
        return body
    title = e(tr("Relatório de diferenças"))
    return (f"<!DOCTYPE html>\n<html lang='{language()}'><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{CSS} body {{ max-width: 1100px; margin: 24px auto; padding: 0 16px; }}</style>"
            f"</head><body>\n{body}\n</body></html>\n")


def write_html(path: Path | str, report: Report) -> None:
    Path(path).write_text(to_html(report), encoding="utf-8")


def write_pdf(path: Path | str, report: Report) -> None:
    story = fitz.Story(html=to_html(report, standalone=False), user_css=CSS)
    page_rect = fitz.paper_rect("a4")
    where = page_rect + (36, 36, -36, -36)
    writer = fitz.DocumentWriter(str(path))
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()


def write_report(path: Path | str, report: Report) -> str:
    """Grava no formato indicado pela extensão (.pdf, .html/.htm, .csv). Devolve o formato."""
    suffix = Path(path).suffix.lower().lstrip(".")
    fmt = "html" if suffix == "htm" else suffix
    if fmt not in FORMATS:
        raise ValueError(f"formato não suportado: {suffix}")
    {"pdf": write_pdf, "html": write_html, "csv": write_csv}[fmt](path, report)
    return fmt


def make_report(created: str, mode: str, documents: Sequence[str], pairs: Sequence[PairReport]) -> Report:
    return Report(created, mode, list(documents), list(pairs))
