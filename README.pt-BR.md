# PDF Compare

[English](README.md) · **Português**

Aplicativo para Windows que exibe de **2 a 6 PDFs lado a lado**, pesquisa em todos ao
mesmo tempo e avança ou retrocede página por página, em todos juntos ou em cada um separadamente.
Também destaca as diferenças de texto entre as versões, permite marcar as páginas (destaques,
formas, caixas de texto, balões, carimbos e notas) sem alterar os arquivos e exporta a
comparação como PDF ou PNG.
Os arquivos são processados somente no computador local.

Código-fonte: <https://github.com/PedroHTF/pdf-compare>

Gostou? [☕ Pague um café para o autor](https://www.buymeacoffee.com/phtf)

## Download

Baixe a versão mais recente em **[Releases](https://github.com/PedroHTF/pdf-compare/releases/latest)**:

- `PDFCompare-Setup-<versão>.exe`: instalador para Windows (recomendado). Cria atalho no Menu Iniciar,
  aparece em "Abrir com" para PDFs e abre arquivos de sessão `.pdfcompare` com duplo clique.
- `PDFCompare-<versão>-portable.zip`: versão portátil; extraia e rode `PDFCompare.exe`.
- `codigo-fonte-PDFCompare-<versão>.zip`: código-fonte completo (AGPL-3.0).

Na primeira execução o Windows SmartScreen pode avisar que o programa não é reconhecido
(ele não tem assinatura digital paga): clique em **Mais informações › Executar assim mesmo**.

## Como usar

| Quero… | Como |
|---|---|
| Abrir PDFs | Arraste os arquivos para a janela, ou **Adicionar PDFs…** (Ctrl+O). Até 6. |
| Abrir uma pasta inteira | **Arquivo › Abrir pasta…** (Ctrl+Shift+O): abre os PDFs da pasta em ordem de nome (até 6) |
| Reabrir arquivos usados antes | **Arquivo › Abertos recentemente** (PDFs e sessões) |
| Salvar e retomar o trabalho | **Arquivo › Salvar sessão…** (Ctrl+S) guarda os PDFs, a página de cada um e o zoom num arquivo `.pdfcompare`. **Abrir sessão…** restaura tudo |
| Abrir PDF com senha | O programa pede a senha (3 tentativas). **Pular este arquivo** abre os demais. A senha não é guardada. |
| Avançar/voltar **todos** juntos | **◀ Anterior / Próxima ▶** na barra, ou setas ← → / Page Up / Page Down |
| Avançar/voltar **um** PDF só | **◀ ▶** no cabeçalho do painel, ou digite o número da página no campo do painel |
| Desfazer ajustes individuais | **Realinhar** (Ctrl+L): todos voltam a mostrar a mesma página |
| Pesquisar em todos | Digite na caixa **Pesquisar** (Ctrl+F). Cada painel mostra quantas ocorrências tem |
| Ir à próxima ocorrência em **todos** | Enter ou F3 (Shift+Enter / Shift+F3 volta) |
| Ir à próxima ocorrência em **um** PDF | **▲ ▼** na etiqueta amarela do painel |
| Ver todas as ocorrências em lista | **Lista de ocorrências** (Ctrl+Shift+F): trecho e página de cada uma; clique para ir até ela |
| Ver as diferenças de texto | **Comparar texto** (Ctrl+D). F7 / Shift+F7 vão para a próxima / anterior diferença |
| Comparar PDFs grandes por partes | A comparação é feita em lotes de páginas (padrão: 50). **Comparar próximo lote ▶** (F8) na barra de status; Shift+F8 volta |
| Destacar, sublinhar ou tachar um trecho | Escolha a ferramenta na **barra de marcação** (Destacar: Ctrl+H) e arraste sobre o texto |
| Desenhar retângulo, elipse, linha, seta ou à mão livre | Escolha a ferramenta e arraste na página |
| Desenhar um polígono | Clique em cada vértice e dê duplo clique para terminar (Esc cancela) |
| Escrever na página | **Caixa de texto** (arraste a área) ou **Balão** (arraste do ponto indicado até onde fica o texto) |
| Carimbar ("Aprovado", "Revisar"…) | **Carimbo** — a seta ao lado escolhe o texto ou permite digitar outro |
| Adicionar uma nota | **Nota** (Ctrl+M) e clique no ponto da página. Passe o mouse sobre a nota para ler |
| Mover, redimensionar ou editar | Ferramenta **Selecionar** (ou Esc): arraste a marcação ou as alças dos cantos; duplo clique edita o texto |
| Copiar, colar, excluir | Ctrl+C, Ctrl+V (cola na página à vista), Delete. Botão direito mostra as opções |
| Desfazer / refazer | Ctrl+Z / Ctrl+Y |
| Trocar cor, preenchimento, espessura, opacidade, fonte | Barra de marcação: vale para as próximas marcações e para a selecionada |
| Ver todas as marcações | **Exibir › Lista de marcações** (Ctrl+Shift+M), com filtro por tipo e cor |
| Configurações (idiomas, cores, estilo padrão) | **Editar › Configurações…** (Ctrl+,) |
| Exportar | **Exportar…** (Ctrl+E): comparação lado a lado (posição atual ou todas), página atual de cada PDF, ou cada PDF com as anotações. PDF ou PNG |
| Pesquisar em PDF escaneado | **Ferramentas › Reconhecer texto em PDFs escaneados (OCR)** — requer o Tesseract (veja abaixo) |
| Zoom | Ctrl + roda do mouse, Ctrl++ / Ctrl+-, ou a lista de zoom (largura, página inteira, %) |
| Rolagem acompanhada | **Rolagem vinculada** (ligada por padrão): rolar um PDF rola os outros |
| Trocar o idioma (English / Português) | **Ferramentas › Idioma / Language** e reinicie o programa |
| Ver todos os atalhos | F1 |

**Modelo de navegação.** Todos os PDFs compartilham uma posição. Os botões de um painel
deslocam só aquele documento. Depois disso, ao avançar todos juntos, a diferença é mantida,
o que permite comparar versões com páginas a mais ou a menos. Quando um PDF não tem página
naquela posição, o painel avisa e indica como trazê-lo de volta.

**Pesquisa.** Por padrão ignora maiúsculas e acentos ("acao" encontra "Ação"). Em **Opções**
dá para diferenciar maiúsculas, exigir palavra inteira ou considerar acentos. Também encontra
frases e palavras hifenizadas na quebra de linha. PDFs escaneados (somente imagem) passam a
ser pesquisáveis com o OCR ligado.

**Idioma.** A interface existe em inglês e em português. Na primeira execução o programa usa o
idioma do Windows (português se o sistema estiver em português; inglês nos demais casos). Para
trocar, use **Ferramentas › Idioma / Language** e reinicie o programa.

**Comparar texto.** O primeiro PDF aberto é a referência; cada um dos outros é comparado com ele,
palavra por palavra. Cores: **verde** = incluído, **vermelho** (tachado) = removido,
**azul** = alterado. A comparação ignora quebras de linha e de página (texto que só mudou de
página não aparece como diferença) e a pontuação nas bordas das palavras; maiúsculas e acentos
contam. A barra de status mostra o total por PDF. As cores podem ser trocadas em
**Editar › Configurações… › Comparação**.

**Comparação em lotes.** Em PDFs grandes a comparação é dividida em lotes de páginas do 1º PDF
(os outros acompanham o alinhamento de cada painel). A barra de status mostra "Lote 2 de 8 ·
páginas 51–100", com **◀** e **Comparar próximo lote ▶** (F8). Ela roda em segundo plano, com
progresso e botão **Cancelar**, sem travar o programa. Em **Editar › Configurações… › Comparação**:
- **Páginas por lote** (ou "Tudo de uma vez");
- **Comparar o próximo lote:** ao clicar, ou automaticamente em segundo plano, escolhendo
  quantos lotes preparar à frente e se deve pausar enquanto você rola as páginas ou faz marcações;
- **Quando o alinhamento mudar** (◀ ▶ de um painel, página digitada ou Realinhar): o programa
  espera você terminar de ajustar e mostra **Recomparar** na barra de lotes; até lá, a comparação
  atual continua na tela. Também dá para escolher recomparar automaticamente. Lotes com as mesmas
  páginas vêm do cache, e ir à próxima diferença (F7) nunca refaz a comparação;
- **Comparações salvas:** os lotes comparados ficam guardados (`%APPDATA%\PDFCompare\PDF Compare\comparacoes`),
  identificados pelo conteúdo dos PDFs, e são reaproveitados ao reabrir os mesmos arquivos.
  Os não usados são apagados depois de N dias (ou nunca); **Limpar cache agora** apaga tudo.

**Marcações.** Destaques, formas, textos, carimbos e notas ficam guardados na pasta de dados do programa
(`%APPDATA%\PDFCompare\PDF Compare\anotacoes`), um arquivo por documento, identificado pelo
conteúdo do PDF — reaparecem mesmo se o arquivo for renomeado ou movido. **O PDF original
nunca é alterado.** Para levar as anotações junto, use **Exportar… › Cada PDF inteiro com as
anotações** (gera um novo PDF com anotações de verdade, editáveis em outros leitores) ou marque
**Incluir minhas marcações** nas outras opções de exportação.

**Exportar.** Em PDF o texto continua selecionável; em PNG gera uma imagem por posição
(`comparacao_001.png`, `comparacao_002.png`…), com a resolução escolhida.

**OCR (opcional).** Usa o [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) por meio do
PyMuPDF. Ele não vem com o programa: instale-o à parte (no Windows, o instalador da
[UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)); o inglês já vem incluído e,
para PDFs em português, marque também o idioma **Portuguese** na instalação.
O programa procura o Tesseract na variável `TESSDATA_PREFIX` e nas pastas padrão de instalação.
O idioma padrão do OCR é o inglês, `eng` (mude em **Editar › Configurações…** ou **Ferramentas › Idioma do OCR…**, por exemplo
`por` ou `eng+por`).
Só as páginas sem texto e com imagem passam pelo OCR, que leva alguns segundos por página; o
resultado serve para pesquisar e comparar, e o PDF não é alterado. Sem o Tesseract, o programa
avisa e continua funcionando normalmente.

## Licença

Software livre sob a **GNU AGPL v3 ou posterior** (arquivo [LICENSE](LICENSE)). A licença é
obrigatória porque o programa usa o PyMuPDF/MuPDF, que é AGPL. No programa: **Ajuda › Licença e créditos…**.

- **Pode:** usar para qualquer fim (inclusive comercial), estudar, modificar e distribuir, de graça ou cobrando.
- **Ao distribuir:** entregar o código-fonte completo, manter os avisos de copyright e a licença,
  e manter versões modificadas sob a AGPL. Usar sem distribuir não gera obrigação.
- **Como cumprir:** o `build.ps1` já coloca `LICENCA.txt` e `codigo-fonte-PDFCompare-<versão>.zip`
  dentro de `dist\PDFCompare`. Distribuindo a pasta inteira, o código-fonte vai junto.
  O código também está publicado em <https://github.com/PedroHTF/pdf-compare>, e o link
  aparece no programa (**Sobre** e **Licença e créditos**).
- **Autoria:** troque "Os autores do PDF Compare" pelo seu nome em `app/__init__.py` (`__author__`).

Componentes de terceiros e licenças: PyMuPDF/MuPDF (AGPL-3.0), PySide6/Qt (LGPL-3.0), Python (PSF)
e o carregador do PyInstaller (GPL-2.0 com exceção). Os textos completos estão em `licenses/`.
O Tesseract OCR (Apache-2.0) é opcional, instalado pelo usuário e não é distribuído com o programa.
As versões exatas usadas no build estão em `requirements-lock.txt`.

## Desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m app.main                      # executar
python -m app.main a.pdf b.pdf          # executar já abrindo arquivos
python -m app.main trabalho.pdfcompare  # executar abrindo uma sessão salva
python -m pytest                        # testes (lógica e interface, sem abrir janelas)
                                        # os testes de OCR real só rodam se o Tesseract estiver instalado
```

### Gerar o executável

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

O build roda os testes antes e gera `dist\PDFCompare\PDFCompare.exe`. Para distribuir,
copie a pasta `dist\PDFCompare` inteira.

### Gerar o instalador

Com o [Inno Setup 6](https://jrsoftware.org/isinfo.php) instalado, depois do `build.ps1`:

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.2.0 installer.iss
```

O instalador fica em `dist\installer\`.

### Publicar uma versão

O GitHub gera tudo sozinho (`.github/workflows/release.yml`): testes, executável, instalador,
pacote portátil e código-fonte. Para lançar:

1. Atualize `__version__` em `app/__init__.py` e faça o merge na `main`.
2. Crie e envie a tag com o mesmo número:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
3. Em alguns minutos a Release aparece em **Releases**, com os arquivos para download.
   Se a tag não bater com `__version__`, o workflow para com erro.

Em cada pull request o mesmo workflow roda sem publicar nada; os arquivos gerados ficam em
**Actions › (execução) › Artifacts**, para testar antes do lançamento.

### Estrutura

```
app/
  main.py                  ponto de entrada
  model/session.py         PDF aberto (arquivo + deslocamento de alinhamento)
  services/navigation.py   posição global, ajustes por PDF, ocorrências (sem Qt)
  services/text_index.py   extração de palavras com posição, normalização de texto
  services/search.py       pesquisa de palavras e frases
  services/indexer.py      indexação em segundo plano sem travar a interface (e OCR, se ligado)
  services/text_diff.py    comparação de texto palavra por palavra
  services/diff_batches.py lotes de páginas e cache das comparações em disco
  services/batch_runner.py execução dos lotes em segundo plano
  services/annotations.py  marcações (destaques, formas, textos, carimbos, notas) fora do PDF; PDF anotado
  services/preferences.py  cores da comparação e estilo padrão das marcações
  services/export.py       exportação lado a lado e das páginas atuais (PDF/PNG)
  services/workspace.py    abrir pasta, arquivos recentes e sessões (.pdfcompare)
  services/ocr.py          OCR opcional com Tesseract (detecção e reconhecimento)
  i18n.py                  idioma da interface (tr); i18n_en.py tem as traduções para o inglês
  ui/main_window.py        janela, menus, barras, grade, arrastar e soltar
  ui/pane.py               painel de um PDF (renderização, destaques, controles)
  ui/search_bar.py         barra de pesquisa
  ui/results_panel.py      lista de ocorrências (trecho + página)
  ui/marks_panel.py        lista de marcações com filtros
  ui/mark_widgets.py       botão de cor e barra de estilo das marcações
  ui/settings_dialog.py    janela de Configurações
  ui/export_dialog.py      diálogo de exportação
  ui/widgets.py            componentes auxiliares
  ui/style.py              estilos (tema claro e escuro)
  ui/resources.py          acesso ao ícone e ao logo
  resources/logo.svg       logo (fonte); app.ico e logo_256.png são gerados a partir dele
  legal.py                 dados de licença e componentes de terceiros
  ui/license_dialog.py     janela "Licença e créditos"
tools/make_icon.py         regenera app.ico e logo_256.png após editar o logo.svg
installer.iss              configuração do instalador (Inno Setup)
.github/workflows/         build automático e publicação de Releases
tools/make_source_zip.py   gera o pacote de código-fonte que acompanha o .exe
licenses/                  textos completos das licenças (AGPL, LGPL, GPL, PSF, PyInstaller)
tests/                     testes de cada serviço e da interface
samples/                   PDFs de exemplo
```

### Decisões técnicas

- **PyMuPDF** para renderização e extração de texto com coordenadas (necessárias para destacar).
- A indexação roda em fatias de tempo na thread principal, porque o PyMuPDF não suporta
  múltiplas threads. A interface continua respondendo e a pesquisa já funciona com as páginas
  indexadas, atualizando quando termina.
- Renderização só da página visível, com cache pequeno por painel e nitidez em telas de alta resolução.
- Preferências (zoom, opções de pesquisa, tamanho da janela, última pasta, listas laterais,
  recentes, OCR, cores e estilo das marcações) ficam salvas entre execuções.
- A comparação de texto é feita em dois níveis (linhas, depois palavras dentro das linhas
  diferentes) com `difflib`, para continuar rápida em documentos longos. Ela roda em uma thread
  separada sobre as palavras já extraídas (nunca o PyMuPDF), lote a lote, com cache em disco.
- Os textos do código são escritos em português e passam por `tr()`; as traduções para o inglês
  ficam em `app/i18n_en.py`. O teste `tests/test_i18n.py` falha se algum texto ficar sem tradução.
- Toda a lógica nova (diferenças, marcações, exportação, sessões, OCR) fica em `app/services`,
  sem Qt, e é testada diretamente.
