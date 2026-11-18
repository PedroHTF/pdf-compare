# Gera o executável do Windows em dist\PDFCompare\PDFCompare.exe
# Uso (na pasta do projeto):  powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"

& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Testes falharam; build cancelado." }

& $python -m PyInstaller --noconfirm --clean --windowed `
    --name PDFCompare `
    --icon app\resources\app.ico `
    --add-data "app\resources;app\resources" `
    --add-data "licenses;licenses" `
    --exclude-module tkinter `
    run.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

# Exigências da licença AGPL ao distribuir: texto da licença e código-fonte junto do programa
Copy-Item LICENSE "dist\PDFCompare\LICENCA.txt"
& $python tools\make_source_zip.py "dist\PDFCompare"
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o pacote de código-fonte." }

Write-Host "`nPronto: dist\PDFCompare\PDFCompare.exe" -ForegroundColor Green
