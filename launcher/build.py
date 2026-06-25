"""
Build Automation Module for AnonyMus (P2P Windows Installer).

Automates the compilation of the GUI launcher using PyInstaller, writes the
Inno Setup configuration script, compiles the setup installer, and self-signs
the generated binaries using PowerShell Authenticode signatures.
"""

import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ISCC_PATH = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"


def run_pyinstaller():
    """
    Executes PyInstaller to bundle the launcher script and nested applications.
    
    Creates a folder-based distribution incorporating the app_p2p directory.
    """
    print("--------------------------------------------------")
    print("Step 1: Running PyInstaller...")
    print("--------------------------------------------------")
    
    # Resolve PyInstaller location
    pyinstaller_exe = os.path.join(BASE_DIR, "venv", "Scripts", "pyinstaller.exe")
    if not os.path.exists(pyinstaller_exe):
        pyinstaller_exe = "pyinstaller"
        
    cmd = [
        pyinstaller_exe,
        "--name", "NetworkDiagnostics",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--add-data", "app_p2p;app_p2p",
        "--hidden-import", "flask",
        "--hidden-import", "flask_socketio",
        "--hidden-import", "flask_limiter",
        "--hidden-import", "eventlet",
        "--hidden-import", "cryptography",
        "--hidden-import", "bcrypt",
        "--hidden-import", "requests",
        "--hidden-import", "psycopg2",
        "--hidden-import", "python-dotenv",
        "--hidden-import", "dotenv",
        "--hidden-import", "zeroconf",
        "launcher.py"
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print("PyInstaller compilation complete.\n")


def write_iss_script():
    """Generates the Inno Setup script compiler instructions (setup.iss)."""
    print("--------------------------------------------------")
    print("Step 2: Generating Inno Setup script (setup.iss)...")
    print("--------------------------------------------------")
    
    iss_content = f"""; Inno Setup Script for Windows Network Diagnostics Utility
[Setup]
AppName=Windows Network Diagnostics Utility
AppVersion=1.0
DefaultDirName={{localappdata}}\\NetDiagnostics
DefaultGroupName=Network Diagnostics Utility
OutputBaseFilename=NetworkDiagnosticsInstaller
OutputDir=output
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=yes

[Files]
Source: "dist\\NetworkDiagnostics\\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\Network Diagnostics Utility"; Filename: "{{app}}\\NetworkDiagnostics.exe"
Name: "{{userdesktop}}\\Network Diagnostics Utility"; Filename: "{{app}}\\NetworkDiagnostics.exe"

[Run]
Filename: "{{app}}\\NetworkDiagnostics.exe"; Description: "Launch Network Diagnostics Utility"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  MsgResult: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    if UninstallSilent() then
    begin
      DelTree(ExpandConstant('{{app}}\\bin'), True, True, True);
      DeleteFile(ExpandConstant('{{app}}\\local_node.db'));
      DeleteFile(ExpandConstant('{{app}}\\diagnostics_config.json'));
      DelTree(ExpandConstant('{{app}}'), True, True, True);
    end
    else
    begin
      MsgResult := MsgBox('Do you want to completely and securely remove all chat databases, configuration files, and downloaded Tor bundles from your system?', mbConfirmation, MB_YESNO);
      if MsgResult = idYes then
      begin
        DelTree(ExpandConstant('{{app}}\\bin'), True, True, True);
        DeleteFile(ExpandConstant('{{app}}\\local_node.db'));
        DeleteFile(ExpandConstant('{{app}}\\diagnostics_config.json'));
        DelTree(ExpandConstant('{{app}}'), True, True, True);
      end;
    end;
  end;
end;
"""
    iss_path = os.path.join(BASE_DIR, "setup.iss")
    with open(iss_path, "w", encoding="utf-8") as f:
        f.write(iss_content)
    print(f"setup.iss written successfully to {iss_path}.\n")


def compile_installer():
    """Executes the Inno Setup compiler (ISCC.exe) on the generated setup.iss script."""
    print("--------------------------------------------------")
    print("Step 3: Compiling installer with Inno Setup...")
    print("--------------------------------------------------")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    iss_path = os.path.join(BASE_DIR, "setup.iss")
    
    if not os.path.exists(ISCC_PATH):
        raise FileNotFoundError(f"Inno Setup Compiler not found at: {ISCC_PATH}")
        
    cmd = [ISCC_PATH, iss_path]
    print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print("Installer compiled successfully.\n")


def sign_executables():
    """Generates a self-signed code-signing certificate and signs the built binaries via PowerShell."""
    print("--------------------------------------------------")
    print("Step 4: Creating Self-Signed Certificate & Signing...")
    print("--------------------------------------------------")
    
    launcher_exe = os.path.join(DIST_DIR, "NetworkDiagnostics", "NetworkDiagnostics.exe")
    installer_exe = os.path.join(OUTPUT_DIR, "NetworkDiagnosticsInstaller.exe")
    
    # PowerShell commands to provision certificate and execute Set-AuthenticodeSignature
    ps_script = f"""
    $Subject = "CN=NetDiagnostics Project Code Sign"
    $Cert = Get-ChildItem Cert:\\CurrentUser\\My | Where-Object {{ $_.Subject -eq $Subject }} | Select-Object -First 1
    
    if (-not $Cert) {{
        Write-Host "Creating new self-signed code signing certificate..."
        $Cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject -CertStoreLocation Cert:\\CurrentUser\\My -FriendlyName "NetDiagnostics Code Signing"
    }} else {{
        Write-Host "Reusing existing code signing certificate..."
    }}
    
    Write-Host "Signing Launcher Executable: {launcher_exe}"
    Set-AuthenticodeSignature -FilePath "{launcher_exe}" -Certificate $Cert
    
    Write-Host "Signing Installer Executable: {installer_exe}"
    Set-AuthenticodeSignature -FilePath "{installer_exe}" -Certificate $Cert
    
    Write-Host "Verification:"
    Get-AuthenticodeSignature -FilePath "{launcher_exe}"
    Get-AuthenticodeSignature -FilePath "{installer_exe}"
    """
    
    print("Running PowerShell signing commands...")
    subprocess.run(["powershell", "-Command", ps_script], check=True)
    print("Signing operations completed successfully.\n")


def main():
    """Main execution loop for build pipeline orchestration."""
    try:
        # Purge previous build output folders
        if os.path.exists(OUTPUT_DIR):
            shutil.rmtree(OUTPUT_DIR)
            
        run_pyinstaller()
        write_iss_script()
        compile_installer()
        sign_executables()
        
        print("==================================================")
        print("BUILD SUCCESSFUL!")
        print(f"Installer: {os.path.join(OUTPUT_DIR, 'NetworkDiagnosticsInstaller.exe')}")
        print("==================================================")
    except Exception as e:
        print(f"\nBUILD FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
