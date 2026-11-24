"""Traduções para o inglês (chave = texto original em português).

Ao criar um texto novo com tr(), acrescente a tradução aqui: o teste
tests/test_i18n.py falha se algum texto ficar sem tradução.
"""

EN = {
    # --- legal / licença ---------------------------------------------------------
    "Arquivo de licença não encontrado: {name}": "License file not found: {name}",
    "Os autores do PDF Compare": "The PDF Compare authors",
    "AGPL-3.0 (ou licença comercial)": "AGPL-3.0 (or commercial license)",
    "PyInstaller (carregador)": "PyInstaller (bootloader)",
    "GPL-2.0 com exceção de carregador": "GPL-2.0 with bootloader exception",
    "Equipe PyInstaller": "PyInstaller team",
    "GNU AGPL v3 (licença deste programa e do PyMuPDF/MuPDF)": "GNU AGPL v3 (license of this program and of PyMuPDF/MuPDF)",
    "GNU LGPL v3 (Qt / PySide6)": "GNU LGPL v3 (Qt / PySide6)",
    "GNU GPL v3 (referenciada pela LGPL e pela AGPL)": "GNU GPL v3 (referenced by the LGPL and the AGPL)",
    "Python Software Foundation License (Python)": "Python Software Foundation License (Python)",
    "PyInstaller (GPL v2 com exceção para o carregador)": "PyInstaller (GPL v2 with bootloader exception)",
    "O código-fonte completo desta versão está no arquivo <b>{zip}</b>, na pasta do programa "
    "(botão <i>Abrir pasta do programa</i>, abaixo).":
        "The complete source code of this version is in the file <b>{zip}</b>, in the program folder "
        "(<i>Open program folder</i> button below).",
    "Na versão executável, o código-fonte completo acompanha o programa no arquivo <b>{zip}</b>.":
        "In the executable version, the complete source code comes with the program in the file <b>{zip}</b>.",
    "Licença e créditos": "License and credits",
    "Resumo": "Summary",
    "Componentes": "Components",
    "Textos das licenças": "License texts",
    "Abrir pasta do programa": "Open program folder",
    "As bibliotecas do Qt (LGPL) ficam como arquivos separados na pasta <i>_internal</i> e podem ser "
    "substituídas por versões compatíveis. Dê dois cliques em um componente para ver o texto da licença dele.":
        "The Qt libraries (LGPL) are kept as separate files in the <i>_internal</i> folder and can be "
        "replaced with compatible versions. Double-click a component to see its license text.",
    "Componente": "Component",
    "Versão": "Version",
    "Licença": "License",
    "Responsável": "Owner",

    # --- abertura de PDFs ----------------------------------------------------------
    "“{name}” não é um PDF.": "“{name}” is not a PDF.",
    "“{name}” não contém páginas.": "“{name}” has no pages.",
    "Não foi possível abrir “{name}”: arquivo inválido ou corrompido.":
        "Could not open “{name}”: invalid or corrupted file.",
    "“{name}” está protegido por senha.": "“{name}” is password protected.",
    "Senha incorreta para “{name}”.": "Wrong password for “{name}”.",
    "Senha incorreta para “{name}” ({n} tentativas). Abra o arquivo de novo para tentar outra vez.":
        "Wrong password for “{name}” ({n} attempts). Open the file again to try once more.",
    "“{name}” está protegido por senha.\n\nDigite a senha para abri-lo:":
        "“{name}” is password protected.\n\nEnter the password to open it:",
    "Senha incorreta. Tente novamente (tentativa {attempt} de {total}).\n\nSenha de “{name}”:":
        "Wrong password. Try again (attempt {attempt} of {total}).\n\nPassword for “{name}”:",
    "PDF protegido": "Protected PDF",
    "Abrir": "Open",
    "Pular este arquivo": "Skip this file",
    "Limite atingido": "Limit reached",
    "Já há {n} PDFs abertos. Feche um para adicionar outro.": "{n} PDFs are already open. Close one to add another.",
    "Não aberto (senha não informada): {names}": "Not opened (no password given): {names}",
    "Limite de {n} PDFs: não foram abertos — {names}.": "Limit of {n} PDFs: not opened — {names}.",
    "{n} arquivo ignorado por não ser PDF.": "{n} file ignored because it is not a PDF.",
    "{n} arquivos ignorados por não serem PDF.": "{n} files ignored because they are not PDFs.",
    "Alguns arquivos não foram abertos": "Some files were not opened",
    "Adicionar PDFs": "Add PDFs",
    "Documentos PDF (*.pdf)": "PDF documents (*.pdf)",
    "Escolher PDFs…": "Choose PDFs…",
    "Arraste seus PDFs para cá": "Drag your PDFs here",
    "Compare de 2 a 6 documentos lado a lado, pesquise em todos ao mesmo tempo\n"
    "e avance página por página — em todos juntos ou em cada um separadamente.":
        "Compare 2 to 6 documents side by side, search all of them at once\n"
        "and move page by page — all together or each one separately.",
    "Adicione outro PDF": "Add another PDF",
    "para comparar lado a lado": "to compare side by side",
    "Adicionar PDF…": "Add PDF…",
    "Solte para adicionar os PDFs à comparação.": "Drop to add the PDFs to the comparison.",

    # --- ações e menus --------------------------------------------------------------
    "&Adicionar PDFs…": "&Add PDFs…",
    "Adicionar PDFs à comparação": "Add PDFs to the comparison",
    "Abrir &pasta…": "Open &folder…",
    "Abrir os PDFs de uma pasta (até 6, em ordem de nome)": "Open the PDFs in a folder (up to 6, in name order)",
    "Abrir &sessão…": "Open &session…",
    "Reabrir um conjunto de PDFs salvo, com páginas e zoom": "Reopen a saved set of PDFs, with pages and zoom",
    "&Salvar sessão…": "&Save session…",
    "Salvar os PDFs abertos, as páginas e o zoom para reabrir depois":
        "Save the open PDFs, pages and zoom to reopen later",
    "&Exportar…": "&Export…",
    "Exportar a comparação ou as páginas atuais como PDF ou PNG": "Export the comparison or the current pages as PDF or PNG",
    "&Fechar todos": "&Close all",
    "Fechar todos os PDFs": "Close all PDFs",
    "Sai&r": "E&xit",
    "Sair do programa": "Exit the program",
    "Anterior": "Previous",
    "Página anterior em todos os PDFs": "Previous page in all PDFs",
    "Próxima": "Next",
    "Próxima página em todos os PDFs": "Next page in all PDFs",
    "Início": "Start",
    "Ir para o início de todos os PDFs": "Go to the start of all PDFs",
    "Fim": "End",
    "Ir para o fim de todos os PDFs": "Go to the end of all PDFs",
    "Realinhar": "Realign",
    "Desfazer ajustes individuais: todos voltam a mostrar a mesma página":
        "Undo individual adjustments: all go back to showing the same page",
    "&Pesquisar": "&Search",
    "Pesquisar em todos os PDFs": "Search all PDFs",
    "Próxima ocorrência": "Next match",
    "Ir para a próxima ocorrência em cada PDF": "Go to the next match in each PDF",
    "Ocorrência anterior": "Previous match",
    "Ir para a ocorrência anterior em cada PDF": "Go to the previous match in each PDF",
    "Comparar &texto": "Compare &text",
    "Destacar as diferenças de texto em relação ao primeiro PDF": "Highlight text differences from the first PDF",
    "Próxima diferença": "Next difference",
    "Ir para a próxima diferença de texto em cada PDF": "Go to the next text difference in each PDF",
    "Diferença anterior": "Previous difference",
    "Ir para a diferença de texto anterior em cada PDF": "Go to the previous text difference in each PDF",
    "&Destacar texto": "&Highlight text",
    "Arraste sobre o texto para destacá-lo": "Drag over the text to highlight it",
    "Adicionar &nota": "Add &note",
    "Clique na página para adicionar uma nota": "Click on the page to add a note",
    "Destacar": "Highlight",
    "Nota": "Note",
    "Reconhecer texto em PDFs escaneados (&OCR)": "Recognize text in scanned PDFs (&OCR)",
    "Usa o Tesseract OCR, se instalado, para pesquisar e comparar PDFs escaneados":
        "Uses Tesseract OCR, if installed, to search and compare scanned PDFs",
    "&Idioma do OCR…": "OCR &language…",
    "Ajustar à &largura": "Fit &width",
    "&Página inteira": "Whole &page",
    "&Aumentar zoom": "Zoom &in",
    "&Diminuir zoom": "Zoom &out",
    "Rolagem &vinculada": "&Linked scrolling",
    "Ao rolar a página de um PDF, os outros acompanham": "When you scroll one PDF, the others follow",
    "&Atalhos de teclado": "&Keyboard shortcuts",
    "&Licença e créditos…": "&License and credits…",
    "O que você pode fazer com este programa e licenças dos componentes":
        "What you can do with this program, and component licenses",
    "&Sobre": "&About",
    "&Arquivo": "&File",
    "Abertos &recentemente": "Open &recent",
    "&Navegar": "&Navigate",
    "&Exibir": "&View",
    "&Ferramentas": "&Tools",
    "A&juda": "&Help",
    "Barra principal": "Main toolbar",
    "Zoom de todos os PDFs (Ctrl + roda do mouse)": "Zoom of all PDFs (Ctrl + mouse wheel)",
    "Ajustar à largura": "Fit width",
    "Página inteira": "Whole page",
    "Pesquisa": "Search",

    # --- pesquisa e lista de ocorrências -------------------------------------------
    "Ocorrências": "Matches",
    "Lista de &ocorrências": "&Match list",
    "Mostrar a lista de ocorrências da pesquisa (Ctrl+Shift+F)": "Show the list of search matches (Ctrl+Shift+F)",
    "Lista": "List",
    "Preparando pesquisa… %p%": "Preparing search… %p%",
    "{hits} em {docs} de {total} — Enter vai para a próxima": "{hits} in {docs} of {total} — Enter goes to the next",
    "{n} ocorrência": "{n} match",
    "{n} ocorrências": "{n} matches",
    "{n} PDF": "{n} PDF",
    "{n} PDFs": "{n} PDFs",
    " · ainda lendo o texto dos PDFs…": " · still reading the PDFs' text…",
    "Nenhuma ocorrência encontrada": "No matches found",
    "Nenhuma ocorrência para navegar.": "No matches to navigate.",
    "&Pesquisar:": "&Search:",
    "Palavra ou frase — busca em todos os PDFs (Ctrl+F)": "Word or phrase — searches all PDFs (Ctrl+F)",
    "Ocorrência anterior em cada PDF (Shift+Enter ou Shift+F3)": "Previous match in each PDF (Shift+Enter or Shift+F3)",
    "Próxima ocorrência em cada PDF (Enter ou F3)": "Next match in each PDF (Enter or F3)",
    "Diferenciar maiúsculas e minúsculas": "Match case",
    "Somente palavras inteiras": "Whole words only",
    "Ignorar acentos (ação = acao)": "Ignore accents (é = e)",
    "Opções": "Options",
    "Opções de pesquisa": "Search options",
    "Digite algo na pesquisa para ver as ocorrências aqui.": "Type something in the search box to see the matches here.",
    "Lista de ocorrências da pesquisa": "List of search matches",
    "{n} ocorrência(s) de “{query}”. Clique para ir até ela.": "{n} match(es) for “{query}”. Click one to go to it.",
    "Nenhuma ocorrência de “{query}”.": "No matches for “{query}”.",
    "p. {page}  —  {snippet}": "p. {page}  —  {snippet}",
    "… e mais {n} (use ▲ ▼ no painel)": "… and {n} more (use ▲ ▼ in the pane)",

    # --- painel ---------------------------------------------------------------------
    "\nProtegido por senha (desbloqueado enquanto estiver aberto)": "\nPassword protected (unlocked while open)",
    "Página anterior somente neste PDF": "Previous page in this PDF only",
    "Próxima página somente neste PDF": "Next page in this PDF only",
    "Digite uma página e pressione Enter (somente neste PDF)": "Type a page and press Enter (this PDF only)",
    "Página atual deste PDF": "Current page of this PDF",
    "Ocorrências da pesquisa neste PDF": "Search matches in this PDF",
    "Ocorrência anterior neste PDF": "Previous match in this PDF",
    "Próxima ocorrência neste PDF": "Next match in this PDF",
    "Fechar este PDF": "Close this PDF",
    "nenhuma": "none",
    "Nenhuma ocorrência neste PDF": "No matches in this PDF",
    "{n} ocorr.": "{n} found",
    "{pos} de {n}": "{pos} of {n}",
    "{n} ocorrência(s) neste PDF — use ▼ para ir à próxima": "{n} match(es) in this PDF — use ▼ to go to the next",
    "Ocorrência {pos} de {n} neste PDF": "Match {pos} of {n} in this PDF",
    "Este PDF começa mais adiante.\nUse ▶ neste painel para trazê-lo para cá.":
        "This PDF starts further ahead.\nUse ▶ in this pane to bring it here.",
    "Fim do documento ({n} páginas).\nUse ◀ neste painel para voltar.":
        "End of document ({n} pages).\nUse ◀ in this pane to go back.",
    "Todos os PDFs realinhados na mesma página.": "All PDFs realigned to the same page.",

    # --- barra de status, atalhos e sobre ------------------------------------------
    "Abra ou arraste de 2 a 6 PDFs para começar  (Ctrl+O)": "Open or drag 2 to 6 PDFs to start  (Ctrl+O)",
    "Adicione pelo menos mais um PDF para comparar.": "Add at least one more PDF to compare.",
    "◀ ▶ ou setas do teclado: avançam todos juntos  ·  botões de cada painel: ajustam só aquele PDF  ·  "
    "Ctrl+F: pesquisar em todos":
        "◀ ▶ or arrow keys: move all together  ·  buttons in each pane: adjust only that PDF  ·  "
        "Ctrl+F: search all",
    "Atalhos de teclado": "Keyboard shortcuts",
    "Adicionar PDFs (ou arraste os arquivos para a janela)": "Add PDFs (or drag the files onto the window)",
    "Abrir todos os PDFs de uma pasta": "Open all PDFs in a folder",
    "Salvar sessão (PDFs, páginas e zoom)": "Save session (PDFs, pages and zoom)",
    "Exportar comparação ou páginas atuais (PDF/PNG)": "Export comparison or current pages (PDF/PNG)",
    "Início / fim de todos os PDFs": "Start / end of all PDFs",
    "Realinhar: todos na mesma página": "Realign: all on the same page",
    "Próxima ocorrência em cada PDF": "Next match in each PDF",
    "Ocorrência anterior em cada PDF": "Previous match in each PDF",
    "Mostrar/ocultar a lista de ocorrências": "Show/hide the match list",
    "Limpar a pesquisa (com o cursor na caixa de pesquisa)": "Clear the search (with the cursor in the search box)",
    "Comparar texto: destacar diferenças em relação ao 1º PDF": "Compare text: highlight differences from the 1st PDF",
    "Próxima / anterior diferença de texto em cada PDF": "Next / previous text difference in each PDF",
    "Destacar texto (arraste sobre o texto)": "Highlight text (drag over the text)",
    "Adicionar nota (clique na página)": "Add note (click on the page)",
    "Botão direito": "Right click",
    "Editar ou remover a anotação sob o cursor": "Edit or remove the annotation under the cursor",
    "Ctrl + roda do mouse": "Ctrl + mouse wheel",
    "Aumentar / diminuir zoom": "Zoom in / out",
    "Ajustar à largura / página inteira": "Fit width / whole page",
    "Sobre o {app}": "About {app}",
    "<p>Compare de 2 a 6 PDFs lado a lado, com pesquisa simultânea e navegação página a página.</p>"
    "<p>Os arquivos são processados apenas neste computador.</p>":
        "<p>Compare 2 to 6 PDFs side by side, with simultaneous search and page-by-page navigation.</p>"
        "<p>Files are processed only on this computer.</p>",
    '<p>{copyright}<br>Software livre sob a licença GNU AGPL v3.<br>Código-fonte: <a href="{url}">{url}</a></p>':
        '<p>{copyright}<br>Free software under the GNU AGPL v3 license.<br>Source code: <a href="{url}">{url}</a></p>',
    "Licença e créditos…": "License and credits…",

    # --- pasta, recentes e sessões --------------------------------------------------
    "Abrir os PDFs de uma pasta": "Open the PDFs in a folder",
    "Nenhum PDF": "No PDFs",
    "Não há arquivos PDF em “{name}”.": "There are no PDF files in “{name}”.",
    "Limpar lista": "Clear list",
    "  (sessão)": "  (session)",
    "Arquivo não encontrado": "File not found",
    "“{path}” não existe mais.": "“{path}” no longer exists.",
    "Salvar sessão": "Save session",
    "Sessão do PDF Compare (*{suffix})": "PDF Compare session (*{suffix})",
    "Sessão não salva": "Session not saved",
    "Sessão salva em “{name}”.": "Session saved to “{name}”.",
    "Abrir sessão": "Open session",
    "Sessão não aberta": "Session not opened",
    "Arquivos não encontrados": "Files not found",
    "Estes PDFs da sessão não foram encontrados:\n": "These PDFs from the session were not found:\n",
    "“{name}” não é um arquivo de sessão válido.": "“{name}” is not a valid session file.",
    "“{name}” foi criado por uma versão mais nova do programa.": "“{name}” was created by a newer version of the program.",
    "Não foi possível salvar a sessão: {error}": "Could not save the session: {error}",
    "Não foi possível ler “{name}”: {error}": "Could not read “{name}”: {error}",

    # --- anotações ------------------------------------------------------------------
    "Destacar: arraste sobre o texto. Ctrl+H de novo para sair.": "Highlight: drag over the text. Ctrl+H again to exit.",
    "Nota: clique no ponto da página. Ctrl+M de novo para sair.": "Note: click on the spot on the page. Ctrl+M again to exit.",
    "Anotação não salva": "Annotation not saved",
    "Não foi possível ler o arquivo para guardar a anotação.": "Could not read the file to store the annotation.",
    "Não foi possível gravar a anotação: {error}": "Could not save the annotation: {error}",
    "Arraste sobre o texto que deseja destacar.": "Drag over the text you want to highlight.",
    "Texto da nota:": "Note text:",
    "Editar texto da nota…": "Edit note text…",
    "Adicionar comentário…": "Add comment…",
    "Remover anotação": "Remove annotation",

    # --- comparação de texto --------------------------------------------------------
    "Comparando texto… aguardando a leitura dos PDFs": "Comparing text… waiting for the PDFs to be read",
    "Texto idêntico ao do 1º PDF": "Text identical to the 1st PDF",
    "Diferenças em relação a {name} — {parts}": "Differences from {name} — {parts}",
    "Nenhuma diferença de texto para navegar.": "No text differences to navigate.",

    # --- exportação -----------------------------------------------------------------
    "O que exportar": "What to export",
    "Comparação lado a lado (todos os PDFs em uma página)": "Side-by-side comparison (all PDFs on one page)",
    "Página atual de cada PDF (um arquivo por PDF)": "Current page of each PDF (one file per PDF)",
    "Cada PDF inteiro com as anotações (PDF, um arquivo por PDF)": "Each whole PDF with annotations (PDF, one file per PDF)",
    "PDF (texto continua selecionável)": "PDF (text stays selectable)",
    "PNG (imagem)": "PNG (image)",
    "Somente a posição atual": "Current position only",
    "Todas as páginas (uma página/imagem por posição)": "All pages (one page/image per position)",
    " dpi": " dpi",
    "Incluir minhas marcações (destaques, formas, textos e notas)": "Include my marks (highlights, shapes, text and notes)",
    "Formato:": "Format:",
    "Páginas:": "Pages:",
    "Resolução do PNG:": "PNG resolution:",
    "O PDF original nunca é alterado: a exportação cria arquivos novos.":
        "The original PDF is never changed: exporting creates new files.",
    "Exportar…": "Export…",
    "Exportar comparação": "Export comparison",
    "Pasta de destino": "Destination folder",
    "{n} arquivo exportado": "{n} file exported",
    "{n} arquivos exportados": "{n} files exported",
    " em {folder}": " to {folder}",
    "Exportação não concluída": "Export not completed",
    "Nenhum PDF para exportar.": "No PDF to export.",
    "Formato desconhecido: {fmt}": "Unknown format: {fmt}",
    "Não foi possível gravar “{name}”: {error}": "Could not write “{name}”: {error}",
    "{name} · página {page}": "{name} · page {page}",
    "(sem página nesta posição)": "(no page at this position)",

    # --- OCR ------------------------------------------------------------------------
    "OCR desativado: Tesseract OCR não encontrado.": "OCR turned off: Tesseract OCR not found.",
    "OCR indisponível": "OCR unavailable",
    "OCR desativado": "OCR turned off",
    "OCR ligado: páginas escaneadas serão reconhecidas (pode levar alguns segundos por página).":
        "OCR on: scanned pages will be recognized (may take a few seconds per page).",
    "nenhum (Tesseract não encontrado)": "none (Tesseract not found)",
    "Idioma do OCR": "OCR language",
    "Código do idioma do Tesseract (ex.: eng, por, eng+por).\nInstalados: {langs}":
        "Tesseract language code (e.g. eng, por, eng+por).\nInstalled: {langs}",
    "“{name}” parece escaneado (sem texto). Ative Ferramentas › OCR para pesquisar nele.":
        "“{name}” seems to be scanned (no text). Turn on Tools › OCR to search it.",
    "Para usar o OCR, instale o Tesseract OCR (para Windows: instalador da UB Mannheim, "
    "https://github.com/UB-Mannheim/tesseract/wiki) e marque os idiomas desejados durante a "
    "instalação (o inglês já vem incluído). Se ele foi instalado em outra pasta, defina a "
    "variável de ambiente TESSDATA_PREFIX com o caminho da pasta “tessdata”. Depois, "
    "reinicie o programa.":
        "To use OCR, install Tesseract OCR (for Windows: the UB Mannheim installer, "
        "https://github.com/UB-Mannheim/tesseract/wiki) and select the languages you need during "
        "installation (English is already included). If it was installed in another folder, set the "
        "TESSDATA_PREFIX environment variable to the path of the “tessdata” folder. Then restart "
        "the program.",
    "OCR disponível.": "OCR available.",
    "Tesseract OCR não encontrado.": "Tesseract OCR not found.",
    "Falha no OCR: {error}": "OCR failed: {error}",
    "O Tesseract OCR não foi encontrado neste computador.": "Tesseract OCR was not found on this computer.",
    "O Tesseract foi encontrado, mas falta o idioma “{missing}”.\nIdiomas instalados: {langs}.":
        "Tesseract was found, but the “{missing}” language is missing.\nInstalled languages: {langs}.",
    "nenhum": "none",
    # --- v0.3.0: Configurações e marcações ---
    '&Configurações…':
        '&Settings…',
    '&Copiar marcação':
        '&Copy mark',
    '&Desfazer':
        '&Undo',
    '&Excluir marcação':
        '&Delete mark',
    '&Marcações':
        '&Marks',
    '&Refazer':
        '&Redo',
    '&Selecionar e mover':
        '&Select and move',
    "<p>Comparar texto: <span style='color:{added}'>■</span> incluído, <span style='color:{removed}'>■</span> removido, <span style='color:{changed}'>■</span> alterado (cores em Ferramentas › Configurações).</p>":
        "<p>Compare text: <span style='color:{added}'>■</span> added, <span style='color:{removed}'>■</span> removed, <span style='color:{changed}'>■</span> changed (colors in Tools › Settings).</p>",
    '<p>Em cada painel: <b>◀ ▶</b> mudam só aquele PDF, <b>▲ ▼</b> navegam pelas ocorrências dele e o campo de página permite digitar o número.</p>':
        '<p>In each pane: <b>◀ ▶</b> change only that PDF, <b>▲ ▼</b> go through its matches and the page field lets you type a number.</p>',
    'A troca de idioma vale depois de reiniciar o programa.':
        'The new language takes effect after restarting the program.',
    'Alterado':
        'Changed',
    'Aplicar o estilo atual':
        'Apply current style',
    'Aprovado':
        'Approved',
    'Balão':
        'Callout',
    'Balão: arraste do ponto indicado até onde fica o texto':
        'Callout: drag from the point to where the text goes',
    'Barra de &marcação':
        '&Markup toolbar',
    'Barra de marcação':
        'Markup toolbar',
    'Caixa de texto':
        'Text box',
    'Caixa de texto: arraste para definir a área (ou clique)':
        'Text box: drag to set the area (or click)',
    'Cancelar':
        'Cancel',
    'Cancelar o desenho, desmarcar ou voltar à seleção':
        'Cancel drawing, deselect or go back to selecting',
    'Caneta':
        'Pen',
    'Caneta: desenhe à mão livre':
        'Pen: draw freehand',
    'Carimbo':
        'Stamp',
    'Carimbo “{stamp}”: clique na página. Esc para sair.':
        'Stamp “{stamp}”: click on the page. Esc to exit.',
    'Carimbo: escolha o texto e clique na página':
        'Stamp: choose the text and click on the page',
    'Co&lar marcação':
        '&Paste mark',
    'Colar a marcação copiada na página à vista do painel':
        'Paste the copied mark on the page shown in the pane',
    'Confidencial':
        'Confidential',
    'Configurações':
        'Settings',
    'Copiar':
        'Copy',
    'Copiar, colar ou excluir a marcação selecionada':
        'Copy, paste or delete the selected mark',
    'Cor':
        'Color',
    'Cor do contorno e do texto':
        'Outline and text color',
    'Cor do destaque':
        'Highlight color',
    'Desfazer / refazer alterações nas marcações':
        'Undo / redo changes to marks',
    'Desfazer a última alteração nas marcações':
        'Undo the last change to marks',
    'Destacar texto: arraste sobre o texto':
        'Highlight text: drag over the text',
    'Destaque':
        'Highlight',
    'Divergência':
        'Discrepancy',
    'Duplo clique':
        'Double-click',
    'E&ditar':
        '&Edit',
    'Editar o texto da marcação':
        'Edit the mark’s text',
    'Editar texto…':
        'Edit text…',
    'Elipse':
        'Ellipse',
    'Elipse: arraste na página':
        'Ellipse: drag on the page',
    'Esc para sair.':
        'Esc to exit.',
    'Escolher cor…':
        'Choose color…',
    'Espessura':
        'Width',
    'Espessura do contorno':
        'Outline width',
    'Este painel não tem página nesta posição.':
        'This pane has no page at this position.',
    'Fonte':
        'Font',
    'Geral':
        'General',
    'Idiomas instalados: {langs}. Use + para combinar (ex.: eng+por).':
        'Installed languages: {langs}. Use + to combine (e.g. eng+por).',
    'Idiomas, cores da comparação e estilo das marcações':
        'Languages, comparison colors and mark style',
    'Incluído':
        'Added',
    'Incluído · removido · alterado, em relação ao primeiro PDF (cores em Ferramentas › Configurações). F7 vai para a próxima diferença.':
        'Added · removed · changed, relative to the first PDF (colors in Tools › Settings). F7 goes to the next difference.',
    'Linha':
        'Line',
    'Linha: arraste na página':
        'Line: drag on the page',
    'Lista de &marcações':
        '&Marks list',
    'Lista de marcações':
        'Marks list',
    'Marcação copiada. Ctrl+V cola na página à vista.':
        'Mark copied. Ctrl+V pastes it on the page shown.',
    'Marcações':
        'Marks',
    'Mostrar a lista de todas as marcações (Ctrl+Shift+M)':
        'Show the list of all marks (Ctrl+Shift+M)',
    'Mostrar só um tipo de marcação':
        'Show only one type of mark',
    'Mostrar só uma cor':
        'Show only one color',
    'Mostrar/ocultar a lista de marcações':
        'Show/hide the marks list',
    'Nenhuma marcação ainda. Use a barra de marcação para destacar, desenhar ou escrever.':
        'No marks yet. Use the markup toolbar to highlight, draw or write.',
    'Nota: clique no ponto da página':
        'Note: click on the spot on the page',
    'Ondulado':
        'Squiggly',
    'Opacidade':
        'Opacity',
    'Outro texto…':
        'Other text…',
    'Polígono':
        'Polygon',
    'Polígono: clique em cada vértice e dê duplo clique para terminar (Esc cancela)':
        'Polygon: click each vertex and double-click to finish (Esc cancels)',
    'Preench.':
        'Fill',
    'Preenchimento das formas':
        'Shape fill',
    'Refazer a alteração desfeita':
        'Redo the undone change',
    'Rejeitado':
        'Rejected',
    'Removido':
        'Removed',
    'Restaurar cores padrão':
        'Restore default colors',
    'Restaurar estilo padrão':
        'Restore default style',
    'Retângulo':
        'Rectangle',
    'Retângulo: arraste na página':
        'Rectangle: drag on the page',
    'Revisar':
        'Review',
    'Selecionar, mover e redimensionar marcações (duplo clique edita o texto)':
        'Select, move and resize marks (double-click edits the text)',
    'Sem preenchimento':
        'No fill',
    'Seta':
        'Arrow',
    'Seta: arraste do início até a ponta':
        'Arrow: drag from the start to the tip',
    'Sublinhado':
        'Underline',
    'Sublinhado ondulado: arraste sobre o texto':
        'Squiggly underline: drag over the text',
    'Sublinhar texto: arraste sobre o texto':
        'Underline text: drag over the text',
    'Tachado':
        'Strikeout',
    'Tachar texto: arraste sobre o texto':
        'Strike out text: drag over the text',
    'Tamanho da fonte':
        'Font size',
    'Tamanho da fonte das caixas de texto, balões e carimbos':
        'Font size for text boxes, callouts and stamps',
    'Texto do carimbo:':
        'Stamp text:',
    'Texto:':
        'Text:',
    'Todas as cores':
        'All colors',
    'Todos os tipos':
        'All types',
    'p. {page}  —  {kind}':
        'p. {page}  —  {kind}',
    '{n} marcação(ões). Clique para ir até ela.':
        '{n} mark(s). Click to go to it.',
    # --- v0.3.0: comparação em lotes ---
    ' dias':
        ' days',
    ' páginas':
        ' pages',
    'Ao clicar em “Comparar próximo lote”':
        'When I click “Compare next batch”',
    'Apagar as não usadas após':
        'Delete unused results after',
    'Automaticamente, em segundo plano':
        'Automatically, in the background',
    'Cancelar a comparação em andamento (os lotes prontos continuam)':
        'Cancel the comparison in progress (finished batches are kept)',
    'Comparando texto…':
        'Comparing text…',
    'Comparar este lote':
        'Compare this batch',
    'Comparar o próximo lote':
        'Compare the next batch',
    'Comparar o próximo lote de páginas e ir até ele':
        'Compare the next batch of pages and go to it',
    'Comparar próximo lote':
        'Compare next batch',
    'Comparar próximo lote ▶':
        'Compare next batch ▶',
    'Comparação':
        'Comparison',
    'Comparação cancelada. Os lotes já comparados continuam valendo.':
        'Comparison canceled. Batches already compared are kept.',
    'Comparação em lotes':
        'Batch comparison',
    'Comparações salvas (cache)':
        'Saved comparisons (cache)',
    'Cores':
        'Colors',
    'Limpar cache agora':
        'Clear cache now',
    'Lote ainda não comparado — use “Comparar este lote” (F8)':
        'Batch not compared yet — use “Compare this batch” (F8)',
    'Lote anterior':
        'Previous batch',
    'Lote {n} de {total} · páginas {first}–{last}':
        'Batch {n} of {total} · pages {first}–{last}',
    'Lotes já comparados são reaproveitados ao reabrir os mesmos PDFs.':
        'Batches already compared are reused when the same PDFs are opened again.',
    'Lotes preparados à frente':
        'Batches prepared ahead',
    'Nunca':
        'Never',
    'Pausar enquanto eu rolo as páginas ou faço marcações':
        'Pause while I scroll pages or add marks',
    'Páginas por lote':
        'Pages per batch',
    'Todos':
        'All',
    'Tudo de uma vez':
        'All at once',
    'Voltar ao lote de páginas anterior':
        'Go back to the previous batch of pages',
    '{n} resultado(s) salvos · {size}':
        '{n} saved result(s) · {size}',
    'comparando…':
        'comparing…',
    'não comparado':
        'not compared',
    '{done} de {total} lotes comparados':
        '{done} of {total} batches compared',
    'Próximo lote ▶':
        'Next batch ▶',
}
