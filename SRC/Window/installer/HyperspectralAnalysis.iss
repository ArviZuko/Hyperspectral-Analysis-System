; =====================================================================
; Inno Setup Script: Hyperspectral Analysis System
; File: installer\HyperspectralAnalysis.iss
; Output: Output\HyperspectralAnalysis_Setup.exe
; =====================================================================

#define MyAppName "Hyperspectral Analysis System"
#define MyAppVersion "1.0"
#define MyAppPublisher "SMARTLAB-SU"
#define MyAppExeName "HyperspectralAnalysis.exe"
#define MyInstallerBaseName "HyperspectralAnalysis_Setup"

[Setup]
AppId={{8F3B2C10-6C1E-4E7A-9E2A-6D7C0F4A9B21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/SMARTLAB-SU/SPECTRUM
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\assets\logo.ico
OutputDir=..\Output
OutputBaseFilename={#MyInstallerBaseName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
CloseApplications=yes
RestartApplications=no
VersionInfoDescription=Hyperspectral Analysis System Setup
VersionInfoProductName=Hyperspectral Analysis System
VersionInfoCompany=SMARTLAB-SU
VersionInfoVersion=1.0.0.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Dirs]
; Ensure user has write permissions to Exports folder even under Program Files
Name: "{app}\Exports"; Permissions: users-modify; Check: IsAdminInstallMode
Name: "{app}\Exports"; Check: not IsAdminInstallMode
Name: "{app}\assets"

[Files]
; Main application executable
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Application assets and icons
Source: "..\assets\logo.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\logo.png"; DestDir: "{app}\assets"; Flags: ignoreversion
; Microsoft Visual C++ Redistributable (installed silently for clean Windows systems)
Source: "..\assets\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall ignoreversion skipifsourcedoesntexist

[Icons]
; Start Menu shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\logo.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop shortcut (optional by user checkbox)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\assets\logo.ico"

[Run]
; Silently install Visual C++ Redistributable if bundled and running with admin privileges
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Microsoft Visual C++ Redistributable (Required Runtime)..."; Flags: waituntilterminated skipifdoesntexist; Check: IsAdminInstallMode
; Option to launch application immediately after installation
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
