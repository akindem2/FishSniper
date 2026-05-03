import time
import pyautogui
import pydirectinput
from PIL import ImageGrab
import win32gui
import win32com.client
import win32con
import ctypes
import pygetwindow as gw

# --- 1440p COORDINATES ---
CAST_ROD_POS = (1161, 1124)
BITE_INDICATOR_POS = (1536, 1119)
BAR_COLOR_POS = (1261, 1033)
CLAIM_FISH_POS = (1457, 491)
MINIGAME_REGION = (1043, 1033, 476, 25)

TOLERANCE = 10
MAX_WAIT_FOR_BITE = 35
MAX_MINIGAME_TIME = 10
MAX_WAIT_FOR_CAST = 35

class FishSolBot:
    def __init__(self):
        self.is_running = False
        self.should_exit = False
        
        # Pathing & Auto-Sell Tracker
        self.has_done_initial_pathing = False  # NEW: Tracks if we walked to the spot yet
        self.catch_count = 0
        self.max_catches = 1  # Adjust this to change how many fish before selling

    def colors_match(self, c1, c2, tol=TOLERANCE):
        return (abs(c1[0] - c2[0]) <= tol and 
                abs(c1[1] - c2[1]) <= tol and 
                abs(c1[2] - c2[2]) <= tol)

    # -------------------------
    # RELIABLE ROBLOX FOCUS
    # -------------------------
    def focus_roblox(self):
        """Forces Roblox to the front using the TopMost bypass."""
        roblox_hwnd = None

        def enum_cb(hwnd, _):
            nonlocal roblox_hwnd
            if win32gui.IsWindowVisible(hwnd) and "roblox" in win32gui.GetWindowText(hwnd).lower():
                roblox_hwnd = hwnd
        win32gui.EnumWindows(enum_cb, None)

        if not roblox_hwnd:
            print("[System] Could not find a running Roblox window.")
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
            print(f"[System] Focus trick failed: {e}")
            return False

    # -------------------------
    # AUTO-SELL & PATHING
    # -------------------------
    def reset_character(self):
        print("[Pathing] Resetting character...")
        time.sleep(0.2)
        pydirectinput.press('esc')
        time.sleep(0.2)
        pydirectinput.press('r')
        time.sleep(0.2)
        pydirectinput.press('enter')
        time.sleep(2.6)

    def setup_camera(self):
        print("[Pathing] Setting up camera orientation...")
        pydirectinput.moveTo(52, 621)
        time.sleep(0.1)
        pydirectinput.moveTo(52, 611, duration=0.2)
        time.sleep(0.22)
        pydirectinput.click()
        time.sleep(0.22)
        pydirectinput.moveTo(525, 158)
        time.sleep(0.1)
        pydirectinput.moveTo(525, 148, duration=0.2)
        time.sleep(0.22)
        pydirectinput.click()
        time.sleep(0.22)
        
        # Zoom In completely
        for _ in range(80):
            if not self.is_running: return
            pyautogui.scroll(100)
            time.sleep(0.01)
        time.sleep(0.5)
        
        # Zoom Out to required distance
        for _ in range(35):
            if not self.is_running: return
            pyautogui.scroll(-20)
            
            time.sleep(0.01)
        time.sleep(0.3)

    def walk_to_merchant(self):
        print("[Pathing] Walking to merchant...")
        pydirectinput.keyDown('w')
        pydirectinput.keyDown('a')
        time.sleep(4)
        if not self.is_running: 
            pydirectinput.keyUp('w'); pydirectinput.keyUp('a')
            return
            
        pydirectinput.keyUp('w')
        time.sleep(0.6)
        pydirectinput.keyUp('a')
        time.sleep(0.2)
        
        pydirectinput.keyDown('w')
        time.sleep(0.4)
        pydirectinput.keyUp('w')
        time.sleep(0.3)
        
        pydirectinput.keyDown('d')
        time.sleep(0.25)
        pydirectinput.keyUp('d')
        time.sleep(0.15)
        
        pydirectinput.keyDown('w')
        time.sleep(.8)
        pydirectinput.keyDown('space')
        time.sleep(1.2)
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('space')
        time.sleep(0.3)
        
        pydirectinput.keyDown('a')
        pydirectinput.keyDown('w')
        time.sleep(0.2)
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('w')
        time.sleep(0.2)

    def sell_fish_logic(self):
        print("[Auto-Sell] Opening merchant UI...")
        pydirectinput.keyDown('e')
        time.sleep(0.3)
        pydirectinput.keyUp('e')
        time.sleep(0.3)
        pydirectinput.moveTo(1308, 1073 - 50)
        pydirectinput.moveTo(1308, 1073, duration=0.2)
        time.sleep(0.1)
        pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
        time.sleep(0.2)

        pydirectinput.moveTo(1289, 1264 - 50)
        pydirectinput.moveTo(1289, 1264, duration=0.2)
        time.sleep(0.1)
        pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
        time.sleep(0.8)

        print("[Auto-Sell] Selling fish...")
        for _ in range(22):  
            if not self.is_running: return
            
            pydirectinput.moveTo(1117, 550 - 50)
            pydirectinput.moveTo(1117, 550, duration=0.2)
            pydirectinput.moveTo(1110,550, duration=0.1)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(0.2)
            
            pydirectinput.moveTo(904, 1080 - 50)
            pydirectinput.moveTo(904, 1080, duration=0.2)
            pydirectinput.moveTo(894, 1080, duration=0.2)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(0.3)
            
            pydirectinput.moveTo(1002, 831 - 50)
            pydirectinput.moveTo(1002, 831, duration=0.2)
            pydirectinput.moveTo(992, 831, duration=0.2)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(1.0)

    def walk_back_to_spot(self):
        print("[Pathing] Walking from merchant to fishing spot...")
        pydirectinput.moveTo(1958, 361)
        time.sleep(0.2)
        pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
        time.sleep(0.2)
        
        pydirectinput.keyDown('a')
        time.sleep(1.2)
        pydirectinput.keyUp('a')
        time.sleep(0.075)
        pydirectinput.keyDown('w')
        time.sleep(2.6)
        pydirectinput.keyUp('w')

    def do_pathing_routine(self, do_sell=True):
        """Runs the pathing. If do_sell is False, it skips interacting with the merchant."""
        print(f"=== PATHING ROUTINE STARTED (Selling: {do_sell}) ===")
        self.reset_character()
        if not self.is_running: return
        self.setup_camera()
        if not self.is_running: return
        self.walk_to_merchant()
        if not self.is_running: return
        
        if do_sell:
            self.sell_fish_logic()
            if not self.is_running: return
            
        self.walk_back_to_spot()
        
        # Reset counter to 0
        self.catch_count = 0
        print("=== PATHING COMPLETE. READY TO FISH ===")

    # -------------------------
    # MAIN FISHING LOGIC
    # -------------------------
    def play_fishing_cycle(self):
        self.focus_roblox()

        # 0A. Initial Pathing (Runs ONCE when the script is started)
        if not self.has_done_initial_pathing:
            print("Detected first run! Walking to fishing spot...")
            self.do_pathing_routine(do_sell=False) # Skips the selling logic to save time
            if self.is_running:
                self.has_done_initial_pathing = True
            return

        # 0B. Normal Auto-Sell Pathing
        if self.catch_count >= self.max_catches:
            self.do_pathing_routine(do_sell=True)
            return

        # 1. Cast the fishing rod
        pydirectinput.moveTo(CAST_ROD_POS[0], CAST_ROD_POS[1] - 50)
        time.sleep(0.1)

        pydirectinput.moveTo(CAST_ROD_POS[0], CAST_ROD_POS[1], duration=0.2)
        time.sleep(0.1)

        pydirectinput.moveTo(CAST_ROD_POS[0]-10, CAST_ROD_POS[1], duration=0.1)
        time.sleep(0.1)
        pydirectinput.mouseDown()
        time.sleep(0.05)
        pydirectinput.mouseUp()

        time.sleep(0.3)

        if not self.is_running:
            return

        pixel = pyautogui.pixel(*CAST_ROD_POS)
        if self.colors_match(pixel, (49, 49, 59), tol=20) or self.colors_match(pixel, (120,140,255), tol=5):
            print("Cast may have failed. Retrying...")
            pydirectinput.moveTo(10, 10)
            time.sleep(0.1)
            return

        start_wait = time.time()
        bar_color = None

        # 2. Wait for bite
        while time.time() - start_wait < MAX_WAIT_FOR_BITE:
            if not self.is_running:
                return

            pixel = pyautogui.pixel(*BITE_INDICATOR_POS)
            if self.colors_match(pixel, (255, 255, 255), tol=5):
                pyautogui.moveTo(950, 880)
                time.sleep(0.05)
                bar_color = pyautogui.pixel(*BAR_COLOR_POS)
                print(f"Bite! Bar color detected: {bar_color}")
                break

            time.sleep(0.05)

        if not bar_color:
            time.sleep(1.5)
            pydirectinput.moveTo(10, 10)
            time.sleep(0.1)
            pydirectinput.moveTo(CLAIM_FISH_POS[0], CLAIM_FISH_POS[1] - 50)
            time.sleep(0.1)
            pydirectinput.moveTo(*CLAIM_FISH_POS, duration=0.2)
            time.sleep(0.3)
            pydirectinput.mouseDown()
            time.sleep(0.1)
            pydirectinput.mouseUp()
            time.sleep(0.5)
            print("Fishing timeout or no bite detected. Retrying...")
            return

        # 3. Mini-game
        print("Playing mini-game...")
        minigame_start = time.time()

        while time.time() - minigame_start < MAX_MINIGAME_TIME:
            if not self.is_running:
                return

            img = pyautogui.screenshot(region=MINIGAME_REGION)
            pixels = img.load()

            bar_found = False
            for x in range(0, img.width, 3):
                for y in range(0, img.height, 3):
                    if self.colors_match(pixels[x, y], bar_color):
                        bar_found = True
                        break
                if bar_found:
                    break

            if not bar_found:
                pydirectinput.click()

        pydirectinput.mouseUp()

        # 4. Claim fish
        print("Mini-game finished. Waiting for Claim button...")
        time.sleep(1.5)
        pydirectinput.moveTo(10, 10)
        time.sleep(0.1)
        pydirectinput.moveTo(CLAIM_FISH_POS[0], CLAIM_FISH_POS[1] - 50)
        time.sleep(0.1)
        pydirectinput.moveTo(*CLAIM_FISH_POS, duration=0.2)
        time.sleep(0.3)
        
        pydirectinput.moveTo(CLAIM_FISH_POS[0]-10, CLAIM_FISH_POS[1], duration=0.1)
        time.sleep(0.1)
        
        pydirectinput.mouseDown()
        time.sleep(0.1)
        pydirectinput.mouseUp()
        time.sleep(0.5)
        
        self.catch_count += 1
        print(f"--> Fish caught successfully! Total catches before selling: {self.catch_count}/{self.max_catches}")

    # -------------------------
    # UI CONTROLLED LOOP
    # -------------------------
    def start(self):
        print("FishSol bot ready (UI-controlled mode).")

        while not self.should_exit:
            if self.is_running:
                self.play_fishing_cycle()
            else:
                time.sleep(0.1)

    def toggle_on(self):
        print("[System] Bot Started")
        self.is_running = True

    def toggle_off(self):
        print("[System] Bot Paused")
        self.is_running = False
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('s')
        pydirectinput.keyUp('d')

    def exit_script(self):
        print("[System] Bot Exiting")
        self.is_running = False
        self.should_exit = True