# Novidades / Changelog

Cada versão tem um `### Resumo` (português) e um `### Summary` (inglês) curtos: eles viram o texto
"O que mudou" / "What's new" da Release no GitHub (`tools/release_notes.py`). Os detalhes vêm depois.

## [0.4.0] — 2026-11

### Resumo

- **Alinhamento corrigido e com mais controle:** remover um espaço agora o remove de fato; espaços podem ser **travados** (o alinhamento automático não os muda nem recria); e **Alinhar seleções** (Ctrl+Shift+A) força dois trechos escolhidos por você a ficarem lado a lado.
- **Escolha o que comparar:** cabeçalho, rodapé e laterais podem ficar de fora. O cabeçalho e o rodapé são detectados ao abrir os PDFs, e as linhas se ajustam arrastando na própria página. Páginas inteiras (capa, índice) também podem ser ignoradas.
- **A comparação segue o seu alinhamento:** trechos e páginas que você alinhou à mão são comparados entre si.
- **Comparar só a página atual:** pelo menu ▾ do botão Comparar texto; acompanha quando você muda de página.
- **Uma página por vez:** a roda do mouse passa para a página seguinte ao chegar ao fim (quantos dentes, nas Configurações).

### Summary

- **Alignment fixed and more control:** removing a space really removes it; spaces can be **locked**; **Align selections** (Ctrl+Shift+A) lines up two passages you choose.
- **Choose what to compare:** leave out header, footer and sides (header/footer detected automatically, lines draggable on the page) and whole pages such as covers or contents.
- **The comparison follows your manual alignment.**
- **Compare only the current page**, following as you navigate.
- **One page at a time:** the mouse wheel turns to the next page at the end (number of notches in Settings).

### Português

**Alinhamento por conteúdo (rolagem contínua)**
- Correção: remover um espaço de alinhamento agora o remove de fato. Antes, o alinhamento automático
  recriava o espaço logo abaixo (na âncora seguinte) e podia sobrar uma faixa laranja. Agora a diferença
  é aceita até os PDFs voltarem a coincidir sozinhos. Diminuir um espaço pela alça segue a mesma regra.
- Travar espaços (botão direito › Travar este espaço / Remover e travar este espaço): um espaço travado
  não é alterado nem recriado pelo alinhamento automático, não se arrasta por engano e continua depois
  de "Realinhar". Aparece com um cadeado; Navegar › Destravar todos os espaços desfaz.
- Alinhar seleções (Ctrl+Shift+A): arraste sobre um trecho em um PDF e depois sobre o trecho
  correspondente em outro. O início e o fim dos dois trechos ficam na mesma altura, com prioridade sobre
  o alinhamento automático. Os trechos alinhados ganham uma barra verde na margem; botão direito sobre
  eles desfaz.

**O que entra na comparação**
- Ignorar cabeçalho e/ou rodapé (Configurações › Comparação): faixas no topo e na base de cada página,
  em % da altura, ficam fora da comparação de texto, do relatório, da diferença visual e do alinhamento
  por conteúdo. Aparecem sombreadas nas páginas.
- Ignorar páginas (botão direito na página › Ignorar esta página na comparação, ou Ferramentas › Páginas
  ignoradas na comparação…, ex.: "1-3, 7"): para capa, índice etc. Lembradas ao reabrir o mesmo PDF.
- A comparação segue o alinhamento feito à mão (opção, ligada por padrão): cada trecho alinhado por
  seleção (ou página fixada ao lado da referência) é comparado com o trecho correspondente.
- Comparar só a página atual: menu ▾ do botão "Comparar texto" (ou Ferramentas › Abrangência da
  comparação). A comparação acompanha quando você muda de página.

- Faixas na própria página: com a comparação ligada, as linhas do cabeçalho e do rodapé podem ser
  arrastadas na página (a partir da borda, para criar uma faixa).
- Cabeçalho e rodapé detectados ao abrir os PDFs: texto que se repete no topo e na base das páginas
  (números trocados, ex.: "Página 3 de 10"), até 40% do topo e da base. Pode ser desligado em
  Configurações › O que comparar.
- Faixas nas laterais (esquerda e direita), desligadas por padrão.

**Visualização**
- Uma página por vez: rolar com a roda do mouse além do fim da página abre a seguinte (e além do início,
  a anterior, mostrando o fim dela). Exibir › Rolar para a próxima página liga/desliga; em Configurações ›
  Geral, escolha quantos dentes da roda (1 a 10) passam de página.

### English

**Content alignment (continuous scrolling)**
- Fix: removing an alignment space now really removes it. Previously, automatic alignment recreated it
  just below (at the next anchor) and an orange strip could be left behind. The difference is now
  accepted until the PDFs line up again on their own. Shrinking a space with its handle follows the same rule.
- Lock spaces (right-click › Lock this space / Remove and lock this space): a locked space is not changed
  or recreated by automatic alignment, can't be dragged by accident and is kept by "Realign". It shows a
  padlock; Navigate › Unlock all spaces undoes it.
- Align selections (Ctrl+Shift+A): drag over a passage in one PDF, then over the matching passage in
  another. The start and end of both passages are lined up, overriding automatic alignment. Aligned
  passages get a green bar in the margin; right-click on it to undo.

**What is compared**
- Ignore header and/or footer (Settings › Comparison): bands at the top and bottom of every page, in % of
  its height, are left out of the text comparison, the report, the visual difference and content
  alignment. They are shaded on the pages.
- Ignore pages (right-click a page › Ignore this page in the comparison, or Tools › Ignored pages…,
  e.g. "1-3, 7"): for covers, tables of contents etc. Remembered when the same PDF is opened again.
- The comparison follows manual alignment (option, on by default): each passage aligned by selection
  (or page pinned next to the reference) is compared with its matching passage.
- Compare only the current page: ▾ menu of the "Compare text" button (or Tools › Comparison scope).
  The comparison follows as you change pages.

- Bands on the page itself: with the comparison on, the header and footer lines can be dragged on the
  page (from the edge, to create a band).
- Header and footer detected when opening PDFs: text repeated at the top and bottom of the pages
  (numbers ignored, e.g. "Page 3 of 10"), up to 40% from the top and bottom. Can be turned off in
  Settings › What to compare.
- Side bands (left and right), off by default.

**Viewing**
- One page at a time: scrolling the mouse wheel past the end of a page opens the next one (and past
  the top, the previous one, showing its end). View › Scroll to the next page turns it on/off; in
  Settings › General, choose how many wheel notches (1 to 10) turn the page.

## [0.3.0] — 2026-11

### Resumo

- **Marcações completas:** além de destacar, agora dá para sublinhar, tachar, desenhar retângulos, círculos, setas e à mão livre, escrever caixas de texto e balões, e carimbar ("Aprovado", "Revisar"…). Tudo pode ser movido, redimensionado e desfeito (Ctrl+Z), e há uma lista com todas as marcações.
- **Escolha a referência:** compare todos com qualquer um dos PDFs, ou cada versão com a anterior (em cadeia).
- **Alinhar por conteúdo:** páginas incluídas ou removidas são detectadas, e as páginas iguais ficam lado a lado.
- **Rolagem contínua:** veja as páginas em sequência; com o alinhamento ligado, aparecem espaços onde há texto a mais ou a menos, para os trechos iguais ficarem na mesma altura.
- **Diferença visual (opcional):** encontra mudanças em imagens, assinaturas, carimbos e páginas escaneadas.
- **Relatório de diferenças:** a lista de mudanças em PDF, HTML ou CSV (Excel).
- **PDFs grandes:** a comparação é feita por partes, sem travar o programa, e o resultado fica salvo para a próxima vez.
- **Configurações** (Ctrl+,) para idiomas, cores e estilo, e **aviso de nova versão** (pode ser desligado).

### Summary

- **Full markup tools:** underline, strikeout, shapes, arrows, pen, text boxes, callouts and stamps; move, resize, undo; marks list.
- **Choose the reference** PDF or compare **in a chain** (each version with the previous one).
- **Align by content:** added or removed pages are detected and matching pages sit side by side.
- **Continuous scrolling** with alignment spaces that keep matching passages at the same height.
- **Optional visual difference** for images, signatures, stamps and scanned pages.
- **Difference report** as PDF, HTML or CSV.
- **Large PDFs** are compared in batches in the background, with results cached.
- **Settings** window and a **new-version notice** (can be turned off).

### Português

**Marcações**
- Barra de marcação com destaque, sublinhado, tachado e ondulado; retângulo, elipse, linha, seta,
  polígono e caneta; caixa de texto, balão e carimbos (Aprovado, Revisar, Divergência, OK, Rejeitado,
  Confidencial ou texto próprio).
- Selecionar, mover e redimensionar; duplo clique edita o texto; copiar, colar e excluir;
  desfazer e refazer (Ctrl+Z / Ctrl+Y).
- Estilo (cor, preenchimento, espessura, opacidade, fonte) para as novas marcações e para a selecionada.
- Lista de marcações (Ctrl+Shift+M) com filtros por tipo e cor.
- Na exportação, todas viram anotações PDF editáveis em outros leitores. O PDF original continua intacto.

**Comparação**
- Escolha do PDF de referência ou comparação em cadeia (cada PDF com o anterior).
- Comparação em lotes de páginas, em segundo plano, com progresso e Cancelar; modo "ao clicar" ou
  automático; cache em disco dos lotes já comparados, com limpeza configurável.
- Alinhamento por conteúdo (Ctrl+Shift+L): páginas incluídas ou removidas aparecem lado a lado com o
  painel vazio; ajustes manuais salvos para os mesmos PDFs.
- Diferença visual opcional (Ctrl+Shift+V): áreas com aparência diferente (imagens, assinaturas,
  carimbos, páginas escaneadas), com sensibilidade ajustável.
- Relatório de diferenças (Ctrl+Shift+R) em PDF, HTML ou CSV.

**Visualização**
- Rolagem contínua (Ctrl+Shift+C) além de uma página por vez; com o alinhamento por conteúdo, espaços
  do tamanho do conteúdo incluído ou removido mantêm os trechos iguais na mesma altura. Os espaços podem
  ser ajustados, inseridos ou removidos, e trechos podem ser alinhados à mão.

**Geral**
- Janela de Configurações (Ctrl+,): idiomas, comparação, cores e estilo das marcações.
- Aviso de nova versão (no máximo uma vez por dia; pode ser desligado) e Ajuda › Verificar atualizações agora.
- Novo menu Editar. README em inglês, com versão em português.

### English

**Marks**
- Markup toolbar with highlight, underline, strikeout and squiggly; rectangle, ellipse, line, arrow,
  polygon and pen; text box, callout and stamps (Approved, Review, Discrepancy, OK, Rejected,
  Confidential or your own text).
- Select, move and resize; double-click edits the text; copy, paste and delete; undo and redo.
- Style (color, fill, width, opacity, font) for new marks and the selected one.
- Marks list (Ctrl+Shift+M) filtered by type and color.
- On export they become PDF annotations editable in other readers. The original PDF is never changed.

**Comparison**
- Choose the reference PDF, or compare in a chain (each PDF with the previous one).
- Batch comparison in the background, with progress and Cancel; "on click" or automatic mode; on-disk
  cache of compared batches with configurable cleanup.
- Align by content (Ctrl+Shift+L): added or removed pages appear side by side with an empty pane;
  manual adjustments are saved for the same PDFs.
- Optional visual difference (Ctrl+Shift+V): areas that look different (images, signatures, stamps,
  scanned pages), with adjustable sensitivity.
- Difference report (Ctrl+Shift+R) as PDF, HTML or CSV.

**Viewing**
- Continuous scrolling (Ctrl+Shift+C) besides one page at a time; with content alignment, spaces the size
  of the added or removed content keep matching passages at the same height. Spaces can be adjusted,
  inserted or removed, and passages can be aligned by hand.

**General**
- Settings window (Ctrl+,): languages, comparison, colors and mark style.
- New-version notice (at most once a day; can be turned off) and Help › Check for updates now.
- New Edit menu. README in English, with a Portuguese version.

## [0.2.0]

Exportação, anotações (destaques e notas), comparação de texto, lista de ocorrências, sessões e pastas
recentes, OCR opcional, interface em inglês e português.
