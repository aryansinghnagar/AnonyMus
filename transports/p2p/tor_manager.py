"""
Tor Process Management Module for AnonyMus (P2P Decentralized Architecture).

Handles automated download, integrity verification, path traversal-safe extraction,
configuration writing (torrc), subprocess spawning, and bootstrap monitoring
for the embedded Tor Expert Bundle onion service proxy.

Perf fix P4: Tor circuit stickiness for outbound message routing.
==============================================================
Outbound HTTP-over-Tor requests (message transmission, chunk proxying,
presence pings) used to share a single SOCKS5 connection to the Tor daemon,
which means Tor routed them all through the SAME circuit. This causes two
problems:

  1. (Privacy) All peers see the same circuit exit identity — linkability.
  2. (Performance) When sending to a different peer, Tor would tear down the
     existing circuit and build a new one (100-300 ms latency) rather than
     reusing the existing circuit for the same peer.

The fix is *per-peer circuit isolation* via SOCKS5 username/password auth:
Tor's ``IsolateSOCKSAuth`` (enabled by default in modern torrc) routes each
unique (username, password) tuple through a separate circuit. By deriving
a stable per-peer auth tuple from a hash of (peer_onion + per-process salt),
we get:
  - Same peer → same circuit → reuses the established 3-hop circuit (~100-300 ms
    latency saving on subsequent messages to the same peer).
  - Different peers → different circuits → unlinkability.

The cache is exposed via ``get_peer_circuit_socks_url(peer_onion)`` and
``get_or_create_peer_httpx_client(peer_onion)``. Callers should prefer the
latter so connection pooling (HTTP keep-alive) is also per-peer, maximising
the latency savings.
"""

import atexit
import hashlib
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

# Configuration version and bundle extraction paths
TOR_VERSION = "15.0.16"
if getattr(sys, "frozen", False):
    APP_ROOT = os.path.dirname(sys.executable)
else:
    APP_ROOT = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
BIN_DIR = os.path.join(APP_ROOT, "bin")
TOR_DIR = os.path.join(BIN_DIR, "tor")
TOR_DATA_DIR = os.path.join(BIN_DIR, "tor_data")
TOR_SERVICE_DIR = os.path.join(BIN_DIR, "tor_service")
TOR_RC_PATH = os.path.join(BIN_DIR, "torrc")

# Detect platform
SYSTEM = platform.system().lower()
ARCH = platform.machine().lower()

# Resolve correct download URL and binary name for platform
if SYSTEM == "windows":
    TOR_URL = f"https://dist.torproject.org/torbrowser/{TOR_VERSION}/tor-expert-bundle-windows-x86_64-{TOR_VERSION}.tar.gz"
    EXE_NAME = "tor.exe"
elif SYSTEM == "darwin":
    TOR_URL = f"https://dist.torproject.org/torbrowser/{TOR_VERSION}/tor-expert-bundle-macos-x86_64-{TOR_VERSION}.tar.gz"
    EXE_NAME = "tor"
else:
    TOR_URL = f"https://dist.torproject.org/torbrowser/{TOR_VERSION}/tor-expert-bundle-linux-x86_64-{TOR_VERSION}.tar.gz"
    EXE_NAME = "tor"


def find_free_port(start_port):
    """
    Scans sequential network ports starting at start_port to find a free port.

    Args:
        start_port (int): Port index to begin scanning.

    Returns:
        int: Free port index.
    """
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                pass
        port += 1
    raise RuntimeError("No free ports available!")


SOCKS_PORT = 9050
CONTROL_PORT = 9051
PEER_PORT = 8080

# Spawned Tor subprocess reference
tor_process = None


def cleanup():
    """Ensures the background Tor process is cleanly terminated on application exit."""
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


# Register termination hook
atexit.register(cleanup)


def setup_directories():
    """Initializes local storage directory layout for Tor binaries and runtime logs."""
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(TOR_DIR, exist_ok=True)
    os.makedirs(TOR_DATA_DIR, exist_ok=True)
    os.makedirs(TOR_SERVICE_DIR, exist_ok=True)


def find_tor_binary(search_path):
    """
    Recursively scans search_path to locate the compiled Tor executable.

    Args:
        search_path (str): Target directory to traverse.

    Returns:
        str: Absolute path to the Tor executable, or None if not found.
    """
    for root, dirs, files in os.walk(search_path):
        for file in files:
            if file.lower() == EXE_NAME.lower():
                return os.path.join(root, file)
    return None


def calculate_sha256(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def fetch_expected_sha256(tor_version, filename):
    urls = [
        f"https://dist.torproject.org/torbrowser/{tor_version}/sha256sums-unsigned-builds.txt",
        f"https://dist.torproject.org/torbrowser/{tor_version}/sha256sums.txt",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req) as response:
                content = response.read().decode("utf-8")
            for line in content.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    h, f = parts[0], parts[1]
                    if f.lstrip("*") == filename:
                        return h
        except Exception:
            continue
    raise RuntimeError(
        f"Could not retrieve checksum for {filename} from Tor Project distribution server."
    )


def verify_gpg_signature(archive_path, signature_path):
    import shutil
    import subprocess

    gpg_bin = shutil.which("gpg")
    if not gpg_bin:
        return False

    try:
        print("Importing Tor Project signing key...")
        subprocess.run(
            [
                gpg_bin,
                "--keyserver",
                "keys.openpgp.org",
                "--recv-keys",
                "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )

        print("Verifying GPG signature...")
        res = subprocess.run(
            [gpg_bin, "--verify", signature_path, archive_path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if res.returncode == 0:
            print("GPG signature verification passed.")
            return True
        else:
            raise ValueError(
                f"Tor Expert Bundle GPG signature is INVALID! Verification failed:\n{res.stderr}"
            )
    except subprocess.SubprocessError as e:
        print(
            f"GPG subprocess error (keyserver offline?): {e}. Falling back to SHA-256."
        )
        return False


def download_and_extract_tor():
    """
    Downloads Tor Expert Bundle if not present locally and extracts it safely.

    Implements path traversal sanitization checks to block malicious tar archives.

    Returns:
        str: Path to the validated Tor executable.
    """
    setup_directories()

    local_binary = find_tor_binary(TOR_DIR)
    if local_binary and os.path.exists(local_binary):
        print(f"Found local Tor binary at {local_binary}")
        return local_binary

    print(f"Downloading Tor Expert Bundle version {TOR_VERSION} for {SYSTEM}...")
    temp_archive = os.path.join(BIN_DIR, "tor_bundle.tar.gz")

    try:
        # Construct download request with custom User-Agent to avoid CDN blocks
        req = urllib.request.Request(
            TOR_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with (
            urllib.request.urlopen(req) as response,
            open(temp_archive, "wb") as out_file,
        ):
            shutil.copyfileobj(response, out_file)

        # Try GPG validation if GPG is available
        import shutil as local_shutil

        gpg_bin = local_shutil.which("gpg")
        gpg_verified = False
        if gpg_bin:
            temp_sig = temp_archive + ".asc"
            print("Downloading Tor Expert Bundle GPG signature...")
            try:
                sig_req = urllib.request.Request(
                    TOR_URL + ".asc",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                )
                with (
                    urllib.request.urlopen(sig_req) as response,
                    open(temp_sig, "wb") as out_file,
                ):
                    local_shutil.copyfileobj(response, out_file)
                gpg_verified = verify_gpg_signature(temp_archive, temp_sig)
            except Exception as e:
                print(f"Failed to fetch/verify GPG signature: {e}")
            finally:
                if os.path.exists(temp_sig):
                    os.remove(temp_sig)

        # Verify integrity using SHA-256 if GPG was not verified
        if not gpg_verified:
            print("Verifying archive integrity via SHA-256...")
            archive_name = os.path.basename(TOR_URL)
            expected_hash = fetch_expected_sha256(TOR_VERSION, archive_name)
            actual_hash = calculate_sha256(temp_archive)
            if actual_hash != expected_hash:
                raise ValueError(
                    f"Tor Expert Bundle checksum mismatch!\n"
                    f"Expected: {expected_hash}\n"
                    f"Actual:   {actual_hash}"
                )
            print("Integrity verification passed.")
        else:
            print("Integrity verification passed via GPG.")

        print("Download complete. Extracting archive...")

        # Safely extract archive verifying directories to prevent directory traversal attacks
        with tarfile.open(temp_archive, "r:gz") as tar:
            real_tor_dir = os.path.realpath(TOR_DIR)
            for member in tar.getmembers():
                member_path = os.path.realpath(os.path.join(real_tor_dir, member.name))
                if (
                    not member_path.startswith(real_tor_dir + os.sep)
                    and member_path != real_tor_dir
                ):
                    # Ignore path traversal attempts outside target directory
                    continue
                tar.extract(member, path=real_tor_dir)

        print("Extraction complete.")

        if os.path.exists(temp_archive):
            os.remove(temp_archive)

    except Exception as e:
        print(f"Failed to download/extract Tor: {e}")
        if os.path.exists(temp_archive):
            os.remove(temp_archive)
        raise e

    extracted_binary = find_tor_binary(TOR_DIR)
    if not extracted_binary:
        raise FileNotFoundError("Could not find Tor binary inside the extracted files.")

    if SYSTEM != "windows":
        os.chmod(extracted_binary, 0o755)

    return extracted_binary


TOR_SERVICES_PARENT_DIR = os.path.join(BIN_DIR, "hidden_services")


def write_torrc(socks_port, control_port, peer_port):
    """
    Writes custom configuration settings (torrc) for all Onion Hidden Services.
    """
    os.makedirs(TOR_SERVICES_PARENT_DIR, exist_ok=True)

    # Migrate old tor_service to hidden_services/main if it exists
    main_service_dir = os.path.join(TOR_SERVICES_PARENT_DIR, "main")
    if not os.path.exists(main_service_dir):
        if os.path.exists(TOR_SERVICE_DIR):
            try:
                shutil.copytree(TOR_SERVICE_DIR, main_service_dir)
            except Exception:
                os.makedirs(main_service_dir, exist_ok=True)
        else:
            os.makedirs(main_service_dir, exist_ok=True)

    # Find all hidden service directories
    subdirs = []
    if os.path.exists(TOR_SERVICES_PARENT_DIR):
        for name in os.listdir(TOR_SERVICES_PARENT_DIR):
            path = os.path.join(TOR_SERVICES_PARENT_DIR, name)
            if os.path.isdir(path):
                subdirs.append(path)

    torrc_content = f"""SocksPort 127.0.0.1:{socks_port}
ControlPort 127.0.0.1:{control_port}
CookieAuthentication 1
DataDirectory {TOR_DATA_DIR.replace(os.sep, "/")}
"""
    for s_dir in subdirs:
        torrc_content += f"""HiddenServiceDir {s_dir.replace(os.sep, "/")}
HiddenServicePort 80 127.0.0.1:{peer_port}
"""

    with open(TOR_RC_PATH, "w") as f:
        f.write(torrc_content)
    print(f"Wrote torrc configuration with {len(subdirs)} services to {TOR_RC_PATH}")


def reload_tor_config(control_port):
    """Sends the SIGNAL RELOAD command over the Tor control port using Cookie Authentication."""
    cookie_path = os.path.join(TOR_DATA_DIR, "control_auth_cookie")
    if not os.path.exists(cookie_path):
        raise FileNotFoundError("Tor control auth cookie not found.")

    with open(cookie_path, "rb") as f:
        cookie_bytes = f.read()
    cookie_hex = cookie_bytes.hex().upper()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", control_port))
        s.recv(1024)  # Read banner

        # Authenticate
        s.sendall(f"AUTHENTICATE {cookie_hex}\r\n".encode())
        resp = s.recv(1024).decode()
        if "250" not in resp:
            raise RuntimeError(f"Tor control authentication failed: {resp}")

        # Signal reload
        s.sendall(b"SIGNAL RELOAD\r\n")
        resp = s.recv(1024).decode()
        if "250" not in resp:
            raise RuntimeError(f"Tor configuration reload failed: {resp}")
        print("Tor configuration reloaded successfully!")
    finally:
        s.close()


def add_onion_service(service_name: str) -> str:
    """
    Configures and spins up a new hidden service dynamically.

    Args:
        service_name (str): Unique subfolder identifier.

    Returns:
        str: Generated .onion address.
    """
    service_dir = os.path.join(TOR_SERVICES_PARENT_DIR, service_name)
    os.makedirs(service_dir, exist_ok=True)

    # Update configuration file and trigger Tor reload
    write_torrc(SOCKS_PORT, CONTROL_PORT, PEER_PORT)
    reload_tor_config(CONTROL_PORT)

    # Wait for the hostname to be generated by Tor
    hostname_path = os.path.join(service_dir, "hostname")
    for _ in range(30):
        if os.path.exists(hostname_path):
            with open(hostname_path) as f:
                onion = f.read().strip()
                if onion:
                    return onion
        time.sleep(1)
    raise FileNotFoundError(f"Tor failed to generate hostname for {service_name}")


def get_onion_address():
    """
    Monitors the main Hidden Service directory to extract its generated hostname.

    Returns:
        str: Generated onion service address.
    """
    main_dir = os.path.join(TOR_SERVICES_PARENT_DIR, "main")
    hostname_path = os.path.join(main_dir, "hostname")
    for _ in range(30):  # Wait up to 30 seconds for hostname generation
        if os.path.exists(hostname_path):
            with open(hostname_path) as f:
                onion = f.read().strip()
                if onion:
                    return onion
        time.sleep(1)
    raise FileNotFoundError("Tor failed to generate main Onion service hostname.")


def launch_tor(peer_port=None):
    """
    Spawns background Tor service, monitoring logs to block until bootstrap completes.

    Returns:
        tuple: (onion_address, socks_port, peer_port) configuration parameters.
    """
    global tor_process, SOCKS_PORT, CONTROL_PORT, PEER_PORT

    # Resolve unused network ports dynamically
    SOCKS_PORT = find_free_port(9050)
    CONTROL_PORT = find_free_port(9051)
    if peer_port is not None:
        PEER_PORT = peer_port
    else:
        PEER_PORT = find_free_port(8080)

    tor_binary = download_and_extract_tor()
    write_torrc(SOCKS_PORT, CONTROL_PORT, PEER_PORT)

    print(f"Launching Tor on SOCKS port {SOCKS_PORT}, Control port {CONTROL_PORT}...")

    # Spawn background Tor process, suppressing popup terminal on Windows
    tor_process = subprocess.Popen(
        [tor_binary, "-f", TOR_RC_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if SYSTEM == "windows" else 0,
    )

    bootstrapped = False
    start_time = time.time()

    while True:
        if tor_process.poll() is not None:
            stdout, _ = tor_process.communicate()
            print(stdout)
            raise RuntimeError("Tor process exited prematurely.")

        line = tor_process.stdout.readline()
        if not line:
            break

        if "Bootstrapped" in line:
            print(f"[Tor Log] {line.strip()}")

        if "Bootstrapped 100%" in line:
            bootstrapped = True
            print("Tor successfully bootstrapped!")
            break

        # Fail if bootstrap does not complete within 120s
        if time.time() - start_time > 120:
            cleanup()
            raise TimeoutError("Tor bootstrap timed out after 120 seconds.")

    if not bootstrapped:
        raise RuntimeError("Tor failed to bootstrap.")

    onion_address = get_onion_address()
    print(f"Your User ID (Onion Address): {onion_address}")
    return onion_address, SOCKS_PORT, PEER_PORT


# ============================================================================
# Perf fix P4: Tor circuit stickiness for outbound message routing.
# ============================================================================


# Per-process random salt mixed into the per-peer SOCKS5 auth tuple so two
# AnonyMus processes on the same machine don't share circuits (different salt
# → different (user, pass) → different Tor circuits even for the same peer).
_PROCESS_CIRCUIT_SALT: bytes = os.urandom(16)
_PEER_CLIENT_CACHE: dict[str, "object"] = {}  # peer_onion -> httpx.AsyncClient
_PEER_CLIENT_LOCK = threading.Lock()
_PEER_CLIENT_TTL_SECONDS = 300.0  # 5 min idle → close & rebuild on next use


def _peer_circuit_auth(peer_onion: str) -> tuple[str, str]:
    """Derive a stable per-peer SOCKS5 (username, password) tuple.

    The tuple is derived from ``SHA-256(peer_onion || process_salt)`` so:
      - Same peer + same process → same tuple → same Tor circuit (stickiness).
      - Same peer + different process → different tuple → different circuit
        (prevents cross-process linkability).
      - Different peers → different tuples → different circuits
        (prevents peer-to-peer linkability via shared circuit exit).
    """
    h = hashlib.sha256(peer_onion.encode("utf-8") + _PROCESS_CIRCUIT_SALT).digest()
    # SOCKS5 auth fields are arbitrary bytes; use base32 for filesystem-safe
    # representation in case Tor logs them.
    user = h[:12].hex()
    password = h[12:24].hex()
    return user, password


def get_peer_circuit_socks_url(peer_onion: str) -> str:
    """Return a SOCKS5h URL with per-peer auth for circuit stickiness.

    The URL uses the ``socks5h://`` scheme so DNS resolution happens on the
    Tor side (important for ``.onion`` addresses, which are not real DNS
    names but Tor-internal service identifiers).

    Perf fix P4: by using a stable per-peer (user, pass) tuple, Tor's
    ``IsolateSOCKSAuth`` (default-on) routes each peer through a separate
    circuit. Subsequent messages to the same peer reuse the established
    circuit, saving ~100-300 ms of circuit-construction latency.
    """
    user, password = _peer_circuit_auth(peer_onion)
    return f"socks5h://{user}:{password}@127.0.0.1:{SOCKS_PORT}"


def get_peer_circuit_proxies(peer_onion: str) -> dict[str, str]:
    """Return an httpx-compatible proxies dict for the given peer."""
    url = get_peer_circuit_socks_url(peer_onion)
    return {"http://": url, "https://": url}


async def get_or_create_peer_httpx_client(peer_onion: str, timeout: float = 10.0):
    """Return a cached httpx.AsyncClient bound to a per-peer Tor circuit.

    Perf fix P4: returns a long-lived httpx.AsyncClient per peer so:
      - HTTP keep-alive reuses the TCP+TLS connection to the peer's onion
        service (saves another 50-100 ms per request after the first).
      - The SOCKS5 auth tuple is set once per client (Tor circuit stickiness).

    Clients are cached for ``_PEER_CLIENT_TTL_SECONDS`` (300s by default);
    an idle client is closed and rebuilt on the next call to avoid keeping
    a Tor circuit open forever (Tor will eventually rotate the circuit
    anyway after its 10-minute max circuit lifetime).
    """
    import httpx

    now = time.monotonic()
    # Clean up stale clients opportunistically.
    with _PEER_CLIENT_LOCK:
        stale: list[str] = []
        for onion, (client, last_used) in _PEER_CLIENT_CACHE.items():
            if now - last_used > _PEER_CLIENT_TTL_SECONDS:
                stale.append(onion)
        for onion in stale:
            client, _ = _PEER_CLIENT_CACHE.pop(onion, (None, None))
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass

    cached = _PEER_CLIENT_CACHE.get(peer_onion)
    if cached is not None:
        client, _ = cached
        _PEER_CLIENT_CACHE[peer_onion] = (client, now)
        return client

    # Build a new client with per-peer circuit proxies.
    # Note: socks5h requires the optional ``socksio`` package (installed via
    # ``httpx[socks]``). If absent, fall back to the plain SOCKS5 URL
    # without auth (circuit stickiness is lost but functionality is preserved).
    try:
        proxies = get_peer_circuit_proxies(peer_onion)
        client = httpx.AsyncClient(proxies=proxies, timeout=timeout)
    except Exception:
        # Fallback: no auth on the proxy URL.
        proxies = {
            "http://": f"socks5://127.0.0.1:{SOCKS_PORT}",
            "https://": f"socks5://127.0.0.1:{SOCKS_PORT}",
        }
        client = httpx.AsyncClient(proxies=proxies, timeout=timeout)

    with _PEER_CLIENT_LOCK:
        _PEER_CLIENT_CACHE[peer_onion] = (client, now)
    return client


async def close_all_peer_clients() -> None:
    """Close all cached per-peer httpx clients (used on shutdown)."""
    with _PEER_CLIENT_LOCK:
        items = list(_PEER_CLIENT_CACHE.items())
        _PEER_CLIENT_CACHE.clear()
    for _, (client, _) in items:
        try:
            await client.aclose()
        except Exception:
            pass


atexit.register(lambda: None)  # placeholder; async close must be explicit


if __name__ == "__main__":
    try:
        onion, socks, peer = launch_tor()
        print(f"Running... SOCKS proxy on 127.0.0.1:{socks}")
        print("Press Ctrl+C to terminate.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()
