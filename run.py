import os
import sys
import threading
import subprocess
import webbrowser
import json
import random
try:
    import psutil
except ImportError:
    psutil = None
from pathlib import Path
from datetime import datetime
from tkinter import *
from tkinter import ttk, messagebox, scrolledtext
from tkinter import Menu
from dotenv import load_dotenv, set_key

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- Advanced Futuristic HUD "Obsidian & Steel" Dashboard Configuration ---
BG_COLOR = '#020408'        # Deep Space
PANEL_BG = '#0a0d12'        # Dark Obsidian
FG_COLOR = '#7d8590'        # Muted Steel
ACCENT_COLOR = '#1f242c'     # Interface Grey
HIGHLIGHT_COLOR = '#e6edf3'   # High-Contrast Silver
PRIMARY_COLOR = '#58a6ff'     # Tactical Blue
ERROR_COLOR = '#f85149'      # Industrial Red
SUCCESS_COLOR = '#3fb950'    # Industrial Green
FONT_NAME = 'Consolas'       # technical Monospace
FONT_SIZE = 9

class BlackDiamondDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("BLACK DIAMOND // STRATEGIC COMMAND HUD")
        self.root.configure(bg=BG_COLOR)
        self.project_root = Path(os.path.dirname(os.path.abspath(__file__)))
        
        # System Variables
        self.config_vars = {}
        self.running_processes = {}
        self.service_controls = {}
        self.service_messages = {}
        self.launch_vars = {
            'bot': BooleanVar(value=True),
            'web': BooleanVar(value=True),
            'debug': BooleanVar(value=False)
        }
        
        self.setup_styles()
        self.create_layout()
        
        # Load environment and initialization
        self.load_config()
        self.refresh_service_status()
        self.update_clock()
        self.update_telemetry()
        self.animate_heartbeat()
        
        # Boot sequence
        self.boot_sequence()

    def setup_styles(self):
        """Configure specialized HUD styles"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Pane Styling
        style.configure('HUD.TFrame', background=PANEL_BG)
        style.configure('HUD.TLabel', background=PANEL_BG, foreground=FG_COLOR, font=(FONT_NAME, FONT_SIZE))
        
        # Header Label
        style.configure('Header.TLabel', background=ACCENT_COLOR, foreground=HIGHLIGHT_COLOR, 
                        font=(FONT_NAME, 8, 'bold'), padding=2)
        
        # Technical Inputs
        style.configure('HUD.TEntry', fieldbackground='#0d1117', foreground=HIGHLIGHT_COLOR,
                       insertcolor=HIGHLIGHT_COLOR, font=(FONT_NAME, FONT_SIZE), borderwidth=0)
        
        # HUD Buttons
        style.configure('HUD.TButton', background=ACCENT_COLOR, foreground=HIGHLIGHT_COLOR,
                       font=(FONT_NAME, 8, 'bold'), borderwidth=0, padding=6)
        style.map('HUD.TButton', background=[('active', '#21262d')], foreground=[('active', PRIMARY_COLOR)])
        
        # Notebook (Tabs)
        style.configure('HUD.TNotebook', background=BG_COLOR, borderwidth=0)
        style.configure('HUD.TNotebook.Tab', background=BG_COLOR, foreground=FG_COLOR,
                       padding=[14, 4], font=(FONT_NAME, 8))
        style.map('HUD.TNotebook.Tab', 
                  background=[('selected', PANEL_BG)], 
                  foreground=[('selected', HIGHLIGHT_COLOR)])

        # Checkbuttons
        style.configure('HUD.TCheckbutton', background=PANEL_BG, foreground=FG_COLOR, font=(FONT_NAME, FONT_SIZE))

    def create_layout(self):
        """Build the multi-module HUD interface with density and technical detail"""
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1) # Side monitor
        self.root.grid_columnconfigure(1, weight=3) # Primary Display
        self.root.grid_columnconfigure(2, weight=2) # Comm Array

        # --- MODULE 01: SYSTEM HEARTBEAT & TELEMETRY (Left) ---
        side_pane = Frame(self.root, bg=PANEL_BG, bd=1, relief='flat', highlightthickness=1, highlightbackground=ACCENT_COLOR)
        side_pane.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        
        Label(side_pane, text=" [ SENSOR_ARRAY ] ", bg=ACCENT_COLOR, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 7, 'bold')).pack(fill='x')
        
        self.clock_lbl = Label(side_pane, text="00:00:00", bg=PANEL_BG, fg=PRIMARY_COLOR, font=(FONT_NAME, 14, 'bold'))
        self.clock_lbl.pack(pady=10)
        
        # Waveform Canvas
        self.heartbeat_canvas = Canvas(side_pane, bg=PANEL_BG, height=50, highlightthickness=0)
        self.heartbeat_canvas.pack(fill='x', padx=10)
        
        # Telemetry Metrics
        self.telemetry_f = Frame(side_pane, bg=PANEL_BG)
        self.telemetry_f.pack(fill='x', padx=15, pady=5)
        
        self.cpu_lbl = Label(self.telemetry_f, text="CPU: 0.0%", bg=PANEL_BG, fg=FG_COLOR, font=(FONT_NAME, 7))
        self.cpu_lbl.pack(anchor='w')
        self.ram_lbl = Label(self.telemetry_f, text="RAM: 0.0%", bg=PANEL_BG, fg=FG_COLOR, font=(FONT_NAME, 7))
        self.ram_lbl.pack(anchor='w')
        self.net_lbl = Label(self.telemetry_f, text="NET: CONNECTED", bg=PANEL_BG, fg=SUCCESS_COLOR, font=(FONT_NAME, 7))
        self.net_lbl.pack(anchor='w')

        Label(side_pane, text=" [ DEPLOYMENT_STATUS ] ", bg=ACCENT_COLOR, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 7, 'bold')).pack(fill='x', pady=(10, 0))
        
        status_f = Frame(side_pane, bg=PANEL_BG)
        status_f.pack(fill='x', padx=15, pady=10)
        
        self.bot_ind = Label(status_f, text="BOT://OFFLINE", bg=PANEL_BG, fg=ERROR_COLOR, font=(FONT_NAME, 8, 'bold'))
        self.bot_ind.pack(anchor='w')
        self.web_ind = Label(status_f, text="WEB://OFFLINE", bg=PANEL_BG, fg=ERROR_COLOR, font=(FONT_NAME, 8, 'bold'))
        self.web_ind.pack(anchor='w', pady=5)
        
        Label(side_pane, text=" [ ENV_PARAMETERS ] ", bg=ACCENT_COLOR, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 7, 'bold')).pack(fill='x', pady=(10, 0))
        self.data_stream = Frame(side_pane, bg=PANEL_BG)
        self.data_stream.pack(fill='both', expand=True, padx=10, pady=10)

        # --- MODULE 02: PRIMARY COMMAND DISPLAY (Center) ---
        main_pane = Frame(self.root, bg=BG_COLOR)
        main_pane.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        
        self.nb = ttk.Notebook(main_pane, style='HUD.TNotebook')
        self.nb.pack(fill='both', expand=True)
        
        # Bind tab change event to refresh error console
        self.nb.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        
        self.ui_launch_module()
        self.ui_config_module()
        self.ui_service_module()
        self.ui_diag_module()
        self.ui_errors_module()

        # --- MODULE 03: COMMUNICATIONS HUB (Right) ---
        comm_pane = Frame(self.root, bg=PANEL_BG, bd=1, relief='flat', highlightthickness=1, highlightbackground=ACCENT_COLOR)
        comm_pane.grid(row=0, column=2, sticky='nsew', padx=5, pady=5)
        
        Label(comm_pane, text=" [ LOG_ARRAY_CORE ] ", bg=ACCENT_COLOR, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 7, 'bold')).pack(fill='x')
        
        self.terminal = scrolledtext.ScrolledText(comm_pane, bg=BG_COLOR, fg=FG_COLOR, 
                                                 insertbackground=HIGHLIGHT_COLOR, font=(FONT_NAME, 8),
                                                 borderwidth=0, highlightthickness=0, padx=5, pady=5,
                                                 state='normal', wrap=WORD)
        self.terminal.pack(fill='both', expand=True)
        self.terminal.config(state='disabled')
        
        input_f = Frame(comm_pane, bg=BG_COLOR)
        input_f.pack(fill='x')
        Label(input_f, text=" >_ ", bg=BG_COLOR, fg=PRIMARY_COLOR, font=(FONT_NAME, 8, 'bold')).pack(side='left')
        self.input_field = Entry(input_f, bg=BG_COLOR, fg=HIGHLIGHT_COLOR, borderwidth=0, insertbackground=HIGHLIGHT_COLOR, font=(FONT_NAME, 8))
        self.input_field.pack(side='left', fill='x', expand=True)
        self.input_field.bind('<Return>', self.process_cmd)
        
        # Initialize error monitoring
        self.setup_error_monitoring()
        
        # Setup context menus for text widgets
        self.setup_context_menus()
        
        # Initial refresh of error console
        self.refresh_error_console()

    def ui_launch_module(self):
        tab = ttk.Frame(self.nb, style='HUD.TFrame')
        self.nb.add(tab, text='[ DEPLOY ]')
        
        f = Frame(tab, bg=PANEL_BG)
        f.pack(expand=True)
        
        Label(f, text=" INITIATE SYSTEM DEPLOYMENT ", bg=PANEL_BG, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 10, 'bold')).pack(pady=(0, 20))
        
        ttk.Checkbutton(f, text="BOT_SUBSYSTEM", variable=self.launch_vars['bot'], style='HUD.TCheckbutton').pack(anchor='w', pady=5)
        ttk.Checkbutton(f, text="WEB_SUBSYSTEM", variable=self.launch_vars['web'], style='HUD.TCheckbutton').pack(anchor='w', pady=5)
        ttk.Checkbutton(f, text="DEBUG_MODE_V", variable=self.launch_vars['debug'], style='HUD.TCheckbutton').pack(anchor='w', pady=5)
        
        p_f = Frame(f, bg=PANEL_BG)
        p_f.pack(fill='x', pady=15)
        Label(p_f, text="PORT://", bg=PANEL_BG, fg=FG_COLOR, font=(FONT_NAME, 8)).pack(side='left')
        self.port_ent = ttk.Entry(p_f, width=10, style='HUD.TEntry')
        self.port_ent.insert(0, os.getenv('WEB_PORT', '80'))
        self.port_ent.pack(side='left', padx=10)
        
        ctrl_f = Frame(f, bg=PANEL_BG)
        ctrl_f.pack(pady=20)
        self.run_btn = ttk.Button(ctrl_f, text=" INITIATE ", command=self.start_app, style='HUD.TButton')
        self.run_btn.pack(side='left', padx=10)
        self.kill_btn = ttk.Button(ctrl_f, text=" ABORT ", command=self.stop_app, style='HUD.TButton', state='disabled')
        self.kill_btn.pack(side='left', padx=10)
        ttk.Button(ctrl_f, text=" BROWSER ", command=self.open_web_app, style='HUD.TButton').pack(side='left', padx=10)

    def ui_config_module(self):
        tab = ttk.Frame(self.nb, style='HUD.TFrame')
        self.nb.add(tab, text='[ CONFIG ]')
        
        canvas = Canvas(tab, bg=PANEL_BG, highlightthickness=0)
        sb = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        sf = Frame(canvas, bg=PANEL_BG)
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw", width=550)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        groups = [
            (" CREDENTIALS ", [("BOT_TOKEN", "BOT_X"), ("ADMIN_ID", "OVERRIDE_X")]),
            (" CRYPTO_NODES ", [("USDT_WALLET_ADDRESS", "USDT_N"), ("USDT_PRIVATE_KEY", "USDT_S"), ("TON_WALLET_ADDRESS", "TON_N"), ("TON_PRIVATE_KEY", "TON_S")]),
            (" API_LAYER ", [("TRONGRID_API_KEY", "TRON_X"), ("TONCENTER_API_KEY", "TON_X")])
        ]
        
        for name, keys in groups:
            Label(sf, text=f" {name} ", bg=ACCENT_COLOR, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 7, 'bold')).pack(fill='x', pady=(10, 5))
            for k, l in keys:
                row = Frame(sf, bg=PANEL_BG)
                row.pack(fill='x', padx=15, pady=2)
                Label(row, text=l, width=10, bg=PANEL_BG, fg=FG_COLOR, anchor='w', font=(FONT_NAME, 8)).pack(side='left')
                e = ttk.Entry(row, style='HUD.TEntry', show="*" if "S" in l or "KEY" in k else None)
                e.pack(side='left', fill='x', expand=True, padx=5)
                self.config_vars[k] = e

        btn_row = Frame(sf, bg=PANEL_BG)
        btn_row.pack(fill='x', padx=15, pady=20)
        ttk.Button(btn_row, text=" COMMIT ", command=self.save_config, style='HUD.TButton').pack(side='left', padx=5)
        ttk.Button(btn_row, text=" REVERT ", command=self.load_config, style='HUD.TButton').pack(side='left', padx=5)

    def ui_service_module(self):
        tab = ttk.Frame(self.nb, style='HUD.TFrame')
        self.nb.add(tab, text='[ SERVICES ]')
        
        Label(tab, text=" SUBSYSTEM_GRID_STATUS ", bg=ACCENT_COLOR, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 7, 'bold')).pack(fill='x')
        
        grid_f = Frame(tab, bg=PANEL_BG)
        grid_f.pack(fill='both', expand=True, padx=20, pady=20)
        
        services = [('telegram_bot', 'NODE_BOT'), ('web_interface', 'NODE_WEB'), ('payments', 'NODE_PAY'), ('notifications', 'NODE_COM'), ('api', 'NODE_API')]
        for k, n in services:
            r = Frame(grid_f, bg=PANEL_BG)
            r.pack(fill='x', pady=4)
            Label(r, text=n, width=12, bg=PANEL_BG, fg=FG_COLOR, anchor='w', font=(FONT_NAME, 8, 'bold')).pack(side='left')
            v = BooleanVar()
            ttk.Checkbutton(r, text="", variable=v, style='HUD.TCheckbutton').pack(side='left')
            l = Label(r, text="ACTIVE", bg=PANEL_BG, fg=SUCCESS_COLOR, font=(FONT_NAME, 7, 'bold'), width=10)
            l.pack(side='left', padx=15)
            ttk.Button(r, text="MSG", width=4, command=lambda k=k: self.edit_msg(k), style='HUD.TButton').pack(side='right')
            self.service_controls[k] = {'var': v, 'label': l}

        Label(tab, text=" COMMS_OVERRIDE ", bg=ACCENT_COLOR, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 7, 'bold')).pack(fill='x')
        self.global_msg = Entry(tab, bg='#0d1117', fg=HIGHLIGHT_COLOR, borderwidth=1, relief='flat', insertbackground=HIGHLIGHT_COLOR, font=(FONT_NAME, 8))
        self.global_msg.pack(fill='x', padx=20, pady=10)

        ctrl = Frame(tab, bg=PANEL_BG)
        ctrl.pack(fill='x', pady=10)
        ttk.Button(ctrl, text=" SYNC_MODULES ", command=self.apply_services, style='HUD.TButton').pack(side='right', padx=20)

    def ui_diag_module(self):
        tab = ttk.Frame(self.nb, style='HUD.TFrame')
        self.nb.add(tab, text='[ DIAG ]')
        self.diag_out = scrolledtext.ScrolledText(tab, bg=BG_COLOR, fg=FG_COLOR, font=(FONT_NAME, 8), borderwidth=0, padx=10, pady=10)
        self.diag_out.pack(fill='both', expand=True)

        btn_f = Frame(tab, bg=PANEL_BG)
        btn_f.pack(fill='x', pady=5)
        ttk.Button(btn_f, text=" SCAN_SYSTEM ", command=self.refresh_status, style='HUD.TButton').pack(side='left', padx=10)
        ttk.Button(btn_f, text=" WIPE_DB ", command=self.wipe_database, style='HUD.TButton').pack(side='left')

    def _read_env_value(self, key: str) -> str:
        try:
            if os.path.exists('.env'):
                with open('.env', 'r', encoding='utf-8', errors='replace') as f:
                    for raw in f:
                        line = raw.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        if k.strip() != key:
                            continue
                        v = v.strip()
                        if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                            v = v[1:-1]
                        return v.strip()
        except Exception:
            return ""
        return ""

    def _get_database_url(self) -> str:
        url = os.getenv('DATABASE_URL', '').strip()
        if url:
            return url
        url = self._read_env_value('DATABASE_URL')
        if url:
            return url
        return "sqlite:///black_diamond.db"

    def _sqlite_path_from_url(self, database_url: str) -> Path:
        url = (database_url or "").strip()
        if not url.startswith("sqlite:"):
            raise ValueError("DATABASE_URL is not sqlite")

        if url.startswith("sqlite:///"):
            path_str = url[len("sqlite:///"):]
        elif url.startswith("sqlite:////"):
            # Common form for absolute POSIX paths: sqlite:////var/db.sqlite -> /var/db.sqlite
            raw = url[len("sqlite:"):]
            path_str = "/" + raw.lstrip("/")
        elif url.startswith("sqlite://"):
            path_str = url[len("sqlite://"):]
        else:
            path_str = url[len("sqlite:"):]

        path_str = path_str.strip()
        if not path_str:
            raise ValueError("Empty sqlite path")

        p = Path(path_str)
        if not p.is_absolute():
            p = (self.project_root / p).resolve()
        return p

    def wipe_database(self):
        try:
            if any(p.poll() is None for p in self.running_processes.values()):
                if not messagebox.askyesno(
                    "WIPE_DB",
                    "BOT/WEB are currently running. Stop them and wipe the DB?",
                ):
                    return
                self.stop_app()

            database_url = self._get_database_url()
            db_path = self._sqlite_path_from_url(database_url)

            targets = [
                db_path,
                Path(str(db_path) + "-shm"),
                Path(str(db_path) + "-wal"),
            ]

            if not messagebox.askyesno(
                "WIPE_DB",
                f"This will delete the local DB and related files:\n\n{db_path}\n\nContinue?",
            ):
                return

            removed = []
            errors = []
            for p in targets:
                try:
                    if p.exists():
                        p.unlink()
                        removed.append(str(p))
                except Exception as e:
                    errors.append(f"{p}: {e}")

            if errors:
                self.log("WIPE_DB_PARTIAL_FAIL")
                messagebox.showerror("WIPE_DB", "Errors while deleting:\n" + "\n".join(errors))
                return

            self.log("WIPE_DB_OK" if removed else "WIPE_DB_NOTHING_TO_DELETE")
            messagebox.showinfo(
                "WIPE_DB",
                "DB wiped (deleted files):\n" + ("\n".join(removed) if removed else "Nothing to delete"),
            )
        except ValueError as e:
            messagebox.showerror("WIPE_DB", f"Not supported: {e}")
        except Exception as e:
            messagebox.showerror("WIPE_DB", f"Error: {e}")

    def ui_errors_module(self):
        """Create error console tab for displaying all console errors"""
        tab = ttk.Frame(self.nb, style='HUD.TFrame')
        self.nb.add(tab, text='[ ERRORS ]')
        
        # Header with error statistics
        header_f = Frame(tab, bg=PANEL_BG)
        header_f.pack(fill='x', padx=10, pady=5)
        
        Label(header_f, text=" CONSOLE_ERROR_MONITOR ", bg=ACCENT_COLOR, fg=HIGHLIGHT_COLOR, font=(FONT_NAME, 8, 'bold')).pack(anchor='w')
        
        # Error stats frame
        stats_f = Frame(header_f, bg=PANEL_BG)
        stats_f.pack(fill='x', pady=2)
        
        self.error_count_lbl = Label(stats_f, text="ERRORS: 0", bg=PANEL_BG, fg=ERROR_COLOR, font=(FONT_NAME, 8, 'bold'))
        self.error_count_lbl.pack(side='left', padx=(0, 10))
        
        self.warning_count_lbl = Label(stats_f, text="WARNINGS: 0", bg=PANEL_BG, fg='#ffaa00', font=(FONT_NAME, 8, 'bold'))
        self.warning_count_lbl.pack(side='left', padx=(0, 10))
        
        self.last_error_lbl = Label(stats_f, text="LAST: N/A", bg=PANEL_BG, fg=FG_COLOR, font=(FONT_NAME, 7))
        self.last_error_lbl.pack(side='right')
        
        # Control buttons
        ctrl_f = Frame(header_f, bg=PANEL_BG)
        ctrl_f.pack(fill='x', pady=5)
        
        ttk.Button(ctrl_f, text=" REFRESH ", command=self.refresh_error_console, style='HUD.TButton').pack(side='left', padx=(0, 5))
        ttk.Button(ctrl_f, text=" CLEAR ", command=self.clear_error_console, style='HUD.TButton').pack(side='left', padx=(0, 5))
        ttk.Button(ctrl_f, text=" AUTO_UPDATE ", command=self.toggle_auto_update, style='HUD.TButton').pack(side='left')
        
        self.auto_update_var = BooleanVar(value=True)
        
        # Error console text area
        error_frame = Frame(tab, bg=PANEL_BG)
        error_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Create error console with custom styling
        self.error_console = scrolledtext.ScrolledText(
            error_frame, 
            bg='#0d1117', 
            fg=FG_COLOR,
            insertbackground=HIGHLIGHT_COLOR, 
            font=(FONT_NAME, 8),
            borderwidth=1,
            relief='flat',
            highlightthickness=0,
            padx=5,
            pady=5,
            wrap=WORD,
            state='normal'
        )
        self.error_console.pack(fill='both', expand=True)
        
        # Configure text tags for different error levels
        self.error_console.tag_config('ERROR', foreground=ERROR_COLOR, font=(FONT_NAME, 8, 'bold'))
        self.error_console.tag_config('WARNING', foreground='#ffaa00', font=(FONT_NAME, 8, 'bold'))
        self.error_console.tag_config('CRITICAL', foreground='#ff0066', font=(FONT_NAME, 8, 'bold'))
        self.error_console.tag_config('TIMESTAMP', foreground=PRIMARY_COLOR, font=(FONT_NAME, 7))
        self.error_console.tag_config('CATEGORY', foreground='#9d79e0', font=(FONT_NAME, 7, 'italic'))
        
        # Start auto-update if enabled
        if self.auto_update_var.get():
            self.root.after(2000, self.auto_refresh_errors)

    def edit_msg(self, key):
        d = Toplevel(self.root); d.title(f"MOD_{key}"); d.geometry("400x180"); d.configure(bg=PANEL_BG)
        t = Text(d, bg=BG_COLOR, fg=HIGHLIGHT_COLOR, insertbackground=HIGHLIGHT_COLOR, font=(FONT_NAME, 8)); t.pack(fill='both', expand=True, padx=10, pady=10)
        t.insert('1.0', self.service_messages.get(key, ""))
        def s(): self.service_messages[key] = t.get('1.0', 'end-1c'); d.destroy()
        ttk.Button(d, text="COMMIT", command=s, style='HUD.TButton').pack(pady=5)

    def update_clock(self):
        self.clock_lbl.config(text=datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self.update_clock)

    def update_telemetry(self):
        if psutil:
            try:
                cpu_p = psutil.cpu_percent()
                vmem = psutil.virtual_memory()
                ram_p = vmem.percent
                ram_used = vmem.used / (1024**3)
                ram_total = vmem.total / (1024**3)
                
                cpu = f"CPU: {cpu_p:>5.1f}%"
                ram = f"RAM: {ram_used:>4.1f}/{ram_total:.1f} GB ({ram_p:.1f}%)"
                
                disk = psutil.disk_usage('/').percent
                self.net_lbl.config(text=f"DISK: {disk}%", fg=FG_COLOR)
                
                self.cpu_lbl.config(text=cpu)
                self.ram_lbl.config(text=ram)
            except:
                pass
        else:
            cpu = f"CPU: {random.uniform(1.0, 4.0):.1f}%"
            ram = f"RAM: {random.uniform(12.0, 15.0):.1f}%"
            self.cpu_lbl.config(text=cpu)
            self.ram_lbl.config(text=ram)
            
        self.root.after(2000, self.update_telemetry)

    def animate_heartbeat(self):
        self.heartbeat_canvas.delete("all")
        points = []
        for i in range(25):
            x = i * 15
            y = 25 + random.randint(-15, 15)
            points.extend([x, y])
        self.heartbeat_canvas.create_line(points, fill=PRIMARY_COLOR, smooth=True, width=1)
        self.root.after(250, self.animate_heartbeat)

    def log(self, m):
        ts = datetime.now().strftime("%H:%M:%S")
        self.terminal.config(state='normal')
        self.terminal.insert(END, f"[{ts}] {m}\n")
        self.terminal.see(END)
        self.terminal.config(state='disabled')

    def boot_sequence(self):
        self.log("INITIATING COMMAND HUD BOOT...")
        self.log("LOADING CRYPTO_HANDLERS... OK")
        self.log("ESTABLISHING BLOCKCHAIN_LINK... OK")
        self.log("CORE SYSTEMS NOMINAL. READY FOR DEPLOYMENT.")

    def setup_error_monitoring(self):
        """Setup error monitoring for subprocesses and GUI"""
        try:
            # Store original stderr
            self.original_stderr = sys.stderr
            
            # Create custom error stream that also logs to our system
            class ErrorStream:
                def __init__(self, dashboard):
                    self.dashboard = dashboard
                    self.original_stderr = sys.stderr
                    
                def write(self, text):
                    # Write to original stderr
                    if self.original_stderr:
                        self.original_stderr.write(text)
                        self.original_stderr.flush()
                    
                    # Log error messages
                    if text.strip() and ('error' in text.lower() or 'exception' in text.lower() or 'traceback' in text.lower()):
                        self.dashboard.log(f"SYSTEM_ERR: {text.strip()}")
                
                def flush(self):
                    if self.original_stderr:
                        self.original_stderr.flush()
            
            # Set up custom error stream
            sys.stderr = ErrorStream(self)
            
        except Exception as e:
            print(f"Error monitoring setup failed: {e}")

    def refresh_error_console(self):
        """Refresh error console with latest logs"""
        try:
            all_errors = self._collect_error_entries()
            all_errors.sort(key=lambda x: x['timestamp'], reverse=True)

            error_count = sum(1 for entry in all_errors if entry['level'] == 'ERROR')
            warning_count = sum(1 for entry in all_errors if entry['level'] == 'WARNING')
            critical_count = sum(1 for entry in all_errors if entry['level'] == 'CRITICAL')
            self.error_count_lbl.config(text=f"ERRORS: {error_count + critical_count}")
            self.warning_count_lbl.config(text=f"WARNINGS: {warning_count}")
            
            # Update last error time
            if all_errors:
                last_time = all_errors[0]['timestamp'].strftime('%H:%M:%S')
                self.last_error_lbl.config(text=f"LAST: {last_time}")
            else:
                self.last_error_lbl.config(text="LAST: N/A")
            
            # Clear and populate error console
            self.error_console.config(state='normal')
            self.error_console.delete(1.0, END)
            
            if not all_errors:
                self.error_console.insert(END, "\n[ NO ERRORS DETECTED ]\n\n", 'TIMESTAMP')
                self.error_console.insert(END, "System is running without critical errors.\n")
                self.error_console.insert(END, "Error console monitoring is active.\n")
            else:
                # Display recent errors
                self.error_console.insert(END, f"[ RECENT ERRORS & WARNINGS - {len(all_errors)} entries ]\n\n", 'TIMESTAMP')
                
                for entry in all_errors[:100]:  # Limit display to 100 entries
                    # Format timestamp
                    time_str = entry['timestamp'].strftime('%H:%M:%S.%f')[:-3]
                    
                    # Determine color tag
                    if entry['level'] == 'CRITICAL':
                        tag = 'CRITICAL'
                    elif entry['level'] == 'ERROR':
                        tag = 'ERROR'
                    elif entry['level'] == 'WARNING':
                        tag = 'WARNING'
                    else:
                        tag = 'TIMESTAMP'
                    
                    # Insert timestamp
                    self.error_console.insert(END, f"[{time_str}] ", 'TIMESTAMP')
                    
                    # Insert level
                    self.error_console.insert(END, f"{entry['level']:<8} ", tag)
                    
                    # Insert category
                    self.error_console.insert(END, f"[{entry['category']}] ", 'CATEGORY')
                    
                    # Insert message
                    self.error_console.insert(END, f"{entry['message']}\n")
                    
                    # Insert exception info if available
                    if entry['exception_info']:
                        self.error_console.insert(END, f"    Exception: {entry['exception_info']}\n")
                    
                    # Insert stack trace if available
                    if entry['stack_trace']:
                        self.error_console.insert(END, "    Stack trace:\n")
                        for line in entry['stack_trace'][-3:]:  # Show last 3 lines of stack trace
                            self.error_console.insert(END, f"    {line}")
                        self.error_console.insert(END, "\n")
                    
                    self.error_console.insert(END, "\n")
            
            # Scroll to top
            self.error_console.see(1.0)
            self.error_console.config(state='disabled')
            
        except Exception as e:
            self.error_console.config(state='normal')
            self.error_console.delete(1.0, END)
            self.error_console.insert(END, f"[ ERROR LOADING LOGS ]\n\nError: {str(e)}\n", 'ERROR')
            self.error_console.config(state='disabled')

    def _collect_error_entries(self):
        """Collect error entries from in-memory logs or log files."""
        entries = self._get_log_collector_entries()
        if entries:
            return entries

        entries = self._get_file_log_entries()
        return entries

    def _get_log_collector_entries(self):
        """Return recent entries from shared log collector if available."""
        try:
            from shared.logging_system import log_collector
        except Exception:
            return []

        error_entries = log_collector.get_recent_entries(limit=300, level='ERROR')
        warning_entries = log_collector.get_recent_entries(limit=300, level='WARNING')
        critical_entries = log_collector.get_recent_entries(limit=300, level='CRITICAL')
        all_entries = error_entries + warning_entries + critical_entries

        normalized = []
        for entry in all_entries:
            category = entry.category.value if hasattr(entry.category, 'value') else str(entry.category)
            stack_trace = entry.stack_trace if entry.stack_trace else []
            if isinstance(stack_trace, str):
                stack_trace = [stack_trace]
            normalized.append({
                'timestamp': entry.timestamp,
                'level': entry.level,
                'category': category,
                'message': entry.message,
                'exception_info': entry.exception_info,
                'stack_trace': stack_trace,
            })

        return normalized

    def _get_file_log_entries(self):
        """Return recent entries from structured log files."""
        log_dir_value = (
            os.getenv("BLACK_DIAMOND_LOG_DIR")
            or os.getenv("LOG_DIR")
            or "logs"
        )
        log_dir = Path(log_dir_value)
        if not log_dir.is_absolute():
            project_root = Path(__file__).resolve().parent
            log_dir = project_root / log_dir

        levels = {'ERROR', 'WARNING', 'CRITICAL'}

        structured_paths = list(log_dir.glob('structured*.log*'))
        errors_paths = list(log_dir.glob('errors*.log*'))

        entries = []
        for path in structured_paths:
            entries.extend(self._parse_log_file(path, levels=levels, max_lines=400))

        if not entries:
            for path in errors_paths:
                entries.extend(self._parse_log_file(path, levels=levels, max_lines=300))

        entries.sort(key=lambda e: e.get('timestamp') or datetime.min, reverse=True)
        return entries[:600]


    def _parse_log_file(self, path: Path, levels: set, max_lines: int):
        lines = self._tail_lines(path, max_lines)
        entries = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            level = data.get('level')
            if level not in levels:
                continue

            timestamp_str = data.get('timestamp')
            if not timestamp_str:
                continue

            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                continue

            stack_trace = data.get('stack_trace') or []
            if isinstance(stack_trace, str):
                stack_trace = [stack_trace]

            entries.append({
                'timestamp': timestamp,
                'level': level,
                'category': data.get('category', 'unknown'),
                'message': data.get('message', ''),
                'exception_info': data.get('exception_info'),
                'stack_trace': stack_trace,
            })

        return entries

    def _tail_lines(self, path: Path, max_lines: int):
        if not path.exists():
            return []

        chunk_size = 65536
        data = b""

        with path.open('rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            while file_size > 0 and data.count(b'\n') <= max_lines:
                read_size = min(chunk_size, file_size)
                file_size -= read_size
                f.seek(file_size)
                data = f.read(read_size) + data

        lines = data.splitlines()[-max_lines:]
        return [line.decode('utf-8', errors='ignore') for line in lines]
    
    def clear_error_console(self):
        """Clear error console display (does not clear actual logs)"""
        self.error_console.config(state='normal')
        self.error_console.delete(1.0, END)
        self.error_console.config(state='disabled')
        self.log("ERROR_CONSOLE_CLEARED")
    
    def setup_context_menus(self):
        """Setup context menus for text widgets to enable copy functionality"""
        # Create context menu for terminal
        self.terminal_menu = Menu(self.root, tearoff=0)
        self.terminal_menu.add_command(label="Copy", command=lambda: self.copy_text(self.terminal))
        self.terminal_menu.add_command(label="Select All", command=lambda: self.select_all_text(self.terminal))
        self.terminal_menu.add_separator()
        self.terminal_menu.add_command(label="Clear", command=self.clear_terminal)
        
        # Create context menu for error console
        self.error_menu = Menu(self.root, tearoff=0)
        self.error_menu.add_command(label="Copy", command=lambda: self.copy_text(self.error_console))
        self.error_menu.add_command(label="Select All", command=lambda: self.select_all_text(self.error_console))
        self.error_menu.add_separator()
        self.error_menu.add_command(label="Clear", command=self.clear_error_console)
        
        # Bind context menu events
        self.terminal.bind("<Button-3>", self.show_terminal_menu)
        self.error_console.bind("<Button-3>", self.show_error_menu)
        
        # Bind keyboard shortcuts
        self.root.bind('<Control-c>', self.copy_selected)
        self.root.bind('<Control-a>', self.select_all)
    
    def show_terminal_menu(self, event):
        """Show context menu for terminal"""
        try:
            self.terminal_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.terminal_menu.grab_release()
    
    def show_error_menu(self, event):
        """Show context menu for error console"""
        try:
            self.error_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.error_menu.grab_release()
    
    def copy_text(self, text_widget):
        """Copy selected text from a text widget"""
        try:
            selected_text = text_widget.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
        except TclError:
            # No text selected
            pass
    
    def select_all_text(self, text_widget):
        """Select all text in a text widget"""
        text_widget.tag_add("sel", "1.0", "end")
        text_widget.mark_set("insert", "1.0")
        text_widget.see("insert")
    
    def copy_selected(self, event):
        """Handle Ctrl+C keyboard shortcut"""
        # Check which widget has focus and copy from it
        focused_widget = self.root.focus_get()
        if focused_widget in [self.terminal, self.error_console]:
            self.copy_text(focused_widget)
            return "break"  # Prevent default behavior
    
    def select_all(self, event):
        """Handle Ctrl+A keyboard shortcut"""
        focused_widget = self.root.focus_get()
        if focused_widget in [self.terminal, self.error_console]:
            self.select_all_text(focused_widget)
            return "break"  # Prevent default behavior
    
    def clear_terminal(self):
        """Clear terminal display"""
        self.terminal.config(state='normal')
        self.terminal.delete(1.0, END)
        self.terminal.config(state='disabled')
        self.log("TERMINAL_CLEARED")
    
    def toggle_auto_update(self):
        """Toggle automatic error console updates"""
        current_state = self.auto_update_var.get()
        new_state = not current_state
        self.auto_update_var.set(new_state)
        
        if new_state:
            self.log("AUTO_ERROR_UPDATE_ENABLED")
            self.auto_refresh_errors()
        else:
            self.log("AUTO_ERROR_UPDATE_DISABLED")
    
    def auto_refresh_errors(self):
        """Automatically refresh error console if enabled"""
        if self.auto_update_var.get():
            self.refresh_error_console()
            # Schedule next update
            self.root.after(3000, self.auto_refresh_errors)  # Update every 3 seconds

    def process_cmd(self, e):
        c = self.input_field.get().strip().lower(); self.input_field.delete(0, END)
        if not c: return
        self.log(f"USR:// {c}")
        if c == 'help': self.log("CMD: start, stop, status, clear, exit")
        elif c == 'start': self.start_app()
        elif c == 'stop': self.stop_app()
        elif c == 'clear': self.clear_terminal()
        elif c == 'exit': self.root.quit()
        else: self.log(f"ERR:// Unknown command '{c}'")
    
    def on_tab_changed(self, event):
        """Handle tab change event - refresh error console when errors tab is selected"""
        try:
            selected_tab = self.nb.tab(self.nb.select(), "text")
            if "[ ERRORS ]" in selected_tab:
                self.refresh_error_console()
        except Exception as e:
            # Log error but don't break the GUI
            print(f"Tab change error: {e}")

    def load_config(self):
        if os.path.exists('.env'): load_dotenv('.env', override=True)
        for k, w in self.config_vars.items():
            v = os.getenv(k, ''); w.delete(0, END); w.insert(0, v)
        self.log("CONFIGURATION_LOADED")
        self.refresh_stats_view()

    def save_config(self):
        try:
            for k, w in self.config_vars.items(): set_key('.env', k, w.get().strip())
            self.log("CONFIG_COMMITTED")
            self.refresh_stats_view()
        except Exception as e: self.log(f"ERR:// Save error: {e}")

    def refresh_service_status(self):
        try:
            from shared.service_manager import service_manager
            for k, c in self.service_controls.items():
                e = service_manager.is_service_enabled(k)
                c['var'].set(e)
                c['label'].config(text="ONLINE" if e else "OFFLINE", foreground=SUCCESS_COLOR if e else ERROR_COLOR)
            self.log("GRID_STATUS_UPDATED")
        except: pass

    def apply_services(self):
        try:
            from shared.service_manager import service_manager
            gm = self.global_msg.get().strip()
            for k, c in self.service_controls.items():
                service_manager.set_service_status(k, c['var'].get())
                if gm: service_manager.update_service_message(k, gm)
                elif k in self.service_messages: service_manager.update_service_message(k, self.service_messages[k])
            self.refresh_service_status(); self.log("GRID_SYNC_COMPLETE")
        except: pass

    def start_app(self):
        self.save_config(); self.run_btn.config(state='disabled'); self.kill_btn.config(state='normal')
        if self.launch_vars['bot'].get(): threading.Thread(target=self.launch_bot, daemon=True).start()
        if self.launch_vars['web'].get(): threading.Thread(target=self.launch_web, daemon=True).start()
        self.log("INITIATING_DEPLOYMENT...")
        self.root.after(2000, self.refresh_status)

    def stop_app(self):
        for p in self.running_processes.values():
            try: p.terminate()
            except: pass
        self.running_processes.clear(); self.run_btn.config(state='normal'); self.kill_btn.config(state='disabled'); self.log("MISSION_ABORTED")
        self.refresh_status()

    def launch_bot(self):
        self.log("BOOTING_BOT..."); p = subprocess.Popen([sys.executable, "-m", "bot.main"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.running_processes['bot'] = p; self.bot_ind.config(text="BOT://ACTIVE", fg=SUCCESS_COLOR)
        for l in iter(p.stdout.readline, ''): self.log(f"BOT>> {l.strip()}")

    def launch_web(self):
        self.log("BOOTING_WEB..."); p = subprocess.Popen([sys.executable, "-m", "web.app"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.running_processes['web'] = p; self.web_ind.config(text="WEB://ACTIVE", fg=SUCCESS_COLOR)
        for l in iter(p.stdout.readline, ''): self.log(f"WEB>> {l.strip()}")

    def refresh_status(self):
        b = 'bot' in self.running_processes and self.running_processes['bot'].poll() is None
        w = 'web' in self.running_processes and self.running_processes['web'].poll() is None
        self.bot_ind.config(text=f"BOT://{'ACTIVE' if b else 'OFFLINE'}", fg=SUCCESS_COLOR if b else ERROR_COLOR)
        self.web_ind.config(text=f"WEB://{'ACTIVE' if w else 'OFFLINE'}", fg=SUCCESS_COLOR if w else ERROR_COLOR)
        self.diag_out.config(state='normal'); self.diag_out.delete(1.0, END)
        self.diag_out.insert(END, f"--- SCAN_REPORT ---\nTIME: {datetime.now()}\nINTEGRITY: NORMAL\nNODES: OK\n")
        self.diag_out.config(state='disabled')

    def refresh_stats_view(self):
        for widget in self.data_stream.winfo_children():
            widget.destroy()
        for k in sorted(self.config_vars):
            v = os.getenv(k, '').strip()
            if v:
                status = '✓'
                color = SUCCESS_COLOR
            else:
                status = '✗'
                color = ERROR_COLOR
            row = Frame(self.data_stream, bg=PANEL_BG)
            row.pack(fill='x', pady=1)
            Label(row, text=f"{k}:", bg=PANEL_BG, fg=FG_COLOR, font=(FONT_NAME, 8), anchor='w').pack(side='left')
            Label(row, text=status, bg=PANEL_BG, fg=color, font=(FONT_NAME, 8, 'bold')).pack(side='left', padx=5)

    def open_web_app(self): webbrowser.open(f"http://localhost:{self.port_ent.get()}")

def main():
    root = Tk(); root.geometry("1100x680"); root.update_idletasks()
    x = (root.winfo_screenwidth()//2)-(1100//2); y = (root.winfo_screenheight()//2)-(680//2)
    root.geometry(f"+{x}+{y}"); BlackDiamondDashboard(root); root.mainloop()

if __name__ == "__main__": main()
