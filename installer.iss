; Instalador do PDF Compare (Inno Setup 6) — gerado a partir de dist\PDFCompare.
; Uso (depois do build.ps1):  ISCC.exe /DAppVersion=0.2.0 installer.iss
; O workflow .github/workflows/release.yml faz isso automaticamente.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "PDF Compare"
#define AppExe "PDFCompare.exe"
#define AppUrl "https://github.com/PedroHTF/pdf-compare"

[Setup]
AppId={{ED1F5D33-38A1-4688-A200-B2F8FF663F4A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Os autores do PDF Compare
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Instala só para o usuário atual (sem pedir administrador); o diálogo permite instalar para todos.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=LICENSE
SetupIconFile=app\resources\app.ico
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=dist\installer
OutputBaseFilename=PDFCompare-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "sessionassoc"; Description: "{cm:AssocSessions}"; GroupDescription: "{cm:AssocGroup}"

[CustomMessages]
english.AssocGroup=File types:
english.AssocSessions=Open PDF Compare session files (.pdfcompare) with this program
brazilianportuguese.AssocGroup=Tipos de arquivo:
brazilianportuguese.AssocSessions=Abrir arquivos de sessão do PDF Compare (.pdfcompare) com este programa

[Files]
; Pasta inteira gerada pelo build.ps1 (inclui LICENCA.txt e o zip do código-fonte, exigidos pela AGPL)
Source: "dist\PDFCompare\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; .pdfcompare -> PDF Compare ("Abrir com" e duplo clique). HKA = HKCU ou HKLM conforme o modo de instalação.
Root: HKA; Subkey: "Software\Classes\.pdfcompare"; ValueType: string; ValueName: ""; ValueData: "PDFCompare.Session"; Flags: uninsdeletevalue; Tasks: sessionassoc
Root: HKA; Subkey: "Software\Classes\PDFCompare.Session"; ValueType: string; ValueName: ""; ValueData: "PDF Compare session"; Flags: uninsdeletekey; Tasks: sessionassoc
Root: HKA; Subkey: "Software\Classes\PDFCompare.Session\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: sessionassoc
Root: HKA; Subkey: "Software\Classes\PDFCompare.Session\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: sessionassoc
; Aparece em "Abrir com" para PDFs, sem tomar o lugar do leitor de PDF padrão.
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PDFCompare.Pdf"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\PDFCompare.Pdf"; ValueType: string; ValueName: ""; ValueData: "PDF"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PDFCompare.Pdf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\PDFCompare.Pdf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
