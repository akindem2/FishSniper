import io
import time
import pyautogui
import pydirectinput
from PIL import Image, ImageGrab
import win32gui
import win32con
import ctypes

# Force Windows to run the script at 100% Display Scaling.
# If a user's Windows display settings are at 125% or 150%, PyAutoGUI will click the wrong spots.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

COORDS = {
    "1080p": {
        "FISHING": {
            "CAST_ROD": (862, 843),
            "BITE_INDICATOR": (1176, 836),
            "BAR_COLOR": (955, 767),
            "CLAIM_FISH": (1113, 342),
            "MINIGAME_REGION": (757, 762, 404, 20) 
        },
        "MERCHANT": {
            "CAMERA_SETUP_1": (47, 467),
            "CAMERA_SETUP_2": (382, 140),
            "OPEN_MERCHANT_1": (956, 803),
            "OPEN_MERCHANT_2": (956, 938),
            "SELECT_FISH": (828, 404),
            "SELL_ALL_ON": (680, 804),
            "SELL_ALL_OFF": (512, 804),
            "CONFIRM_SELL": (801, 626),
            "CLOSE_MERCHANT": (1458, 266)

        },
        "START": {
                "START_BUTTON_POS": (251, 1000),
        },
    },
    "1440p": {
        "FISHING": {
            "CAST_ROD": (1161, 1124),
            "BITE_INDICATOR": (1536, 1119),
            "BAR_COLOR": (1261, 1033),
            "CLAIM_FISH": (1457, 491),
            "MINIGAME_REGION": (1043, 1033, 476, 25)
        },
        "MERCHANT": {
            "CAMERA_SETUP_1": (52, 621),
            "CAMERA_SETUP_2": (525, 158),
            "OPEN_MERCHANT_1": (1308, 1073),
            "OPEN_MERCHANT_2": (1289, 1264),
            "SELECT_FISH": (1117, 550),
            "SELL_ALL_ON": (904, 1080),
            "SELL_ALL_OFF": (700, 1078),
            "CONFIRM_SELL": (1002, 831),
            "CLOSE_MERCHANT": (1958, 361)
        },
        "START": {
                "START_BUTTON_POS": (410, 1340),
        }
    },
    "1366x768": {
        "FISHING": {
            "CAST_ROD": (603, 597),
            "BITE_INDICATOR": (866, 593),
            "BAR_COLOR": (674, 533),
            "CLAIM_FISH": (829, 218),
            "MINIGAME_REGION": (513, 531, 343, 18)
        },
        "MERCHANT": {
            "CAMERA_SETUP_1": (26, 325),
            "CAMERA_SETUP_2": (273, 106),
            "OPEN_MERCHANT_1": (682, 563),
            "OPEN_MERCHANT_2": (682, 667),
            "SELECT_FISH": (586, 287),
            "SELL_ALL_ON": (486, 570),
            "SELL_ALL_OFF": (365, 570),
            "CONFIRM_SELL": (573, 447),
            "CLOSE_MERCHANT": (1050, 197)
        },
        "START": {
                "START_BUTTON_POS": (221, 714)
        }
    }
}

PATHING_TIMINGS = {
    "VIP": {
        "ALIGNMENT1": 4.15,
        "ALIGNMENT1.5":0.8,
        "ALIGNMENT2": 0.6,
        "ALIGNMENT3": 0.4,
        "MERCHANT1": 0.25,
        "MERCHANT2": 0.7,
        "MERCHANT3": 1.3,
        "MERCHANT4": 0.2,
        "MERCHANT5": 0.4,
        "MERCHANT6": 1.45,
        "SPOT1": 0.1,
        "SPOT2": 2.0,
    },
    "NORMAL": {
        "ALIGNMENT1": 5.0,
        "ALIGNMENT1.5":0.96,
        "ALIGNMENT2": 0.72,
        "ALIGNMENT3": 0.48,
        "MERCHANT1": 0.3,
        "MERCHANT2": 0.96,
        "MERCHANT3": 1.44,
        "MERCHANT4": 0.24,
        "MERCHANT5": 0.5,
        "MERCHANT6": 1.56,
        "SPOT1": 0.12,
        "SPOT2": 2.4,
    }
}

# Paths run only after the shared route reaches the merchant. Path 1 mirrors
# the old merchant-to-spot route. Replace Paths 2-5 with custom action lists.
# Supported actions: ("wait", seconds), ("hold", key, seconds), ("press", key),
# ("click", coordinate_attribute), ("click_at", x, y), and ("scroll", amount).
def _default_post_merchant_path(timing):
    return [
        ("click", "CLOSE_MERCHANT"),
        ("hold", "d", timing["SPOT1"]),
        ("wait", 0.1),
        ("hold", "w", timing["SPOT2"]),
    ]


POST_MERCHANT_PATHS = {
    "VIP": {
        "Path 1": _default_post_merchant_path(PATHING_TIMINGS["VIP"]),
        "Path 2": [
            ("click", "CLOSE_MERCHANT"),
            ("hold", "d", 0.1),
            ("hold", "w", 1.2),
            ("hold", "a", 0.7),
            ("hold", "w", 0.6),
        ],
        "Path 3": [
            ("click", "CLOSE_MERCHANT"),
            ("hold", "d", 0.1),
            ("hold", "w", 1.2),
            ("hold", "a", 0.7),
            ("hold", "w", 0.6),
            ("hold", "a", 0.3),
            ("hold", "w", 0.3),
        ],
        "Path 4": [
            ("click", "CLOSE_MERCHANT"),
            ("hold", "d", 0.1),
            ("hold", "w", 1.2),
            ("hold", "a", 0.7),
            ("hold", "w", 0.6),
            ("hold", "a", 0.3),
            ("hold", "w", 0.3),
            ("hold", "a", 0.7),
            ("hold", "w", 0.4),
        ],
        "Path 5": [
            ("click", "CLOSE_MERCHANT"),
            ("hold", "d", 0.1),
            ("hold", "w", 1.2),
            ("hold", "a", 0.7),
            ("hold", "w", 0.6),
            ("hold", "a", 0.3),
            ("hold", "w", 0.3),
            ("hold", "a", 0.7),
            ("hold", "w", 0.4),
            ("hold", "a", 0.8),
        ],
    },

    "NORMAL": {
        "Path 1": _default_post_merchant_path(PATHING_TIMINGS["NORMAL"]),
        "Path 2": [
            ("click", "CLOSE_MERCHANT"),
            ("hold", "d", 0.12),
            ("hold", "w", 1.44),
            ("hold", "a", 0.84),
            ("hold", "w", 0.72),
        ],
        "Path 3": [
            ("click", "CLOSE_MERCHANT"),
            ("hold", "d", 0.12),
            ("hold", "w", 1.44),
            ("hold", "a", 0.84),
            ("hold", "w", 0.72),
            ("hold", "a", 0.36),
            ("hold", "w", 0.36),
        ],
        "Path 4": [
            ("click", "CLOSE_MERCHANT"),
            ("hold", "d", 0.12),
            ("hold", "w", 1.44),
            ("hold", "a", 0.84),
            ("hold", "w", 0.72),
            ("hold", "a", 0.36),
            ("hold", "w", 0.36),
            ("hold", "a", 0.84),
            ("hold", "w", 0.48),
        ],
        "Path 5": [
            ("click", "CLOSE_MERCHANT"),
            ("hold", "d", 0.12),
            ("hold", "w", 1.44),
            ("hold", "a", 0.84),
            ("hold", "w", 0.72),
            ("hold", "a", 0.36),
            ("hold", "w", 0.36),
            ("hold", "a", 0.84),
            ("hold", "w", 0.48),
            ("hold", "a", 0.96),
        ],
    }
}

TOLERANCE = 10
MAX_WAIT_FOR_BITE = 35
MAX_MINIGAME_TIME = 10
MAX_WAIT_FOR_CAST = 35

# User-configurable start button detection values.
START_BUTTON_COLOR = (127, 255, 147)
START_BUTTON_COLOR_TOLERANCE = 5
START_BUTTON_WAIT_TIMEOUT = 120
WAIT_FOR_START_BUTTON_TIME = 15

class FishSolBot:
    def __init__(self):
        self.is_running = False
        self.should_exit = False
        self.has_done_initial_pathing = False  
        
        self.is_waiting_for_start_button = True 
        
        self.catch_count = 0
        self.max_catches = 1
        self.sell_loops = 56
        self.cast_fail_count = 0
        self.path_profiles = []
        self.active_path_index = 0
        self.preferred_path_index = 0
        self.consecutive_failsafes = 0
        self.total_consecutive_failsafes = 0  # not reset by path switching — drives the sell-recovery threshold
        self.path_change_callback = None
        self.failsafe_callback = None
        self.last_join_screenshot = None
        self.session_id = 0
        self._active_session_id = None
        self.needs_startup_sell = False
        self.fishing_enabled = True  # whether to actually fish in the currently confirmed biome
        self.anti_afk_interval = 300  # seconds between anti-AFK key presses while not fishing (default 5 min)
        self._last_anti_afk_press = None
        
        # Initialize default variables (Replaces all the global variables)
        self.update_coordinates("1080p", "Normal")

    def get_pixel_color(self, x, y):
        """
        Performance fix: Grabbing a 1x1 bounding box using PIL is exponentially 
        faster than calling pyautogui.pixel() which screenshots the whole screen.
        """
        return ImageGrab.grab(bbox=(x, y, x + 1, y + 1)).getpixel((0, 0))

    def colors_match(self, c1, c2, tol=TOLERANCE):
        return (abs(c1[0] - c2[0]) <= tol and 
                abs(c1[1] - c2[1]) <= tol and 
                abs(c1[2] - c2[2]) <= tol)

    def _cycle_active(self):
        """True while the currently-executing fishing cycle is still the one
        FishSniper actually wants running. `is_running` alone isn't enough:
        the Discord scanner can toggle it back on for a brand-new server join
        while an old, abandoned cycle (e.g. one aborted mid-pathing because
        of a fake-biome detection) is still blocked inside a long sleep/hold
        and hasn't reached a check yet. Comparing the session stamp captured
        at the start of that specific cycle catches this: a stale cycle sees
        the mismatch and bails out even though is_running now reads True
        again for the unrelated new session."""
        return self.is_running and self._active_session_id == self.session_id

    def _interruptible_sleep(self, duration, chunk=0.1):
        """Sleeps in small increments, checking _cycle_active() between each,
        so an abandoned cycle can bail out quickly instead of blocking a
        held key or click sequence for the full duration."""
        end_time = time.time() + duration
        while True:
            if not self._cycle_active():
                return
            remaining = end_time - time.time()
            if remaining <= 0:
                return
            time.sleep(min(chunk, remaining))

    def focus_roblox(self):
        roblox_hwnd = None
        def enum_cb(hwnd, _):
            nonlocal roblox_hwnd
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == "Roblox":
                roblox_hwnd = hwnd
        win32gui.EnumWindows(enum_cb, None)

        if not roblox_hwnd:
            return False

        try:
            if win32gui.IsIconic(roblox_hwnd):
                win32gui.ShowWindow(roblox_hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            win32gui.SetWindowPos(roblox_hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(roblox_hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, 
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetForegroundWindow(roblox_hwnd)
            return True
        except Exception as e:
            return False
    
    def update_coordinates(self, resolution, speed="Normal", max_catches=1, sell_loops=56):
        self.max_catches = int(max_catches)
        self.sell_loops = int(sell_loops)

        # Normalize and map speed/pathing mode strings
        normalized_speed = speed.strip().upper()
        if normalized_speed in ("VIP", "VIP PATHING"):
            normalized_speed = "VIP"
        elif normalized_speed in ("NON VIP", "NON VIP PATHING", "NORMAL"):
            normalized_speed = "NORMAL"

        if normalized_speed not in PATHING_TIMINGS:
            normalized_speed = "NORMAL"

        timing = PATHING_TIMINGS[normalized_speed]
        self.ALIGNMENT1 = timing["ALIGNMENT1"]
        self.ALIGNMENT15 = timing["ALIGNMENT1.5"]
        self.ALIGNMENT2 = timing["ALIGNMENT2"]
        self.ALIGNMENT3 = timing["ALIGNMENT3"]
        self.MERCHANT1 = timing["MERCHANT1"]
        self.MERCHANT2 = timing["MERCHANT2"]
        self.MERCHANT3 = timing["MERCHANT3"]
        self.MERCHANT4 = timing["MERCHANT4"]
        self.MERCHANT5 = timing["MERCHANT5"]
        self.MERCHANT6 = timing["MERCHANT6"]
        print(f"[System] Shared path timings updated to {speed} (mapped to {normalized_speed})")
        self._set_path_profiles(POST_MERCHANT_PATHS[normalized_speed])

        if resolution in COORDS:
            self.CAST_ROD_POS = COORDS[resolution]["FISHING"]["CAST_ROD"]
            self.BITE_INDICATOR_POS = COORDS[resolution]["FISHING"]["BITE_INDICATOR"]
            self.BAR_COLOR_POS = COORDS[resolution]["FISHING"]["BAR_COLOR"]
            self.CLAIM_FISH_POS = COORDS[resolution]["FISHING"]["CLAIM_FISH"]
            self.MINIGAME_REGION = COORDS[resolution]["FISHING"]["MINIGAME_REGION"]
            
            self.CAMERA_SETUP_1 = COORDS[resolution]["MERCHANT"]["CAMERA_SETUP_1"]
            self.CAMERA_SETUP_2 = COORDS[resolution]["MERCHANT"]["CAMERA_SETUP_2"]
            self.OPEN_MERCHANT_1 = COORDS[resolution]["MERCHANT"]["OPEN_MERCHANT_1"]
            self.OPEN_MERCHANT_2 = COORDS[resolution]["MERCHANT"]["OPEN_MERCHANT_2"]
            self.SELECT_FISH = COORDS[resolution]["MERCHANT"]["SELECT_FISH"]
            self.SELL_ALL_ON = COORDS[resolution]["MERCHANT"]["SELL_ALL_ON"]
            self.SELL_ALL_OFF = COORDS[resolution]["MERCHANT"]["SELL_ALL_OFF"]
            self.CONFIRM_SELL = COORDS[resolution]["MERCHANT"]["CONFIRM_SELL"]
            self.CLOSE_MERCHANT = COORDS[resolution]["MERCHANT"]["CLOSE_MERCHANT"]

            self.START_BUTTON_POS = COORDS[resolution]["START"]["START_BUTTON_POS"]
            print(f"[System] Coordinates updated to {resolution}")

    def _set_path_profiles(self, profiles):
        """Load the selected mode's post-merchant action lists."""
        validated = [
            {"name": name, "actions": list(actions)}
            for name, actions in profiles.items()
            if isinstance(name, str) and isinstance(actions, list)
        ]
        if not validated:
            validated = [{"name": "Path 1", "actions": []}]

        self.path_profiles = validated
        self.active_path_index = min(self.active_path_index, len(validated) - 1)
        self._apply_active_path()

    def _apply_active_path(self):
        profile = self.path_profiles[self.active_path_index]
        print(f"[Pathing] Active path: {profile['name']} ({self.active_path_index + 1}/{len(self.path_profiles)})")
        if self.path_change_callback:
            self.path_change_callback(profile["name"])

    def set_path_change_callback(self, callback):
        self.path_change_callback = callback

    def set_failsafe_callback(self, callback):
        """callback(failsafe_count, switched_path, screenshot_bytes,
        triggered_sell) — fired every time record_fishing_failsafe() runs,
        e.g. so the UI can send a webhook alert without fishing.py needing
        to know about webhooks."""
        self.failsafe_callback = callback

    def request_startup_sell(self):
        """Marks that the next server this bot joins should sell off any
        existing inventory before fishing — meant to be called once, when
        the user presses the macro's own Start button. This is a one-shot
        flag: has_done_initial_pathing (which drives whether the "walk to
        spot" routine runs at all) resets on every server join, but this
        flag does not, so only that first join sells; every later join in
        the same run just walks to the spot as usual."""
        self.needs_startup_sell = True

    def set_biome_fishing_enabled(self, enabled):
        """Called by the Discord scanner once a biome is confirmed (or
        changes), based on that biome's "Fish This Biome" setting. When
        False, the bot stops casting/fishing entirely for as long as this
        biome stays active and just sits at the spot doing periodic
        anti-AFK key presses instead — see _idle_while_not_fishing()."""
        enabled = bool(enabled)
        if enabled == self.fishing_enabled:
            return
        self.fishing_enabled = enabled
        self._last_anti_afk_press = None  # start a fresh interval whenever this changes
        print(f"[Fishing Bot] Fishing {'enabled' if enabled else 'disabled'} for the current biome.")

    def set_anti_afk_interval(self, seconds):
        """Sets how often (in seconds) the anti-AFK key press fires while
        fishing is disabled for the current biome."""
        try:
            self.anti_afk_interval = max(1, int(seconds))
        except (TypeError, ValueError):
            pass

    def _idle_while_not_fishing(self):
        """Runs while fishing is disabled for the currently confirmed biome.
        Sits in place doing nothing except, once every anti_afk_interval
        seconds, focusing the Roblox window and tapping the anti-AFK key so
        a long fishing-free stretch doesn't get kicked for inactivity.
        Stays in this single call (rather than returning control to the
        outer fishing loop every tick, which would re-focus the window far
        more often than intended) until fishing is re-enabled or the
        session ends."""
        print("[Fishing Bot] Fishing disabled for this biome — sitting idle with anti-AFK enabled.")
        while self._cycle_active() and not self.fishing_enabled:
            now = time.time()
            if self._last_anti_afk_press is None or now - self._last_anti_afk_press >= self.anti_afk_interval:
                self.focus_roblox()
                pydirectinput.press('space')
                self._last_anti_afk_press = time.time()
                print("[Fishing Bot] Anti-AFK key press sent.")
            self._interruptible_sleep(1.0)

    # Screenshot compression settings. JPEG at this quality is dramatically
    # smaller than a raw PNG for a screen capture, and 1600px wide is still
    # plenty readable for a Discord embed while keeping high-res (1440p/4K,
    # multi-monitor) captures from ballooning in size.
    SCREENSHOT_JPEG_QUALITY = 70
    SCREENSHOT_MAX_WIDTH = 1600

    def capture_screenshot(self):
        """Grabs a full-screen screenshot, downscales it if it's very large,
        and returns it as compressed JPEG bytes (or None on failure).
        Generic helper — used for the join screenshot as well as any other
        on-demand screenshot (e.g. a delayed biome check-in shot)."""
        try:
            screenshot = ImageGrab.grab()
            if screenshot.mode != "RGB":
                screenshot = screenshot.convert("RGB")

            if screenshot.width > self.SCREENSHOT_MAX_WIDTH:
                scale = self.SCREENSHOT_MAX_WIDTH / screenshot.width
                new_size = (self.SCREENSHOT_MAX_WIDTH, max(1, int(screenshot.height * scale)))
                screenshot = screenshot.resize(new_size, Image.LANCZOS)

            buffer = io.BytesIO()
            screenshot.save(buffer, format="JPEG", quality=self.SCREENSHOT_JPEG_QUALITY, optimize=True)
            return buffer.getvalue()
        except Exception as e:
            print(f"[Fishing Bot] Failed to capture screenshot: {e}")
            return None

    def capture_join_screenshot(self):
        """Grabs a full-screen screenshot right after clicking a server's Start
        button, before any character-reset pathing begins, and holds onto it in
        memory. The Discord scanner attaches this to the "Joined: {biome}"
        webhook embed once it confirms the biome from the Roblox logs, which
        happens later/asynchronously — so the embed is fine to be delayed."""
        self.last_join_screenshot = self.capture_screenshot()

    def select_path(self, path_index):
        """Set the manually selected starting path (zero-based index)."""
        if not self.path_profiles:
            return
        self.preferred_path_index = max(0, min(int(path_index), len(self.path_profiles) - 1))
        self.active_path_index = self.preferred_path_index
        self.consecutive_failsafes = 0
        self._apply_active_path()

    def begin_server_session(self):
        """Runs when the scanner joins a new server. Only clears the failsafe
        counter — the active path itself is intentionally left as-is. If a
        failsafe switched it mid-session, that stays the active path on the
        next server too, since the switch was presumably needed to work
        around something (a busy spot, bad timing, etc.) that isn't specific
        to the server that just ended. It only resets back to a specific
        path via an explicit select_path() call (the UI's Starting Path
        dropdown)."""
        self.consecutive_failsafes = 0
        self._apply_active_path()

    def prepare_for_server_join(self):
        """Resets per-join state so the bot treats this as a brand-new
        server: waits for the in-game Start button again, and walks to the
        fishing spot fresh (has_done_initial_pathing back to False, which is
        also what makes the sell-on-start behavior — see
        request_startup_sell() — eligible to run again if the flag is
        still pending)."""
        self.is_waiting_for_start_button = True
        self.has_done_initial_pathing = False

    # How many consecutive no-bite failsafes (regardless of any path
    # switches in between) trigger a full sell-and-restart recovery, on the
    # theory that something's more fundamentally stuck than a bad path.
    FAILSAFE_SELL_THRESHOLD = 5

    def record_fishing_failsafe(self):
        self.consecutive_failsafes += 1
        self.total_consecutive_failsafes += 1
        failsafe_count = self.consecutive_failsafes
        print(f"[Fishing Bot] Failsafe {failsafe_count}/2 on the current server "
              f"({self.total_consecutive_failsafes} in a row overall).")

        screenshot_bytes = self.capture_screenshot()
        switched_path = False

        if self.consecutive_failsafes >= 2 and len(self.path_profiles) >= 2:
            self.active_path_index = (self.active_path_index + 1) % len(self.path_profiles)
            self.consecutive_failsafes = 0
            self._apply_active_path()
            switched_path = True
            print("[Fishing Bot] Two consecutive failsafes: switched to the next path profile.")

        triggered_sell = False
        if self.total_consecutive_failsafes >= self.FAILSAFE_SELL_THRESHOLD:
            triggered_sell = True
            self.consecutive_failsafes = 0
            self.total_consecutive_failsafes = 0
            print(f"[Fishing Bot] {self.FAILSAFE_SELL_THRESHOLD} failsafes in a row — "
                  "selling off inventory and restarting the fishing cycle.")

        if self.failsafe_callback:
            self.failsafe_callback(failsafe_count, switched_path, screenshot_bytes, triggered_sell)

        return triggered_sell

    def record_successful_catch(self):
        if self.consecutive_failsafes or self.total_consecutive_failsafes:
            print("[Fishing Bot] Catch succeeded; clearing failsafe counts.")
        self.consecutive_failsafes = 0
        self.total_consecutive_failsafes = 0

    def reset_character(self):
        if not self._cycle_active():
            return
        print("[Pathing] Resetting character...")
        time.sleep(0.2)
        pydirectinput.press('esc')
        time.sleep(0.2)
        pydirectinput.press('r')
        time.sleep(0.2)
        pydirectinput.press('enter')
        self._interruptible_sleep(2.6)

    def setup_camera(self):
        print("[Pathing] Setting up camera orientation...")
        pydirectinput.moveTo(self.CAMERA_SETUP_1[0], self.CAMERA_SETUP_1[1])
        time.sleep(0.1)
        pydirectinput.moveTo(self.CAMERA_SETUP_1[0], self.CAMERA_SETUP_1[1] - 3, duration=0.2)
        time.sleep(0.22)
        pydirectinput.click()
        time.sleep(0.22)
        pydirectinput.moveTo(self.CAMERA_SETUP_2[0], self.CAMERA_SETUP_2[1])
        time.sleep(0.1)
        pydirectinput.moveTo(self.CAMERA_SETUP_2[0], self.CAMERA_SETUP_2[1] - 3, duration=0.2)
        time.sleep(0.22)
        pydirectinput.click()
        time.sleep(0.22)
        
        # Zoom all the way in
        for _ in range(16):
            if not self._cycle_active(): return
            pyautogui.scroll(500)
            time.sleep(0.01)
        time.sleep(0.2)
        
        # Zoom out slightly to optimal position
        for _ in range(7):
            if not self._cycle_active(): return
            pyautogui.scroll(-300)
            time.sleep(0.01)
        time.sleep(0.1)

    def walk_to_merchant(self):
        print("[Pathing] Walking to merchant...")
        pydirectinput.keyDown('w')
        pydirectinput.keyDown('a')
        self._interruptible_sleep(self.ALIGNMENT1)
        if not self._cycle_active(): 
            pydirectinput.keyUp('w'); pydirectinput.keyUp('a')
            return
            
        pydirectinput.keyUp('w')
        self._interruptible_sleep(self.ALIGNMENT2)
        pydirectinput.keyUp('a')
        if not self._cycle_active():
            return
        time.sleep(0.2)
        
        pydirectinput.keyDown('w')
        self._interruptible_sleep(self.ALIGNMENT3)
        pydirectinput.keyUp('w')
        if not self._cycle_active():
            return
        time.sleep(0.3)
        
        pydirectinput.keyDown('d')
        self._interruptible_sleep(self.MERCHANT1)
        pydirectinput.keyUp('d')
        if not self._cycle_active():
            return
        time.sleep(0.15)
        
        pydirectinput.keyDown('w')
        self._interruptible_sleep(self.MERCHANT2)
        if not self._cycle_active():
            pydirectinput.keyUp('w')
            return
        #pydirectinput.keyDown('space')
        self._interruptible_sleep(self.MERCHANT3)
        pydirectinput.keyUp('w')
        if not self._cycle_active():
            return
        pydirectinput.keyDown('s')
        self._interruptible_sleep(self.ALIGNMENT15)
        pydirectinput.keyUp('s')
        if not self._cycle_active():
            return
        pydirectinput.keyDown('w')
        self._interruptible_sleep(self.MERCHANT5)
        if not self._cycle_active():
            pydirectinput.keyUp('w')
            return
        pydirectinput.keyDown('space')
        self._interruptible_sleep(self.MERCHANT6)
        pydirectinput.keyUp('space')
        pydirectinput.keyUp('w')
        #pydirectinput.keyUp('space')
        if not self._cycle_active():
            return
        time.sleep(0.3)
        
        #pydirectinput.keyDown('a')
        #pydirectinput.keyDown('w')
        #time.sleep(self.MERCHANT4)
        #pydirectinput.keyUp('a')
        #pydirectinput.keyUp('w')
        #time.sleep(0.2)

    def sell_fish_logic(self):
        print("[Auto-Sell] Opening merchant UI...")
        pydirectinput.keyDown('e')
        time.sleep(0.3)
        pydirectinput.keyUp('e')
        time.sleep(0.3)
        pydirectinput.moveTo(self.OPEN_MERCHANT_1[0], self.OPEN_MERCHANT_1[1] - 50)
        pydirectinput.moveTo(self.OPEN_MERCHANT_1[0], self.OPEN_MERCHANT_1[1], duration=0.2)
        time.sleep(0.1)
        pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
        time.sleep(0.2)

        while True:
            if not self._cycle_active(): return
            
            pydirectinput.moveTo(self.OPEN_MERCHANT_2[0], self.OPEN_MERCHANT_2[1] - 3)
            pydirectinput.moveTo(self.OPEN_MERCHANT_2[0], self.OPEN_MERCHANT_2[1], duration=0.2)
            time.sleep(0.1)

            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(0.2)
            
            try:
                current_color = self.get_pixel_color(*self.OPEN_MERCHANT_2)
                if self.colors_match(current_color, (47, 165, 255), tol=15):
                    print("[Auto-Sell] Merchant 2 click failed (detected blue color). Retrying...")
                    time.sleep(0.1)
                    continue
            except Exception:
                pass
            break
            
        time.sleep(0.6)

        print("[Auto-Sell] Selling fish...")
        for _ in range(self.sell_loops):  
            if not self._cycle_active(): return
            
            pydirectinput.moveTo(self.SELECT_FISH[0], self.SELECT_FISH[1] - 50)
            pydirectinput.moveTo(self.SELECT_FISH[0], self.SELECT_FISH[1], duration=0.2)
            pydirectinput.moveTo(self.SELECT_FISH[0] - 3, self.SELECT_FISH[1], duration=0.1)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(0.2)
            
            pydirectinput.moveTo(self.SELL_ALL_ON[0], self.SELL_ALL_ON[1] - 50)
            pydirectinput.moveTo(self.SELL_ALL_ON[0], self.SELL_ALL_ON[1], duration=0.2)
            pydirectinput.moveTo(self.SELL_ALL_ON[0] - 3, self.SELL_ALL_ON[1], duration=0.2)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(0.3)
            
            pydirectinput.moveTo(self.CONFIRM_SELL[0], self.CONFIRM_SELL[1] - 50)
            pydirectinput.moveTo(self.CONFIRM_SELL[0], self.CONFIRM_SELL[1], duration=0.2)
            pydirectinput.moveTo(self.CONFIRM_SELL[0] - 3, self.CONFIRM_SELL[1], duration=0.2)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            self._interruptible_sleep(1.0)

    def walk_back_to_spot(self):
        profile = self.path_profiles[self.active_path_index]
        print(f"[Pathing] Following {profile['name']} from merchant to fishing spot...")
        for action in profile["actions"]:
            if not self._cycle_active():
                return
            try:
                kind = action[0]
                if kind == "wait":
                    self._interruptible_sleep(float(action[1]))
                elif kind == "hold":
                    key, duration = action[1], float(action[2])
                    pydirectinput.keyDown(key)
                    try:
                        self._interruptible_sleep(duration)
                    finally:
                        pydirectinput.keyUp(key)
                elif kind == "press":
                    pydirectinput.press(action[1])
                elif kind == "click":
                    x, y = getattr(self, action[1])
                    pydirectinput.moveTo(x, y - 3)
                    time.sleep(0.1)
                    pydirectinput.moveTo(x, y, duration=0.2)
                    pydirectinput.click()
                elif kind == "click_at":
                    pydirectinput.click(action[1], action[2])
                elif kind == "scroll":
                    pyautogui.scroll(int(action[1]))
                else:
                    print(f"[Pathing] Skipping unknown action: {action}")
            except (IndexError, TypeError, ValueError, AttributeError) as e:
                print(f"[Pathing] Skipping invalid action {action}: {e}")

    def do_pathing_routine(self, do_sell=True):
        print(f"=== PATHING ROUTINE STARTED (Selling: {do_sell}) ===")
        self.reset_character()
        if not self._cycle_active(): return
        self.setup_camera()
        if not self._cycle_active(): return
        self.walk_to_merchant()
        if not self._cycle_active(): return
        
        if do_sell:
            self.sell_fish_logic()
            if not self._cycle_active(): return
            
        self.walk_back_to_spot()
        if do_sell:
            self.catch_count = 0
        print("=== PATHING COMPLETE. READY TO FISH ===")

    def play_fishing_cycle(self):
        # Stamp this invocation with the current session. If the scanner
        # abandons this server (fake biome, priority interrupt, manual stop)
        # partway through and later resumes for a different server, this
        # stamp will no longer match self.session_id, so every check below
        # correctly treats this invocation as stale rather than continuing.
        self._active_session_id = self.session_id
        self.focus_roblox()

        # 0A. New Server Load Wait / Start Button Verification
        if self.is_waiting_for_start_button:
            if self.START_BUTTON_POS == (0, 0):
                print("[Fishing Bot] Warning: Start coordinates default. Bypassing check.")
                self.is_waiting_for_start_button = False
                return

            print(f"[Fishing Bot] Waiting {WAIT_FOR_START_BUTTON_TIME} seconds for Roblox to load before checking for Start button...")
            for _ in range(WAIT_FOR_START_BUTTON_TIME * 2):  # Total time, checking every 0.5s
                if not self._cycle_active(): return
                time.sleep(0.5)

            print("[Fishing Bot] Checking for Start button...")
            wait_start = time.time()
            button_clicked = False

            while time.time() - wait_start < 60:
                if not self._cycle_active(): return
                
                try:
                    current_color = self.get_pixel_color(*self.START_BUTTON_POS)
                    print(f"[Fishing Bot] Detected color at start button: {current_color}")
                    
                    if self.colors_match(current_color, START_BUTTON_COLOR, tol=START_BUTTON_COLOR_TOLERANCE):
                        print("[Fishing Bot] Play/Start Button detected! Waiting 2 seconds before clicking...")
                        time.sleep(2.0)
                        
                        pydirectinput.moveTo(self.START_BUTTON_POS[0], self.START_BUTTON_POS[1] - 20)
                        time.sleep(0.1)
                        pydirectinput.moveTo(*self.START_BUTTON_POS, duration=0.2)
                        time.sleep(0.1)
                        pydirectinput.mouseDown()
                        time.sleep(0.05)
                        pydirectinput.mouseUp()
                        
                        time.sleep(3.0) 
                        button_clicked = True
                        break 
                except Exception:
                    pass
                
                time.sleep(0.5) 

            if not button_clicked:
                print("[Fishing Bot] Start button not found or timed out. Assuming already in-game.")
            else:
                # Capture proof-of-join before any character-reset pathing begins;
                # it gets attached to the "Joined" webhook embed once the biome
                # is confirmed from the Roblox logs. Waits a beat after the click
                # so the screenshot doesn't catch the button's click animation
                # mid-frame.
                self._interruptible_sleep(1.0)
                if self._cycle_active():
                    print("[Fishing Bot] Capturing join screenshot...")
                    self.capture_join_screenshot()

            self.is_waiting_for_start_button = False
            self.has_done_initial_pathing = False
            return

        # 0B. Fishing Toggle — checked before any pathing happens. If
        # fishing is disabled for the currently expected/confirmed biome,
        # skip walking to the merchant/spot entirely and just sit right
        # here (wherever that is — spawn, if no pathing has happened yet)
        # with periodic anti-AFK presses. has_done_initial_pathing stays
        # False the whole time this is skipped, so the moment fishing gets
        # enabled again (a corrected biome confirmation, or a biome-to-biome
        # transition into an enabled biome) the walk-to-spot step below
        # still runs normally, just later than usual.
        if not self.fishing_enabled:
            self._idle_while_not_fishing()
            return

        # 0C. Initial Pathing
        if not self.has_done_initial_pathing:
            do_sell = self.needs_startup_sell
            if do_sell:
                print("Detected first run! Selling out any leftover inventory before heading to the fishing spot...")
            else:
                print("Detected first run! Walking to fishing spot...")
            self.do_pathing_routine(do_sell=do_sell)
            if self._cycle_active():
                self.has_done_initial_pathing = True
                if do_sell:
                    self.needs_startup_sell = False
            return

        # 0D. Auto-Sell Trigger
        if self.catch_count >= self.max_catches:
            self.do_pathing_routine(do_sell=True)
            return

        # 1. Cast the fishing rod
        pydirectinput.moveTo(self.CAST_ROD_POS[0], self.CAST_ROD_POS[1] - 50)
        time.sleep(0.1)
        pydirectinput.moveTo(self.CAST_ROD_POS[0], self.CAST_ROD_POS[1], duration=0.2)
        time.sleep(0.1)
        pydirectinput.moveTo(self.CAST_ROD_POS[0]-3, self.CAST_ROD_POS[1], duration=0.1)
        time.sleep(0.1)
        pydirectinput.mouseDown()
        time.sleep(0.05)
        pydirectinput.mouseUp()
        time.sleep(0.3)

        if not self._cycle_active():
            return

        start_wait = time.time()
        bar_color = None

        # 2. Wait for bite
        while time.time() - start_wait < MAX_WAIT_FOR_BITE:
            if not self._cycle_active():
                return

            pixel = self.get_pixel_color(*self.BITE_INDICATOR_POS)
            if self.colors_match(pixel, (255, 255, 255), tol=5):
                pyautogui.moveTo(950, 880)
                
                # Wait 0.5s for the minigame UI to pop up before sampling its color
                time.sleep(0.5) 
                bar_color = self.get_pixel_color(*self.BAR_COLOR_POS)
                print(f"Bite! Bar color detected: {bar_color}")
                break

            time.sleep(0.05)

        if not bar_color:
            time.sleep(1.5)
            pydirectinput.moveTo(10, 10)
            time.sleep(0.1)
            pydirectinput.moveTo(self.CLAIM_FISH_POS[0], self.CLAIM_FISH_POS[1] - 50)
            time.sleep(0.1)
            pydirectinput.moveTo(*self.CLAIM_FISH_POS, duration=0.2)
            time.sleep(0.3)
            pydirectinput.mouseDown()
            time.sleep(0.1)
            pydirectinput.mouseUp()
            time.sleep(0.5)
            print("Fishing timeout or no bite detected. Retrying recovery pathing...")

            # Press start button in case it failed to press at the start
            pydirectinput.moveTo(self.START_BUTTON_POS[0], self.START_BUTTON_POS[1] - 20)
            time.sleep(0.1)
            pydirectinput.moveTo(*self.START_BUTTON_POS, duration=0.2)
            time.sleep(0.1)
            pydirectinput.mouseDown()
            time.sleep(0.05)
            pydirectinput.mouseUp()

            should_sell = self.record_fishing_failsafe()
            self.do_pathing_routine(do_sell=should_sell)
            return

        # 3. Mini-game (Reverted to clicks, keeping ImageGrab + CPU sleep)
        print("Playing mini-game...")
        minigame_start = time.time()

        while time.time() - minigame_start < MAX_MINIGAME_TIME:
            if not self._cycle_active():
                return

            # Grab just the minigame region. (Much faster than whole screen)
            x, y, w, h = self.MINIGAME_REGION
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            pixels = img.load()

            bar_found = False
            for img_x in range(0, img.width, 3):
                for img_y in range(0, img.height, 3):
                    if self.colors_match(pixels[img_x, img_y], bar_color):
                        bar_found = True
                        break
                if bar_found:
                    break

            if not bar_found:
                pydirectinput.click()
                
            # Crucial: Prevent 100% CPU lockup and input thread queueing
            time.sleep(0.01) 

        # The original code had a mouseUp here as a safety fallback
        pydirectinput.mouseUp()

        # 4. Claim fish
        print("Mini-game finished. Waiting for Claim button...")
        time.sleep(1.5)
        pydirectinput.moveTo(10, 10)
        time.sleep(0.1)
        pydirectinput.moveTo(self.CLAIM_FISH_POS[0], self.CLAIM_FISH_POS[1] - 50)
        time.sleep(0.1)
        pydirectinput.moveTo(*self.CLAIM_FISH_POS, duration=0.2)
        time.sleep(0.3)
        pydirectinput.moveTo(self.CLAIM_FISH_POS[0]-3, self.CLAIM_FISH_POS[1], duration=0.1)
        time.sleep(0.1)
        pydirectinput.mouseDown()
        time.sleep(0.1)
        pydirectinput.mouseUp()
        time.sleep(0.5)
        
        self.catch_count += 1
        self.record_successful_catch()
        print(f"--> Fish caught successfully! Server tally: {self.catch_count}/{self.max_catches}")

    def start(self):
        print("FishSol bot ready (UI-controlled mode).")
        while not self.should_exit:
            if self.is_running:
                self.play_fishing_cycle()
            else:
                time.sleep(0.1)

    def toggle_on(self, reset_initial_pathing=True):
        print("[System] Bot Started")
        self.is_running = True
        if reset_initial_pathing:
            self.has_done_initial_pathing = False

    def toggle_off(self):
        print("[System] Bot Paused")
        self.session_id += 1
        self.is_running = False
        # Clear out any screenshot from the session we're leaving — a new
        # join (or a resumed pause) should never end up attaching a stale
        # screenshot to the wrong server's "Joined" embed.
        self.last_join_screenshot = None
        # A fresh session should default to fishing until the scanner
        # confirms a biome that says otherwise.
        self.fishing_enabled = True
        self._last_anti_afk_press = None
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('s')
        pydirectinput.keyUp('d')

    def exit_script(self):
        print("[System] Bot Exiting")
        self.is_running = False
        self.should_exit = True