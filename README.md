# PDF Compare

**English** · [Português](README.pt-BR.md)

A Windows app that shows **2 to 6 PDFs side by side**, searches all of them at once and moves
page by page through all of them together or through each one separately.
It also highlights text differences between versions, lets you mark up pages (highlights,
shapes, text boxes, callouts, stamps and notes) without changing the files, and exports the
comparison as PDF or PNG. Files are processed only on your computer.

Source code: <https://github.com/PedroHTF/pdf-compare>

Like it? [☕ Buy the author a coffee](https://www.buymeacoffee.com/phtf)

## Download

Get the latest version from **[Releases](https://github.com/PedroHTF/pdf-compare/releases/latest)**:

- `PDFCompare-Setup-<version>.exe`: Windows installer (recommended). Adds a Start Menu shortcut,
  appears in "Open with" for PDFs and opens `.pdfcompare` session files with a double-click.
- `PDFCompare-<version>-portable.zip`: portable version; extract it and run `PDFCompare.exe`.
- `codigo-fonte-PDFCompare-<version>.zip`: complete source code (AGPL-3.0).

On first run, Windows SmartScreen may warn that the program is not recognized (it has no paid
code-signing certificate): click **More info › Run anyway**.

The interface is available in English and Portuguese. On first run it follows the Windows
language (Portuguese if Windows is in Portuguese, English otherwise). To switch, use
**Tools › Idioma / Language** or **Edit › Settings…** and restart the program.

## How to use

| I want to… | How |
|---|---|
| Open PDFs | Drag the files onto the window, or **Add PDFs…** (Ctrl+O). Up to 6. |
| Open a whole folder | **File › Open folder…** (Ctrl+Shift+O): opens the folder's PDFs in name order (up to 6) |
| Reopen files used before | **File › Open recent** (PDFs and sessions) |
| Save and resume my work | **File › Save session…** (Ctrl+S) stores the PDFs, each one's page and the zoom in a `.pdfcompare` file. **Open session…** restores everything |
| Open a password-protected PDF | The program asks for the password (3 attempts). **Skip this file** opens the others. The password is not stored. |
| Move **all** PDFs forward/back | **◀ Previous / Next ▶** on the toolbar, or ← → / Page Up / Page Down |
| Move **one** PDF only | **◀ ▶** in the pane header, or type the page number in the pane's field |
| Undo per-PDF adjustments | **Realign** (Ctrl+L): all PDFs show the same page again |
| Search all PDFs | Type in the **Search** box (Ctrl+F). Each pane shows how many matches it has |
| Go to the next match in **all** PDFs | Enter or F3 (Shift+Enter / Shift+F3 goes back) |
| Go to the next match in **one** PDF | **▲ ▼** on the pane's yellow label |
| See all matches in a list | **Match list** (Ctrl+Shift+F): snippet and page of each one; click to go there |
| See text differences | **Compare text** (Ctrl+D). F7 / Shift+F7 go to the next / previous difference |
| See differences in images, signatures, stamps or scanned pages | **Tools › Visual difference** (Ctrl+Shift+V): different areas get a dashed outline. Works with or without **Compare text**; sensitivity in **Settings › Comparison** |
| Get the list of changes | **File › Difference report…** (Ctrl+Shift+R): page, text before and after, as PDF, HTML or CSV |
| Choose the reference PDF | Right-click a PDF › **Use as comparison reference**, or **Tools › Comparison reference** |
| Compare each version with the previous one | **Tools › Comparison reference › In a chain** (v1→v2→v3) |
| Align pages by content | **Align by content** (Ctrl+Shift+L): added or removed pages appear with an empty pane next to them. A pane’s ◀ ▶ choose which page sits next to the reference; **Realign** undoes it |
| See all pages in sequence | **Continuous scrolling** (Ctrl+Shift+C) |
| Adjust the alignment in continuous scrolling | Drag the handle below a space; right-click › **Insert space here**, **Remove this space** or **Align this passage with…** (then click the matching passage in another PDF) |
| Compare large PDFs in parts | Comparison runs in batches of pages (default: 50). **Compare next batch ▶** (F8) on the status bar; Shift+F8 goes back |
| Highlight, underline or strike out text | Pick the tool on the **markup toolbar** (Highlight: Ctrl+H) and drag over the text |
| Draw a rectangle, ellipse, line, arrow or freehand | Pick the tool and drag on the page |
| Draw a polygon | Click each vertex and double-click to finish (Esc cancels) |
| Write on the page | **Text box** (drag the area) or **Callout** (drag from the point to where the text goes) |
| Stamp ("Approved", "Review"…) | **Stamp**: the arrow next to it picks the text or lets you type another one |
| Add a note | **Note** (Ctrl+M) and click on the page. Hover over the note to read it |
| Move, resize or edit | **Select** tool (or Esc): drag the mark or its corner handles; double-click edits the text |
| Copy, paste, delete | Ctrl+C, Ctrl+V (pastes on the page shown), Delete. Right-click shows the options |
| Undo / redo | Ctrl+Z / Ctrl+Y |
| Change color, fill, width, opacity, font | Markup toolbar: applies to the next marks and to the selected one |
| See all marks | **View › Marks list** (Ctrl+Shift+M), filtered by type and color |
| Settings (languages, colors, default style) | **Edit › Settings…** (Ctrl+,) |
| Export | **Export…** (Ctrl+E): side-by-side comparison (current position or all), current page of each PDF, or each PDF with its marks. PDF or PNG |
| Search scanned PDFs | **Tools › Recognize text in scanned PDFs (OCR)**, requires Tesseract (see below) |
| Zoom | Ctrl + mouse wheel, Ctrl++ / Ctrl+-, or the zoom list (width, whole page, %) |
| Linked scrolling | **Linked scrolling** (on by default): scrolling one PDF scrolls the others |
| See all shortcuts | F1 |
| Know about new versions | The program shows a notice on the status bar (at most once a day; turn it off in **Edit › Settings… › General**). **Help › Check for updates now** checks right away |

**Navigation model.** All PDFs share one position. A pane's buttons shift only that document.
After that, moving all PDFs together keeps the offset, so you can compare versions with extra
or missing pages. When a PDF has no page at that position, the pane says so and shows how to
bring it back.

**Search.** By default it ignores case and accents ("acao" finds "Ação"). Under **Options** you
can match case, require whole words or match accents. It also finds phrases and words
hyphenated across lines. Scanned (image-only) PDFs become searchable with OCR on.

**Compare text.** The first PDF opened is the reference; each of the others is compared with it,
word by word. Default colors: **green** = added, **red** (struck through) = removed,
**blue** = changed. The comparison ignores line and page breaks (text that only moved to another
page is not a difference) and punctuation at the edges of words; case and accents count. The
status bar shows the total per PDF. Colors can be changed in **Edit › Settings… › Comparison**.

**Visual difference (optional).** Compares how pages look, pixel by pixel: renders both pages in
grayscale, computes the difference and groups the changed areas. It finds what the text comparison
cannot see (images, signatures, stamps, drawn tables, scanned PDFs without OCR). It is computed for the
pages shown and kept in memory; sensitivity (1–100 %) and color are in **Settings › Comparison**.

**Difference report.** Lists each text change (added, removed, changed) with the pages and the text
before and after, for each comparison (reference or chain). **PDF** to send or print, **HTML** to open in
a browser and **CSV** for Excel.

**Reference and chain.** By default each PDF is compared with the first one. You can choose another
PDF as the reference (a **Reference** badge in its header) or compare **in a chain**: the 2nd with
the 1st, the 3rd with the 2nd, and so on.

**Align by content.** The PDFs' text lines are compared in order and each page sits next to the
reference page it shares the most lines with. Pages that exist in only one PDF appear with an empty
pane, with an explanation, in the others. Heavily changed or text-less pages are paired by similarity
and order. Manual adjustments (pane ◀ ▶, typed page, spaces and passages) are saved for those PDFs
(by content) and come back when they are opened again; **Realign** undoes them all.

**Continuous scrolling.** Shows pages one below the other (**View › Continuous scrolling**). With
content alignment on, **alignment spaces** the size of the added or removed content are inserted
where it would be, so matching passages sit at the same height in every PDF. When pages break at
different points, spaces are also inserted at the breaks. When the automatic alignment gets it wrong
(e.g. scanned PDFs), drag a space's handle, insert or remove a space, or use **Align this passage
with…**; a manually adjusted space lasts until the next matching passage.

**Batch comparison.** With large PDFs the comparison is split into batches of pages of the first
PDF (the others follow each pane's alignment). The status bar shows "Batch 2 of 8 · pages 51–100",
with **◀** and **Compare next batch ▶** (F8). It runs in the background, with progress and a
**Cancel** button, without freezing the program. In **Edit › Settings… › Comparison**:
- **Pages per batch** (or "All at once");
- **Compare the next batch:** when you click, or automatically in the background, choosing how
  many batches to prepare ahead and whether to pause while you scroll or add marks;
- **When the alignment changes** (pane ◀ ▶, typed page or Realign): the program waits until you
  finish adjusting and shows **Recompare** on the batch bar; until then the current comparison
  stays on screen. You can also choose to recompare automatically. Batches with the same pages
  come from the cache, and going to the next difference (F7) never redoes the comparison;
- **Saved comparisons:** compared batches are stored (`%APPDATA%\PDFCompare\PDF Compare\comparacoes`),
  identified by the PDFs' content, and reused when the same files are opened again. Unused ones
  are deleted after N days (or never); **Clear cache now** deletes everything.

**Marks.** Highlights, shapes, text, stamps and notes are stored in the program's data folder
(`%APPDATA%\PDFCompare\PDF Compare\anotacoes`), one file per document, identified by the PDF's
content, so they come back even if the file is renamed or moved. **The original PDF is never
changed.** To take the marks with you, use **Export… › Each whole PDF with annotations** (creates a
new PDF with real annotations, editable in other readers) or check **Include my marks** in
the other export options.

**Export.** In PDF the text stays selectable; PNG creates one image per position
(`comparacao_001.png`, `comparacao_002.png`…) at the chosen resolution.

**OCR (optional).** Uses [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) through
PyMuPDF. It does not ship with the program: install it separately (on Windows, the
[UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) installer); English is included and,
for PDFs in Portuguese, also select the **Portuguese** language during installation.
The program looks for Tesseract in the `TESSDATA_PREFIX` variable and in the default install folders.
The default OCR language is English, `eng` (change it in **Edit › Settings…** or
**Tools › OCR language…**, for example `por` or `eng+por`).
Only pages with images and no text go through OCR, which takes a few seconds per page; the
result is used for searching and comparing, and the PDF is not changed. Without Tesseract, the
program says so and keeps working normally.

## License

Free software under the **GNU AGPL v3 or later** (file [LICENSE](LICENSE)). This license is
required because the program uses PyMuPDF/MuPDF, which is AGPL. In the program: **Help › License and credits…**.

- **You may:** use it for any purpose (including commercial), study, modify and distribute it, free or paid.
- **When distributing:** provide the complete source code, keep the copyright notices and the
  license, and keep modified versions under the AGPL. Using without distributing creates no obligation.
- **How to comply:** `build.ps1` already puts `LICENCA.txt` and `codigo-fonte-PDFCompare-<version>.zip`
  inside `dist\PDFCompare`. If you distribute the whole folder, the source code goes with it.
  The code is also published at <https://github.com/PedroHTF/pdf-compare>, and the link appears
  in the program (**About** and **License and credits**).
- **Authorship:** replace "Os autores do PDF Compare" with your name in `app/__init__.py` (`__author__`).

Third-party components and licenses: PyMuPDF/MuPDF (AGPL-3.0), PySide6/Qt (LGPL-3.0), Python (PSF)
and the PyInstaller bootloader (GPL-2.0 with exception). Full texts are in `licenses/`.
Tesseract OCR (Apache-2.0) is optional, installed by the user and not distributed with the program.
The exact versions used in the build are in `requirements-lock.txt`.

## Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m app.main                      # run
python -m app.main a.pdf b.pdf          # run opening files
python -m app.main work.pdfcompare      # run opening a saved session
python -m pytest                        # tests (logic and UI, no windows shown)
                                        # real OCR tests only run if Tesseract is installed
```

### Build the executable

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

The build runs the tests first and creates `dist\PDFCompare\PDFCompare.exe`. To distribute,
copy the whole `dist\PDFCompare` folder.

### Build the installer

With [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed, after `build.ps1`:

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.3.0 installer.iss
```

The installer goes to `dist\installer\`.

### Publish a version

GitHub builds everything (`.github/workflows/release.yml`): tests, executable, installer,
portable package and source code. To release:

1. Update `__version__` in `app/__init__.py`, write the changes in `CHANGELOG.md` (a `## [version]`
   section, which becomes the Release text) and merge into `main`.
2. Create and push the tag with the same number:
   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```
3. A few minutes later the Release appears under **Releases** with the files to download.
   If the tag does not match `__version__`, the workflow stops with an error.

On each pull request the same workflow runs without publishing; the generated files are under
**Actions › (run) › Artifacts**, for testing before the release.

### Structure

```
app/
  main.py                  entry point
  model/session.py         open PDF (file + alignment offset)
  services/navigation.py   global position, per-PDF adjustments, matches (no Qt)
  services/text_index.py   word extraction with positions, text normalization
  services/search.py       word and phrase search
  services/indexer.py      background indexing without freezing the UI (and OCR, if on)
  services/text_diff.py    word-by-word text comparison
  services/diff_batches.py page batches and on-disk cache of comparisons
  services/batch_runner.py runs batches in the background
  services/content_align.py content alignment (matching pages and lines) and manual adjustments
  services/strip_layout.py continuous-scrolling layout with alignment spaces
  services/visual_diff.py  visual (pixel-by-pixel) difference between pages
  services/report.py       difference report as PDF, HTML and CSV
  services/updates.py      new-version notice (checks the latest GitHub Release)
  services/annotations.py  marks (highlights, shapes, text, stamps, notes) kept outside the PDF; annotated PDF
  services/preferences.py  comparison colors and default mark style
  services/export.py       side-by-side and current-page export (PDF/PNG)
  services/workspace.py    open folder, recent files and sessions (.pdfcompare)
  services/ocr.py          optional OCR with Tesseract (detection and recognition)
  i18n.py                  UI language (tr); i18n_en.py has the English translations
  ui/main_window.py        window, menus, toolbars, grid, drag and drop
  ui/pane.py               one PDF's pane (rendering, marks, controls)
  ui/continuous.py         continuous-scrolling canvas (pages cut at the spaces)
  ui/search_bar.py         search bar
  ui/results_panel.py      match list (snippet + page)
  ui/marks_panel.py        marks list with filters
  ui/mark_widgets.py       color button and mark style bar
  ui/settings_dialog.py    Settings window
  ui/export_dialog.py      export dialog
  ui/widgets.py            helper components
  ui/style.py              styles (light and dark theme)
  ui/resources.py          access to the icon and logo
  resources/logo.svg       logo (source); app.ico and logo_256.png are generated from it
  legal.py                 license data and third-party components
  ui/license_dialog.py     "License and credits" window
tools/make_icon.py         regenerates app.ico and logo_256.png after editing logo.svg
installer.iss              installer configuration (Inno Setup)
.github/workflows/         automatic build and Release publishing
tools/make_source_zip.py   builds the source package that ships with the .exe
licenses/                  full license texts (AGPL, LGPL, GPL, PSF, PyInstaller)
tests/                     tests for each service and the UI
samples/                   sample PDFs
```

### Technical decisions

- **PyMuPDF** for rendering and extracting text with coordinates (needed for highlighting).
- Indexing runs in time slices on the main thread, because PyMuPDF does not support multiple
  threads. The UI stays responsive and search already works on the indexed pages, updating when
  indexing finishes.
- Only the visible page is rendered, with a small per-pane cache and sharp output on high-DPI screens.
- Preferences (zoom, search options, window size, last folder, side lists, recent files, OCR,
  mark colors and style) are saved between runs.
- Text comparison works on two levels (lines, then words inside the differing lines) with
  `difflib`, so it stays fast on long documents. It runs in a worker thread on the already
  extracted words (never PyMuPDF), batch by batch, with results cached on disk.
- Source-code strings are written in Portuguese and go through `tr()`; English translations
  are in `app/i18n_en.py`. `tests/test_i18n.py` fails if any string is left untranslated.
- All core logic (differences, marks, export, sessions, OCR) lives in `app/services`, without
  Qt, and is tested directly.
