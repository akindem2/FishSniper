import customtkinter as ctk
import threading
import json
import fishing
from discord_scanner import scanner
import os
from pathlib import Path
import sys

class DualLogger(object):
    def __init__(self, widget, original_stdout):
        self.widget = widget
        self.original_stdout = original_stdout

    def write(self, text):
        if self.original_stdout is not None:
            self.original_stdout.write(text)
            self.original_stdout.flush()
        def append():
            self.widget.configure(state="normal")
            self.widget.insert("end", text)
            self.widget.see("end")
            self.widget.configure(state="disabled")
        self.widget.after(0, append)

    def flush(self):
        if self.original_stdout is not None:
            self.original_stdout.flush()

BIOMES = ["Rainy", "Snowy", "Windy", "Hell", "Heaven", "Corruption", "Starfall", "Sand Storm", "Null", "Glitched", "Dreamspace", "Cyberspace"]

# Biome scanner pause durations (in seconds)
BIOME_PAUSE_DURATIONS = {
    "Rainy": 120,      # 2 minutes
    "Snowy": 120,      # 2 minutes
    "Windy": 120,      # 2 minutes
    "Hell": 666,       # 666 seconds
    "Heaven": 240,     # 240 seconds
    "Corruption": 650, # 650 seconds
    "Starfall": 600,   # 10 minutes
    "Sand Storm": 650, # 650 seconds
    "Null": 99,        # 99 seconds
    "Glitched": 164,   # 164 seconds
    "Dreamspace": 192, # 192 seconds
    "Cyberspace": 720  # 12 minutes
}

fish_loop = fishing.FishSolBot()

# Settings file path in LOCALAPPDATA
SETTINGS_DIR = Path(os.getenv("LOCALAPPDATA")) / "FishSniper"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

def ensure_settings_dir():
    """Create settings directory if it doesn't exist"""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

def load_settings_from_file():
    """Load settings from LOCALAPPDATA"""
    ensure_settings_dir()
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Settings Load Error] Could not load settings: {e}")
    return None

def save_settings_to_file(settings_data):
    """Save settings to LOCALAPPDATA"""
    ensure_settings_dir()
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_data, f, indent=2)
        print(f"[Settings Saved] Settings saved to {SETTINGS_FILE}")
    except Exception as e:
        print(f"[Settings Save Error] Could not save settings: {e}")

class FishSniperUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FishSniper")
        self.geometry("950x700")

        # Link global instances
        scanner.fish_loop = fish_loop

        # Configure Grid Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Fonts
        self.title_font = ctk.CTkFont(family="Helvetica", size=20, weight="bold")
        self.heading_font = ctk.CTkFont(family="Helvetica", size=14, weight="bold")
        self.normal_font = ctk.CTkFont(family="Helvetica", size=12)

        # --- SIDEBAR (Column 0) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(11, weight=1) # Push everything up

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="🎣 FishSniper", font=self.title_font)
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 30))

        # Start/Stop Button
        self.universal_button = ctk.CTkButton(self.sidebar_frame, text="🟢 Start FishSniper", font=self.heading_font,
                                              command=self.toggle_universal, fg_color="#28a745", hover_color="#218838", height=40)
        self.universal_button.grid(row=1, column=0, padx=20, pady=10)

        # Status Label
        self.status_label = ctk.CTkLabel(self.sidebar_frame, text="Status: Stopped", font=self.normal_font)
        self.status_label.grid(row=2, column=0, padx=20, pady=5)

        # Resolution Dropdown
        self.res_label = ctk.CTkLabel(self.sidebar_frame, text="Screen Resolution:", font=self.normal_font)
        self.res_label.grid(row=3, column=0, padx=20, pady=(20, 0))
        self.res_dropdown = ctk.CTkOptionMenu(self.sidebar_frame, values=["1080p", "1440p", "1366x768"], command=self.save_settings)
        self.res_dropdown.grid(row=4, column=0, padx=20, pady=(5, 10))

        # Speed Dropdown
        self.speed_label = ctk.CTkLabel(self.sidebar_frame, text="Pathing Speed:", font=self.normal_font)
        self.speed_label.grid(row=5, column=0, padx=20, pady=(20, 0))
        self.speed_dropdown = ctk.CTkOptionMenu(self.sidebar_frame, values=["Normal", "VIP"], command=self.save_settings)
        self.speed_dropdown.grid(row=6, column=0, padx=20, pady=(5, 10))

        # Max Fish
        self.max_catches_label = ctk.CTkLabel(self.sidebar_frame, text="Max Fish:", font=self.normal_font)
        self.max_catches_label.grid(row=7, column=0, padx=20, pady=(20, 0))
        self.max_catches_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="1", width=140)
        self.max_catches_entry.grid(row=8, column=0, padx=20, pady=(5, 10))
        self.max_catches_entry.insert(0, "1")

        # Sell Loops
        self.sell_loops_label = ctk.CTkLabel(self.sidebar_frame, text="Sell Loops (22 for all):", font=self.normal_font)
        self.sell_loops_label.grid(row=9, column=0, padx=20, pady=(20, 0))
        self.sell_loops_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="22", width=140)
        self.sell_loops_entry.grid(row=10, column=0, padx=20, pady=(5, 10))
        self.sell_loops_entry.insert(0, "22")

        # Save Button at bottom of sidebar
        self.save_bottom = ctk.CTkButton(self.sidebar_frame, text="💾 Save Settings", command=self.save_settings, fg_color="#007bff", hover_color="#0056b3")
        self.save_bottom.grid(row=12, column=0, padx=20, pady=(10, 20))


        # --- MAIN AREA (Column 1) ---
        self.tabview = ctk.CTkTabview(self, width=650)
        self.tabview.grid(row=0, column=1, padx=(20, 20), pady=(20, 20), sticky="nsew")
        
        self.tab_dash = self.tabview.add("📋 Dashboard")
        self.tab_auth = self.tabview.add("⚙️ Settings")
        self.tab_biomes = self.tabview.add("🌍 Biomes")
        self.tab_servers = self.tabview.add("💬 Servers")

        # --- TAB: DASHBOARD ---
        self.tab_dash.grid_columnconfigure(0, weight=1)
        self.tab_dash.grid_rowconfigure(1, weight=1)
        
        self.log_label = ctk.CTkLabel(self.tab_dash, text="Application Logs", font=self.heading_font)
        self.log_label.grid(row=0, column=0, padx=20, pady=(10, 0), sticky="w")

        self.log_textbox = ctk.CTkTextbox(self.tab_dash, font=ctk.CTkFont(family="Consolas", size=12), state="disabled")
        self.log_textbox.grid(row=1, column=0, padx=20, pady=(10, 20), sticky="nsew")

        # Redirect stdout/stderr to the textbox
        sys.stdout = DualLogger(self.log_textbox, sys.stdout)
        sys.stderr = DualLogger(self.log_textbox, sys.stderr)


        # --- TAB: SETTINGS ---
        self.tab_auth.grid_columnconfigure(0, weight=1)
        
        self.auth_heading = ctk.CTkLabel(self.tab_auth, text="Credentials & Integrations", font=self.heading_font)
        self.auth_heading.grid(row=0, column=0, padx=20, pady=(10, 5), sticky="w")

        self.rb_token_label = ctk.CTkLabel(self.tab_auth, text="Roblox Cookie (.ROBLOSECURITY):", font=self.normal_font)
        self.rb_token_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        self.rb_token_entry = ctk.CTkEntry(self.tab_auth, placeholder_text="Enter Roblox Cookie", width=400)
        self.rb_token_entry.grid(row=2, column=0, padx=20, pady=(5, 10), sticky="w")

        self.ds_token_label = ctk.CTkLabel(self.tab_auth, text="Discord User Token:", font=self.normal_font)
        self.ds_token_label.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.ds_token_entry = ctk.CTkEntry(self.tab_auth, placeholder_text="Enter Discord Token", width=400)
        self.ds_token_entry.grid(row=4, column=0, padx=20, pady=(5, 10), sticky="w")

        self.ds_webhook_label = ctk.CTkLabel(self.tab_auth, text="Discord Webhook URL (Optional):", font=self.normal_font)
        self.ds_webhook_label.grid(row=5, column=0, padx=20, pady=(10, 0), sticky="w")
        self.ds_webhook_entry = ctk.CTkEntry(self.tab_auth, placeholder_text="Enter Discord Webhook URL", width=400)
        self.ds_webhook_entry.grid(row=6, column=0, padx=20, pady=(5, 10), sticky="w")

        # (Fishing Parameters moved to sidebar)


        # --- TAB: BIOMES ---
        self.tab_biomes.grid_columnconfigure(0, weight=1)
        self.tab_biomes.grid_rowconfigure(1, weight=1)

        self.biomes_label = ctk.CTkLabel(self.tab_biomes, text="Select Biomes to Hunt", font=self.heading_font)
        self.biomes_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        self.scroll_biomes = ctk.CTkScrollableFrame(self.tab_biomes)
        self.scroll_biomes.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        self.biome_checkboxes = []
        for biome in BIOMES:
            cb = ctk.CTkSwitch(self.scroll_biomes, text=biome, font=self.normal_font)
            cb.pack(anchor="w", pady=5, padx=10)
            self.biome_checkboxes.append(cb)


        # --- TAB: SERVERS ---
        self.tab_servers.grid_columnconfigure(0, weight=1)
        self.tab_servers.grid_rowconfigure(1, weight=1)

        self.mapping_label = ctk.CTkLabel(self.tab_servers, text="Discord Server Configuration", font=self.heading_font)
        self.mapping_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        self.guild_scroll_frame = ctk.CTkScrollableFrame(self.tab_servers)
        self.guild_scroll_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="nsew")

        self.guild_entries = []  # Store tuples of (guild_entry, channels_entry) widgets

        button_frame = ctk.CTkFrame(self.tab_servers, fg_color="transparent")
        button_frame.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="w")

        self.add_guild_btn = ctk.CTkButton(button_frame, text="+ Add Server", command=self.add_guild_entry, width=120)
        self.add_guild_btn.pack(side="left", padx=(0, 10))

        self.remove_guild_btn = ctk.CTkButton(button_frame, text="- Remove Server", command=self.remove_guild_entry, width=120, fg_color="#dc3545", hover_color="#c82333")
        self.remove_guild_btn.pack(side="left")

        # Add initial entry
        self.add_guild_entry()


        # --- INITIALIZATION ---
        self.is_running = False
        self.scanner_paused_until = 0

        self.load_settings()
        self.initialize_scanner()

        threading.Thread(target=fish_loop.start, daemon=True).start()
        threading.Thread(target=scanner.start_scanner, daemon=True).start()

    def toggle_universal(self):
        """Universal start/stop button with intelligent state management"""
        from webhook import Webhook
        webhook_url = self.ds_webhook_entry.get().strip()

        if not self.is_running:
            # STARTING: Begin with scanner active
            self.is_running = True
            self.universal_button.configure(text="Stop FishSniper", fg_color="red", hover_color="dark red")
            self.status_label.configure(text="Status: Scanning for biomes...")

            # Start scanner (it will handle the rest of the logic)
            self.save_settings()  # Auto-sync before launching scanner
            scanner.toggle_on()
            print("[FishSniper] Started - Scanner active, waiting for biome detection")
            Webhook(webhook_url).send_app_started()

        else:
            # STOPPING: Stop everything
            self.is_running = False
            self.universal_button.configure(text="Start FishSniper", fg_color="green", hover_color="dark green")
            self.status_label.configure(text="Status: Stopped")

            # Stop both scanner and fishing
            scanner.toggle_off()
            fish_loop.toggle_off()
            print("[FishSniper] Stopped - All systems paused")
            Webhook(webhook_url).send_app_stopped()

    def update_status(self, new_status):
        """Update the status label from external calls"""
        self.status_label.configure(text=f"Status: {new_status}")

    def start_sniping(self):
        # Legacy method - redirect to universal toggle
        if not self.is_running:
            self.toggle_universal()

    def pause_sniping(self):
        # Legacy method - redirect to universal toggle
        if self.is_running:
            self.toggle_universal()

    def start_scanner(self):
        # Legacy method - handled by universal toggle
        pass

    def stop_scanner(self):
        # Legacy method - handled by universal toggle
        pass

    def add_guild_entry(self):
        """Add a new guild+channels entry row"""
        entry_frame = ctk.CTkFrame(self.guild_scroll_frame)
        entry_frame.pack(fill="x", padx=5, pady=5)

        guild_label = ctk.CTkLabel(entry_frame, text="Server ID:", font=("Helvetica", 9))
        guild_label.pack(anchor="w")
        guild_entry = ctk.CTkEntry(entry_frame, placeholder_text="Guild ID", width=200, height=28)
        guild_entry.pack(fill="x", padx=0, pady=(0, 5))

        channels_label = ctk.CTkLabel(entry_frame, text="Channel IDs (comma-separated):", font=("Helvetica", 9))
        channels_label.pack(anchor="w")
        channels_entry = ctk.CTkEntry(entry_frame, placeholder_text="CH1, CH2, CH3", width=200, height=28)
        channels_entry.pack(fill="x", padx=0, pady=(0, 3))

        self.guild_entries.append((guild_entry, channels_entry))

    def remove_guild_entry(self):
        """Remove the last guild+channels entry row"""
        if len(self.guild_entries) > 1:  # Keep at least one
            guild_entry, channels_entry = self.guild_entries.pop()
            guild_entry.master.destroy()
        else:
            print("[UI] Cannot remove the last server entry")

    def load_settings(self):
        """Load settings from LOCALAPPDATA and populate UI"""
        settings = load_settings_from_file()
        if not settings:
            print("[Settings] No saved settings found, using defaults")
            return

        try:
            # Load resolution and speed
            if 'resolution' in settings:
                self.res_dropdown.set(settings['resolution'])
                
            if 'speed' in settings:
                self.speed_dropdown.set(settings['speed'])

            # Load tokens
            if 'rb_token' in settings:
                self.rb_token_entry.delete(0, 'end')
                self.rb_token_entry.insert(0, settings['rb_token'])

            if 'ds_token' in settings:
                self.ds_token_entry.delete(0, 'end')
                self.ds_token_entry.insert(0, settings['ds_token'])

            if 'webhook_url' in settings:
                self.ds_webhook_entry.delete(0, 'end')
                self.ds_webhook_entry.insert(0, settings['webhook_url'])

            if 'max_catches' in settings:
                self.max_catches_entry.delete(0, 'end')
                self.max_catches_entry.insert(0, str(settings['max_catches']))

            if 'sell_loops' in settings:
                self.sell_loops_entry.delete(0, 'end')
                self.sell_loops_entry.insert(0, str(settings['sell_loops']))

            # Load selected biomes
            if 'selected_biomes' in settings:
                for cb, biome in zip(self.biome_checkboxes, BIOMES):
                    if biome in settings['selected_biomes']:
                        cb.select()
                    else:
                        cb.deselect()

            # Load guild mappings into the guild entries
            if 'guild_mappings' in settings and settings['guild_mappings']:
                # Clear existing entries except the first
                while len(self.guild_entries) > 1:
                    self.remove_guild_entry()

                # Load each guild mapping into an entry
                for i, mapping in enumerate(settings['guild_mappings']):
                    if i >= len(self.guild_entries):
                        self.add_guild_entry()
                    
                    guild_entry, channels_entry = self.guild_entries[i]
                    
                    if 'guild_id' in mapping:
                        guild_entry.delete(0, 'end')
                        guild_entry.insert(0, mapping['guild_id'])
                    
                    if 'channel_ids' in mapping:
                        channels = ', '.join(map(str, mapping['channel_ids']))
                        channels_entry.delete(0, 'end')
                        channels_entry.insert(0, channels)

            print("[Settings] Settings loaded successfully from LOCALAPPDATA")
        except Exception as e:
            print(f"[Settings Load Error] Error loading settings: {e}")

    def save_settings(self, value=None):
        rb_token = self.rb_token_entry.get().strip() # Cookie
        ds_token = self.ds_token_entry.get().strip() # User Token
        webhook_url = self.ds_webhook_entry.get().strip()
        res = self.res_dropdown.get()
        speed = self.speed_dropdown.get()
        
        try:
            max_catches = int(self.max_catches_entry.get().strip() or "1")
        except ValueError:
            max_catches = 1
            
        try:
            sell_loops = int(self.sell_loops_entry.get().strip() or "22")
        except ValueError:
            sell_loops = 22
        
        # Sync coordinates and speed
        fish_loop.update_coordinates(res, speed, max_catches, sell_loops)
        
        # Gather chosen biomes
        selected_biomes = [biome for cb, biome in zip(self.biome_checkboxes, BIOMES) if cb.get() == 1]
        
        # Parse all guild entries and convert to mappings
        guild_mappings = []
        for guild_entry, channels_entry in self.guild_entries:
            guild_id = guild_entry.get().strip()
            channels_str = channels_entry.get().strip()
            
            if guild_id:  # Only add if guild ID is provided
                channel_ids = [ch.strip() for ch in channels_str.split(',') if ch.strip()]
                
                guild_mappings.append({
                    "guild_id": guild_id,
                    "channel_ids": channel_ids,
                    "category_ids": []
                })

        # Sync values inside running Scanner Thread instance
        scanner.load_settings(ds_token, selected_biomes, rb_token, guild_mappings, webhook_url, self)

        # Save settings to LOCALAPPDATA
        settings_data = {
            'resolution': res,
            'speed': speed,
            'max_catches': max_catches,
            'sell_loops': sell_loops,
            'rb_token': rb_token,
            'ds_token': ds_token,
            'webhook_url': webhook_url,
            'selected_biomes': selected_biomes,
            'guild_mappings': guild_mappings
        }
        save_settings_to_file(settings_data)

        print("--- Settings Synchronized ---")
        print(f"Roblox Cookie Entered: {'Yes' if len(rb_token) > 0 else 'No'}")
        print(f"Discord Token Entered: {'Yes' if len(ds_token) > 0 else 'No'}")
        print(f"Resolution: {res}")
        print(f"Pathing Speed: {speed}")
        print(f"Monitoring Biomes: {selected_biomes}")
        print(f"Server Configurations: {len(guild_mappings)} rules loaded.")

    def initialize_scanner(self):
        """Initialize scanner with current settings and UI reference"""
        rb_token = self.rb_token_entry.get().strip()
        ds_token = self.ds_token_entry.get().strip()
        webhook_url = self.ds_webhook_entry.get().strip()
        selected_biomes = [biome for cb, biome in zip(self.biome_checkboxes, BIOMES) if cb.get() == 1]
        
        # Parse guild mappings
        guild_mappings = []
        for guild_entry, channels_entry in self.guild_entries:
            guild_id = guild_entry.get().strip()
            channels_str = channels_entry.get().strip()
            
            if guild_id:
                channel_ids = [ch.strip() for ch in channels_str.split(',') if ch.strip()]
                guild_mappings.append({
                    "guild_id": guild_id,
                    "channel_ids": channel_ids,
                    "category_ids": []
                })

        scanner.load_settings(ds_token, selected_biomes, rb_token, guild_mappings, webhook_url, self)