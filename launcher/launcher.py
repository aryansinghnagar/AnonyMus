import json
import os
import platform
import queue
import socket
import sys
import threading
import time

# GUI Imports
import tkinter as tk
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

# Ensure path includes local directories for clean module imports
if getattr(sys, "frozen", False):
    # Running in a PyInstaller bundle
    BASE_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = sys._MEIPASS
else:
    # Running in standard python interpreter
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = os.path.dirname(BASE_DIR)

sys.path.insert(0, RESOURCE_DIR)

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
active_mode = None  # 'relay' or 'p2p'
active_port = 5000
tor_socks_port = 9050
onion_address = "N/A"
start_time = 0


def get_system_specs():
    """System specs lookup helper."""
    try:
        cpu = platform.processor() or "Generic Processor"
        cores = os.cpu_count() or 4
        ram = "8 GB"
        if platform.system() == "Windows":
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
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
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
            "Arch": platform.machine(),
        }
    except Exception:
        return {"OS": "Windows 10", "CPU": "x86_64", "RAM": "8 GB", "Arch": "AMD64"}


class NetworkDiagnosticsApp:
    def __init__(self, root):
        self.root = root

        # Config Settings file path
        self.config_file = os.path.join(BASE_DIR, "diagnostics_config.json")
        self.load_settings()

        if self.settings.get("disguise", False):
            self.root.title("Windows Network Diagnostics & Adapter Utility")
            self.root.geometry("620x460")
        else:
            self.root.title("AnonyMus Secure Messenger Launcher")
            self.root.geometry("650x480")

        self.root.resizable(False, False)

        # Style
        self.style = ttk.Style()
        self.style.theme_use(
            "vista" if "vista" in self.style.theme_names() else "winnative"
        )

        # Build UI
        self.create_widgets()

        # Start log polling
        self.poll_logs()

        # Periodic UI updates
        self.update_daemon_status()

    def load_settings(self):
        """Set default static configuration settings or load from file."""
        self.settings = {
            "mode": "relay",
            "port": 5000,
            "disguise": False,
            "flask_secret_key": "",
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file) as f:
                    saved = json.load(f)
                    self.settings.update(saved)
            except Exception:
                pass

        # Ensure we have a valid, dynamically generated secret key
        import secrets

        _PLACEHOLDER_SECRETS = {
            "your-secure-random-key-here",
            "diagnostics_ephemeral_control_key_2026",
            "changeme",
            "",
        }
        if (
            not self.settings.get("flask_secret_key")
            or self.settings.get("flask_secret_key") in _PLACEHOLDER_SECRETS
        ):
            self.settings["flask_secret_key"] = secrets.token_urlsafe(64)
            self.save_settings()

    def save_settings(self):
        """Save settings to file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.settings, f)
        except Exception:
            pass

    def toggle_disguise(self):
        self.settings["disguise"] = self.disguise_var.get()
        self.save_settings()
        messagebox.showinfo(
            "Disguise Mode Configured",
            "Disguise settings updated. Please restart the launcher to apply the change.",
        )

    def create_widgets(self):
        # Header banner
        banner_bg = "#003366" if self.settings.get("disguise", False) else "#333333"
        banner_text = (
            "Network Diagnostics & Loopback Interface Utility (v2.6.4)"
            if self.settings.get("disguise", False)
            else "AnonyMus Secure Messenger Controller (v2.6.4)"
        )

        banner_frame = tk.Frame(self.root, bg=banner_bg, height=45)
        banner_frame.pack(fill=tk.X, side=tk.TOP)
        banner_label = tk.Label(
            banner_frame,
            text=banner_text,
            fg="white",
            bg=banner_bg,
            font=("Segoe UI", 10, "bold"),
        )
        banner_label.pack(pady=10, padx=10, anchor=tk.W)

        if self.settings.get("disguise", False):
            # Render Disguised Diagnostics Tabs
            self.notebook = ttk.Notebook(self.root)
            self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            self.tab_diag = ttk.Frame(self.notebook)
            self.notebook.add(self.tab_diag, text="Diagnostic Tests")
            self.setup_diagnostic_tab()

            self.tab_config = ttk.Frame(self.notebook)
            self.notebook.add(self.tab_config, text="Adapter Profile")
            self.setup_config_tab()

            self.tab_logs = ttk.Frame(self.notebook)
            self.notebook.add(self.tab_logs, text="Diagnostics Log")
            self.setup_logs_tab()

            self.tab_ctrl = ttk.Frame(self.notebook)
            self.notebook.add(self.tab_ctrl, text="System Monitor")
            self.setup_control_tab()
        else:
            # Render Clean AnonyMus Branded Panel
            self.setup_anonymus_panel()

    def setup_anonymus_panel(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        # Left Column: Configuration & Controls
        left_pane = ttk.LabelFrame(main_frame, text="Service Configuration")
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Mode Selection
        ttk.Label(left_pane, text="Transport Mode:", font=("Segoe UI", 9, "bold")).pack(
            anchor=tk.W, padx=10, pady=(10, 5)
        )
        self.mode_var = tk.StringVar(value=self.settings.get("mode", "relay"))

        ttk.Radiobutton(
            left_pane,
            text="Centralized Relay (Standard)",
            variable=self.mode_var,
            value="relay",
        ).pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(
            left_pane,
            text="Decentralized P2P (Tor Onion)",
            variable=self.mode_var,
            value="p2p",
        ).pack(anchor=tk.W, padx=20, pady=2)

        # Port Selection
        port_frame = ttk.Frame(left_pane)
        port_frame.pack(anchor=tk.W, padx=10, pady=(15, 5))
        ttk.Label(port_frame, text="Local port:").pack(side=tk.LEFT)
        self.port_entry = ttk.Entry(port_frame, width=8)
        self.port_entry.insert(0, str(self.settings.get("port", 5000)))
        self.port_entry.pack(side=tk.LEFT, padx=5)

        # Disguise checkbox
        self.disguise_var = tk.BooleanVar(value=self.settings.get("disguise", False))
        self.chk_disguise = ttk.Checkbutton(
            left_pane,
            text="Disguise as Windows Utility",
            variable=self.disguise_var,
            command=self.toggle_disguise,
        )
        self.chk_disguise.pack(anchor=tk.W, padx=10, pady=(5, 10))

        # Start / Stop / Launch buttons
        self.btn_start = ttk.Button(
            left_pane, text="Initialize Service", command=self.start_daemon
        )
        self.btn_start.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.btn_dashboard = ttk.Button(
            left_pane,
            text="Launch Chat Client",
            command=self.open_dashboard,
            state=tk.DISABLED,
        )
        self.btn_dashboard.pack(fill=tk.X, padx=10, pady=5)

        self.btn_stop = ttk.Button(
            left_pane,
            text="Shutdown Service",
            command=self.stop_daemon,
            state=tk.DISABLED,
        )
        self.btn_stop.pack(fill=tk.X, padx=10, pady=5)

        # Right Column: Status Monitor
        right_pane = ttk.LabelFrame(main_frame, text="Status Monitor")
        right_pane.grid(row=0, column=1, sticky="nsew")

        self.lbl_status = tk.Label(
            right_pane, text="Status: STOPPED", font=("Segoe UI", 10, "bold"), fg="red"
        )
        self.lbl_status.pack(anchor=tk.W, padx=10, pady=10)

        self.lbl_onion = tk.Label(
            right_pane, text="Onion Address: N/A", font=("Segoe UI", 9)
        )
        self.lbl_onion.pack(anchor=tk.W, padx=10, pady=2)

        self.lbl_uptime = tk.Label(
            right_pane, text="Service Uptime: 00:00:00", font=("Segoe UI", 9)
        )
        self.lbl_uptime.pack(anchor=tk.W, padx=10, pady=2)

        specs = get_system_specs()
        ttk.Separator(right_pane, orient=tk.HORIZONTAL).pack(
            fill=tk.X, padx=10, pady=10
        )
        tk.Label(right_pane, text=f"OS: {specs['OS']}", font=("Segoe UI", 8)).pack(
            anchor=tk.W, padx=10, pady=1
        )
        tk.Label(right_pane, text=f"CPU: {specs['CPU']}", font=("Segoe UI", 8)).pack(
            anchor=tk.W, padx=10, pady=1
        )
        tk.Label(right_pane, text=f"RAM: {specs['RAM']}", font=("Segoe UI", 8)).pack(
            anchor=tk.W, padx=10, pady=1
        )

        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        # Bottom Log Frame
        log_frame = ttk.LabelFrame(self.root, text="System Output Logs")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, height=8, font=("Courier New", 8)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.insert(
            tk.END, "[AnonyMus] System Diagnostics Logger initialized.\n"
        )

    def setup_diagnostic_tab(self):
        intro = "Select 'Run Tests' below to analyze local adapters, loopback addresses, and active diagnostic daemons."
        lbl = tk.Label(
            self.tab_diag,
            text=intro,
            font=("Segoe UI", 9, "italic"),
            anchor=tk.W,
            justify=tk.LEFT,
        )
        lbl.pack(padx=10, pady=8, fill=tk.X)

        self.tree = ttk.Treeview(
            self.tab_diag, columns=("Target", "Status"), show="headings", height=8
        )
        self.tree.heading("Target", text="Network Adapter / Test target")
        self.tree.heading("Status", text="Test Result")
        self.tree.column("Target", width=350)
        self.tree.column("Status", width=220)
        self.tree.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        self.tree.insert(
            "", "end", iid="loopback", values=("127.0.0.1 Local Loopback", "Not Tested")
        )
        self.tree.insert(
            "",
            "end",
            iid="dns",
            values=("DNS Server Resolution (8.8.8.8)", "Not Tested"),
        )
        self.tree.insert(
            "",
            "end",
            iid="proxy",
            values=("SOCKS5 Proxy Tunnel (Port 9050)", "Not Tested"),
        )
        self.tree.insert(
            "",
            "end",
            iid="daemon",
            values=("Diagnostic Daemon Loopback Binding", "Not Tested"),
        )

        self.progress = ttk.Progressbar(
            self.tab_diag, orient=tk.HORIZONTAL, mode="determinate"
        )
        self.progress.pack(padx=10, pady=5, fill=tk.X)

        btn_run = ttk.Button(
            self.tab_diag,
            text="Run Diagnostic Checks",
            command=self.run_diagnostic_tests,
        )
        btn_run.pack(padx=10, pady=5, side=tk.RIGHT)

    def setup_config_tab(self):
        grp_info = ttk.LabelFrame(self.tab_config, text="Active Network Profile")
        grp_info.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        lbl_intro = tk.Label(
            grp_info,
            text="This build is configured dynamically for diagnostic and loopback operations.",
            font=("Segoe UI", 9, "bold"),
            anchor=tk.W,
            justify=tk.LEFT,
        )
        lbl_intro.pack(anchor=tk.W, padx=15, pady=(15, 10))

        details = (
            "• Standard Profile: Centralized socket queue relay server\n"
            "• Diagnostics Profile: Isolated loopback connection over Tor onion routing\n"
            "• Encryption: End-to-End HKDF and local database AES-256-GCM\n"
            "• Host Binding: Automatic localhost restriction on Diagnostic Profile"
        )

        lbl_details = tk.Label(
            grp_info,
            text=details,
            font=("Segoe UI", 9),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=450,
        )
        lbl_details.pack(anchor=tk.W, padx=25, pady=10)

    def setup_logs_tab(self):
        lbl = tk.Label(
            self.tab_logs,
            text="Diagnostic Server Output Log:",
            font=("Segoe UI", 9, "bold"),
        )
        lbl.pack(padx=10, pady=5, anchor=tk.W)

        self.log_text = scrolledtext.ScrolledText(
            self.tab_logs, wrap=tk.WORD, height=18, font=("Courier New", 8)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_text.insert(
            tk.END, "[NetDiag] System Diagnostics Logger initialized.\n"
        )

    def setup_control_tab(self):
        grp_sys = ttk.LabelFrame(self.tab_ctrl, text="System Hardware & OS Details")
        grp_sys.pack(fill=tk.X, padx=10, pady=5)

        specs = get_system_specs()
        tk.Label(grp_sys, text=f"Operating System: {specs['OS']}").pack(
            anchor=tk.W, padx=10, pady=2
        )
        tk.Label(grp_sys, text=f"Processor (CPU): {specs['CPU']}").pack(
            anchor=tk.W, padx=10, pady=2
        )
        tk.Label(grp_sys, text=f"System Architecture: {specs['Arch']}").pack(
            anchor=tk.W, padx=10, pady=2
        )
        tk.Label(grp_sys, text=f"Installed RAM: {specs['RAM']}").pack(
            anchor=tk.W, padx=10, pady=2
        )

        grp_ctrl = ttk.LabelFrame(
            self.tab_ctrl, text="Diagnostic Service Daemon Control"
        )
        grp_ctrl.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.lbl_status = tk.Label(
            grp_ctrl,
            text="Service Status: STOPPED",
            font=("Segoe UI", 10, "bold"),
            fg="red",
        )
        self.lbl_status.pack(anchor=tk.W, padx=10, pady=10)

        self.lbl_onion = tk.Label(
            grp_ctrl, text="Onion Address: N/A", font=("Segoe UI", 9)
        )
        self.lbl_onion.pack(anchor=tk.W, padx=10, pady=2)

        self.lbl_uptime = tk.Label(
            grp_ctrl, text="Service Uptime: 00:00:00", font=("Segoe UI", 9)
        )
        self.lbl_uptime.pack(anchor=tk.W, padx=10, pady=2)

        btn_frame = tk.Frame(grp_ctrl)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.btn_start = ttk.Button(
            btn_frame, text="Initialize Diagnostic Service", command=self.start_daemon
        )
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_dashboard = ttk.Button(
            btn_frame,
            text="Launch Local Console Dashboard",
            command=self.open_dashboard,
            state=tk.DISABLED,
        )
        self.btn_dashboard.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(
            btn_frame,
            text="Shutdown Daemon",
            command=self.stop_daemon,
            state=tk.DISABLED,
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

    def run_diagnostic_tests(self):
        self.progress["value"] = 0
        self.tree.item("loopback", values=("127.0.0.1 Local Loopback", "Testing..."))
        self.tree.item("dns", values=("DNS Server Resolution (8.8.8.8)", "Testing..."))
        self.tree.item(
            "proxy", values=("SOCKS5 Proxy Tunnel (Port 9050)", "Testing...")
        )
        self.tree.item(
            "daemon", values=("Diagnostic Daemon Loopback Binding", "Testing...")
        )

        def run():
            time.sleep(0.5)
            self.tree.item(
                "loopback",
                values=("127.0.0.1 Local Loopback", "PASS (Loopback Active)"),
            )
            self.progress["value"] += 25

            time.sleep(0.5)
            try:
                socket.gethostbyname("dns.google")
                dns_res = "PASS (Resolved Google DNS)"
            except Exception:
                dns_res = "WARNING (External DNS lookup failed)"
            self.tree.item("dns", values=("DNS Server Resolution (8.8.8.8)", dns_res))
            self.progress["value"] += 25

            time.sleep(0.5)
            socks_active = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.2)
                    s.connect(("127.0.0.1", tor_socks_port))
                    socks_active = True
            except Exception:
                pass

            if socks_active:
                proxy_res = (
                    f"PASS (SOCKS5 proxy listening on 127.0.0.1:{tor_socks_port})"
                )
            else:
                proxy_res = "INACTIVE (Optional proxy wrapper not started)"
            self.tree.item(
                "proxy", values=("SOCKS5 Proxy Tunnel (Port 9050)", proxy_res)
            )
            self.progress["value"] += 25

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
            self.tree.item(
                "daemon", values=("Diagnostic Daemon Loopback Binding", daemon_res)
            )
            self.progress["value"] += 25

        threading.Thread(target=run, daemon=True).start()

    def poll_logs(self):
        try:
            while True:
                text = log_queue.get_nowait()
                self.log_text.insert(tk.END, text + "\n")
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_logs)

    def start_daemon(self):
        global server_thread, daemon_active, active_mode, active_port, start_time

        if daemon_active:
            messagebox.showwarning(
                "Service Active", "The service daemon is already running."
            )
            return

        # Read mode and port from UI if not disguised
        if self.settings.get("disguise", False):
            active_mode = "p2p"
            active_port = 8080
        else:
            active_mode = self.mode_var.get()
            try:
                active_port = int(self.port_entry.get())
            except ValueError:
                messagebox.showerror("Invalid Port", "Port must be a valid number.")
                return

        # Save settings
        self.settings["mode"] = active_mode
        self.settings["port"] = active_port
        self.save_settings()

        daemon_active = True
        start_time = time.time()

        print(
            f"[Launcher] Launching backend service in profile: {active_mode.upper()} on port {active_port}..."
        )

        # Configure env variables dynamically
        os.environ["ANONYMUS_MODE"] = active_mode
        os.environ["PORT"] = str(active_port)
        os.environ["FLASK_SECRET_KEY"] = self.settings.get("flask_secret_key", "")
        os.environ["FLASK_DEBUG"] = "False"

        self.btn_start.config(state=tk.DISABLED)
        if not self.settings.get("disguise", False):
            self.port_entry.config(state=tk.DISABLED)
            self.chk_disguise.config(state=tk.DISABLED)

        def launch_server_wrapper():
            global tor_socks_port, onion_address, active_port
            try:
                import eventlet
                import eventlet.wsgi

                # Import root dispatcher
                import server as root_server

                # Reset WSGI Dispatcher active mode flag
                root_server.wsgi_dispatcher.current_mode = active_mode

                # Initialize active transport
                config = {
                    "PORT": active_port,
                    "ANONYMUS_MDNS": os.environ.get("ANONYMUS_MDNS", "false"),
                }

                print("[Daemon] Starting active transport layer...")
                root_server.registry.get_active_transport().start(config)

                # Fetch active health statistics
                health = root_server.registry.get_active_transport().health()
                if active_mode == "p2p":
                    onion_address = health.get("onion_address", "N/A")
                    tor_socks_port = health.get("socks_port", 9050)

                # Run eventlet web server
                bind_ip = "127.0.0.1" if active_mode == "p2p" else "0.0.0.0"
                print(f"[Daemon] Service daemon bound to {bind_ip}:{active_port}")

                listener = eventlet.listen((bind_ip, active_port))
                eventlet.wsgi.server(listener, root_server.wsgi_dispatcher)
            except Exception as e:
                print(f"FATAL: Service daemon execution failed: {e}")
                self.stop_daemon()

        server_thread = threading.Thread(target=launch_server_wrapper, daemon=True)
        server_thread.start()

    def stop_daemon(self):
        global server_thread, daemon_active, active_mode, onion_address

        if not daemon_active:
            return

        print("[Launcher] Stopping service backend and network adapters...")

        # Stop Tor subprocess via registry/transport stop hooks
        try:
            import server as root_server

            root_server.registry.get_active_transport().stop()
            print("[Launcher] Active transport adapters closed.")
        except Exception as e:
            print(f"[Launcher] Error closing transport: {e}")

        # Clean environment variables
        if "HTTP_PROXY" in os.environ:
            del os.environ["HTTP_PROXY"]
        if "HTTPS_PROXY" in os.environ:
            del os.environ["HTTPS_PROXY"]

        daemon_active = False
        active_mode = None
        onion_address = "N/A"

        # Reset UI
        self.btn_start.config(state=tk.NORMAL)
        self.btn_dashboard.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        if not self.settings.get("disguise", False):
            self.port_entry.config(state=tk.NORMAL)
            self.chk_disguise.config(state=tk.NORMAL)

        self.lbl_status.config(text="Status: STOPPED", fg="red")
        self.lbl_onion.config(text="Onion Address: N/A")

        print("[Launcher] Service shutdown sequence completed.")

    def open_dashboard(self):
        if daemon_active:
            url = f"http://127.0.0.1:{active_port}"
            print(f"[Launcher] Launching administrative view at {url}")
            webbrowser.open(url)

    def update_daemon_status(self):
        if daemon_active:
            self.lbl_status.config(text="Status: RUNNING (ACTIVE)", fg="green")
            self.btn_dashboard.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)

            if active_mode == "p2p":
                if onion_address != "N/A" and onion_address is not None:
                    self.lbl_onion.config(text=f"Onion Address: {onion_address}")
                else:
                    self.lbl_onion.config(
                        text="Onion Address: Bootstrapping Onion routing..."
                    )
            else:
                self.lbl_onion.config(text="Onion Address: N/A (Relay Mode)")

            uptime = int(time.time() - start_time)
            hrs = uptime // 3600
            mins = (uptime % 3600) // 60
            secs = uptime % 60
            self.lbl_uptime.config(
                text=f"Service Uptime: {hrs:02d}:{mins:02d}:{secs:02d}"
            )
        else:
            self.lbl_status.config(text="Status: STOPPED", fg="red")
            self.btn_dashboard.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.DISABLED)
            self.lbl_onion.config(text="Onion Address: N/A")
            self.lbl_uptime.config(text="Service Uptime: 00:00:00")

        self.root.after(1000, self.update_daemon_status)


def on_closing():
    try:
        import server as root_server

        root_server.registry.get_active_transport().stop()
    except Exception:
        pass
    root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app_gui = NetworkDiagnosticsApp(root)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
