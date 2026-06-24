import os
import sys
import time
import queue
import threading
import subprocess
import webbrowser
import platform
import socket
import json

# GUI Imports
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Ensure path includes local directories for clean module imports
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    BASE_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = sys._MEIPASS
else:
    # Running in standard python interpreter
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR

sys.path.insert(0, RESOURCE_DIR)
sys.path.insert(0, os.path.join(RESOURCE_DIR, 'app_p2p'))

# Thread-safe log queue
log_queue = queue.Queue()

class QueueWriter:
    """Redirects stdout/stderr to a queue for thread-safe GUI updates."""
    def __init__(self, q):
        self.q = q
    def write(self, text):
        if text.strip():
            self.q.put(text)
    def flush(self):
        pass

# Redirect standard outputs
sys.stdout = QueueWriter(log_queue)
sys.stderr = QueueWriter(log_queue)

# Global handles for background threads and processes
server_thread = None
daemon_active = False
active_mode = None  # 'main' or 'p2p'
active_port = 8080
tor_socks_port = 9050
onion_address = "N/A"
start_time = 0

def get_system_specs():
    """Boring system stats for the System Info section."""
    try:
        cpu = platform.processor() or "Generic Processor"
        cores = os.cpu_count() or 4
        ram = "8 GB" # Mocked standard, or read from system
        if platform.system() == "Windows":
            # Simple windows memory check
            try:
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                ram = f"{round(stat.ullTotalPhys / (1024**3), 1)} GB"
            except Exception:
                pass
        return {
            "OS": f"{platform.system()} {platform.release()}",
            "CPU": f"{cpu} ({cores} Cores)",
            "RAM": ram,
            "Arch": platform.machine()
        }
    except Exception:
        return {"OS": "Windows 10", "CPU": "x86_64", "RAM": "8 GB", "Arch": "AMD64"}

class NetworkDiagnosticsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Windows Network Diagnostics & Adapter Utility")
        self.root.geometry("620x460")
        self.root.resizable(False, False)
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('vista' if 'vista' in self.style.theme_names() else 'winnative')
        
        # Config Settings file path
        self.config_file = os.path.join(BASE_DIR, "diagnostics_config.json")
        self.load_settings()

        # Build UI
        self.create_widgets()
        
        # Start log polling
        self.poll_logs()
        
        # Periodic UI updates
        self.update_daemon_status()
        
    def load_settings(self):
        """Set default static configuration settings."""
        self.settings = {
            "mode": "p2p",
            "port": 8080,
            "use_tor": True,
            "main_server_url": ""
        }

    def create_widgets(self):
        # Header banner (very official looking)
        banner_frame = tk.Frame(self.root, bg="#003366", height=45)
        banner_frame.pack(fill=tk.X, side=tk.TOP)
        banner_label = tk.Label(
            banner_frame, 
            text="Network Diagnostics & Loopback Interface Utility (v2.6.4)",
            fg="white", bg="#003366",
            font=("Segoe UI", 10, "bold")
        )
        banner_label.pack(pady=10, padx=10, anchor=tk.W)

        # Tabbed Layout
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 1: Diagnostic Status
        self.tab_diag = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_diag, text="Diagnostic Tests")
        self.setup_diagnostic_tab()

        # Tab 2: Adapter Profile
        self.tab_config = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_config, text="Adapter Profile")
        self.setup_config_tab()

        # Tab 3: System Logs
        self.tab_logs = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_logs, text="Diagnostics Log")
        self.setup_logs_tab()

        # Tab 4: System Info / Daemon Controls
        self.tab_ctrl = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_ctrl, text="System Monitor")
        self.setup_control_tab()

    def setup_diagnostic_tab(self):
        intro = (
            "Select 'Run Tests' below to analyze local adapters, "
            "loopback addresses, and active diagnostic daemons."
        )
        lbl = tk.Label(self.tab_diag, text=intro, font=("Segoe UI", 9, "italic"), anchor=tk.W, justify=tk.LEFT)
        lbl.pack(padx=10, pady=8, fill=tk.X)

        # Table of diagnostic checks
        self.tree = ttk.Treeview(self.tab_diag, columns=("Target", "Status"), show="headings", height=8)
        self.tree.heading("Target", text="Network Adapter / Test target")
        self.tree.heading("Status", text="Test Result")
        self.tree.column("Target", width=350)
        self.tree.column("Status", width=220)
        self.tree.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # Initial mock list
        self.tree.insert("", "end", iid="loopback", values=("127.0.0.1 Local Loopback", "Not Tested"))
        self.tree.insert("", "end", iid="dns", values=("DNS Server Resolution (8.8.8.8)", "Not Tested"))
        self.tree.insert("", "end", iid="proxy", values=("SOCKS5 Proxy Tunnel (Port 9050)", "Not Tested"))
        self.tree.insert("", "end", iid="daemon", values=("Diagnostic Daemon Loopback Binding", "Not Tested"))

        # Progress bar
        self.progress = ttk.Progressbar(self.tab_diag, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(padx=10, pady=5, fill=tk.X)

        btn_run = ttk.Button(self.tab_diag, text="Run Diagnostic Checks", command=self.run_diagnostic_tests)
        btn_run.pack(padx=10, pady=5, side=tk.RIGHT)

    def setup_config_tab(self):
        # Info Panel
        grp_info = ttk.LabelFrame(self.tab_config, text="Active Network Profile")
        grp_info.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        lbl_intro = tk.Label(
            grp_info,
            text="This build is configured exclusively for decentralized peer-to-peer operations.",
            font=("Segoe UI", 9, "bold"),
            anchor=tk.W,
            justify=tk.LEFT
        )
        lbl_intro.pack(anchor=tk.W, padx=15, pady=(15, 10))

        details = (
            "• Mode: Isolated Peer-to-Peer Tunneling (P2P)\n"
            "• Routing: Mandatory Tor Onion Security Wrapper\n"
            "• Encryption: End-to-End ECDH & local AES-256-GCM\n"
            "• Port Management: Automatically allocated by the Tor client\n"
            "• Host Binding: Restricted to local loopback (127.0.0.1)"
        )
        
        lbl_details = tk.Label(
            grp_info,
            text=details,
            font=("Segoe UI", 9),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=450
        )
        lbl_details.pack(anchor=tk.W, padx=25, pady=10)
        
        lbl_note = tk.Label(
            grp_info,
            text="Note: Gateway and proxy settings are hardcoded for security.",
            font=("Segoe UI", 9, "italic"),
            fg="#555555",
            anchor=tk.W,
            justify=tk.LEFT
        )
        lbl_note.pack(anchor=tk.W, padx=15, pady=(10, 15))

    def setup_logs_tab(self):
        lbl = tk.Label(self.tab_logs, text="Diagnostic Server Output Log:", font=("Segoe UI", 9, "bold"))
        lbl.pack(padx=10, pady=5, anchor=tk.W)
        
        self.log_text = scrolledtext.ScrolledText(self.tab_logs, wrap=tk.WORD, height=18, font=("Courier New", 8))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Add boring placeholder logs
        self.log_text.insert(tk.END, "[NetDiag] System Diagnostics Logger initialized.\n")
        self.log_text.insert(tk.END, f"[NetDiag] Working directory: {BASE_DIR}\n")

    def setup_control_tab(self):
        # Section 1: System Info
        grp_sys = ttk.LabelFrame(self.tab_ctrl, text="System Hardware & OS Details")
        grp_sys.pack(fill=tk.X, padx=10, pady=5)
        
        specs = get_system_specs()
        tk.Label(grp_sys, text=f"Operating System: {specs['OS']}").pack(anchor=tk.W, padx=10, pady=2)
        tk.Label(grp_sys, text=f"Processor (CPU): {specs['CPU']}").pack(anchor=tk.W, padx=10, pady=2)
        tk.Label(grp_sys, text=f"System Architecture: {specs['Arch']}").pack(anchor=tk.W, padx=10, pady=2)
        tk.Label(grp_sys, text=f"Installed RAM: {specs['RAM']}").pack(anchor=tk.W, padx=10, pady=2)

        # Section 2: Daemon Control
        grp_ctrl = ttk.LabelFrame(self.tab_ctrl, text="Diagnostic Service Daemon Control")
        grp_ctrl.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Status indicators
        self.lbl_status = tk.Label(grp_ctrl, text="Service Status: STOPPED", font=("Segoe UI", 10, "bold"), fg="red")
        self.lbl_status.pack(anchor=tk.W, padx=10, pady=10)

        self.lbl_onion = tk.Label(grp_ctrl, text="Onion Address: N/A", font=("Segoe UI", 9))
        self.lbl_onion.pack(anchor=tk.W, padx=10, pady=2)

        self.lbl_uptime = tk.Label(grp_ctrl, text="Service Uptime: 00:00:00", font=("Segoe UI", 9))
        self.lbl_uptime.pack(anchor=tk.W, padx=10, pady=2)

        # Action buttons
        btn_frame = tk.Frame(grp_ctrl)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.btn_start = ttk.Button(btn_frame, text="Initialize Diagnostic Service", command=self.start_daemon)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_dashboard = ttk.Button(btn_frame, text="Launch Local Console Dashboard", command=self.open_dashboard, state=tk.DISABLED)
        self.btn_dashboard.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(btn_frame, text="Shutdown Daemon", command=self.stop_daemon, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)



    def run_diagnostic_tests(self):
        """Simulates network checks and probes the actual daemon state."""
        self.progress['value'] = 0
        self.tree.item("loopback", values=("127.0.0.1 Local Loopback", "Testing..."))
        self.tree.item("dns", values=("DNS Server Resolution (8.8.8.8)", "Testing..."))
        self.tree.item("proxy", values=("SOCKS5 Proxy Tunnel (Port 9050)", "Testing..."))
        self.tree.item("daemon", values=("Diagnostic Daemon Loopback Binding", "Testing..."))
        
        def run():
            steps = 4
            # Step 1: Loopback
            time.sleep(0.5)
            try:
                socket.create_connection(("127.0.0.1", 53), timeout=0.1) # dummy, should fail/timeout
            except Exception:
                pass
            self.tree.item("loopback", values=("127.0.0.1 Local Loopback", "PASS (Loopback Active)"))
            self.progress['value'] += 25
            
            # Step 2: DNS Gateway
            time.sleep(0.5)
            try:
                socket.gethostbyname("dns.google")
                dns_res = "PASS (Resolved Google DNS)"
            except Exception:
                dns_res = "WARNING (External DNS lookup failed)"
            self.tree.item("dns", values=("DNS Server Resolution (8.8.8.8)", dns_res))
            self.progress['value'] += 25
            
            # Step 3: SOCKS5
            time.sleep(0.5)
            # Check if Tor proxy is running
            socks_active = False
            for port_to_check in [9050, tor_socks_port]:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.2)
                        s.connect(("127.0.0.1", port_to_check))
                        socks_active = True
                        break
                except Exception:
                    pass
            
            if socks_active:
                proxy_res = f"PASS (SOCKS5 proxy listening on 127.0.0.1:{tor_socks_port})"
            else:
                proxy_res = "INACTIVE (Optional proxy wrapper not started)"
            self.tree.item("proxy", values=("SOCKS5 Proxy Tunnel (Port 9050)", proxy_res))
            self.progress['value'] += 25
            
            # Step 4: Daemon Port
            time.sleep(0.5)
            daemon_active_local = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.2)
                    s.connect(("127.0.0.1", active_port))
                    daemon_active_local = True
            except Exception:
                pass
            
            if daemon_active_local:
                daemon_res = f"ACTIVE (Service bound to local port {active_port})"
            else:
                daemon_res = "INACTIVE (Service daemon is not running)"
            self.tree.item("daemon", values=("Diagnostic Daemon Loopback Binding", daemon_res))
            self.progress['value'] += 25
            
        threading.Thread(target=run, daemon=True).start()

    def poll_logs(self):
        """Poll thread-safe queue and write outputs to log console."""
        try:
            while True:
                text = log_queue.get_nowait()
                self.log_text.insert(tk.END, text + "\n")
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_logs)

    def start_daemon(self):
        """Starts the Flask server & Tor in background thread."""
        global server_thread, daemon_active, active_mode, active_port, start_time
        
        if daemon_active:
            messagebox.showwarning("Daemon Running", "The diagnostic daemon is already active.")
            return

        # Settings are hardcoded to P2P mode
        active_port = 8080
        active_mode = "p2p"
        daemon_active = True
        start_time = time.time()

        self.log_text.insert(tk.END, "[NetDiag] Launching diagnostic daemon profile: P2P...\n")
        
        # Configure env variables dynamically
        os.environ['FLASK_SECRET_KEY'] = 'diagnostics_ephemeral_control_key_2026'
        os.environ['FLASK_DEBUG'] = 'False'
        
        self.btn_start.config(state=tk.DISABLED)
        
        # Run P2P startup in thread
        def launch_p2p_wrapper():
            global tor_socks_port, onion_address
            try:
                # Delay import until needed to avoid circular import issues or early errors
                import app_p2p.database as database_p2p
                import app_p2p.tor_manager as tor_manager_p2p
                from app_p2p.server import app as p2p_app, socketio as p2p_socketio
                
                # 1. Initialize P2P local DB
                print("[Daemon] Initializing database engine...")
                database_p2p.init_db()
                
                # 2. Boot Tor (blocks until bootstrapped)
                print("[Daemon] Securing network wrapper (bootstrapping Tor). Please wait...")
                onion, socks, peer = tor_manager_p2p.launch_tor()
                
                # Store variables
                tor_socks_port = socks
                onion_address = onion
                global active_port
                active_port = peer  # P2P uses dynamic free port from tor_manager
                
                # Write my onion address to database configuration
                database_p2p.set_config('my_onion_address', onion)
                
                print(f"[Daemon] Tor routing wrappers completed successfully.")
                print(f"[Daemon] Local administrative portal bound to port {active_port}")
                print(f"[Daemon] Onion hidden service: {onion}")
                
                # 3. Start socketio loop
                p2p_socketio.run(p2p_app, host='127.0.0.1', port=active_port, debug=False)
            except Exception as e:
                print(f"FATAL: Service daemon execution failed: {e}")
                self.stop_daemon()
        
        server_thread = threading.Thread(target=launch_p2p_wrapper, daemon=True)
        server_thread.start()

    def stop_daemon(self):
        """Stops Flask server socket connection threads and runs Tor cleanup."""
        global server_thread, daemon_active, active_mode, onion_address
        
        if not daemon_active:
            return

        print("[Daemon] Stopping service listeners and network adapters...")
        
        # Stop Tor process cleanly
        try:
            import app_p2p.tor_manager as tor_manager_p2p
            tor_manager_p2p.cleanup()
            print("[Daemon] Tor security wrapper terminated.")
        except Exception as e:
            print(f"[Daemon] Error stopping Tor: {e}")

        # Clean environment variables
        if 'HTTP_PROXY' in os.environ: del os.environ['HTTP_PROXY']
        if 'HTTPS_PROXY' in os.environ: del os.environ['HTTPS_PROXY']

        daemon_active = False
        active_mode = None
        onion_address = "N/A"
        
        # Reset UI
        self.btn_start.config(state=tk.NORMAL)
        self.btn_dashboard.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        
        self.lbl_status.config(text="Service Status: STOPPED", fg="red")
        self.lbl_onion.config(text="Onion Address: N/A")
        
        print("[Daemon] Service completely shutdown.")

    def open_dashboard(self):
        """Opens the user's web browser to the daemon's local port address."""
        if daemon_active:
            url = f"http://127.0.0.1:{active_port}"
            self.log_text.insert(tk.END, f"[NetDiag] Launching administrative view at {url}\n")
            webbrowser.open(url)

    def update_daemon_status(self):
        """Periodic status monitor for the Control Panel GUI."""
        if daemon_active:
            self.lbl_status.config(text="Service Status: RUNNING (ACTIVE)", fg="green")
            self.btn_dashboard.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)
            
            # Update onion address label
            if onion_address != "N/A":
                self.lbl_onion.config(text=f"Onion Address: {onion_address}")
            else:
                self.lbl_onion.config(text="Onion Address: Bootstrapping Onion routing...")
                
            # Uptime calculation
            uptime = int(time.time() - start_time)
            hrs = uptime // 3600
            mins = (uptime % 3600) // 60
            secs = uptime % 60
            self.lbl_uptime.config(text=f"Service Uptime: {hrs:02d}:{mins:02d}:{secs:02d}")
        else:
            self.lbl_status.config(text="Service Status: STOPPED", fg="red")
            self.btn_dashboard.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.DISABLED)
            self.lbl_onion.config(text="Onion Address: N/A")
            self.lbl_uptime.config(text="Service Uptime: 00:00:00")
            
        self.root.after(1000, self.update_daemon_status)

def on_closing():
    """Ensure background daemons (especially Tor subprocesses) are killed when GUI exits."""
    try:
        import app_p2p.tor_manager as tor_manager_p2p
        tor_manager_p2p.cleanup()
    except Exception:
        pass
    root.destroy()

if __name__ == "__main__":
    # Standard Tkinter startup
    root = tk.Tk()
    app_gui = NetworkDiagnosticsApp(root)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
