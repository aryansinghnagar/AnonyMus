import os
import shutil
import subprocess
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_MAIN_DIR = os.path.join(BASE_DIR, "app_main")
APP_P2P_DIR = os.path.join(BASE_DIR, "app_p2p")

def clean_directory(dir_path):
    """Remove directory if it exists and recreate it."""
    if os.path.exists(dir_path):
        print(f"Cleaning existing directory: {dir_path}")
        shutil.rmtree(dir_path)
    os.makedirs(dir_path, exist_ok=True)

def export_main_branch():
    """Archive main branch via git and extract to app_main."""
    print("Exporting 'main' branch using git archive...")
    zip_path = os.path.join(BASE_DIR, "main_temp.zip")
    
    # Run git archive
    try:
        subprocess.run(
            ["git", "archive", "--format=zip", "-o", zip_path, "main"],
            cwd=BASE_DIR,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error executing git archive: {e}")
        raise e

    # Extract zip file
    print(f"Extracting main_temp.zip to {APP_MAIN_DIR}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(APP_MAIN_DIR)
        
    # Delete temporary zip
    if os.path.exists(zip_path):
        os.remove(zip_path)
    print("Export of 'main' branch complete.")

def copy_p2p_branch():
    """Copy the current working tree files (p2p) to app_p2p."""
    print("Copying 'p2p' branch files (from working directory)...")
    
    # Files and folders to copy
    items_to_copy = [
        ("server.py", "server.py"),
        ("database.py", "database.py"),
        ("tor_manager.py", "tor_manager.py"),
        ("static", "static"),
        ("templates", "templates")
    ]
    
    for src_name, dest_name in items_to_copy:
        src_path = os.path.join(BASE_DIR, src_name)
        dest_path = os.path.join(APP_P2P_DIR, dest_name)
        
        if not os.path.exists(src_path):
            print(f"Warning: Source item {src_path} does not exist!")
            continue
            
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dest_path)
        else:
            shutil.copy2(src_path, dest_path)
            
    print("Copy of 'p2p' branch complete.")

def refactor_main():
    """Rename main modules and adjust imports to prevent namespace collision."""
    print("Refactoring app_main modules...")
    
    # Paths
    server_path = os.path.join(APP_MAIN_DIR, "server.py")
    database_path = os.path.join(APP_MAIN_DIR, "database.py")
    
    server_dest = os.path.join(APP_MAIN_DIR, "server_main.py")
    database_dest = os.path.join(APP_MAIN_DIR, "database_main.py")
    
    # 1. Update imports in server.py before renaming
    if os.path.exists(server_path):
        with open(server_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Replace import database with local package import
        # We replace both 'import database' and 'from database import ...' if any,
        # but in server.py it's just 'import database'
        content = content.replace("import database", "import app_main.database_main as database")
        
        with open(server_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    # 2. Perform renames
    if os.path.exists(server_path):
        os.rename(server_path, server_dest)
    if os.path.exists(database_path):
        os.rename(database_path, database_dest)
        
    print("app_main refactoring complete.")

def refactor_p2p():
    """Rename p2p modules and adjust imports to prevent namespace collision."""
    print("Refactoring app_p2p modules...")
    
    # Paths
    server_path = os.path.join(APP_P2P_DIR, "server.py")
    database_path = os.path.join(APP_P2P_DIR, "database.py")
    tor_manager_path = os.path.join(APP_P2P_DIR, "tor_manager.py")
    
    server_dest = os.path.join(APP_P2P_DIR, "server_p2p.py")
    database_dest = os.path.join(APP_P2P_DIR, "database_p2p.py")
    tor_manager_dest = os.path.join(APP_P2P_DIR, "tor_manager_p2p.py")
    
    # 1. Update imports in server.py before renaming
    if os.path.exists(server_path):
        with open(server_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Replace local imports with refactored ones
        content = content.replace("import database", "import app_p2p.database_p2p as database")
        content = content.replace("import tor_manager", "import app_p2p.tor_manager_p2p as tor_manager")
        
        with open(server_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    # 2. Perform renames
    if os.path.exists(server_path):
        os.rename(server_path, server_dest)
    if os.path.exists(database_path):
        os.rename(database_path, database_dest)
    if os.path.exists(tor_manager_path):
        os.rename(tor_manager_path, tor_manager_dest)
        
    print("app_p2p refactoring complete.")

def main():
    try:
        clean_directory(APP_MAIN_DIR)
        clean_directory(APP_P2P_DIR)
        
        export_main_branch()
        copy_p2p_branch()
        
        refactor_main()
        refactor_p2p()
        
        print("\nAll files successfully prepared and refactored!")
    except Exception as e:
        print(f"\nFailed to prepare files: {e}")

if __name__ == "__main__":
    main()
