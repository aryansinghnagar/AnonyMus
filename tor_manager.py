import os
import sys
import platform
import urllib.request
import tarfile
import subprocess
import time
import atexit
import shutil
import socket

# Configuration
TOR_VERSION = "15.0.16"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")
TOR_DIR = os.path.join(BIN_DIR, "tor")
TOR_DATA_DIR = os.path.join(BIN_DIR, "tor_data")
TOR_SERVICE_DIR = os.path.join(BIN_DIR, "tor_service")
TOR_RC_PATH = os.path.join(BIN_DIR, "torrc")

# Detect platform
SYSTEM = platform.system().lower()
ARCH = platform.machine().lower()

# Determine download URL and binary name
if SYSTEM == "windows":
    TOR_URL = f"https://dist.torproject.org/torbrowser/{TOR_VERSION}/tor-expert-bundle-windows-x86_64-{TOR_VERSION}.tar.gz"
    EXE_NAME = "tor.exe"
elif SYSTEM == "darwin":
    # macOS expert bundles are typically x86_64 or universal
    TOR_URL = f"https://dist.torproject.org/torbrowser/{TOR_VERSION}/tor-expert-bundle-macos-x86_64-{TOR_VERSION}.tar.gz"
    EXE_NAME = "tor"
else:
    # Default to Linux x86_64
    TOR_URL = f"https://dist.torproject.org/torbrowser/{TOR_VERSION}/tor-expert-bundle-linux-x86_64-{TOR_VERSION}.tar.gz"
    EXE_NAME = "tor"

# Dynamic port checking to avoid collisions
def find_free_port(start_port):
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
        port += 1
    raise RuntimeError("No free ports available!")

SOCKS_PORT = 9050
CONTROL_PORT = 9051
PEER_PORT = 8080  # Port where Flask handles P2P traffic

# Active Tor process reference
tor_process = None

def cleanup():
    """Ensure Tor process is terminated on exit."""
    global tor_process
    if tor_process:
        print("Stopping Tor process...")
        tor_process.terminate()
        try:
            tor_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tor_process.kill()
        tor_process = None
        print("Tor stopped successfully.")

atexit.register(cleanup)

def setup_directories():
    """Create directory structure for Tor binaries, data, and service keys."""
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(TOR_DIR, exist_ok=True)
    os.makedirs(TOR_DATA_DIR, exist_ok=True)
    os.makedirs(TOR_SERVICE_DIR, exist_ok=True)

def find_tor_binary(search_path):
    """Recursively search for the Tor executable in extracted files."""
    for root, dirs, files in os.walk(search_path):
        for file in files:
            if file.lower() == EXE_NAME.lower():
                return os.path.join(root, file)
    return None

def download_and_extract_tor():
    """Download the Tor Expert Bundle and extract the binaries."""
    setup_directories()
    
    # Check if binary already exists locally
    local_binary = find_tor_binary(TOR_DIR)
    if local_binary and os.path.exists(local_binary):
        print(f"Found local Tor binary at {local_binary}")
        return local_binary

    # Download Tor Expert Bundle
    print(f"Downloading Tor Expert Bundle version {TOR_VERSION} for {SYSTEM}...")
    temp_archive = os.path.join(BIN_DIR, "tor_bundle.tar.gz")
    
    try:
        # User-agent header to avoid download blocks
        req = urllib.request.Request(
            TOR_URL, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(temp_archive, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        print("Download complete. Extracting archive...")
        
        # Safe extraction (guarding against directory traversal)
        with tarfile.open(temp_archive, "r:gz") as tar:
            for member in tar.getmembers():
                # Prevent path traversal vulnerabilities
                if member.name.startswith("/") or ".." in member.name:
                    continue
                tar.extract(member, path=TOR_DIR)
                
        print("Extraction complete.")
        
        # Clean up archive
        if os.path.exists(temp_archive):
            os.remove(temp_archive)
            
    except Exception as e:
        print(f"Failed to download/extract Tor: {e}")
        # Clean up on failure
        if os.path.exists(temp_archive):
            os.remove(temp_archive)
        raise e

    # Find the extracted executable
    extracted_binary = find_tor_binary(TOR_DIR)
    if not extracted_binary:
        raise FileNotFoundError("Could not find Tor binary inside the extracted files.")
    
    # Make executable on Unix platforms
    if SYSTEM != "windows":
        os.chmod(extracted_binary, 0o755)
        
    return extracted_binary

def write_torrc(socks_port, control_port, peer_port):
    """Write the torrc configuration file for the Onion Service."""
    # SOCKS5 proxy port, control port, and hidden service mapping
    torrc_content = f"""SocksPort 127.0.0.1:{socks_port}
ControlPort 127.0.0.1:{control_port}
CookieAuthentication 1
DataDirectory {TOR_DATA_DIR.replace(os.sep, '/')}
HiddenServiceDir {TOR_SERVICE_DIR.replace(os.sep, '/')}
HiddenServicePort 80 127.0.0.1:{peer_port}
"""
    with open(TOR_RC_PATH, "w") as f:
        f.write(torrc_content)
    print(f"Wrote torrc configuration to {TOR_RC_PATH}")

def get_onion_address():
    """Retrieve the generated onion address for this node."""
    hostname_path = os.path.join(TOR_SERVICE_DIR, "hostname")
    for _ in range(30):  # Wait up to 30 seconds for Tor to generate the hostname
        if os.path.exists(hostname_path):
            with open(hostname_path, "r") as f:
                onion = f.read().strip()
                if onion:
                    return onion
        time.sleep(1)
    raise FileNotFoundError("Tor failed to generate Onion service hostname.")

def launch_tor():
    """Launch the embedded Tor process and block until bootstrapped."""
    global tor_process, SOCKS_PORT, CONTROL_PORT, PEER_PORT
    
    # Dynamic port configuration if standard ports are in use
    SOCKS_PORT = find_free_port(9050)
    CONTROL_PORT = find_free_port(9051)
    PEER_PORT = find_free_port(8080)
    
    tor_binary = download_and_extract_tor()
    write_torrc(SOCKS_PORT, CONTROL_PORT, PEER_PORT)
    
    print(f"Launching Tor on SOCKS port {SOCKS_PORT}, Control port {CONTROL_PORT}...")
    
    # Start Tor process
    # Pass config file using -f
    tor_process = subprocess.Popen(
        [tor_binary, "-f", TOR_RC_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if SYSTEM == "windows" else 0
    )
    
    # Monitor bootstrapping progress
    bootstrapped = False
    start_time = time.time()
    
    while True:
        # Avoid hanging if the process dies
        if tor_process.poll() is not None:
            stdout, _ = tor_process.communicate()
            print(stdout)
            raise RuntimeError("Tor process exited prematurely.")
            
        line = tor_process.stdout.readline()
        if not line:
            break
            
        # Log Tor output
        if "Bootstrapped" in line:
            print(f"[Tor Log] {line.strip()}")
            
        if "Bootstrapped 100%" in line:
            bootstrapped = True
            print("Tor successfully bootstrapped!")
            break
            
        # Timeout after 2 minutes
        if time.time() - start_time > 120:
            cleanup()
            raise TimeoutError("Tor bootstrap timed out after 120 seconds.")
            
    if not bootstrapped:
        raise RuntimeError("Tor failed to bootstrap.")
        
    onion_address = get_onion_address()
    print(f"Your AnonyMus Onion Address: {onion_address}")
    return onion_address, SOCKS_PORT, PEER_PORT

if __name__ == "__main__":
    try:
        onion, socks, peer = launch_tor()
        print(f"Running... SOCKS proxy on 127.0.0.1:{socks}")
        print("Press Ctrl+C to terminate.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()
