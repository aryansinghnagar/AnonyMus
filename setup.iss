; Inno Setup Script for Windows Network Diagnostics Utility
[Setup]
AppName=Windows Network Diagnostics Utility
AppVersion=1.0
DefaultDirName={localappdata}\NetDiagnostics
DefaultGroupName=Network Diagnostics Utility
OutputBaseFilename=NetworkDiagnosticsInstaller
OutputDir=output
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=yes

[Files]
Source: "dist\NetworkDiagnostics\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Network Diagnostics Utility"; Filename: "{app}\NetworkDiagnostics.exe"
Name: "{userdesktop}\Network Diagnostics Utility"; Filename: "{app}\NetworkDiagnostics.exe"

[Run]
Filename: "{app}\NetworkDiagnostics.exe"; Description: "Launch Network Diagnostics Utility"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  MsgResult: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    if UninstallSilent() then
    begin
      DelTree(ExpandConstant('{app}\bin'), True, True, True);
      DeleteFile(ExpandConstant('{app}\local_node.db'));
      DeleteFile(ExpandConstant('{app}\users.db'));
      DeleteFile(ExpandConstant('{app}\diagnostics_config.json'));
      DelTree(ExpandConstant('{app}'), True, True, True);
    end
    else
    begin
      MsgResult := MsgBox('Do you want to completely and securely remove all chat databases, configuration files, and downloaded Tor bundles from your system?', mbConfirmation, MB_YESNO);
      if MsgResult = idYes then
      begin
        DelTree(ExpandConstant('{app}\bin'), True, True, True);
        DeleteFile(ExpandConstant('{app}\local_node.db'));
        DeleteFile(ExpandConstant('{app}\users.db'));
        DeleteFile(ExpandConstant('{app}\diagnostics_config.json'));
        DelTree(ExpandConstant('{app}'), True, True, True);
      end;
    end;
  end;
end;
