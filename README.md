# PDF Compare

Aplicativo para Windows que exibe de **2 a 6 PDFs lado a lado**, pesquisa em todos ao
mesmo tempo e avança ou retrocede página por página, em todos juntos ou em cada um separadamente.
Os arquivos são processados somente no computador local.

Código-fonte: <https://github.com/PedroHTF/pdf-compare>

Gostou? [☕ Pague um café para o autor](https://www.buymeacoffee.com/phtf)

## Como usar

| Quero… | Como |
|---|---|
| Abrir PDFs | Arraste os arquivos para a janela, ou **Adicionar PDFs…** (Ctrl+O). Até 6. |
| Abrir PDF com senha | O programa pede a senha (3 tentativas). **Pular este arquivo** abre os demais. A senha não é guardada. |
| Avançar/voltar **todos** juntos | **◀ Anterior / Próxima ▶** na barra, ou setas ← → / Page Up / Page Down |
| Avançar/voltar **um** PDF só | **◀ ▶** no cabeçalho do painel, ou digite o número da página no campo do painel |
| Desfazer ajustes individuais | **Realinhar** (Ctrl+L): todos voltam a mostrar a mesma página |
| Pesquisar em todos | Digite na caixa **Pesquisar** (Ctrl+F). Cada painel mostra quantas ocorrências tem |
| Ir à próxima ocorrência em **todos** | Enter ou F3 (Shift+Enter / Shift+F3 volta) |
| Ir à próxima ocorrência em **um** PDF | **▲ ▼** na etiqueta amarela do painel |
| Zoom | Ctrl + roda do mouse, Ctrl++ / Ctrl+-, ou a lista de zoom (largura, página inteira, %) |
| Rolagem acompanhada | **Rolagem vinculada** (ligada por padrão): rolar um PDF rola os outros |
| Ver todos os atalhos | F1 |

**Modelo de navegação.** Todos os PDFs compartilham uma posição. Os botões de um painel
deslocam só aquele documento. Depois disso, ao avançar todos juntos, a diferença é mantida,
o que permite comparar versões com páginas a mais ou a menos. Quando um PDF não tem página
naquela posição, o painel avisa e indica como trazê-lo de volta.

**Pesquisa.** Por padrão ignora maiúsculas e acentos ("acao" encontra "Ação"). Em **Opções**
dá para diferenciar maiúsculas, exigir palavra inteira ou considerar acentos. Também encontra
frases e palavras hifenizadas na quebra de linha. PDFs escaneados (somente imagem) não têm
texto pesquisável; OCR está fora do escopo.

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
As versões exatas usadas no build estão em `requirements-lock.txt`.

## Desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m app.main                      # executar
python -m app.main a.pdf b.pdf          # executar já abrindo arquivos
python -m pytest                        # testes (lógica e interface, sem abrir janelas)
```

### Gerar o executável

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

O build roda os testes antes e gera `dist\PDFCompare\PDFCompare.exe`. Para distribuir,
copie a pasta `dist\PDFCompare` inteira.

### Estrutura

```
app/
  main.py                  ponto de entrada
  model/session.py         PDF aberto (arquivo + deslocamento de alinhamento)
  services/navigation.py   posição global, ajustes por PDF, ocorrências (sem Qt)
  services/text_index.py   extração de palavras com posição, normalização de texto
  services/search.py       pesquisa de palavras e frases
  services/indexer.py      indexação em segundo plano sem travar a interface
  ui/main_window.py        janela, menus, barras, grade, arrastar e soltar
  ui/pane.py               painel de um PDF (renderização, destaques, controles)
  ui/search_bar.py         barra de pesquisa
  ui/widgets.py            componentes auxiliares
  ui/style.py              estilos (tema claro e escuro)
  ui/resources.py          acesso ao ícone e ao logo
  resources/logo.svg       logo (fonte); app.ico e logo_256.png são gerados a partir dele
  legal.py                 dados de licença e componentes de terceiros
  ui/license_dialog.py     janela "Licença e créditos"
tools/make_icon.py         regenera app.ico e logo_256.png após editar o logo.svg
tools/make_source_zip.py   gera o pacote de código-fonte que acompanha o .exe
licenses/                  textos completos das licenças (AGPL, LGPL, GPL, PSF, PyInstaller)
tests/                     testes de busca, navegação e interface
samples/                   PDFs de exemplo
```

### Decisões técnicas

- **PyMuPDF** para renderização e extração de texto com coordenadas (necessárias para destacar).
- A indexação roda em fatias de tempo na thread principal, porque o PyMuPDF não suporta
  múltiplas threads. A interface continua respondendo e a pesquisa já funciona com as páginas
  indexadas, atualizando quando termina.
- Renderização só da página visível, com cache pequeno por painel e nitidez em telas de alta resolução.
- Preferências (zoom, opções de pesquisa, tamanho da janela, última pasta) ficam salvas entre sessões.
