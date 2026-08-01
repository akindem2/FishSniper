import customtkinter as ctk
import threading
import json
import io
import requests
from PIL import Image
import fishing
from discord_scanner import scanner, biome_thumbnail_url
import os
from pathlib import Path
import sys
from tkinter import messagebox

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
THEME = {
    "bg": "#0f1117",
    "bg_alt": "#151822",
    "card": "#1b1f2b",
    "card_border": "#2a2f3d",
    "card_hover": "#232838",
    "accent": "#22d3ee",
    "accent_hover": "#0891b2",
    "accent2": "#8b5cf6",
    "accent2_hover": "#6d28d9",
    "success": "#22c55e",
    "success_hover": "#16a34a",
    "danger": "#ef4444",
    "danger_hover": "#b91c1c",
    "text": "#e5e7eb",
    "text_dim": "#9ca3af",
    "text_faint": "#5b6272",
}

TIER_COLORS = ["#22d3ee", "#38bdf8", "#818cf8", "#a78bfa", "#c084fc", "#e879f9", "#f472b6", "#fb923c"]


def tier_color(tier_index):
    return TIER_COLORS[(tier_index - 1) % len(TIER_COLORS)]


BIOMES = ["Rainy", "Snowy", "Windy", "Hell", "Heaven", "Corruption", "Starfall", "Sand Storm", "Null",
          "Glitched", "Dreamspace", "Cyberspace", "Singularity"]

BIOME_ICONS = {
    "Rainy": "🌧️", "Snowy": "❄️", "Windy": "💨", "Hell": "🔥", "Heaven": "☁️",
    "Corruption": "☠️", "Starfall": "🌠", "Sand Storm": "🏜️", "Null": "⬛",
    "Glitched": "🧩", "Dreamspace": "💤", "Cyberspace": "🖥️", "Singularity": "🌀",
}

# ---------------------------------------------------------------------------
# Biome thumbnails (downloaded lazily on a background thread; emoji above are
# the fallback shown until a thumbnail loads, or if it fails to load at all)
# ---------------------------------------------------------------------------
_biome_pil_cache = {}   # biome -> PIL.Image or None; safe to populate off the main thread
_biome_ctk_image_cache = {}  # (biome, size) -> ctk.CTkImage; must be built on the main thread


def fetch_biome_pil_image(biome_name):
    """Downloads + decodes a biome's thumbnail. Thread-safe (pure I/O + PIL, no Tk calls)."""
    if biome_name in _biome_pil_cache:
        return _biome_pil_cache[biome_name]
    try:
        resp = requests.get(biome_thumbnail_url(biome_name), timeout=4)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        _biome_pil_cache[biome_name] = img
        return img
    except Exception as e:
        print(f"[UI] Could not load thumbnail for {biome_name}: {e}")
        _biome_pil_cache[biome_name] = None
        return None


def get_biome_ctk_image(biome_name, size=(20, 20)):
    """Builds (and caches) a CTkImage from the PIL cache. Call only on the main thread."""
    key = (biome_name, size)
    if key in _biome_ctk_image_cache:
        return _biome_ctk_image_cache[key]
    pil_img = _biome_pil_cache.get(biome_name)
    if pil_img is None:
        return None
    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
    _biome_ctk_image_cache[key] = ctk_img
    return ctk_img

# Used only to seed a sensible default the first time the Priority tab is
# used (mirrors the tiers that used to be hardcoded). After that, whatever
# the user arranges in the UI is what's saved and loaded from then on.
DEFAULT_TIER_SEED = [
    ["Glitched", "Dreamspace", "Cyberspace"],
    ["Singularity"],
    ["Rainy", "Snowy", "Windy", "Hell", "Heaven", "Corruption", "Starfall", "Sand Storm", "Null"],
]

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


class StatusPill(ctk.CTkFrame):
    """Small rounded status indicator: colored dot + text."""
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=THEME["card"], corner_radius=20, border_width=1,
                          border_color=THEME["card_border"], **kwargs)
        self.dot = ctk.CTkLabel(self, text="●", text_color=THEME["text_faint"], font=ctk.CTkFont(size=14))
        self.dot.pack(side="left", padx=(14, 4), pady=8)
        self.text_label = ctk.CTkLabel(self, text="Stopped", text_color=THEME["text_dim"],
                                        font=ctk.CTkFont(size=12, weight="bold"))
        self.text_label.pack(side="left", padx=(0, 14), pady=8)

    def set_state(self, text, color):
        self.text_label.configure(text=text)
        self.dot.configure(text_color=color)


class BiomeCard(ctk.CTkFrame):
    """A draggable card representing one biome, used on the Priority board."""
    def __init__(self, master, biome_name, board, **kwargs):
        super().__init__(master, fg_color=THEME["card"], corner_radius=10, border_width=1,
                          border_color=THEME["card_border"], height=40, **kwargs)
        self.biome_name = biome_name
        self.board = board
        self.pack_propagate(False)

        thumb = get_biome_ctk_image(biome_name, size=(18, 18))
        if thumb:
            self.icon_label = ctk.CTkLabel(self, text="", image=thumb)
        else:
            self.icon_label = ctk.CTkLabel(self, text=BIOME_ICONS.get(biome_name, "🌐"),
                                            font=ctk.CTkFont(size=13))
        self.icon_label.pack(side="left", padx=(10, 4), pady=6)

        self.label = ctk.CTkLabel(self, text=biome_name, font=ctk.CTkFont(size=12, weight="bold"),
                                   text_color=THEME["text"])
        self.label.pack(side="left", padx=(0, 10), pady=6)

        for widget in (self, self.icon_label, self.label):
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<B1-Motion>", self._on_motion)
            widget.bind("<ButtonRelease-1>", self._on_release)

        try:
            self.configure(cursor="hand2")
        except Exception:
            pass

    def _on_press(self, event):
        self.board.start_drag(self.biome_name, event)

    def _on_motion(self, event):
        self.board.update_drag(event)

    def _on_release(self, event):
        self.board.end_drag(event)


class PriorityBoard(ctk.CTkFrame):
    """
    Trello-style tier board for assigning biome priority levels.
    Tier 1 = highest priority; larger tier numbers are lower priority.
    Biomes must be dragged out of "Unassigned" into a tier before they can
    be used (enforced by the app before starting).
    """
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app  # reference to FishSniperUI for enabled biomes + callbacks

        self.assignments = {}  # biome_name -> tier index (1-based); absent = unassigned
        self.num_tiers = 3

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkLabel(self, text="Drag biomes between columns \u2014 Tier 1 is the highest priority.",
                               font=ctk.CTkFont(size=12), text_color=THEME["text_dim"])
        header.grid(row=0, column=0, sticky="w", padx=4, pady=(0, 10))

        self.columns_scroll = ctk.CTkScrollableFrame(self, orientation="horizontal", fg_color="transparent")
        self.columns_scroll.grid(row=1, column=0, sticky="nsew")

        self.column_widgets = {}  # key: "unassigned" or tier int -> {"frame":, "body":}
        self.drag_ghost = None
        self.dragging_biome = None

        self._build_columns()

    # ---- column construction ---------------------------------------------
    def _build_columns(self):
        for child in self.columns_scroll.winfo_children():
            child.destroy()
        self.column_widgets = {}

        self._add_column_widget("unassigned", "📥 Unassigned", THEME["text_faint"], removable=False)
        for tier in range(1, self.num_tiers + 1):
            title = f"🏆 Tier {tier}" if tier == 1 else f"Tier {tier}"
            removable = (tier == self.num_tiers and self.num_tiers > 1)
            self._add_column_widget(tier, title, tier_color(tier), removable=removable)

        self._add_tier_button()

    def _add_column_widget(self, key, title, color, removable):
        col = ctk.CTkFrame(self.columns_scroll, width=190, fg_color=THEME["bg_alt"], corner_radius=12,
                            border_width=1, border_color=THEME["card_border"])
        col.pack(side="left", fill="y", padx=6, pady=2)
        col.pack_propagate(False)
        col.configure(height=380)

        header_frame = ctk.CTkFrame(col, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 6))

        title_label = ctk.CTkLabel(header_frame, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                                    text_color=color)
        title_label.pack(side="left")

        if removable:
            remove_btn = ctk.CTkButton(header_frame, text="✕", width=22, height=22, font=ctk.CTkFont(size=11),
                                        fg_color="transparent", hover_color=THEME["danger"],
                                        text_color=THEME["text_dim"], command=self.remove_last_tier)
            remove_btn.pack(side="right")

        accent_line = ctk.CTkFrame(col, fg_color=color, height=2, corner_radius=1)
        accent_line.pack(fill="x", padx=10, pady=(0, 8))

        body = ctk.CTkFrame(col, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        self.column_widgets[key] = {"frame": col, "body": body}

    def _add_tier_button(self):
        add_col = ctk.CTkFrame(self.columns_scroll, width=60, fg_color="transparent")
        add_col.pack(side="left", fill="y", padx=6, pady=2)
        btn = ctk.CTkButton(add_col, text="+", width=44, height=44, corner_radius=22,
                             font=ctk.CTkFont(size=18, weight="bold"),
                             fg_color=THEME["card"], hover_color=THEME["card_hover"],
                             border_width=1, border_color=THEME["card_border"],
                             command=self.add_tier)
        btn.pack(pady=150)

    def add_tier(self):
        self.num_tiers += 1
        self._build_columns()
        self.render()

    def remove_last_tier(self):
        if self.num_tiers <= 1:
            return
        removed_tier = self.num_tiers
        for biome, tier in list(self.assignments.items()):
            if tier == removed_tier:
                del self.assignments[biome]
        self.num_tiers -= 1
        self._build_columns()
        self.render()

    # ---- rendering ---------------------------------------------------------
    def render(self):
        """Redraws all cards from self.assignments + the app's enabled biomes."""
        for col in self.column_widgets.values():
            for child in col["body"].winfo_children():
                child.destroy()

        enabled = self.app.get_enabled_biomes()
        for biome in enabled:
            tier = self.assignments.get(biome)
            key = tier if (tier is not None and tier in self.column_widgets) else "unassigned"
            card = BiomeCard(self.column_widgets[key]["body"], biome, self)
            card.pack(fill="x", pady=3)

    # ---- drag and drop -------------------------------------------------------
    def start_drag(self, biome_name, event):
        self.dragging_biome = biome_name
        if self.drag_ghost is not None:
            try:
                self.drag_ghost.destroy()
            except Exception:
                pass

        ghost = ctk.CTkToplevel(self)
        ghost.overrideredirect(True)
        try:
            ghost.attributes("-topmost", True)
        except Exception:
            pass
        try:
            ghost.attributes("-alpha", 0.88)
        except Exception:
            pass

        icon = BIOME_ICONS.get(biome_name, "🌐")
        thumb = get_biome_ctk_image(biome_name, size=(16, 16))
        if thumb:
            lbl = ctk.CTkLabel(ghost, text=f"  {biome_name}", image=thumb, compound="left",
                                fg_color=THEME["accent"], text_color="#0b0f14", corner_radius=8,
                                font=ctk.CTkFont(size=12, weight="bold"))
        else:
            lbl = ctk.CTkLabel(ghost, text=f"{icon}  {biome_name}", fg_color=THEME["accent"],
                                text_color="#0b0f14", corner_radius=8, font=ctk.CTkFont(size=12, weight="bold"))
        lbl.pack(ipadx=10, ipady=6)
        ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
        self.drag_ghost = ghost

    def update_drag(self, event):
        if self.drag_ghost is not None:
            try:
                self.drag_ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
            except Exception:
                pass

    def end_drag(self, event):
        if self.drag_ghost is not None:
            try:
                self.drag_ghost.destroy()
            except Exception:
                pass
            self.drag_ghost = None

        if not self.dragging_biome:
            return

        target_key = None
        for key, col in self.column_widgets.items():
            frame = col["frame"]
            try:
                x1, y1 = frame.winfo_rootx(), frame.winfo_rooty()
                x2, y2 = x1 + frame.winfo_width(), y1 + frame.winfo_height()
            except Exception:
                continue
            if x1 <= event.x_root <= x2 and y1 <= event.y_root <= y2:
                target_key = key
                break

        if target_key is not None:
            if target_key == "unassigned":
                self.assignments.pop(self.dragging_biome, None)
            else:
                self.assignments[self.dragging_biome] = target_key

        self.dragging_biome = None
        self.render()
        self.app.on_priority_changed()

    # ---- data access ---------------------------------------------------------
    def get_unassigned(self):
        enabled = self.app.get_enabled_biomes()
        return [b for b in enabled if b not in self.assignments]

    def load_data(self, assignments, num_tiers):
        self.assignments = dict(assignments) if assignments else {}
        self.num_tiers = max(1, num_tiers or 1)
        self.assignments = {b: t for b, t in self.assignments.items() if 1 <= t <= self.num_tiers}
        self._build_columns()
        self.render()

    def seed_defaults(self):
        for tier_idx, biomes in enumerate(DEFAULT_TIER_SEED, start=1):
            for biome in biomes:
                self.assignments[biome] = tier_idx
        self.num_tiers = max(self.num_tiers, len(DEFAULT_TIER_SEED))
        self._build_columns()


class FishSniperUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")

        self.title("FishSniper")
        self.geometry("1080x780")
        self.configure(fg_color=THEME["bg"])

        # Link global instances
        scanner.fish_loop = fish_loop
        fish_loop.set_path_change_callback(self._on_active_path_changed)

        # Configure Grid Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Fonts
        self.title_font = ctk.CTkFont(family="Helvetica", size=20, weight="bold")
        self.heading_font = ctk.CTkFont(family="Helvetica", size=14, weight="bold")
        self.normal_font = ctk.CTkFont(family="Helvetica", size=12)
        self.small_font = ctk.CTkFont(family="Helvetica", size=10)

        # --- SIDEBAR (Column 0) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=THEME["bg_alt"])
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)
        self.sidebar_frame.grid_rowconfigure(9, weight=1)

        logo_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=20, pady=(24, 20), sticky="w")
        ctk.CTkLabel(logo_frame, text="🎣", font=ctk.CTkFont(size=26)).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(logo_frame, text="FishSniper", font=self.title_font, text_color=THEME["text"]).pack(side="left")

        self.universal_button = ctk.CTkButton(
            self.sidebar_frame, text="▶  Start FishSniper", font=self.heading_font,
            command=self.toggle_universal, fg_color=THEME["success"], hover_color=THEME["success_hover"],
            height=42, corner_radius=10)
        self.universal_button.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.status_pill = StatusPill(self.sidebar_frame)
        self.status_pill.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")

        self.active_path_label = ctk.CTkLabel(
            self.sidebar_frame, text="Active Path: Path 1", font=self.small_font,
            text_color=THEME["accent"], anchor="w",
        )
        self.active_path_label.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")

        quick_card = ctk.CTkFrame(self.sidebar_frame, fg_color=THEME["card"], corner_radius=12,
                                   border_width=1, border_color=THEME["card_border"])
        quick_card.grid(row=4, column=0, padx=20, pady=(0, 16), sticky="ew")

        ctk.CTkLabel(quick_card, text="FISHING SETUP", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=THEME["text_faint"]).pack(anchor="w", padx=14, pady=(12, 6))

        self._sidebar_field_label(quick_card, "Screen Resolution")
        self.res_dropdown = ctk.CTkOptionMenu(quick_card, values=["1080p", "1440p", "1366x768"],
                                               command=self.save_settings, fg_color=THEME["bg_alt"],
                                               button_color=THEME["accent"], button_hover_color=THEME["accent_hover"],
                                               dropdown_fg_color=THEME["card"])
        self.res_dropdown.pack(fill="x", padx=14, pady=(0, 10))

        self._sidebar_field_label(quick_card, "Pathing Mode")
        self.speed_dropdown = ctk.CTkOptionMenu(quick_card, values=["Vip Pathing", "Non Vip Pathing"],
                                                 command=self.save_settings, fg_color=THEME["bg_alt"],
                                                 button_color=THEME["accent"],
                                                 button_hover_color=THEME["accent_hover"],
                                                 dropdown_fg_color=THEME["card"])
        self.speed_dropdown.pack(fill="x", padx=14, pady=(0, 10))

        self._sidebar_field_label(quick_card, "Starting Path")
        self.path_dropdown = ctk.CTkOptionMenu(
            quick_card, values=[f"Path {number}" for number in range(1, 6)],
            command=self.on_path_selection, fg_color=THEME["bg_alt"],
            button_color=THEME["accent"], button_hover_color=THEME["accent_hover"],
            dropdown_fg_color=THEME["card"],
        )
        self.path_dropdown.set("Path 1")
        self.path_dropdown.pack(fill="x", padx=14, pady=(0, 10))

        self._sidebar_field_label(quick_card, "Max Fish")
        self.max_catches_entry = ctk.CTkEntry(quick_card, placeholder_text="1", fg_color=THEME["bg_alt"],
                                               border_color=THEME["card_border"])
        self.max_catches_entry.pack(fill="x", padx=14, pady=(0, 10))
        self.max_catches_entry.insert(0, "1")

        self._sidebar_field_label(quick_card, "Sell Loops (22 = all)")
        self.sell_loops_entry = ctk.CTkEntry(quick_card, placeholder_text="22", fg_color=THEME["bg_alt"],
                                              border_color=THEME["card_border"])
        self.sell_loops_entry.pack(fill="x", padx=14, pady=(0, 14))
        self.sell_loops_entry.insert(0, "22")

        self.save_bottom = ctk.CTkButton(self.sidebar_frame, text="💾  Save Settings", command=self.save_settings,
                                          fg_color=THEME["accent2"], hover_color=THEME["accent2_hover"],
                                          height=38, corner_radius=10)
        self.save_bottom.grid(row=10, column=0, padx=20, pady=(0, 20), sticky="sew")

        # --- MAIN AREA (Column 1) ---
        self.tabview = ctk.CTkTabview(self, fg_color=THEME["bg"], segmented_button_fg_color=THEME["bg_alt"],
                                       segmented_button_selected_color=THEME["accent"],
                                       segmented_button_selected_hover_color=THEME["accent_hover"],
                                       segmented_button_unselected_color=THEME["bg_alt"],
                                       text_color=THEME["text"])
        self.tabview.grid(row=0, column=1, padx=(16, 20), pady=20, sticky="nsew")

        self.tab_dash = self.tabview.add("📋 Dashboard")
        self.tab_auth = self.tabview.add("⚙️ Settings")
        self.tab_biomes = self.tabview.add("🌍 Biomes")
        self.tab_priority = self.tabview.add("🏆 Priority")
        self.tab_servers = self.tabview.add("💬 Servers")

        self._build_dashboard_tab()
        self._build_settings_tab()
        self._build_biomes_tab()
        self._build_priority_tab()
        self._build_servers_tab()

        # Thumbnails are fetched over the network, so load them in the
        # background and swap them in once each one lands rather than
        # blocking startup on 13 HTTP requests.
        threading.Thread(target=self._preload_thumbnails, daemon=True).start()

        # --- INITIALIZATION ---
        self.is_running = False

        self.load_settings()
        self.initialize_scanner()

        threading.Thread(target=fish_loop.start, daemon=True).start()
        threading.Thread(target=scanner.start_scanner, daemon=True).start()

    # ------------------------------------------------------------------
    # Small layout helpers
    # ------------------------------------------------------------------
    def _sidebar_field_label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=self.small_font, text_color=THEME["text_dim"]).pack(
            anchor="w", padx=14, pady=(0, 3))

    def _credential_field(self, card, index, label_text, placeholder, last=False):
        pady_top = 16 if index == 0 else 14
        ctk.CTkLabel(card, text=label_text, font=self.normal_font, text_color=THEME["text_dim"]).grid(
            row=index * 2, column=0, padx=16, pady=(pady_top, 4), sticky="w")
        entry = ctk.CTkEntry(card, placeholder_text=placeholder, fg_color=THEME["bg_alt"],
                              border_color=THEME["card_border"], height=34)
        entry.grid(row=index * 2 + 1, column=0, padx=16, pady=(0, 16 if last else 4), sticky="ew")
        return entry

    def _server_field(self, parent, placeholder, last=False):
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder, fg_color=THEME["bg_alt"],
                              border_color=THEME["card_border"], height=28)
        entry.pack(fill="x", padx=12, pady=(8, 14 if last else 0))
        return entry

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------
    def _build_dashboard_tab(self):
        self.tab_dash.grid_columnconfigure(0, weight=1)
        self.tab_dash.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.tab_dash, text="Application Logs", font=self.heading_font,
                     text_color=THEME["text"]).grid(row=0, column=0, padx=4, pady=(6, 10), sticky="w")

        self.log_textbox = ctk.CTkTextbox(self.tab_dash, font=ctk.CTkFont(family="Consolas", size=12),
                                           state="disabled", fg_color=THEME["bg_alt"], border_width=1,
                                           border_color=THEME["card_border"], corner_radius=10)
        self.log_textbox.grid(row=1, column=0, padx=4, pady=(0, 6), sticky="nsew")

        # Redirect stdout/stderr to the textbox
        sys.stdout = DualLogger(self.log_textbox, sys.stdout)
        sys.stderr = DualLogger(self.log_textbox, sys.stderr)

    def _build_settings_tab(self):
        self.tab_auth.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.tab_auth, text="Credentials & Integrations", font=self.heading_font,
                     text_color=THEME["text"]).grid(row=0, column=0, padx=4, pady=(6, 14), sticky="w")

        card = ctk.CTkFrame(self.tab_auth, fg_color=THEME["card"], corner_radius=12, border_width=1,
                             border_color=THEME["card_border"])
        card.grid(row=1, column=0, padx=4, pady=(0, 10), sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        self.rb_token_entry = self._credential_field(card, 0, "🎮 Roblox Cookie (.ROBLOSECURITY)",
                                                       "Enter Roblox Cookie")
        self.ds_token_entry = self._credential_field(card, 1, "💬 Discord User Token", "Enter Discord Token")
        self.ds_webhook_entry = self._credential_field(card, 2, "🔔 Discord Webhook URL (Optional)",
                                                         "Enter Discord Webhook URL")
        self.ds_ping_user_id_entry = self._credential_field(
            card, 3, "📣 Discord User ID to Ping (Optional)",
            "Pinged on Glitched / Dreamspace / Cyberspace joins", last=True)

    def _build_biomes_tab(self):
        self.tab_biomes.grid_columnconfigure(0, weight=1)
        self.tab_biomes.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.tab_biomes, text="Select Biomes to Hunt", font=self.heading_font,
                     text_color=THEME["text"]).grid(row=0, column=0, padx=4, pady=(6, 10), sticky="w")

        self.scroll_biomes = ctk.CTkScrollableFrame(self.tab_biomes, fg_color="transparent")
        self.scroll_biomes.grid(row=1, column=0, padx=2, pady=(0, 10), sticky="nsew")
        for col in range(3):
            self.scroll_biomes.grid_columnconfigure(col, weight=1)

        self.biome_switches = {}
        self.biome_icon_labels = {}
        for i, biome in enumerate(BIOMES):
            row, col = divmod(i, 3)
            card = ctk.CTkFrame(self.scroll_biomes, fg_color=THEME["card"], corner_radius=10,
                                 border_width=1, border_color=THEME["card_border"])
            card.grid(row=row, column=col, padx=6, pady=6, sticky="ew")

            row_frame = ctk.CTkFrame(card, fg_color="transparent")
            row_frame.pack(anchor="w", padx=12, pady=10, fill="x")

            thumb = get_biome_ctk_image(biome, size=(20, 20))
            if thumb:
                icon_label = ctk.CTkLabel(row_frame, text="", image=thumb)
            else:
                icon_label = ctk.CTkLabel(row_frame, text=BIOME_ICONS.get(biome, "🌐"),
                                           font=ctk.CTkFont(size=15))
            icon_label.pack(side="left", padx=(0, 8))
            self.biome_icon_labels[biome] = icon_label

            switch = ctk.CTkSwitch(row_frame, text=biome, font=self.normal_font,
                                    progress_color=THEME["accent"], command=self.on_biome_toggle,
                                    text_color=THEME["text"])
            switch.pack(side="left")
            self.biome_switches[biome] = switch

    def _build_priority_tab(self):
        self.tab_priority.grid_columnconfigure(0, weight=1)
        self.tab_priority.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.tab_priority, text="Priority Tiers", font=self.heading_font,
                     text_color=THEME["text"]).grid(row=0, column=0, padx=4, pady=(6, 4), sticky="w")

        self.priority_board = PriorityBoard(self.tab_priority, self)
        self.priority_board.grid(row=1, column=0, padx=2, pady=(0, 10), sticky="nsew")

    def _build_servers_tab(self):
        self.tab_servers.grid_columnconfigure(0, weight=1)
        self.tab_servers.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.tab_servers, text="Discord Server Configuration", font=self.heading_font,
                     text_color=THEME["text"]).grid(row=0, column=0, padx=4, pady=(6, 10), sticky="w")

        self.guild_scroll_frame = ctk.CTkScrollableFrame(self.tab_servers, fg_color="transparent")
        self.guild_scroll_frame.grid(row=1, column=0, padx=2, pady=(0, 10), sticky="nsew")

        self.guild_entries = []  # list of dicts: frame, name, guild, channels, categories

        button_frame = ctk.CTkFrame(self.tab_servers, fg_color="transparent")
        button_frame.grid(row=2, column=0, padx=4, pady=(0, 6), sticky="w")

        self.add_guild_btn = ctk.CTkButton(button_frame, text="+ Add Server", command=self.add_guild_entry,
                                            width=130, fg_color=THEME["accent2"],
                                            hover_color=THEME["accent2_hover"])
        self.add_guild_btn.pack(side="left")

        # Add initial entry
        self.add_guild_entry()

    # ------------------------------------------------------------------
    # Behavior
    # ------------------------------------------------------------------
    def get_enabled_biomes(self):
        return [b for b in BIOMES if self.biome_switches[b].get() == 1]

    def on_biome_toggle(self):
        if hasattr(self, "priority_board"):
            self.priority_board.render()

    def on_path_selection(self, value):
        try:
            fish_loop.select_path(int(value.rsplit(" ", 1)[1]) - 1)
        except (IndexError, ValueError):
            return

    def _on_active_path_changed(self, path_name):
        """Receive path changes from the fishing thread without touching Tk off-thread."""
        def update_ui():
            self.active_path_label.configure(text=f"Active Path: {path_name}")
            self.path_dropdown.set(path_name)
        self.after(0, update_ui)

    def on_priority_changed(self):
        # Hook for future auto-persistence; currently a no-op, kept for clarity.
        pass

    def _preload_thumbnails(self):
        """Runs on a background thread: downloads + decodes every biome's thumbnail."""
        for biome in BIOMES:
            fetch_biome_pil_image(biome)
            self.after(0, self._on_thumbnail_loaded, biome)

    def _on_thumbnail_loaded(self, biome):
        """Runs on the main thread once a thumbnail's PIL image is ready."""
        thumb = get_biome_ctk_image(biome, size=(20, 20))
        if thumb and biome in self.biome_icon_labels:
            self.biome_icon_labels[biome].configure(image=thumb, text="")
        if hasattr(self, "priority_board"):
            self.priority_board.render()

    def validate_priority_assignments(self):
        unassigned = self.priority_board.get_unassigned()
        if unassigned:
            messagebox.showerror(
                "Priority Not Set",
                "The following enabled biomes need a priority tier before FishSniper can start:\n\n"
                + "\n".join(f"\u2022 {b}" for b in unassigned)
                + "\n\nGo to the Priority tab and drag them into a tier."
            )
            print(f"[FishSniper] Cannot start \u2014 unassigned biomes: {', '.join(unassigned)}")
            return False
        return True

    def toggle_universal(self):
        """Universal start/stop button with intelligent state management"""
        from webhook import Webhook
        webhook_url = self.ds_webhook_entry.get().strip()

        if not self.is_running:
            if not self.validate_priority_assignments():
                return

            # STARTING: Begin with scanner active
            self.is_running = True
            self.universal_button.configure(text="■  Stop FishSniper", fg_color=THEME["danger"],
                                             hover_color=THEME["danger_hover"])
            self.update_status("Scanning for biomes...")

            self.save_settings()  # Auto-sync before launching scanner
            scanner.toggle_on()
            print("[FishSniper] Started - Scanner active, waiting for biome detection")
            Webhook(webhook_url).send_app_started()

        else:
            # STOPPING: Stop everything
            self.is_running = False
            self.universal_button.configure(text="▶  Start FishSniper", fg_color=THEME["success"],
                                             hover_color=THEME["success_hover"])
            self.update_status("Stopped")

            scanner.toggle_off()
            fish_loop.toggle_off()
            print("[FishSniper] Stopped - All systems paused")
            Webhook(webhook_url).send_app_stopped()

    def update_status(self, new_status):
        """Update the status pill from external calls"""
        color = THEME["text_faint"] if new_status.strip().lower() == "stopped" else THEME["accent"]
        self.status_pill.set_state(new_status, color)

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
        """Add a new guild+channels entry card"""
        entry_frame = ctk.CTkFrame(self.guild_scroll_frame, fg_color=THEME["card"], corner_radius=10,
                                    border_width=1, border_color=THEME["card_border"])
        entry_frame.pack(fill="x", padx=4, pady=6)

        top_row = ctk.CTkFrame(entry_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=(10, 0))

        name_entry = ctk.CTkEntry(top_row, placeholder_text="Server Name (Optional)", fg_color=THEME["bg_alt"],
                                   border_color=THEME["card_border"], height=30)
        name_entry.pack(side="left", fill="x", expand=True)

        remove_btn = ctk.CTkButton(top_row, text="✕", width=26, height=26, font=ctk.CTkFont(size=11),
                                    fg_color="transparent", hover_color=THEME["danger"],
                                    text_color=THEME["text_dim"],
                                    command=lambda: self.remove_guild_entry(entry_frame))
        remove_btn.pack(side="left", padx=(8, 0))

        guild_entry = self._server_field(entry_frame, "Server ID")
        channels_entry = self._server_field(entry_frame, "Channel IDs (comma-separated)")
        categories_entry = self._server_field(entry_frame, "Category IDs (comma-separated)", last=True)

        self.guild_entries.append({
            "frame": entry_frame,
            "name": name_entry,
            "guild": guild_entry,
            "channels": channels_entry,
            "categories": categories_entry,
        })

    def remove_guild_entry(self, frame=None):
        """Remove a specific guild entry card (or the last one if none given)"""
        if len(self.guild_entries) <= 1:  # Keep at least one
            print("[UI] Cannot remove the last server entry")
            return

        if frame is None:
            entry = self.guild_entries.pop()
        else:
            entry = next((e for e in self.guild_entries if e["frame"] == frame), None)
            if entry is None:
                return
            self.guild_entries.remove(entry)

        entry["frame"].destroy()

    def load_settings(self):
        """Load settings from LOCALAPPDATA and populate UI"""
        settings = load_settings_from_file()
        if not settings:
            print("[Settings] No saved settings found, using defaults")
            self.priority_board.seed_defaults()
            self.priority_board.render()
            return

        try:
            # Load resolution and speed (Pathing Mode)
            if 'resolution' in settings:
                self.res_dropdown.set(settings['resolution'])

            if 'speed' in settings:
                saved_speed = settings['speed']
                # Migrate older speed values to new pathing options
                if saved_speed == "VIP":
                    saved_speed = "Vip Pathing"
                elif saved_speed == "Normal":
                    saved_speed = "Non Vip Pathing"
                self.speed_dropdown.set(saved_speed)

            selected_path = settings.get('selected_path', 1)
            try:
                selected_path = min(5, max(1, int(selected_path)))
            except (TypeError, ValueError):
                selected_path = 1
            self.path_dropdown.set(f"Path {selected_path}")
            fish_loop.select_path(selected_path - 1)

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

            if 'discord_ping_user_id' in settings:
                self.ds_ping_user_id_entry.delete(0, 'end')
                self.ds_ping_user_id_entry.insert(0, settings['discord_ping_user_id'])

            if 'max_catches' in settings:
                self.max_catches_entry.delete(0, 'end')
                self.max_catches_entry.insert(0, str(settings['max_catches']))

            if 'sell_loops' in settings:
                self.sell_loops_entry.delete(0, 'end')
                self.sell_loops_entry.insert(0, str(settings['sell_loops']))

            # Load selected biomes
            if 'selected_biomes' in settings:
                for biome in BIOMES:
                    switch = self.biome_switches[biome]
                    if biome in settings['selected_biomes']:
                        switch.select()
                    else:
                        switch.deselect()

            # Load guild mappings into the guild entries
            if 'guild_mappings' in settings and settings['guild_mappings']:
                while len(self.guild_entries) > 1:
                    self.remove_guild_entry()

                for i, mapping in enumerate(settings['guild_mappings']):
                    if i >= len(self.guild_entries):
                        self.add_guild_entry()

                    entry = self.guild_entries[i]

                    name_val = mapping.get('server_name', mapping.get('name', ''))
                    entry["name"].delete(0, 'end')
                    entry["name"].insert(0, name_val)

                    if 'guild_id' in mapping:
                        entry["guild"].delete(0, 'end')
                        entry["guild"].insert(0, mapping['guild_id'])

                    if 'channel_ids' in mapping:
                        channels = ', '.join(map(str, mapping['channel_ids']))
                        entry["channels"].delete(0, 'end')
                        entry["channels"].insert(0, channels)

                    if 'category_ids' in mapping:
                        categories = ', '.join(map(str, mapping['category_ids']))
                        entry["categories"].delete(0, 'end')
                        entry["categories"].insert(0, categories)
                    else:
                        entry["categories"].delete(0, 'end')

            # Load priority board data
            biome_priority_levels = settings.get('biome_priority_levels')
            num_tiers = settings.get('num_tiers', 3)
            if biome_priority_levels:
                self.priority_board.load_data(biome_priority_levels, num_tiers)
            else:
                self.priority_board.seed_defaults()
                self.priority_board.render()

            print("[Settings] Settings loaded successfully from LOCALAPPDATA")
        except Exception as e:
            print(f"[Settings Load Error] Error loading settings: {e}")
            self.priority_board.render()

    def _collect_guild_mappings(self):
        guild_mappings = []
        for entry in self.guild_entries:
            server_name = entry["name"].get().strip()
            guild_id = entry["guild"].get().strip()
            channels_str = entry["channels"].get().strip()
            categories_str = entry["categories"].get().strip()

            if guild_id:  # Only add if guild ID is provided
                channel_ids = [ch.strip() for ch in channels_str.split(',') if ch.strip()]
                category_ids = [cat.strip() for cat in categories_str.split(',') if cat.strip()]

                guild_mappings.append({
                    "server_name": server_name,
                    "guild_id": guild_id,
                    "channel_ids": channel_ids,
                    "category_ids": category_ids
                })
        return guild_mappings

    def save_settings(self, value=None):
        rb_token = self.rb_token_entry.get().strip()  # Cookie
        ds_token = self.ds_token_entry.get().strip()  # User Token
        webhook_url = self.ds_webhook_entry.get().strip()
        ping_user_id = self.ds_ping_user_id_entry.get().strip()
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

        try:
            selected_path = int(self.path_dropdown.get().rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            selected_path = 1

        fish_loop.update_coordinates(res, speed, max_catches, sell_loops)
        fish_loop.select_path(selected_path - 1)

        # Gather chosen biomes
        selected_biomes = self.get_enabled_biomes()

        # Parse all guild entries and convert to mappings
        guild_mappings = self._collect_guild_mappings()

        biome_priority_levels = dict(self.priority_board.assignments)
        num_tiers = self.priority_board.num_tiers

        # Sync values inside running Scanner Thread instance
        scanner.load_settings(ds_token, selected_biomes, rb_token, guild_mappings, webhook_url, self,
                               biome_priority_levels, discord_ping_user_id=ping_user_id)

        # Save settings to LOCALAPPDATA
        settings_data = {
            'resolution': res,
            'speed': speed,
            'max_catches': max_catches,
            'sell_loops': sell_loops,
            'selected_path': selected_path,
            'rb_token': rb_token,
            'ds_token': ds_token,
            'webhook_url': webhook_url,
            'discord_ping_user_id': ping_user_id,
            'selected_biomes': selected_biomes,
            'guild_mappings': guild_mappings,
            'biome_priority_levels': biome_priority_levels,
            'num_tiers': num_tiers,
        }
        save_settings_to_file(settings_data)

        print("--- Settings Synchronized ---")
        print(f"Roblox Cookie Entered: {'Yes' if len(rb_token) > 0 else 'No'}")
        print(f"Discord Token Entered: {'Yes' if len(ds_token) > 0 else 'No'}")
        print(f"Resolution: {res}")
        print(f"Pathing Mode: {speed}")
        print(f"Starting Path: Path {selected_path}")
        print(f"Monitoring Biomes: {selected_biomes}")
        print(f"Server Configurations: {len(guild_mappings)} rules loaded.")

        unassigned = self.priority_board.get_unassigned()
        if unassigned:
            print(f"[FishSniper] Note: these enabled biomes still need a priority tier: {', '.join(unassigned)}")

    def initialize_scanner(self):
        """Initialize scanner with current settings and UI reference"""
        rb_token = self.rb_token_entry.get().strip()
        ds_token = self.ds_token_entry.get().strip()
        webhook_url = self.ds_webhook_entry.get().strip()
        ping_user_id = self.ds_ping_user_id_entry.get().strip()
        selected_biomes = self.get_enabled_biomes()

        guild_mappings = self._collect_guild_mappings()
        biome_priority_levels = dict(self.priority_board.assignments)

        scanner.load_settings(ds_token, selected_biomes, rb_token, guild_mappings, webhook_url, self,
                               biome_priority_levels, discord_ping_user_id=ping_user_id)
