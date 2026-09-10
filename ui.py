import sys
import io
import json
import math
import random
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape
from pathlib import Path
import os

import requests

from PySide6 import QtCore, QtGui, QtWidgets

import fishing
from discord_scanner import scanner, biome_thumbnail_url, format_biome_duration

try:
    import keyboard
except Exception as e:
    keyboard = None
    print(f"[UI] 'keyboard' module unavailable — global hotkeys will be disabled: {e}")

DEFAULT_START_HOTKEY = "f1"
DEFAULT_STOP_HOTKEY = "f2"

MAX_AUTO_ITEMS = 100
MAX_GAUNTLETS = 20

SHOP_RESTOCK_HOUR_ET = 20
SHOP_RESTOCK_TZ = ZoneInfo("America/New_York")


def current_shop_restock_boundary():
    now_et = datetime.now(SHOP_RESTOCK_TZ)
    boundary = now_et.replace(hour=SHOP_RESTOCK_HOUR_ET, minute=0, second=0, microsecond=0)
    if now_et < boundary:
        boundary -= timedelta(days=1)
    return boundary


# ---------------------------------------------------------------------------
# Theme — "deep-water" ocean palette (adapted from the MerchantSnipe
# "arcane-midnight" PySide6 UI, recolored blue for the fishing/water motif).
# ---------------------------------------------------------------------------
THEME = {
    "bg": "#081525",
    "bg_alt": "#0b1c30",
    "card": "#102942",
    "card_border": "#1e3f63",
    "card_hover": "#163351",
    "accent": "#38bdf8",
    "accent_hover": "#7dd3fc",
    "accent2": "#2563eb",
    "accent2_hover": "#1d4ed8",
    "success": "#14b8a6",
    "success_hover": "#0d9488",
    "danger": "#fb7185",
    "danger_hover": "#f43f5e",
    "text": "#e6f0fb",
    "text_dim": "#93a7c2",
    "text_faint": "#586c86",
}

# Background gradient stops for the animated backdrop.
BG_TOP = "#0a1f38"
BG_BOTTOM = "#04070f"

# Translucent surfaces so the animated background shows through cards/inputs.
SURFACE = "rgba(16, 41, 66, 0.72)"
SIDEBAR = "rgba(9, 20, 34, 0.86)"
INPUT_BG = "rgba(6, 15, 28, 0.55)"
SURFACE_SOLID = "#102942"

TIER_COLORS = ["#7dd3fc", "#38bdf8", "#0ea5e9", "#2563eb", "#6366f1", "#22d3ee", "#2dd4bf", "#14b8a6"]


def tier_color(tier_index):
    return TIER_COLORS[(tier_index - 1) % len(TIER_COLORS)]


BIOMES = ["Rainy", "Snowy", "Windy", "Hell", "Heaven", "Corruption", "Starfall", "Sand Storm", "Null",
          "Glitched", "Dreamspace", "Cyberspace", "Singularity", "Blazing Sun", "Incinerator"]

# Monochrome symbol fallbacks (shown before a biome's thumbnail loads).
BIOME_ICONS = {
    "Rainy": "☂", "Snowy": "❄", "Windy": "≈", "Hell": "♨", "Heaven": "☁",
    "Corruption": "☠", "Starfall": "★", "Sand Storm": "░", "Null": "∅",
    "Glitched": "▨", "Dreamspace": "☾", "Cyberspace": "▣", "Singularity": "◎",
    "Blazing Sun": "☀", "Incinerator": "✸",
}

DEFAULT_CHECKIN_SCREENSHOT_CONFIG = {
    "Glitched": {"enabled": True, "delay": 20},
    "Dreamspace": {"enabled": True, "delay": 20},
    "Cyberspace": {"enabled": True, "delay": 60},
}
DEFAULT_CHECKIN_DELAY = 30

DEFAULT_TIER_SEED = [
    ["Glitched", "Dreamspace", "Cyberspace"],
    ["Singularity"],
    ["Rainy", "Snowy", "Windy", "Hell", "Heaven", "Corruption", "Starfall", "Sand Storm", "Null"],
]

# ---------------------------------------------------------------------------
# Biome thumbnails (downloaded lazily on a background thread; the emoji above
# are the fallback shown until a thumbnail loads, or if it fails entirely).
# ---------------------------------------------------------------------------
_biome_bytes_cache = {}   # biome -> raw image bytes or None (safe off the main thread)
_biome_pixmap_cache = {}  # (biome, size) -> QPixmap (build only on the main/GUI thread)


def fetch_biome_bytes(biome_name):
    """Downloads a biome's thumbnail bytes. Thread-safe (pure network I/O).
    Retries a few times with a generous timeout before giving up, since some
    thumbnail hosts (e.g. postimg) can be slow to first-byte — a single short
    timeout would otherwise cache a permanent failure for the session and fall
    back to the emoji icon. Runs on a background thread, so waiting is fine."""
    if biome_name in _biome_bytes_cache:
        return _biome_bytes_cache[biome_name]
    url = biome_thumbnail_url(biome_name)
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=12)
            resp.raise_for_status()
            _biome_bytes_cache[biome_name] = resp.content
            return resp.content
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))
    print(f"[UI] Could not load thumbnail for {biome_name} after 3 attempts: {last_err}")
    _biome_bytes_cache[biome_name] = None
    return None


def get_biome_pixmap(biome_name, size=20):
    """Builds (and caches) a QPixmap from the downloaded bytes. GUI thread only."""
    key = (biome_name, size)
    if key in _biome_pixmap_cache:
        return _biome_pixmap_cache[key]
    data = _biome_bytes_cache.get(biome_name)
    if not data:
        return None
    pix = QtGui.QPixmap()
    if not pix.loadFromData(data):
        return None
    pix = pix.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    _biome_pixmap_cache[key] = pix
    return pix


fish_loop = fishing.FishSolBot()

SETTINGS_DIR = Path(os.getenv("LOCALAPPDATA")) / "FishSniper"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


def ensure_settings_dir():
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings_from_file():
    ensure_settings_dir()
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Settings Load Error] Could not load settings: {e}")
    return None


def save_settings_to_file(settings_data):
    ensure_settings_dir()
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_data, f, indent=2)
        print(f"[Settings Saved] Settings saved to {SETTINGS_FILE}")
    except Exception as e:
        print(f"[Settings Save Error] Could not save settings: {e}")


# ---------------------------------------------------------------------------
# Log line coloring — each line in the Dashboard log is colored based on which
# subsystem ("worker") printed it, read from its leading "[Tag]".
# ---------------------------------------------------------------------------
LOG_LINE_COLOR_GROUPS = [
    (("[Webhook Error]", "[Settings Save Error]", "[Settings Load Error]"), "#fb7185"),
    (("[Fishing Bot]", "[Pathing]", "[Auto-Sell]"), "#38bdf8"),
    (("[Discord Scanner]", "[Log Scanner]"), "#a78bfa"),
    (("[Roblox Launcher]", "[Resolver]"), "#f472b6"),
    (("[Webhook]",), "#2dd4bf"),
    (("[FishSniper]",), "#fbbf24"),
    (("[System]", "[UI]", "[Settings]", "[Settings Saved]"), "#9ca3af"),
]


def _color_for_log_line(line):
    stripped = line.lstrip()
    for prefixes, color in LOG_LINE_COLOR_GROUPS:
        if stripped.startswith(prefixes):
            return color
    return THEME["text"]


# ---------------------------------------------------------------------------
# Stylesheet (QSS) built from the palette above.
# ---------------------------------------------------------------------------
def build_qss():
    T = THEME
    return f"""
    QWidget {{
        color: {T['text']};
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 13px;
    }}
    QToolTip {{ background: {SURFACE_SOLID}; color: {T['text']}; border: 1px solid {T['card_border']}; }}

    /* Sidebar */
    QFrame#sidebar {{ background: {SIDEBAR}; border: none; border-right: 1px solid {T['card_border']}; }}
    QLabel#brand {{ font-size: 18px; font-weight: 800; letter-spacing: 1px; color: {T['text']}; }}
    QLabel#brandSub {{ color: {T['accent']}; font-size: 10px; letter-spacing: 3px; font-weight: 700; }}
    QLabel#activePath {{ color: {T['accent']}; font-size: 11px; font-weight: 600; }}

    QPushButton#nav {{
        background: transparent; color: {T['text_dim']};
        text-align: left; padding: 9px 14px;
        border: none; border-left: 3px solid transparent; border-radius: 9px;
        font-size: 13px; font-weight: 600;
    }}
    QPushButton#nav:hover {{ background: rgba(255,255,255,0.05); color: {T['text']}; }}
    QPushButton#nav:checked {{
        background: rgba(56,189,248,0.14); color: {T['accent']};
        border-left: 3px solid {T['accent']};
    }}

    /* Header */
    QLabel#pageTitle {{ font-size: 20px; font-weight: 800; }}
    QLabel#statusPill {{
        background: {INPUT_BG}; border: 1px solid {T['card_border']};
        border-radius: 12px; padding: 5px 12px; font-weight: 700; color: {T['text_dim']};
    }}

    /* Cards */
    QFrame#card {{
        background: {SURFACE}; border: 1px solid {T['card_border']}; border-radius: 16px;
    }}
    QFrame#innerCard {{
        background: {INPUT_BG}; border: 1px solid {T['card_border']}; border-radius: 12px;
    }}
    QLabel#h1 {{ font-size: 22px; font-weight: 800; }}
    QLabel#heading {{ font-size: 15px; font-weight: 800; }}
    QLabel#muted {{ color: {T['text_dim']}; }}
    QLabel#faint {{ color: {T['text_faint']}; font-size: 11px; }}
    QLabel#caption {{ color: {T['text_faint']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}

    /* Buttons (default = water blue) */
    QPushButton {{
        background: {T['accent']}; color: #06202e; border: none;
        padding: 8px 16px; border-radius: 10px; font-weight: 700;
    }}
    QPushButton:hover {{ background: {T['accent_hover']}; }}
    QPushButton:disabled {{ background: {T['card_border']}; color: {T['text_faint']}; }}
    QPushButton#start {{ background: {T['success']}; color: #04231d; font-size: 14px; }}
    QPushButton#start:hover {{ background: {T['success_hover']}; }}
    QPushButton#stop {{ background: {T['danger']}; color: #2a0710; font-size: 14px; }}
    QPushButton#stop:hover {{ background: {T['danger_hover']}; }}
    QPushButton#ghost {{ background: transparent; color: {T['accent']}; border: 1px solid {T['card_border']}; }}
    QPushButton#ghost:hover {{ background: rgba(56,189,248,0.10); border: 1px solid {T['accent']}; }}
    QPushButton#danger {{ background: {T['danger']}; color: #2a0710; }}
    QPushButton#danger:hover {{ background: {T['danger_hover']}; }}
    QPushButton#iconGhost {{
        background: transparent; color: {T['text_dim']}; border: none; padding: 2px; font-weight: 800;
    }}
    QPushButton#iconGhost:hover {{ color: {T['danger']}; background: rgba(251,113,133,0.12); }}

    /* Inputs */
    QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
        background: {INPUT_BG}; border: 1px solid {T['card_border']};
        border-radius: 9px; padding: 6px 8px;
        selection-background-color: {T['accent']}; selection-color: #06202e;
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {T['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {SURFACE_SOLID}; border: 1px solid {T['card_border']};
        selection-background-color: {T['accent']}; selection-color: #06202e; outline: none;
    }}

    /* Checkboxes (used in place of switches) */
    QCheckBox {{ spacing: 8px; color: {T['text']}; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px;
        border: 1px solid {T['card_border']}; background: {INPUT_BG}; }}
    QCheckBox::indicator:checked {{ background: {T['accent']}; border: 1px solid {T['accent']}; }}

    /* Tier lists (priority board) */
    QListWidget#tierList {{
        background: {INPUT_BG}; border: 1px solid {T['card_border']}; border-radius: 10px;
        padding: 4px;
    }}
    QListWidget#tierList::item {{
        background: {SURFACE_SOLID}; border: 1px solid {T['card_border']}; border-radius: 8px;
        padding: 7px 8px; margin: 3px; color: {T['text']};
    }}
    QListWidget#tierList::item:selected {{ border: 1px solid {T['accent']}; }}

    /* Scroll areas transparent so the backdrop shows through */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {T['card_border']}; border-radius: 5px; min-height: 26px; }}
    QScrollBar::handle:vertical:hover {{ background: {T['accent']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {T['card_border']}; border-radius: 5px; min-width: 26px; }}
    QScrollBar::handle:horizontal:hover {{ background: {T['accent']}; }}
    """


# ---------------------------------------------------------------------------
# Animated backdrop (adapted from MerchantSnipe's AnimatedBackground, blue).
# ---------------------------------------------------------------------------
class AnimatedBackground(QtWidgets.QWidget):
    def __init__(self, parent=None, bubble_count=46):
        super().__init__(parent)
        self._t = 0.0
        rng = random.Random(7)
        # (nx, ny, radius, base_alpha, rise_speed, phase, sway_amp)
        self._bubbles = [
            (rng.random(), rng.random(), rng.uniform(2.0, 7.0), rng.uniform(28, 82),
             rng.uniform(0.0016, 0.0060), rng.uniform(0, 6.28), rng.uniform(3.0, 12.0))
            for _ in range(bubble_count)
        ]
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._t += 0.05
        moved = []
        for (nx, ny, r, a, rise, ph, sway) in self._bubbles:
            ny -= rise  # bubbles drift upward
            if ny < -0.05:
                # respawn just below the bottom edge at a fresh horizontal spot
                ny = 1.05
                nx = random.random()
            moved.append((nx, ny, r, a, rise, ph, sway))
        self._bubbles = moved
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        grad = QtGui.QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QtGui.QColor(BG_TOP))
        grad.setColorAt(1.0, QtGui.QColor(BG_BOTTOM))
        p.fillRect(self.rect(), grad)

        # Soft "current" glows in the water-blue / teal accents.
        self._glow(p, w * 0.18, h * 0.12, max(w, h) * 0.5, QtGui.QColor(56, 189, 248, 34))
        self._glow(p, w * 0.88, h * 0.78, max(w, h) * 0.55, QtGui.QColor(45, 212, 191, 26))
        self._glow(p, w * 0.62, h * 0.30, max(w, h) * 0.35, QtGui.QColor(37, 99, 235, 22))

        # Rising bubbles: a translucent body, a brighter rim, and a small
        # sheen highlight so they read as air bubbles in water.
        for (nx, ny, r, base_a, _rise, ph, sway) in self._bubbles:
            x = nx * w + math.sin(self._t * 1.2 + ph) * sway
            y = ny * h
            center = QtCore.QPointF(x, y)
            a = int(base_a)

            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(150, 210, 240, int(a * 0.35)))
            p.drawEllipse(center, r, r)

            rim = QtGui.QPen(QtGui.QColor(200, 232, 250, min(255, int(a * 1.6))))
            rim.setWidthF(1.1)
            p.setPen(rim)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawEllipse(center, r, r)

            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, min(255, int(a * 1.2))))
            hl = max(0.8, r * 0.28)
            p.drawEllipse(QtCore.QPointF(x - r * 0.32, y - r * 0.32), hl, hl)
        p.end()

    @staticmethod
    def _glow(p, cx, cy, radius, color):
        g = QtGui.QRadialGradient(cx, cy, radius)
        g.setColorAt(0.0, color)
        transparent = QtGui.QColor(color)
        transparent.setAlpha(0)
        g.setColorAt(1.0, transparent)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)


# ---------------------------------------------------------------------------
# Status pill + log emitter helpers.
# ---------------------------------------------------------------------------
class StatusPill(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusPill")
        self.set_state("Stopped", THEME["text_faint"])

    def set_state(self, text, color):
        self.setText(f'<span style="color:{color}">●</span> {escape(text)}')


class _LogEmitter(QtCore.QObject):
    line = QtCore.Signal(str, str)  # (text, color)


class DualLogger(object):
    """Mirrors stdout/stderr into the Dashboard log view, colorizing each line
    by the subsystem that printed it. Writes can arrive from any thread, so the
    actual widget update is marshaled onto the GUI thread via a queued signal."""

    def __init__(self, emitter, original_stdout):
        self.emitter = emitter
        self.original_stdout = original_stdout
        self._buffer = ""

    def write(self, text):
        if self.original_stdout is not None:
            try:
                self.original_stdout.write(text)
                self.original_stdout.flush()
            except Exception:
                pass
        self._buffer += text
        *complete_lines, self._buffer = self._buffer.split("\n")
        for line in complete_lines:
            self.emitter.line.emit(line, _color_for_log_line(line + "\n"))

    def flush(self):
        if self.original_stdout is not None:
            try:
                self.original_stdout.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Priority board (native Qt drag-and-drop between tier columns).
# ---------------------------------------------------------------------------
class _BiomeList(QtWidgets.QListWidget):
    def __init__(self, board, key):
        super().__init__()
        self.board = board
        self.key = key
        self.setObjectName("tierList")
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSpacing(0)
        self.setFixedWidth(184)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.board.sync_from_lists()


class PriorityBoard(QtWidgets.QWidget):
    """Trello-style tier board. Tier 1 = highest priority. Biomes must be
    dragged out of "Unassigned" into a tier before the app will start."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.assignments = {}   # biome -> tier index (1-based)
        self.num_tiers = 3
        self.column_lists = {}  # key ("unassigned"/tier int) -> _BiomeList

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        hint = QtWidgets.QLabel("Drag biomes between columns — Tier 1 is the highest priority.")
        hint.setObjectName("muted")
        outer.addWidget(hint)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        outer.addWidget(self.scroll, 1)

        self.columns_host = QtWidgets.QWidget()
        self.columns_layout = QtWidgets.QHBoxLayout(self.columns_host)
        self.columns_layout.setContentsMargins(2, 2, 2, 2)
        self.columns_layout.setSpacing(10)
        self.columns_layout.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.scroll.setWidget(self.columns_host)

        self._build_columns()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _build_columns(self):
        self._clear_layout(self.columns_layout)
        self.column_lists = {}

        self._add_column("unassigned", "Unassigned", THEME["text_faint"], removable=False)
        for tier in range(1, self.num_tiers + 1):
            title = f"★ Tier {tier}" if tier == 1 else f"Tier {tier}"
            removable = (tier == self.num_tiers and self.num_tiers > 1)
            self._add_column(tier, title, tier_color(tier), removable=removable)

        # "Add tier" column.
        add_col = QtWidgets.QVBoxLayout()
        add_btn = QtWidgets.QPushButton("+")
        add_btn.setObjectName("ghost")
        add_btn.setFixedSize(44, 44)
        add_btn.setCursor(QtCore.Qt.PointingHandCursor)
        add_btn.clicked.connect(self.add_tier)
        add_col.addStretch(1)
        add_col.addWidget(add_btn, 0, QtCore.Qt.AlignHCenter)
        add_col.addStretch(1)
        wrap = QtWidgets.QWidget()
        wrap.setLayout(add_col)
        self.columns_layout.addWidget(wrap)

        self.render()

    def _add_column(self, key, title, color, removable):
        col = QtWidgets.QFrame()
        col.setObjectName("innerCard")
        col.setFixedWidth(196)
        v = QtWidgets.QVBoxLayout(col)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(f"color:{color}; font-weight:800;")
        header.addWidget(title_label)
        header.addStretch(1)
        if removable:
            rm = QtWidgets.QPushButton("✕")
            rm.setObjectName("iconGhost")
            rm.setFixedSize(22, 22)
            rm.setCursor(QtCore.Qt.PointingHandCursor)
            rm.clicked.connect(self.remove_last_tier)
            header.addWidget(rm)
        v.addLayout(header)

        accent = QtWidgets.QFrame()
        accent.setFixedHeight(2)
        accent.setStyleSheet(f"background:{color}; border:none; border-radius:1px;")
        v.addWidget(accent)

        lst = _BiomeList(self, key)
        v.addWidget(lst, 1)
        self.column_lists[key] = lst

        self.columns_layout.addWidget(col)

    def _make_item(self, biome):
        item = QtWidgets.QListWidgetItem(biome)
        item.setData(QtCore.Qt.UserRole, biome)
        pix = get_biome_pixmap(biome, size=18)
        if pix is not None:
            item.setIcon(QtGui.QIcon(pix))
        else:
            item.setText(f"{BIOME_ICONS.get(biome, '◇')}  {biome}")
        return item

    def render(self):
        for lst in self.column_lists.values():
            lst.clear()
        enabled = self.app.get_enabled_biomes()
        for biome in enabled:
            tier = self.assignments.get(biome)
            key = tier if (tier is not None and tier in self.column_lists) else "unassigned"
            self.column_lists[key].addItem(self._make_item(biome))

    def sync_from_lists(self):
        new_assignments = {}
        for key, lst in self.column_lists.items():
            for i in range(lst.count()):
                biome = lst.item(i).data(QtCore.Qt.UserRole)
                if key != "unassigned":
                    new_assignments[biome] = key
        self.assignments = new_assignments
        self.app.on_priority_changed()

    def add_tier(self):
        self.num_tiers += 1
        self._build_columns()

    def remove_last_tier(self):
        if self.num_tiers <= 1:
            return
        removed = self.num_tiers
        for biome, tier in list(self.assignments.items()):
            if tier == removed:
                del self.assignments[biome]
        self.num_tiers -= 1
        self._build_columns()

    def get_unassigned(self):
        enabled = self.app.get_enabled_biomes()
        return [b for b in enabled if b not in self.assignments]

    def load_data(self, assignments, num_tiers):
        self.assignments = dict(assignments) if assignments else {}
        self.num_tiers = max(1, num_tiers or 1)
        self.assignments = {b: t for b, t in self.assignments.items() if 1 <= t <= self.num_tiers}
        self._build_columns()

    def seed_defaults(self):
        for tier_idx, biomes in enumerate(DEFAULT_TIER_SEED, start=1):
            for biome in biomes:
                self.assignments[biome] = tier_idx
        self.num_tiers = max(self.num_tiers, len(DEFAULT_TIER_SEED))
        self._build_columns()


NAV_ITEMS = [
    ("dashboard", "▦ Dashboard"),
    ("settings", "⚙ Settings"),
    ("biomes", "◍ Biomes"),
    ("priority", "★ Priority"),
    ("servers", "▤ Servers"),
    ("shop", "◆ Shop"),
    ("auto_item", "◈ Auto Item"),
    ("gauntlet", "▲ Gauntlet"),
]


class FishSniperUI(QtWidgets.QMainWindow):
    # Queued signal used to run a callable on the GUI thread (see .after()).
    _invoke = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self._loading = False
        self.is_running = False
        self._registered_hotkey_handles = []

        self.setWindowTitle("FishSniper")
        self.resize(1120, 820)
        self.setMinimumSize(940, 640)

        # GUI-thread marshaling: any thread can call self.after(0, fn).
        self._invoke.connect(self._run_on_ui)

        # Link global instances.
        scanner.fish_loop = fish_loop
        fish_loop.set_path_change_callback(self._on_active_path_changed)
        fish_loop.set_failsafe_callback(self._on_fishing_failsafe)
        fish_loop.set_buy_callback(self._on_item_purchased)
        fish_loop.set_session_end_callback(scanner.handle_fish_loop_session_ending)
        fish_loop.set_gauntlet_swap_finished_callback(scanner.handle_gauntlet_swap_finished)
        scanner.set_biome_time_updated_callback(self._on_biome_time_updated)

        root = AnimatedBackground()
        self.setCentralWidget(root)
        h = QtWidgets.QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())
        h.addWidget(self._build_content(), 1)

        # Log emitter (stdout/stderr redirect).
        self._log_emitter = _LogEmitter()
        self._log_emitter.line.connect(self._append_log)
        sys.stdout = DualLogger(self._log_emitter, sys.__stdout__)
        sys.stderr = DualLogger(self._log_emitter, sys.__stderr__)

        self._go("dashboard")

        # Load thumbnails in the background.
        threading.Thread(target=self._preload_thumbnails, daemon=True).start()

        self.load_settings()
        self.initialize_scanner()

        threading.Thread(target=fish_loop.start, daemon=True).start()
        threading.Thread(target=scanner.start_scanner, daemon=True).start()

    # ------------------------------------------------------------------
    # GUI-thread marshaling (drop-in replacement for tk's widget.after)
    # ------------------------------------------------------------------
    def after(self, ms, fn=None):
        if fn is None:
            return
        if ms and ms > 0:
            self._invoke.emit(lambda: QtCore.QTimer.singleShot(int(ms), fn))
        else:
            self._invoke.emit(fn)

    def _run_on_ui(self, fn):
        try:
            fn()
        except Exception as e:
            print(f"[UI] Error in marshaled callback: {e}")

    # ------------------------------------------------------------------
    # Small builder helpers
    # ------------------------------------------------------------------
    def _card(self):
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        shadow = QtWidgets.QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setColor(QtGui.QColor(0, 0, 0, 150))
        shadow.setOffset(0, 6)
        card.setGraphicsEffect(shadow)
        return card

    def _heading(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("heading")
        return lbl

    def _muted(self, text, wrap=False):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("muted")
        if wrap:
            lbl.setWordWrap(True)
        return lbl

    def _faint(self, text, wrap=False):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("faint")
        if wrap:
            lbl.setWordWrap(True)
        return lbl

    def _line_edit(self, placeholder="", text=""):
        e = QtWidgets.QLineEdit()
        if placeholder:
            e.setPlaceholderText(placeholder)
        if text:
            e.setText(text)
        return e

    def _combo(self, values):
        c = QtWidgets.QComboBox()
        c.addItems(values)
        c.setCursor(QtCore.Qt.PointingHandCursor)
        return c

    def _scroll_page(self):
        """Returns (page_widget, content_layout) where content lives in a
        vertical scroll area."""
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(content)
        cl.setContentsMargins(2, 2, 8, 2)
        cl.setSpacing(10)
        scroll.setWidget(content)
        pv.addWidget(scroll)
        return page, cl

    # ------------------------------------------------------------------
    # Chrome: sidebar + content
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        bar = QtWidgets.QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(232)
        v = QtWidgets.QVBoxLayout(bar)
        v.setContentsMargins(16, 20, 16, 16)
        v.setSpacing(8)

        brand = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel("🎣")
        logo.setStyleSheet("font-size: 26px;")
        text_col = QtWidgets.QVBoxLayout()
        text_col.setSpacing(0)
        name = QtWidgets.QLabel("FishSniper")
        name.setObjectName("brand")
        sub = QtWidgets.QLabel("AUTO FISHER")
        sub.setObjectName("brandSub")
        text_col.addWidget(name)
        text_col.addWidget(sub)
        brand.addWidget(logo)
        brand.addSpacing(8)
        brand.addLayout(text_col)
        brand.addStretch(1)
        v.addLayout(brand)
        v.addSpacing(14)

        self.universal_button = QtWidgets.QPushButton("▶  Start FishSniper")
        self.universal_button.setObjectName("start")
        self.universal_button.setMinimumHeight(42)
        self.universal_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.universal_button.clicked.connect(self.toggle_universal)
        v.addWidget(self.universal_button)

        self.status_pill = StatusPill()
        v.addWidget(self.status_pill)

        self.active_path_label = QtWidgets.QLabel("Active Path: Path 1")
        self.active_path_label.setObjectName("activePath")
        v.addWidget(self.active_path_label)
        v.addSpacing(10)

        self.nav = {}
        for key, label in NAV_ITEMS:
            b = QtWidgets.QPushButton(label)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._go(k))
            self.nav[key] = b
            v.addWidget(b)

        v.addStretch(1)

        self.save_bottom = QtWidgets.QPushButton("Save Settings")
        self.save_bottom.setObjectName("ghost")
        self.save_bottom.setMinimumHeight(38)
        self.save_bottom.setCursor(QtCore.Qt.PointingHandCursor)
        self.save_bottom.clicked.connect(lambda: self.save_settings())
        v.addWidget(self.save_bottom)
        return bar

    def _build_content(self):
        wrap = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(wrap)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        self.page_title = QtWidgets.QLabel("Dashboard")
        self.page_title.setObjectName("pageTitle")
        header.addWidget(self.page_title)
        header.addStretch(1)
        v.addLayout(header)

        self.stack = QtWidgets.QStackedWidget()
        self.pages = {
            "dashboard": self._build_dashboard_page(),
            "settings": self._build_settings_page(),
            "biomes": self._build_biomes_page(),
            "priority": self._build_priority_page(),
            "servers": self._build_servers_page(),
            "shop": self._build_shop_page(),
            "auto_item": self._build_auto_item_page(),
            "gauntlet": self._build_gauntlet_page(),
        }
        for key, _ in NAV_ITEMS:
            self.stack.addWidget(self.pages[key])
        v.addWidget(self.stack, 1)
        return wrap

    def _go(self, key):
        for k, b in self.nav.items():
            b.setChecked(k == key)
        self.stack.setCurrentWidget(self.pages[key])
        self.page_title.setText(dict(NAV_ITEMS)[key].split(" ", 1)[-1])

    # ------------------------------------------------------------------
    # Dashboard page (quick setup + logs)
    # ------------------------------------------------------------------
    def _build_dashboard_page(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)

        setup = self._card()
        sv = QtWidgets.QVBoxLayout(setup)
        sv.setContentsMargins(20, 16, 20, 16)
        sv.setSpacing(8)
        sv.addWidget(self._faint("FISHING SETUP"))

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        grid.addWidget(self._muted("Screen Resolution"), 0, 0)
        self.res_dropdown = self._combo(["1080p", "1920x1200", "1440p", "1366x768"])
        self.res_dropdown.currentTextChanged.connect(lambda _v: self.save_settings())
        grid.addWidget(self.res_dropdown, 1, 0)

        grid.addWidget(self._muted("Pathing Mode"), 0, 1)
        self.speed_dropdown = self._combo(["Vip Pathing", "Non Vip Pathing"])
        self.speed_dropdown.currentTextChanged.connect(lambda _v: self.save_settings())
        grid.addWidget(self.speed_dropdown, 1, 1)

        grid.addWidget(self._muted("Starting Path"), 0, 2)
        self.path_dropdown = self._combo([f"Path {n}" for n in range(1, 13)])
        self.path_dropdown.currentTextChanged.connect(self.on_path_selection)
        grid.addWidget(self.path_dropdown, 1, 2)

        grid.addWidget(self._muted("Max Fish"), 2, 0)
        self.max_catches_entry = self._line_edit("1", "1")
        self.max_catches_entry.editingFinished.connect(lambda: self.save_settings())
        grid.addWidget(self.max_catches_entry, 3, 0)

        grid.addWidget(self._muted("Sell Loops (56 = all)"), 2, 1)
        self.sell_loops_entry = self._line_edit("56", "56")
        self.sell_loops_entry.editingFinished.connect(lambda: self.save_settings())
        grid.addWidget(self.sell_loops_entry, 3, 1)
        grid.setColumnStretch(2, 1)

        sv.addLayout(grid)
        v.addWidget(setup)

        logs = self._card()
        lv = QtWidgets.QVBoxLayout(logs)
        lv.setContentsMargins(20, 16, 20, 16)
        lv.setSpacing(8)
        lv.addWidget(self._heading("Application Logs"))
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        self.log_view.setStyleSheet('font-family: "Cascadia Mono","Consolas",monospace; font-size: 12px;')
        lv.addWidget(self.log_view, 1)
        v.addWidget(logs, 1)
        return page

    def _append_log(self, text, color):
        self.log_view.moveCursor(QtGui.QTextCursor.End)
        safe = escape(text).replace(" ", "&nbsp;")
        self.log_view.insertHtml(f'<span style="color:{color};">{safe}</span><br>')
        self.log_view.moveCursor(QtGui.QTextCursor.End)

    # ------------------------------------------------------------------
    # Settings page
    # ------------------------------------------------------------------
    def _build_settings_page(self):
        page, cl = self._scroll_page()

        cl.addWidget(self._heading("Credentials & Integrations"))
        cred = self._card()
        cv = QtWidgets.QVBoxLayout(cred)
        cv.setContentsMargins(18, 16, 18, 16)
        cv.setSpacing(6)

        cv.addWidget(self._muted("Roblox Cookie (.ROBLOSECURITY)"))
        self.rb_token_entry = self._line_edit("Enter Roblox Cookie")
        self.rb_token_entry.setEchoMode(QtWidgets.QLineEdit.Password)
        cv.addWidget(self.rb_token_entry)

        cv.addWidget(self._muted("Discord User Token"))
        self.ds_token_entry = self._line_edit("Enter Discord Token")
        self.ds_token_entry.setEchoMode(QtWidgets.QLineEdit.Password)
        cv.addWidget(self.ds_token_entry)

        cv.addWidget(self._muted("Discord Webhook URL (Optional)"))
        wh_row = QtWidgets.QHBoxLayout()
        self.ds_webhook_entry = self._line_edit("Enter Discord Webhook URL")
        wh_row.addWidget(self.ds_webhook_entry, 1)
        self.webhook_test_btn = QtWidgets.QPushButton("Test")
        self.webhook_test_btn.setObjectName("ghost")
        self.webhook_test_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.webhook_test_btn.clicked.connect(self.test_webhook)
        wh_row.addWidget(self.webhook_test_btn)
        cv.addLayout(wh_row)

        cv.addWidget(self._muted("Discord User ID to Ping (Optional)"))
        self.ds_ping_user_id_entry = self._line_edit(
            "Pinged on Glitched / Dreamspace / Cyberspace joins")
        cv.addWidget(self.ds_ping_user_id_entry)
        cl.addWidget(cred)

        cl.addWidget(self._heading("Fishing Behavior"))
        beh = self._card()
        bv = QtWidgets.QVBoxLayout(beh)
        bv.setContentsMargins(18, 16, 18, 16)
        bv.setSpacing(6)
        self.sell_on_start_switch = QtWidgets.QCheckBox("Sell inventory when FishSniper starts")
        self.sell_on_start_switch.setChecked(True)
        bv.addWidget(self.sell_on_start_switch)
        bv.addWidget(self._faint(
            "Sells off any existing inventory on the first server joined after pressing Start, "
            "before fishing begins. Later server joins in the same run are unaffected.", wrap=True))

        afk_row = QtWidgets.QHBoxLayout()
        afk_row.addWidget(QtWidgets.QLabel("Anti-AFK interval while not fishing (sec):"))
        self.anti_afk_interval_entry = self._line_edit("300", "300")
        self.anti_afk_interval_entry.setFixedWidth(80)
        afk_row.addWidget(self.anti_afk_interval_entry)
        afk_row.addStretch(1)
        bv.addLayout(afk_row)
        bv.addWidget(self._faint(
            "How often the bot focuses the window and presses space while sitting in a biome that "
            "has fishing turned off (see the Biomes tab). Default is 300 seconds (5 minutes).", wrap=True))
        cl.addWidget(beh)

        cl.addWidget(self._heading("Hotkeys"))
        hk = self._card()
        hv = QtWidgets.QVBoxLayout(hk)
        hv.setContentsMargins(18, 16, 18, 16)
        hv.setSpacing(6)

        s_row = QtWidgets.QHBoxLayout()
        s_row.addWidget(QtWidgets.QLabel("Start hotkey:"))
        self.start_hotkey_entry = self._line_edit("", DEFAULT_START_HOTKEY)
        self.start_hotkey_entry.setFixedWidth(120)
        self.start_hotkey_entry.editingFinished.connect(self.apply_hotkeys)
        s_row.addWidget(self.start_hotkey_entry)
        s_row.addStretch(1)
        hv.addLayout(s_row)

        t_row = QtWidgets.QHBoxLayout()
        t_row.addWidget(QtWidgets.QLabel("Stop hotkey: "))
        self.stop_hotkey_entry = self._line_edit("", DEFAULT_STOP_HOTKEY)
        self.stop_hotkey_entry.setFixedWidth(120)
        self.stop_hotkey_entry.editingFinished.connect(self.apply_hotkeys)
        t_row.addWidget(self.stop_hotkey_entry)
        t_row.addStretch(1)
        hv.addLayout(t_row)

        self.hotkey_status_label = self._faint("", wrap=True)
        hv.addWidget(self.hotkey_status_label)
        hv.addWidget(self._faint(
            "Work globally, even while Roblox is focused. Use names like 'f1' or combos like "
            "'ctrl+alt+s'. Applies immediately and is saved with your other settings.", wrap=True))
        cl.addWidget(hk)
        cl.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # Biomes page
    # ------------------------------------------------------------------
    def _build_biomes_page(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(self._heading("Select Biomes to Hunt"))
        header.addStretch(1)
        reset_btn = QtWidgets.QPushButton("Reset All Biome Times")
        reset_btn.setObjectName("danger")
        reset_btn.setCursor(QtCore.Qt.PointingHandCursor)
        reset_btn.clicked.connect(self.reset_all_biome_times)
        header.addWidget(reset_btn)
        v.addLayout(header)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(content)
        grid.setContentsMargins(2, 2, 8, 2)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setAlignment(QtCore.Qt.AlignTop)
        scroll.setWidget(content)
        v.addWidget(scroll, 1)

        self.biome_switches = {}
        self.biome_icon_labels = {}
        self.fish_switches = {}
        self.checkin_switches = {}
        self.checkin_delay_entries = {}
        self.checkin_flaps = {}
        self.checkin_expand_btns = {}
        self.biome_time_labels = {}

        for i, biome in enumerate(BIOMES):
            row, col = divmod(i, 3)
            card = QtWidgets.QFrame()
            card.setObjectName("innerCard")
            cv = QtWidgets.QVBoxLayout(card)
            cv.setContentsMargins(12, 10, 12, 10)
            cv.setSpacing(6)

            top = QtWidgets.QHBoxLayout()
            icon_label = QtWidgets.QLabel(BIOME_ICONS.get(biome, "◇"))
            icon_label.setStyleSheet("font-size: 15px;")
            icon_label.setFixedWidth(24)
            self.biome_icon_labels[biome] = icon_label
            top.addWidget(icon_label)

            switch = QtWidgets.QCheckBox(biome)
            switch.toggled.connect(self.on_biome_toggle)
            self.biome_switches[biome] = switch
            top.addWidget(switch)
            top.addStretch(1)

            expand_btn = QtWidgets.QPushButton("⌄")
            expand_btn.setObjectName("iconGhost")
            expand_btn.setFixedSize(24, 24)
            expand_btn.setCursor(QtCore.Qt.PointingHandCursor)
            expand_btn.clicked.connect(lambda _=False, b=biome: self.toggle_checkin_flap(b))
            self.checkin_expand_btns[biome] = expand_btn
            top.addWidget(expand_btn)
            cv.addLayout(top)

            default_config = DEFAULT_CHECKIN_SCREENSHOT_CONFIG.get(
                biome, {"enabled": False, "delay": DEFAULT_CHECKIN_DELAY})

            flap = QtWidgets.QFrame()
            flap.setObjectName("innerCard")
            fv = QtWidgets.QVBoxLayout(flap)
            fv.setContentsMargins(10, 8, 10, 8)
            fv.setSpacing(4)

            fish_switch = QtWidgets.QCheckBox("Fish This Biome")
            fish_switch.setChecked(True)
            self.fish_switches[biome] = fish_switch
            fv.addWidget(fish_switch)
            fv.addWidget(self._faint(
                "When off, the bot just sits in this biome (with anti-AFK) instead of fishing.", wrap=True))

            checkin_switch = QtWidgets.QCheckBox("Check-in Screenshot")
            checkin_switch.setChecked(bool(default_config["enabled"]))
            self.checkin_switches[biome] = checkin_switch
            fv.addWidget(checkin_switch)

            delay_row = QtWidgets.QHBoxLayout()
            delay_row.addWidget(self._faint("Delay (sec):"))
            delay_entry = self._line_edit("", str(default_config["delay"]))
            delay_entry.setFixedWidth(60)
            delay_row.addWidget(delay_entry)
            delay_row.addStretch(1)
            self.checkin_delay_entries[biome] = delay_entry
            fv.addLayout(delay_row)
            fv.addWidget(self._faint(
                "Sends a follow-up screenshot this many seconds after the biome is confirmed "
                "(skipped if it ends first).", wrap=True))

            time_label = self._muted("Time in Biome: 0:00")
            fv.addWidget(time_label)
            self.biome_time_labels[biome] = time_label

            flap.setVisible(False)
            self.checkin_flaps[biome] = flap
            cv.addWidget(flap)

            grid.addWidget(card, row, col)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        return page

    def toggle_checkin_flap(self, biome):
        flap = self.checkin_flaps[biome]
        expanded = flap.isVisible()
        flap.setVisible(not expanded)
        self.checkin_expand_btns[biome].setText("⌄" if expanded else "⌃")

    def get_checkin_screenshot_settings(self):
        settings = {}
        for biome, switch in self.checkin_switches.items():
            entry = self.checkin_delay_entries.get(biome)
            try:
                delay = max(0, int((entry.text() if entry else "").strip() or 0))
            except ValueError:
                delay = 0
            settings[biome] = {"enabled": switch.isChecked(), "delay": delay}
        return settings

    def get_fishing_enabled_settings(self):
        return {biome: switch.isChecked() for biome, switch in self.fish_switches.items()}

    def refresh_biome_time_labels(self):
        for biome, label in self.biome_time_labels.items():
            total_seconds = scanner.biome_time_totals.get(biome, 0)
            label.setText(f"Time in Biome: {format_biome_duration(total_seconds)}")

    def _on_biome_time_updated(self, biome, new_total_seconds):
        def handle():
            label = self.biome_time_labels.get(biome)
            if label:
                label.setText(f"Time in Biome: {format_biome_duration(new_total_seconds)}")
            self.save_settings()
        self.after(0, handle)

    def reset_all_biome_times(self):
        confirmed = QtWidgets.QMessageBox.question(
            self, "Reset Biome Times",
            "This will permanently reset the recorded time for every biome back to zero.\n\n"
            "This cannot be undone. Continue?",
        ) == QtWidgets.QMessageBox.Yes
        if not confirmed:
            return
        scanner.reset_biome_time_totals()
        self.refresh_biome_time_labels()
        self.save_settings()

    # ------------------------------------------------------------------
    # Priority page
    # ------------------------------------------------------------------
    def _build_priority_page(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addWidget(self._heading("Priority Tiers"))
        self.priority_board = PriorityBoard(self)
        v.addWidget(self.priority_board, 1)
        return page

    # ------------------------------------------------------------------
    # Servers page
    # ------------------------------------------------------------------
    def _build_servers_page(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(self._heading("Discord Server Configuration"))

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        container = QtWidgets.QWidget()
        self.guild_layout = QtWidgets.QVBoxLayout(container)
        self.guild_layout.setContentsMargins(2, 2, 8, 2)
        self.guild_layout.setSpacing(8)
        self.guild_layout.setAlignment(QtCore.Qt.AlignTop)
        scroll.setWidget(container)
        v.addWidget(scroll, 1)

        self.guild_entries = []

        self.add_guild_btn = QtWidgets.QPushButton("+ Add Server")
        self.add_guild_btn.setObjectName("ghost")
        self.add_guild_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.add_guild_btn.clicked.connect(self.add_guild_entry)
        v.addWidget(self.add_guild_btn, 0, QtCore.Qt.AlignLeft)

        self.add_guild_entry()
        return page

    # ------------------------------------------------------------------
    # Shop page
    # ------------------------------------------------------------------
    def _build_shop_page(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(self._heading("Auto-Buy"))
        header.addStretch(1)
        self.buy_master_switch = QtWidgets.QCheckBox("Enable Auto-Buy")
        header.addWidget(self.buy_master_switch)
        v.addLayout(header)

        v.addWidget(self._faint(
            "Runs right after any sell loop, while the merchant is still open — nothing runs at all if "
            "no enabled item is due. The shop restocks daily at 8 PM ET; an item already bought since the "
            "last restock won't be bought again until the next one.", wrap=True))

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(content)
        grid.setContentsMargins(2, 2, 8, 2)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setAlignment(QtCore.Qt.AlignTop)
        scroll.setWidget(content)
        v.addWidget(scroll, 1)

        self.buy_switches = {}
        self.buy_qty_entries = {}
        self.buy_status_labels = {}

        for i, item in enumerate(fishing.BUY_ITEMS):
            row, col = divmod(i, 3)
            name = item["name"]
            max_qty = item["max_qty"]

            card = QtWidgets.QFrame()
            card.setObjectName("innerCard")
            cv = QtWidgets.QVBoxLayout(card)
            cv.setContentsMargins(12, 10, 12, 10)
            cv.setSpacing(6)

            switch = QtWidgets.QCheckBox(name)
            self.buy_switches[name] = switch
            cv.addWidget(switch)

            qty_row = QtWidgets.QHBoxLayout()
            qty_row.addWidget(self._faint(f"Qty (max {max_qty}):"))
            qty_entry = self._line_edit("", "0")
            qty_entry.setFixedWidth(70)
            qty_entry.editingFinished.connect(lambda n=name, m=max_qty: self._clamp_buy_quantity(n, m))
            self.buy_qty_entries[name] = qty_entry
            qty_row.addWidget(qty_entry)
            qty_row.addStretch(1)
            cv.addLayout(qty_row)

            status_label = self._faint("Not bought yet")
            self.buy_status_labels[name] = status_label
            cv.addWidget(status_label)

            grid.addWidget(card, row, col)
        for c in range(3):
            grid.setColumnStretch(c, 1)

        self.refresh_buy_status_labels()
        return page

    def _clamp_buy_quantity(self, item_name, max_qty):
        entry = self.buy_qty_entries.get(item_name)
        if not entry:
            return
        try:
            value = int(entry.text().strip() or "0")
        except ValueError:
            value = 0
        entry.setText(str(max(0, min(value, max_qty))))

    def get_buy_settings(self):
        item_settings = {}
        for item in fishing.BUY_ITEMS:
            name = item["name"]
            switch = self.buy_switches.get(name)
            entry = self.buy_qty_entries.get(name)
            try:
                qty = int((entry.text() if entry else "0").strip() or 0)
            except ValueError:
                qty = 0
            qty = max(0, min(qty, item["max_qty"]))
            item_settings[name] = {"enabled": switch.isChecked() if switch else False, "quantity": qty}
        master_enabled = self.buy_master_switch.isChecked()
        return master_enabled, item_settings

    def refresh_buy_status_labels(self):
        boundary = current_shop_restock_boundary()
        for name, label in self.buy_status_labels.items():
            last = fish_loop.last_purchased.get(name)
            if last is not None and last >= boundary:
                stamp = last.astimezone(SHOP_RESTOCK_TZ).strftime("%I:%M %p").lstrip("0")
                label.setText(f"Bought today ({stamp} ET)")
                label.setStyleSheet(f"color:{THEME['success']}; font-size:11px;")
            else:
                label.setText("Not bought yet")
                label.setStyleSheet(f"color:{THEME['text_faint']}; font-size:11px;")

    def _on_item_purchased(self, item_name, quantity):
        def handle():
            self.refresh_buy_status_labels()
            webhook_url = self.ds_webhook_entry.text().strip()
            if not webhook_url or not webhook_url.startswith("http"):
                return

            def send():
                from webhook import Webhook
                Webhook(webhook_url).send_item_purchased(item_name, quantity)
            threading.Thread(target=send, daemon=True).start()
        self.after(0, handle)

    # ------------------------------------------------------------------
    # Auto Item page
    # ------------------------------------------------------------------
    def _build_auto_item_page(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(self._heading("Auto Item"))
        header.addStretch(1)
        self.auto_item_count_label = self._faint(f"0/{MAX_AUTO_ITEMS}")
        header.addWidget(self.auto_item_count_label)
        add_btn = QtWidgets.QPushButton("+ Add Item")
        add_btn.setObjectName("ghost")
        add_btn.setCursor(QtCore.Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: self.add_auto_item_row())
        header.addWidget(add_btn)
        v.addLayout(header)

        v.addWidget(self._faint(
            "Uses each enabled item on any server whose biome matches one of its checked boxes — "
            "right after the join screenshot, before any pathing begins.", wrap=True))

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        container = QtWidgets.QWidget()
        self.auto_item_layout = QtWidgets.QVBoxLayout(container)
        self.auto_item_layout.setContentsMargins(2, 2, 8, 2)
        self.auto_item_layout.setSpacing(8)
        self.auto_item_layout.setAlignment(QtCore.Qt.AlignTop)
        scroll.setWidget(container)
        v.addWidget(scroll, 1)

        self.auto_item_rows = []
        return page

    def _update_auto_item_count_label(self):
        self.auto_item_count_label.setText(f"{len(self.auto_item_rows)}/{MAX_AUTO_ITEMS}")

    def add_auto_item_row(self, config=None):
        if len(self.auto_item_rows) >= MAX_AUTO_ITEMS:
            QtWidgets.QMessageBox.warning(self, "Auto Item Limit",
                                          f"You can have at most {MAX_AUTO_ITEMS} auto-items.")
            return
        config = config or {}

        card = QtWidgets.QFrame()
        card.setObjectName("innerCard")
        cv = QtWidgets.QVBoxLayout(card)
        cv.setContentsMargins(12, 10, 12, 10)
        cv.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        enabled_switch = QtWidgets.QCheckBox()
        enabled_switch.setChecked(bool(config.get("enabled")))
        top.addWidget(enabled_switch)

        name_entry = self._line_edit("Item name", config.get("name", ""))
        top.addWidget(name_entry, 1)

        top.addWidget(self._faint("Qty:"))
        qty_entry = self._line_edit("", str(config.get("quantity", 1)))
        qty_entry.setFixedWidth(60)
        top.addWidget(qty_entry)

        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setObjectName("iconGhost")
        remove_btn.setFixedSize(28, 28)
        remove_btn.setCursor(QtCore.Qt.PointingHandCursor)
        top.addWidget(remove_btn)
        cv.addLayout(top)

        biome_grid = QtWidgets.QGridLayout()
        biome_grid.setHorizontalSpacing(10)
        biome_grid.setVerticalSpacing(2)
        biome_checks = {}
        configured = set(config.get("biomes", []))
        per_row = 7
        for i, biome in enumerate(BIOMES):
            check = QtWidgets.QCheckBox(biome)
            check.setChecked(biome in configured)
            biome_grid.addWidget(check, i // per_row, i % per_row)
            biome_checks[biome] = check
        cv.addLayout(biome_grid)

        row_data = {
            "frame": card,
            "enabled_switch": enabled_switch,
            "name_entry": name_entry,
            "qty_entry": qty_entry,
            "biome_checks": biome_checks,
        }
        remove_btn.clicked.connect(lambda: self.remove_auto_item_row(row_data))
        self.auto_item_layout.addWidget(card)
        self.auto_item_rows.append(row_data)
        self._update_auto_item_count_label()

    def remove_auto_item_row(self, row_data):
        self.auto_item_rows = [r for r in self.auto_item_rows if r is not row_data]
        row_data["frame"].setParent(None)
        row_data["frame"].deleteLater()
        self._update_auto_item_count_label()

    def get_auto_item_settings(self):
        items = []
        for row in self.auto_item_rows:
            name = row["name_entry"].text().strip()
            if not name:
                continue
            try:
                qty = max(1, int(row["qty_entry"].text().strip() or "1"))
            except ValueError:
                qty = 1
            biomes = [b for b, c in row["biome_checks"].items() if c.isChecked()]
            items.append({"enabled": row["enabled_switch"].isChecked(), "name": name,
                          "quantity": qty, "biomes": biomes})
        return items

    # ------------------------------------------------------------------
    # Gauntlet page
    # ------------------------------------------------------------------
    def _build_gauntlet_page(self):
        page, cl = self._scroll_page()

        header = QtWidgets.QHBoxLayout()
        header.addWidget(self._heading("Gauntlet"))
        header.addStretch(1)
        self.gauntlet_count_label = self._faint(f"0/{MAX_GAUNTLETS}")
        header.addWidget(self.gauntlet_count_label)
        add_btn = QtWidgets.QPushButton("+ Add Device")
        add_btn.setObjectName("ghost")
        add_btn.setCursor(QtCore.Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: self.add_gauntlet_row())
        header.addWidget(add_btn)
        cl.addLayout(header)

        cl.addWidget(self._faint(
            "Swaps to the mapped device the moment a biome is confirmed — safely between casts, never "
            "mid-bite or mid-minigame. Once a swap starts it always finishes, even through a disconnect "
            "or a higher-priority biome; only Stop can cut it short.", wrap=True))

        default_row = QtWidgets.QFrame()
        default_row.setObjectName("innerCard")
        dr = QtWidgets.QHBoxLayout(default_row)
        dr.setContentsMargins(12, 8, 12, 8)
        dr.addWidget(QtWidgets.QLabel("Default device (used for any biome without its own pick below):"))
        self.gauntlet_default_dropdown = self._combo(["None"])
        self.gauntlet_default_dropdown.setFixedWidth(160)
        dr.addWidget(self.gauntlet_default_dropdown)
        dr.addStretch(1)
        cl.addWidget(default_row)

        rows_host = QtWidgets.QWidget()
        self.gauntlet_layout = QtWidgets.QVBoxLayout(rows_host)
        self.gauntlet_layout.setContentsMargins(0, 0, 0, 0)
        self.gauntlet_layout.setSpacing(8)
        cl.addWidget(rows_host)
        self.gauntlet_rows = []

        cl.addWidget(self._heading("Per-Biome Device"))
        biome_grid = QtWidgets.QGridLayout()
        biome_grid.setHorizontalSpacing(10)
        biome_grid.setVerticalSpacing(6)
        self.gauntlet_biome_dropdowns = {}
        for i, biome in enumerate(BIOMES):
            row, col = divmod(i, 3)
            cell = QtWidgets.QFrame()
            cell.setObjectName("innerCard")
            ch = QtWidgets.QHBoxLayout(cell)
            ch.setContentsMargins(10, 6, 10, 6)
            ch.addWidget(QtWidgets.QLabel(biome))
            ch.addStretch(1)
            dropdown = self._combo(["Default"])
            dropdown.setFixedWidth(120)
            ch.addWidget(dropdown)
            self.gauntlet_biome_dropdowns[biome] = dropdown
            biome_grid.addWidget(cell, row, col)
        for c in range(3):
            biome_grid.setColumnStretch(c, 1)
        cl.addLayout(biome_grid)
        cl.addStretch(1)
        return page

    def _update_gauntlet_count_label(self):
        self.gauntlet_count_label.setText(f"{len(self.gauntlet_rows)}/{MAX_GAUNTLETS}")

    def add_gauntlet_row(self, config=None):
        if len(self.gauntlet_rows) >= MAX_GAUNTLETS:
            QtWidgets.QMessageBox.warning(self, "Gauntlet Limit",
                                          f"You can have at most {MAX_GAUNTLETS} gauntlet devices.")
            return
        config = config or {}

        card = QtWidgets.QFrame()
        card.setObjectName("innerCard")
        cv = QtWidgets.QVBoxLayout(card)
        cv.setContentsMargins(12, 10, 12, 10)
        cv.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        name_entry = self._line_edit("Device name (for your own organization)", config.get("name", ""))
        name_entry.editingFinished.connect(self.refresh_gauntlet_dropdown_options)
        top.addWidget(name_entry, 1)
        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setObjectName("iconGhost")
        remove_btn.setFixedSize(28, 28)
        remove_btn.setCursor(QtCore.Qt.PointingHandCursor)
        top.addWidget(remove_btn)
        cv.addLayout(top)

        item_pos = config.get("item_pos", (0, 0))
        button_pos = config.get("gauntlet_button_pos", (0, 0))
        coord_row = QtWidgets.QHBoxLayout()
        coord_row.addWidget(self._faint("Item position:"))
        item_x_entry = self._line_edit("", str(item_pos[0]))
        item_x_entry.setFixedWidth(54)
        item_y_entry = self._line_edit("", str(item_pos[1]))
        item_y_entry.setFixedWidth(54)
        coord_row.addWidget(item_x_entry)
        coord_row.addWidget(item_y_entry)
        coord_row.addSpacing(14)
        coord_row.addWidget(self._faint("Gauntlet button:"))
        button_x_entry = self._line_edit("", str(button_pos[0]))
        button_x_entry.setFixedWidth(54)
        button_y_entry = self._line_edit("", str(button_pos[1]))
        button_y_entry.setFixedWidth(54)
        coord_row.addWidget(button_x_entry)
        coord_row.addWidget(button_y_entry)
        coord_row.addStretch(1)
        cv.addLayout(coord_row)

        scroll_row = QtWidgets.QHBoxLayout()
        scroll_check = QtWidgets.QCheckBox("Needs scroll")
        scroll_check.setChecked(bool(config.get("needs_scroll")))
        scroll_row.addWidget(scroll_check)
        scroll_row.addSpacing(12)
        scroll_row.addWidget(self._faint("Scroll ticks (single wheel clicks):"))
        scroll_ticks_entry = self._line_edit("", str(config.get("scroll_ticks", 0)))
        scroll_ticks_entry.setFixedWidth(50)
        scroll_row.addWidget(scroll_ticks_entry)
        scroll_row.addStretch(1)
        cv.addLayout(scroll_row)

        row_data = {
            "frame": card,
            "name_entry": name_entry,
            "item_x_entry": item_x_entry,
            "item_y_entry": item_y_entry,
            "button_x_entry": button_x_entry,
            "button_y_entry": button_y_entry,
            "scroll_check": scroll_check,
            "scroll_ticks_entry": scroll_ticks_entry,
        }
        remove_btn.clicked.connect(lambda: self.remove_gauntlet_row(row_data))
        self.gauntlet_layout.addWidget(card)
        self.gauntlet_rows.append(row_data)
        self._update_gauntlet_count_label()
        self.refresh_gauntlet_dropdown_options()

    def remove_gauntlet_row(self, row_data):
        self.gauntlet_rows = [r for r in self.gauntlet_rows if r is not row_data]
        row_data["frame"].setParent(None)
        row_data["frame"].deleteLater()
        self._update_gauntlet_count_label()
        self.refresh_gauntlet_dropdown_options()

    def _gauntlet_names(self):
        return [r["name_entry"].text().strip() for r in self.gauntlet_rows if r["name_entry"].text().strip()]

    def _reset_combo(self, combo, values, keep):
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        combo.setCurrentText(keep if keep in values else values[0])
        combo.blockSignals(False)

    def refresh_gauntlet_dropdown_options(self):
        names = self._gauntlet_names()
        default_values = ["None"] + names
        self._reset_combo(self.gauntlet_default_dropdown, default_values,
                          self.gauntlet_default_dropdown.currentText())
        biome_values = ["Default"] + names
        for dropdown in self.gauntlet_biome_dropdowns.values():
            self._reset_combo(dropdown, biome_values, dropdown.currentText())

    def get_gauntlet_settings(self):
        gauntlets = {}
        for row in self.gauntlet_rows:
            name = row["name_entry"].text().strip()
            if not name:
                continue
            try:
                item_pos = (int(row["item_x_entry"].text().strip() or 0),
                            int(row["item_y_entry"].text().strip() or 0))
            except ValueError:
                item_pos = (0, 0)
            try:
                button_pos = (int(row["button_x_entry"].text().strip() or 0),
                              int(row["button_y_entry"].text().strip() or 0))
            except ValueError:
                button_pos = (0, 0)
            try:
                scroll_ticks = max(0, int(row["scroll_ticks_entry"].text().strip() or 0))
            except ValueError:
                scroll_ticks = 0
            gauntlets[name] = {
                "item_pos": item_pos,
                "gauntlet_button_pos": button_pos,
                "needs_scroll": row["scroll_check"].isChecked(),
                "scroll_ticks": scroll_ticks,
            }

        default_name = self.gauntlet_default_dropdown.currentText()
        if default_name == "None" or default_name not in gauntlets:
            default_name = None

        biome_map = {}
        for biome, dropdown in self.gauntlet_biome_dropdowns.items():
            value = dropdown.currentText()
            if value != "Default" and value in gauntlets:
                biome_map[biome] = value
        return gauntlets, default_name, biome_map

    # ------------------------------------------------------------------
    # Behavior
    # ------------------------------------------------------------------
    def get_enabled_biomes(self):
        return [b for b in BIOMES if self.biome_switches[b].isChecked()]

    def on_biome_toggle(self):
        if hasattr(self, "priority_board"):
            self.priority_board.render()

    def on_path_selection(self, value):
        try:
            fish_loop.select_path(int(value.rsplit(" ", 1)[1]) - 1)
        except (IndexError, ValueError):
            return

    def _on_active_path_changed(self, path_name):
        def update_ui():
            self.active_path_label.setText(f"Active Path: {path_name}")
            self.path_dropdown.blockSignals(True)
            self.path_dropdown.setCurrentText(path_name)
            self.path_dropdown.blockSignals(False)
        self.after(0, update_ui)

    def _on_fishing_failsafe(self, failsafe_count, switched_path, screenshot_bytes, triggered_sell):
        def handle():
            webhook_url = self.ds_webhook_entry.text().strip()
            if not webhook_url or not webhook_url.startswith("http"):
                return

            def send():
                from webhook import Webhook
                Webhook(webhook_url).send_failsafe_triggered(
                    failsafe_count, switched_path, screenshot_bytes, triggered_sell)
            threading.Thread(target=send, daemon=True).start()
        self.after(0, handle)

    def on_priority_changed(self):
        pass

    def _preload_thumbnails(self):
        for biome in BIOMES:
            fetch_biome_bytes(biome)
            self.after(0, lambda b=biome: self._on_thumbnail_loaded(b))

    def _on_thumbnail_loaded(self, biome):
        pix = get_biome_pixmap(biome, size=20)
        if pix is not None and biome in self.biome_icon_labels:
            self.biome_icon_labels[biome].setPixmap(pix)
        if hasattr(self, "priority_board"):
            self.priority_board.render()

    def validate_priority_assignments(self):
        unassigned = self.priority_board.get_unassigned()
        if unassigned:
            QtWidgets.QMessageBox.critical(
                self, "Priority Not Set",
                "The following enabled biomes need a priority tier before FishSniper can start:\n\n"
                + "\n".join(f"• {b}" for b in unassigned)
                + "\n\nGo to the Priority tab and drag them into a tier.")
            print(f"[FishSniper] Cannot start — unassigned biomes: {', '.join(unassigned)}")
            return False
        return True

    def toggle_universal(self):
        if not self.is_running:
            self.start_fishsniper()
        else:
            self.stop_fishsniper()

    def _set_universal_running(self, running):
        self.universal_button.setObjectName("stop" if running else "start")
        self.universal_button.setText("■  Stop FishSniper" if running else "▶  Start FishSniper")
        self.universal_button.style().unpolish(self.universal_button)
        self.universal_button.style().polish(self.universal_button)

    def start_fishsniper(self):
        if self.is_running:
            return
        if not self.validate_priority_assignments():
            return

        from webhook import Webhook
        webhook_url = self.ds_webhook_entry.text().strip()

        self.is_running = True
        self._set_universal_running(True)
        self.update_status("Scanning for biomes...")

        self.save_settings()
        if self.sell_on_start_switch.isChecked():
            fish_loop.request_startup_sell()
        scanner.toggle_on()
        print("[FishSniper] Started - Scanner active, waiting for biome detection")
        Webhook(webhook_url).send_app_started()

    def stop_fishsniper(self):
        if not self.is_running:
            return

        from webhook import Webhook
        webhook_url = self.ds_webhook_entry.text().strip()

        self.is_running = False
        self._set_universal_running(False)
        self.update_status("Stopped")

        fish_loop.request_user_stop()
        scanner.toggle_off()
        fish_loop.toggle_off()
        print("[FishSniper] Stopped - All systems paused")
        Webhook(webhook_url).send_app_stopped()

    def apply_hotkeys(self):
        if keyboard is None:
            self.hotkey_status_label.setText(
                "Hotkeys unavailable — the 'keyboard' package failed to load.")
            self.hotkey_status_label.setStyleSheet(f"color:{THEME['danger']}; font-size:11px;")
            return

        for hotkey_handle in self._registered_hotkey_handles:
            try:
                keyboard.remove_hotkey(hotkey_handle)
            except (KeyError, ValueError):
                pass
        self._registered_hotkey_handles = []

        start_key = self.start_hotkey_entry.text().strip() or DEFAULT_START_HOTKEY
        stop_key = self.stop_hotkey_entry.text().strip() or DEFAULT_STOP_HOTKEY

        errors = []
        try:
            handle = keyboard.add_hotkey(start_key, lambda: self.after(0, self.start_fishsniper))
            self._registered_hotkey_handles.append(handle)
        except Exception as e:
            errors.append(f"start hotkey '{start_key}': {e}")

        try:
            handle = keyboard.add_hotkey(stop_key, lambda: self.after(0, self.stop_fishsniper))
            self._registered_hotkey_handles.append(handle)
        except Exception as e:
            errors.append(f"stop hotkey '{stop_key}': {e}")

        if errors:
            self.hotkey_status_label.setText("Could not register — " + "; ".join(errors))
            self.hotkey_status_label.setStyleSheet(f"color:{THEME['danger']}; font-size:11px;")
            print(f"[UI] Hotkey registration error(s): {'; '.join(errors)}")
        else:
            self.hotkey_status_label.setText(f"Active — Start: '{start_key}'   Stop: '{stop_key}'")
            self.hotkey_status_label.setStyleSheet(f"color:{THEME['success']}; font-size:11px;")
            print(f"[UI] Hotkeys registered — Start: '{start_key}', Stop: '{stop_key}'")

    def update_status(self, new_status):
        """Thread-safe: marshals onto the GUI thread (scanner calls this from
        its background thread)."""
        def apply():
            color = THEME["text_faint"] if new_status.strip().lower() == "stopped" else THEME["accent"]
            self.status_pill.set_state(new_status, color)
        self.after(0, apply)

    def test_webhook(self):
        webhook_url = self.ds_webhook_entry.text().strip()
        if not webhook_url or not webhook_url.startswith("http"):
            QtWidgets.QMessageBox.critical(self, "Webhook Test", "Enter a valid Discord webhook URL first.")
            return

        self.webhook_test_btn.setEnabled(False)
        self.webhook_test_btn.setText("Testing...")

        def run_test():
            from webhook import Webhook
            success = Webhook(webhook_url).send_test()
            self.after(0, lambda: self._on_webhook_test_done(success))
        threading.Thread(target=run_test, daemon=True).start()

    def _on_webhook_test_done(self, success):
        self.webhook_test_btn.setEnabled(True)
        self.webhook_test_btn.setText("Test")
        if success:
            QtWidgets.QMessageBox.information(self, "Webhook Test",
                                              "Test message sent! Check your Discord channel.")
        else:
            QtWidgets.QMessageBox.critical(
                self, "Webhook Test",
                "Failed to send the test message. Double-check the URL and your connection—see the "
                "Dashboard logs for details.")

    # Legacy no-op shims (kept for external callers).
    def start_sniping(self):
        if not self.is_running:
            self.toggle_universal()

    def pause_sniping(self):
        if self.is_running:
            self.toggle_universal()

    def start_scanner(self):
        pass

    def stop_scanner(self):
        pass

    # ------------------------------------------------------------------
    # Servers management
    # ------------------------------------------------------------------
    def add_guild_entry(self):
        card = QtWidgets.QFrame()
        card.setObjectName("innerCard")
        cv = QtWidgets.QVBoxLayout(card)
        cv.setContentsMargins(12, 10, 12, 10)
        cv.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        name_entry = self._line_edit("Server Name (Optional)")
        top.addWidget(name_entry, 1)
        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setObjectName("iconGhost")
        remove_btn.setFixedSize(26, 26)
        remove_btn.setCursor(QtCore.Qt.PointingHandCursor)
        top.addWidget(remove_btn)
        cv.addLayout(top)

        guild_entry = self._line_edit("Server ID")
        channels_entry = self._line_edit("Channel IDs (comma-separated)")
        categories_entry = self._line_edit("Category IDs (comma-separated)")
        cv.addWidget(guild_entry)
        cv.addWidget(channels_entry)
        cv.addWidget(categories_entry)

        # Per-server biome filter: a collapsible dropdown listing the biomes
        # currently enabled in the Biomes tab. Unchecking one stops this server
        # from triggering joins for it. Biomes disabled globally never appear,
        # so only biomes selected to hunt can be toggled here. Rebuilt each
        # time it's opened so it reflects the current enabled set.
        biome_header = QtWidgets.QHBoxLayout()
        biome_header.addWidget(self._faint("Biomes to hunt for this server"))
        biome_header.addStretch(1)
        biome_expand_btn = QtWidgets.QPushButton("⌄")
        biome_expand_btn.setObjectName("iconGhost")
        biome_expand_btn.setFixedSize(24, 24)
        biome_expand_btn.setCursor(QtCore.Qt.PointingHandCursor)
        biome_header.addWidget(biome_expand_btn)
        cv.addLayout(biome_header)

        biome_flap = QtWidgets.QFrame()
        biome_flap.setObjectName("innerCard")
        biome_flap_layout = QtWidgets.QGridLayout(biome_flap)
        biome_flap_layout.setContentsMargins(10, 8, 10, 8)
        biome_flap_layout.setHorizontalSpacing(14)
        biome_flap_layout.setVerticalSpacing(2)
        biome_flap.setVisible(False)
        cv.addWidget(biome_flap)

        entry = {
            "frame": card,
            "name": name_entry,
            "guild": guild_entry,
            "channels": channels_entry,
            "categories": categories_entry,
            # Biome titles this server should NOT hunt. Empty = hunt every
            # globally-enabled biome (the default / backward-compatible state).
            "biome_excluded": set(),
            "biome_flap": biome_flap,
            "biome_flap_layout": biome_flap_layout,
            "biome_expand_btn": biome_expand_btn,
            "biome_expanded": False,
            "biome_checks": {},
        }
        biome_expand_btn.clicked.connect(lambda _=False, e=entry: self._toggle_server_biome_flap(e))
        remove_btn.clicked.connect(lambda: self.remove_guild_entry(entry))
        self.guild_layout.addWidget(card)
        self.guild_entries.append(entry)

    def _toggle_server_biome_flap(self, entry):
        expanded = entry["biome_expanded"]
        if not expanded:
            self._rebuild_server_biome_checks(entry)
        entry["biome_flap"].setVisible(not expanded)
        entry["biome_expand_btn"].setText("⌄" if expanded else "⌃")
        entry["biome_expanded"] = not expanded

    def _rebuild_server_biome_checks(self, entry):
        layout = entry["biome_flap_layout"]
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        entry["biome_checks"] = {}

        enabled = self.get_enabled_biomes()
        if not enabled:
            layout.addWidget(self._faint("No biomes selected in the Biomes tab yet."), 0, 0, 1, 2)
            return
        for i, biome in enumerate(enabled):
            cb = QtWidgets.QCheckBox(biome)
            cb.setChecked(biome not in entry["biome_excluded"])
            cb.toggled.connect(lambda checked, b=biome, e=entry: self._on_server_biome_toggled(e, b, checked))
            layout.addWidget(cb, i // 2, i % 2)
            entry["biome_checks"][biome] = cb

    def _on_server_biome_toggled(self, entry, biome, checked):
        if checked:
            entry["biome_excluded"].discard(biome)
        else:
            entry["biome_excluded"].add(biome)

    def remove_guild_entry(self, entry=None):
        if len(self.guild_entries) <= 1:
            print("[UI] Cannot remove the last server entry")
            return
        if entry is None:
            entry = self.guild_entries[-1]
        if entry not in self.guild_entries:
            return
        self.guild_entries.remove(entry)
        entry["frame"].setParent(None)
        entry["frame"].deleteLater()

    def _collect_guild_mappings(self):
        guild_mappings = []
        for entry in self.guild_entries:
            server_name = entry["name"].text().strip()
            guild_id = entry["guild"].text().strip()
            channels_str = entry["channels"].text().strip()
            categories_str = entry["categories"].text().strip()
            if guild_id:
                channel_ids = [ch.strip() for ch in channels_str.split(',') if ch.strip()]
                category_ids = [cat.strip() for cat in categories_str.split(',') if cat.strip()]
                guild_mappings.append({
                    "server_name": server_name,
                    "guild_id": guild_id,
                    "channel_ids": channel_ids,
                    "category_ids": category_ids,
                    "excluded_biomes": sorted(entry.get("biome_excluded", set())),
                })
        return guild_mappings

    # ------------------------------------------------------------------
    # Settings load / save
    # ------------------------------------------------------------------
    def load_settings(self):
        settings = load_settings_from_file()
        if not settings:
            print("[Settings] No saved settings found, using defaults")
            self.priority_board.seed_defaults()
            self.apply_hotkeys()
            return

        self._loading = True
        try:
            if 'resolution' in settings:
                self.res_dropdown.setCurrentText(settings['resolution'])

            if 'speed' in settings:
                saved_speed = settings['speed']
                if saved_speed == "VIP":
                    saved_speed = "Vip Pathing"
                elif saved_speed == "Normal":
                    saved_speed = "Non Vip Pathing"
                self.speed_dropdown.setCurrentText(saved_speed)

            selected_path = settings.get('selected_path', 1)
            try:
                selected_path = min(12, max(1, int(selected_path)))
            except (TypeError, ValueError):
                selected_path = 1
            self.path_dropdown.setCurrentText(f"Path {selected_path}")
            fish_loop.select_path(selected_path - 1)

            if 'rb_token' in settings:
                self.rb_token_entry.setText(settings['rb_token'])
            if 'ds_token' in settings:
                self.ds_token_entry.setText(settings['ds_token'])
            if 'webhook_url' in settings:
                self.ds_webhook_entry.setText(settings['webhook_url'])
            if 'discord_ping_user_id' in settings:
                self.ds_ping_user_id_entry.setText(settings['discord_ping_user_id'])
            if 'max_catches' in settings:
                self.max_catches_entry.setText(str(settings['max_catches']))
            if 'sell_loops' in settings:
                self.sell_loops_entry.setText(str(settings['sell_loops']))

            self.sell_on_start_switch.setChecked(bool(settings.get('sell_on_start', True)))

            anti_afk_interval = settings.get('anti_afk_interval', 300)
            self.anti_afk_interval_entry.setText(str(anti_afk_interval))
            fish_loop.set_anti_afk_interval(anti_afk_interval)

            self.start_hotkey_entry.setText(settings.get('start_hotkey', DEFAULT_START_HOTKEY))
            self.stop_hotkey_entry.setText(settings.get('stop_hotkey', DEFAULT_STOP_HOTKEY))
            self.apply_hotkeys()

            self.buy_master_switch.setChecked(bool(settings.get('buy_master_enabled', False)))

            saved_buy_items = settings.get('buy_item_settings', {})
            for item in fishing.BUY_ITEMS:
                name = item["name"]
                saved = saved_buy_items.get(name, {})
                switch = self.buy_switches.get(name)
                entry = self.buy_qty_entries.get(name)
                if switch is not None:
                    switch.setChecked(bool(saved.get("enabled")))
                if entry is not None:
                    qty = max(0, min(int(saved.get("quantity", 0) or 0), item["max_qty"]))
                    entry.setText(str(qty))

            last_purchased = {}
            for name, iso_str in settings.get('last_purchased', {}).items():
                try:
                    last_purchased[name] = datetime.fromisoformat(iso_str)
                except (TypeError, ValueError):
                    continue
            fish_loop.set_last_purchased(last_purchased)

            buy_master_enabled, buy_item_settings = self.get_buy_settings()
            fish_loop.set_buy_settings(buy_master_enabled, buy_item_settings)
            self.refresh_buy_status_labels()

            saved_biome_times = settings.get('biome_time_totals', {})
            scanner.biome_time_totals = {
                biome: float(seconds) for biome, seconds in saved_biome_times.items()
            }
            self.refresh_biome_time_labels()

            for row in list(self.auto_item_rows):
                row["frame"].setParent(None)
                row["frame"].deleteLater()
            self.auto_item_rows = []
            for item_config in settings.get('auto_items', []):
                self.add_auto_item_row(item_config)
            self._update_auto_item_count_label()

            for row in list(self.gauntlet_rows):
                row["frame"].setParent(None)
                row["frame"].deleteLater()
            self.gauntlet_rows = []
            for gauntlet_name, gauntlet_config in settings.get('gauntlets', {}).items():
                row_config = dict(gauntlet_config)
                row_config["name"] = gauntlet_name
                self.add_gauntlet_row(row_config)
            self._update_gauntlet_count_label()

            gauntlet_names = self._gauntlet_names()
            self.refresh_gauntlet_dropdown_options()
            saved_gauntlet_default = settings.get('gauntlet_default')
            self.gauntlet_default_dropdown.setCurrentText(
                saved_gauntlet_default if saved_gauntlet_default in gauntlet_names else "None")
            saved_gauntlet_biome_map = settings.get('gauntlet_biome_map', {})
            for biome, dropdown in self.gauntlet_biome_dropdowns.items():
                mapped = saved_gauntlet_biome_map.get(biome)
                dropdown.setCurrentText(mapped if mapped in gauntlet_names else "Default")

            gauntlets, gauntlet_default, gauntlet_biome_map = self.get_gauntlet_settings()
            fish_loop.set_gauntlet_settings(gauntlets, gauntlet_default, gauntlet_biome_map)

            if 'selected_biomes' in settings:
                for biome in BIOMES:
                    self.biome_switches[biome].setChecked(biome in settings['selected_biomes'])

            saved_fishing_enabled = settings.get('fishing_enabled_biomes', {})
            for biome, switch in self.fish_switches.items():
                switch.setChecked(bool(saved_fishing_enabled.get(biome, True)))

            saved_checkin = settings.get('checkin_screenshots', {})
            for biome, switch in self.checkin_switches.items():
                default_config = DEFAULT_CHECKIN_SCREENSHOT_CONFIG.get(
                    biome, {"enabled": False, "delay": DEFAULT_CHECKIN_DELAY})
                saved = saved_checkin.get(biome, default_config)
                if isinstance(saved, dict):
                    enabled = saved.get("enabled", default_config["enabled"])
                    delay = saved.get("delay", default_config["delay"])
                else:
                    enabled = bool(saved)
                    delay = default_config["delay"]
                switch.setChecked(bool(enabled))
                delay_entry = self.checkin_delay_entries.get(biome)
                if delay_entry is not None:
                    delay_entry.setText(str(delay))

            if settings.get('guild_mappings'):
                while len(self.guild_entries) > 1:
                    self.remove_guild_entry()
                for i, mapping in enumerate(settings['guild_mappings']):
                    if i >= len(self.guild_entries):
                        self.add_guild_entry()
                    entry = self.guild_entries[i]
                    entry["name"].setText(mapping.get('server_name', mapping.get('name', '')))
                    entry["guild"].setText(str(mapping.get('guild_id', '')))
                    entry["channels"].setText(', '.join(map(str, mapping.get('channel_ids', []))))
                    entry["categories"].setText(', '.join(map(str, mapping.get('category_ids', []))))
                    entry["biome_excluded"] = set(mapping.get('excluded_biomes', []))

            biome_priority_levels = settings.get('biome_priority_levels')
            num_tiers = settings.get('num_tiers', 3)
            if biome_priority_levels:
                self.priority_board.load_data(biome_priority_levels, num_tiers)
            else:
                self.priority_board.seed_defaults()

            print("[Settings] Settings loaded successfully from LOCALAPPDATA")
        except Exception as e:
            print(f"[Settings Load Error] Error loading settings: {e}")
            self.priority_board.render()
            self.apply_hotkeys()
        finally:
            self._loading = False

    def save_settings(self, value=None):
        if self._loading:
            return
        rb_token = self.rb_token_entry.text().strip()
        ds_token = self.ds_token_entry.text().strip()
        webhook_url = self.ds_webhook_entry.text().strip()
        ping_user_id = self.ds_ping_user_id_entry.text().strip()
        res = self.res_dropdown.currentText()
        speed = self.speed_dropdown.currentText()

        try:
            max_catches = int(self.max_catches_entry.text().strip() or "1")
        except ValueError:
            max_catches = 1
        try:
            sell_loops = int(self.sell_loops_entry.text().strip() or "56")
        except ValueError:
            sell_loops = 56
        try:
            selected_path = int(self.path_dropdown.currentText().rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            selected_path = 1
        try:
            anti_afk_interval = max(1, int(self.anti_afk_interval_entry.text().strip() or "300"))
        except ValueError:
            anti_afk_interval = 300

        fish_loop.update_coordinates(res, speed, max_catches, sell_loops)
        fish_loop.select_path(selected_path - 1)
        fish_loop.set_anti_afk_interval(anti_afk_interval)
        self.apply_hotkeys()

        buy_master_enabled, buy_item_settings = self.get_buy_settings()
        fish_loop.set_buy_settings(buy_master_enabled, buy_item_settings)

        selected_biomes = self.get_enabled_biomes()
        guild_mappings = self._collect_guild_mappings()
        biome_priority_levels = dict(self.priority_board.assignments)
        num_tiers = self.priority_board.num_tiers
        checkin_screenshots = self.get_checkin_screenshot_settings()
        fishing_enabled_biomes = self.get_fishing_enabled_settings()
        auto_items = self.get_auto_item_settings()

        gauntlets, gauntlet_default, gauntlet_biome_map = self.get_gauntlet_settings()
        fish_loop.set_gauntlet_settings(gauntlets, gauntlet_default, gauntlet_biome_map)

        scanner.load_settings(ds_token, selected_biomes, rb_token, guild_mappings, webhook_url, self,
                               biome_priority_levels, discord_ping_user_id=ping_user_id,
                               checkin_screenshots=checkin_screenshots,
                               fishing_enabled_biomes=fishing_enabled_biomes,
                               auto_items=auto_items)

        last_purchased_serialized = {
            name: dt.isoformat() for name, dt in fish_loop.last_purchased.items()
        }

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
            'checkin_screenshots': checkin_screenshots,
            'sell_on_start': self.sell_on_start_switch.isChecked(),
            'fishing_enabled_biomes': fishing_enabled_biomes,
            'anti_afk_interval': anti_afk_interval,
            'start_hotkey': self.start_hotkey_entry.text().strip() or DEFAULT_START_HOTKEY,
            'stop_hotkey': self.stop_hotkey_entry.text().strip() or DEFAULT_STOP_HOTKEY,
            'buy_master_enabled': buy_master_enabled,
            'buy_item_settings': buy_item_settings,
            'last_purchased': last_purchased_serialized,
            'biome_time_totals': scanner.biome_time_totals,
            'auto_items': auto_items,
            'gauntlets': gauntlets,
            'gauntlet_default': gauntlet_default,
            'gauntlet_biome_map': gauntlet_biome_map,
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
        rb_token = self.rb_token_entry.text().strip()
        ds_token = self.ds_token_entry.text().strip()
        webhook_url = self.ds_webhook_entry.text().strip()
        ping_user_id = self.ds_ping_user_id_entry.text().strip()
        selected_biomes = self.get_enabled_biomes()

        guild_mappings = self._collect_guild_mappings()
        biome_priority_levels = dict(self.priority_board.assignments)
        checkin_screenshots = self.get_checkin_screenshot_settings()
        fishing_enabled_biomes = self.get_fishing_enabled_settings()
        auto_items = self.get_auto_item_settings()

        gauntlets, gauntlet_default, gauntlet_biome_map = self.get_gauntlet_settings()
        fish_loop.set_gauntlet_settings(gauntlets, gauntlet_default, gauntlet_biome_map)

        scanner.load_settings(ds_token, selected_biomes, rb_token, guild_mappings, webhook_url, self,
                               biome_priority_levels, discord_ping_user_id=ping_user_id,
                               checkin_screenshots=checkin_screenshots,
                               fishing_enabled_biomes=fishing_enabled_biomes,
                               auto_items=auto_items)
