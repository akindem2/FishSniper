import time
import pyautogui
import pydirectinput
from PIL import ImageGrab
import win32gui
import win32com.client
import win32con
import ctypes
import pygetwindow as gw

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
            "CAMERA_SETUP_2": (382, 126),
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
        "ALIGNMENT1": 4,
        "ALIGNMENT2": 0.6,
        "ALIGNMENT3": 0.4,
        "MERCHANT1": 0.25,
        "MERCHANT2": 0.7,
        "MERCHANT3": 1.3,
        "MERCHANT4": 0.2,
        "SPOT1": 6.4,
    },
    "NORMAL": {
        "ALIGNMENT1": 4.8,
        "ALIGNMENT2": 0.72,
        "ALIGNMENT3": 0.48,
        "MERCHANT1": 0.3,
        "MERCHANT2": 0.96,
        "MERCHANT3": 1.44,
        "MERCHANT4": 0.24,
        "SPOT1": 7.68,
    }
}

ALIGNMENT1 = 4.2
ALIGNMENT2 = 0.6
ALIGNMENT3 = 0.4
MERCHANT1 = 0.25
MERCHANT2 = 0.8
MERCHANT3 = 1.2
MERCHANT4 = 0.2
SPOT1 = 6.4

CAST_ROD_POS = COORDS["1080p"]["FISHING"]["CAST_ROD"]
BITE_INDICATOR_POS = COORDS["1080p"]["FISHING"]["BITE_INDICATOR"]
BAR_COLOR_POS = COORDS["1080p"]["FISHING"]["BAR_COLOR"]
CLAIM_FISH_POS = COORDS["1080p"]["FISHING"]["CLAIM_FISH"]
MINIGAME_REGION = COORDS["1080p"]["FISHING"]["MINIGAME_REGION"]

CAMERA_SETUP_1 = COORDS["1080p"]["MERCHANT"]["CAMERA_SETUP_1"]
CAMERA_SETUP_2 = COORDS["1080p"]["MERCHANT"]["CAMERA_SETUP_2"]
OPEN_MERCHANT_1 = COORDS["1080p"]["MERCHANT"]["OPEN_MERCHANT_1"]
OPEN_MERCHANT_2 = COORDS["1080p"]["MERCHANT"]["OPEN_MERCHANT_2"]
SELECT_FISH = COORDS["1080p"]["MERCHANT"]["SELECT_FISH"]
SELL_ALL_ON = COORDS["1080p"]["MERCHANT"]["SELL_ALL_ON"]
SELL_ALL_OFF = COORDS["1080p"]["MERCHANT"]["SELL_ALL_OFF"]
CONFIRM_SELL = COORDS["1080p"]["MERCHANT"]["CONFIRM_SELL"]
CLOSE_MERCHANT = COORDS["1080p"]["MERCHANT"]["CLOSE_MERCHANT"]

START_BUTTON_POS = COORDS["1080p"]["START"]["START_BUTTON_POS"]

TOLERANCE = 10
MAX_WAIT_FOR_BITE = 35
MAX_MINIGAME_TIME = 10
MAX_WAIT_FOR_CAST = 35

# User-configurable start button detection values. Adjust if bot fails to detect the start button on new server loads.
START_BUTTON_COLOR = (127, 255, 147)
START_BUTTON_COLOR_TOLERANCE = 15
START_BUTTON_WAIT_TIMEOUT = 120

class FishSolBot:
    def __init__(self):
        self.is_running = False
        self.should_exit = False
        self.has_done_initial_pathing = False  
        
        # Change this to True!
        self.is_waiting_for_start_button = True 
        
        self.catch_count = 0
        self.max_catches = 1
        self.sell_loops = 22

    def colors_match(self, c1, c2, tol=TOLERANCE):
        return (abs(c1[0] - c2[0]) <= tol and 
                abs(c1[1] - c2[1]) <= tol and 
                abs(c1[2] - c2[2]) <= tol)

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
    
    def update_coordinates(self, resolution, speed="Normal", max_catches=1, sell_loops=22):
        global CAST_ROD_POS, BITE_INDICATOR_POS, BAR_COLOR_POS, CLAIM_FISH_POS, MINIGAME_REGION
        global CAMERA_SETUP_1, CAMERA_SETUP_2, OPEN_MERCHANT_1, OPEN_MERCHANT_2, SELECT_FISH
        global SELL_ALL_ON, SELL_ALL_OFF, CONFIRM_SELL, CLOSE_MERCHANT, START_BUTTON_POS
        
        global ALIGNMENT1, ALIGNMENT2, ALIGNMENT3, MERCHANT1, MERCHANT2, MERCHANT3, MERCHANT4, SPOT1

        self.max_catches = int(max_catches)
        self.sell_loops = int(sell_loops)

        if speed.upper() in PATHING_TIMINGS:
            timing = PATHING_TIMINGS[speed.upper()]
            ALIGNMENT1 = timing["ALIGNMENT1"]
            ALIGNMENT2 = timing["ALIGNMENT2"]
            ALIGNMENT3 = timing["ALIGNMENT3"]
            MERCHANT1 = timing["MERCHANT1"]
            MERCHANT2 = timing["MERCHANT2"]
            MERCHANT3 = timing["MERCHANT3"]
            MERCHANT4 = timing["MERCHANT4"]
            SPOT1 = timing["SPOT1"]
            print(f"[System] Pathing timings updated to {speed}")

        if resolution in COORDS:
            CAST_ROD_POS = COORDS[resolution]["FISHING"]["CAST_ROD"]
            BITE_INDICATOR_POS = COORDS[resolution]["FISHING"]["BITE_INDICATOR"]
            BAR_COLOR_POS = COORDS[resolution]["FISHING"]["BAR_COLOR"]
            CLAIM_FISH_POS = COORDS[resolution]["FISHING"]["CLAIM_FISH"]
            MINIGAME_REGION = COORDS[resolution]["FISHING"]["MINIGAME_REGION"]
            
            CAMERA_SETUP_1 = COORDS[resolution]["MERCHANT"]["CAMERA_SETUP_1"]
            CAMERA_SETUP_2 = COORDS[resolution]["MERCHANT"]["CAMERA_SETUP_2"]
            OPEN_MERCHANT_1 = COORDS[resolution]["MERCHANT"]["OPEN_MERCHANT_1"]
            OPEN_MERCHANT_2 = COORDS[resolution]["MERCHANT"]["OPEN_MERCHANT_2"]
            SELECT_FISH = COORDS[resolution]["MERCHANT"]["SELECT_FISH"]
            SELL_ALL_ON = COORDS[resolution]["MERCHANT"]["SELL_ALL_ON"]
            SELL_ALL_OFF = COORDS[resolution]["MERCHANT"]["SELL_ALL_OFF"]
            CONFIRM_SELL = COORDS[resolution]["MERCHANT"]["CONFIRM_SELL"]
            CLOSE_MERCHANT = COORDS[resolution]["MERCHANT"]["CLOSE_MERCHANT"]

            START_BUTTON_POS = COORDS[resolution]["START"]["START_BUTTON_POS"]
            print(f"[System] Coordinates updated to {resolution}")

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
        pydirectinput.moveTo(CAMERA_SETUP_1[0], CAMERA_SETUP_1[1])
        time.sleep(0.1)
        pydirectinput.moveTo(CAMERA_SETUP_1[0], CAMERA_SETUP_1[1] - 10, duration=0.2)
        time.sleep(0.22)
        pydirectinput.click()
        time.sleep(0.22)
        pydirectinput.moveTo(CAMERA_SETUP_2[0], CAMERA_SETUP_2[1])
        time.sleep(0.1)
        pydirectinput.moveTo(CAMERA_SETUP_2[0], CAMERA_SETUP_2[1] - 10, duration=0.2)
        time.sleep(0.22)
        pydirectinput.click()
        time.sleep(0.22)
        
        # Zoom all the way in
        for _ in range(16):
            if not self.is_running: return
            pyautogui.scroll(500)
            time.sleep(0.01)
        time.sleep(0.2)
        
        # Zoom out slightly to optimal position
        for _ in range(7):
            if not self.is_running: return
            pyautogui.scroll(-100)
            time.sleep(0.01)
        time.sleep(0.1)

    def walk_to_merchant(self):
        print("[Pathing] Walking to merchant...")
        pydirectinput.keyDown('w')
        pydirectinput.keyDown('a')
        time.sleep(ALIGNMENT1)
        if not self.is_running: 
            pydirectinput.keyUp('w'); pydirectinput.keyUp('a')
            return
            
        pydirectinput.keyUp('w')
        time.sleep(ALIGNMENT2)
        pydirectinput.keyUp('a')
        time.sleep(0.2)
        
        pydirectinput.keyDown('w')
        time.sleep(ALIGNMENT3)
        pydirectinput.keyUp('w')
        time.sleep(0.3)
        
        pydirectinput.keyDown('d')
        time.sleep(MERCHANT1)
        pydirectinput.keyUp('d')
        time.sleep(0.15)
        
        pydirectinput.keyDown('w')
        time.sleep(MERCHANT2)
        pydirectinput.keyDown('space')
        time.sleep(MERCHANT3)
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('space')
        time.sleep(0.3)
        
        pydirectinput.keyDown('a')
        pydirectinput.keyDown('w')
        time.sleep(MERCHANT4)
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('w')
        time.sleep(0.2)

    def sell_fish_logic(self):
        print("[Auto-Sell] Opening merchant UI...")
        pydirectinput.keyDown('e')
        time.sleep(0.3)
        pydirectinput.keyUp('e')
        time.sleep(0.3)
        pydirectinput.moveTo(OPEN_MERCHANT_1[0], OPEN_MERCHANT_1[1] - 50)
        pydirectinput.moveTo(OPEN_MERCHANT_1[0], OPEN_MERCHANT_1[1], duration=0.2)
        time.sleep(0.1)
        pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
        time.sleep(0.2)

        while True:
            if not self.is_running: return
            
            pydirectinput.moveTo(OPEN_MERCHANT_2[0], OPEN_MERCHANT_2[1] - 10)
            pydirectinput.moveTo(OPEN_MERCHANT_2[0], OPEN_MERCHANT_2[1], duration=0.2)
            time.sleep(0.1)

            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(0.2)
            
            try:
                current_color = pyautogui.pixel(*OPEN_MERCHANT_2)
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
            if not self.is_running: return
            
            pydirectinput.moveTo(SELECT_FISH[0], SELECT_FISH[1] - 50)
            pydirectinput.moveTo(SELECT_FISH[0], SELECT_FISH[1], duration=0.2)
            pydirectinput.moveTo(SELECT_FISH[0] - 10, SELECT_FISH[1], duration=0.1)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(0.2)
            
            pydirectinput.moveTo(SELL_ALL_ON[0], SELL_ALL_ON[1] - 50)
            pydirectinput.moveTo(SELL_ALL_ON[0], SELL_ALL_ON[1], duration=0.2)
            pydirectinput.moveTo(SELL_ALL_ON[0] - 10, SELL_ALL_ON[1], duration=0.2)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(0.3)
            
            pydirectinput.moveTo(CONFIRM_SELL[0], CONFIRM_SELL[1] - 50)
            pydirectinput.moveTo(CONFIRM_SELL[0], CONFIRM_SELL[1], duration=0.2)
            pydirectinput.moveTo(CONFIRM_SELL[0] - 10, CONFIRM_SELL[1], duration=0.2)
            time.sleep(0.1)
            pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
            time.sleep(1.0)

    def walk_back_to_spot(self):
        print("[Pathing] Walking from merchant to fishing spot...")
        pydirectinput.moveTo(CLOSE_MERCHANT[0], CLOSE_MERCHANT[1]-10)
        time.sleep(0.2)
        pydirectinput.moveTo(CLOSE_MERCHANT[0], CLOSE_MERCHANT[1], duration=0.2)
        time.sleep(0.1)
        pydirectinput.mouseDown(); time.sleep(0.05); pydirectinput.mouseUp()
        time.sleep(0.2)
        
        pydirectinput.keyDown('a')
        time.sleep(SPOT1)
        pydirectinput.keyUp('a')

    def do_pathing_routine(self, do_sell=True):
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
        self.catch_count = 0
        print("=== PATHING COMPLETE. READY TO FISH ===")

    def play_fishing_cycle(self):
        self.focus_roblox()

        # 0A. New Server Load Wait / Start Button Verification
        if self.is_waiting_for_start_button:
            if START_BUTTON_POS == (0, 0):
                print("[Fishing Bot] Warning: Start coordinates default. Bypassing check.")
                self.is_waiting_for_start_button = False
                return

            print("[Fishing Bot] Waiting 10 seconds for Roblox to load before checking for Start button...")
            for _ in range(20):  # 10 seconds, checking is_running every 0.5s
                if not self.is_running: return
                time.sleep(0.5)

            print("[Fishing Bot] Checking for Start button...")
            wait_start = time.time()
            button_clicked = False

            # Wait up to 60 seconds for the start button to appear
            while time.time() - wait_start < 60:
                if not self.is_running: return # Exit if user pauses
                
                try:
                    current_color = pyautogui.pixel(*START_BUTTON_POS)
                    print(f"[Fishing Bot] Detected color at start button: {current_color}")
                    print(str(START_BUTTON_POS))
                    if self.colors_match(current_color, START_BUTTON_COLOR, tol=START_BUTTON_COLOR_TOLERANCE):
                        print("[Fishing Bot] Play/Start Button detected! Waiting 2 seconds before clicking...")
                        time.sleep(2.0)
                        
                        pydirectinput.moveTo(START_BUTTON_POS[0], START_BUTTON_POS[1] - 20)
                        time.sleep(0.1)
                        pydirectinput.moveTo(*START_BUTTON_POS, duration=0.2)
                        time.sleep(0.1)
                        pydirectinput.mouseDown()
                        time.sleep(0.05)
                        pydirectinput.mouseUp()
                        
                        time.sleep(3.0) # Give the game 3 seconds to render the player on the map
                        button_clicked = True
                        break # Successfully clicked, break out of the waiting loop
                except Exception:
                    pass
                
                time.sleep(0.5) # Check twice a second

            if not button_clicked:
                print("[Fishing Bot] Start button not found or timed out. Assuming already in-game.")

            # Disable the start button check for the rest of the session
            self.is_waiting_for_start_button = False
            self.has_done_initial_pathing = False
            return

        # 0B. Initial Pathing (Runs ONCE when joining a new server)
        if not self.has_done_initial_pathing:
            print("Detected first run! Walking to fishing spot...")
            self.do_pathing_routine(do_sell=False) 
            if self.is_running:
                self.has_done_initial_pathing = True
            return

        # 0C. Auto-Sell Trigger
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
        print(f"--> Fish caught successfully! Server tally: {self.catch_count}/{self.max_catches}")

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