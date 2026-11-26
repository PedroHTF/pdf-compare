# Novidades / Changelog

## [Não lançado / Unreleased]

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

## [0.3.0] — 2026-11

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
