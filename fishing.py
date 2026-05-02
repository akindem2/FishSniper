import time
import pyautogui
import pydirectinput
import keyboard
from PIL import ImageGrab
import win32gui
import win32process
import win32com.client
import pygetwindow as gw

# --- 1080p COORDINATES FROM THE AHK SCRIPT ---
CAST_ROD_POS = (862, 843)
BITE_INDICATOR_POS = (1176, 836)
BAR_COLOR_POS = (955, 767)
CLAIM_FISH_POS = (1113, 342)

# Mini-game search area bounding box: (left_X, top_Y, width, height)
# Original AHK box: 757, 762 to 1161, 782
MINIGAME_REGION = (757, 762, 1161 - 757, 782 - 762)

# Thresholds/Timeouts
TOLERANCE = 10  # RGB color variance allowed
MAX_WAIT_FOR_BITE = 35  # Max seconds to wait for a fish to bite
MAX_MINIGAME_TIME = 10  # Max seconds the minigame should last

# --- 1440p COORDINATES FROM THE AHK SCRIPT ---
CAST_ROD_POS = (1161, 1124)
BITE_INDICATOR_POS = (1536, 1119)
BAR_COLOR_POS = (1261, 1033)
CLAIM_FISH_POS = (1457, 491)

# Mini-game search area bounding box: (left_X, top_Y, width, height)
# Original AHK box: 1043, 1033 to 1519, 1058
MINIGAME_REGION = (1043, 1033, 1519 - 1043, 1058 - 1033) # Evaluates to (1043, 1033, 476, 25)

class FishSolBot:
    def __init__(self):
        self.is_running = False
        self.should_exit = False

    def colors_match(self, c1, c2, tol=TOLERANCE):
        """Helper to check if two RGB colors are similar."""
        return (abs(c1[0] - c2[0]) <= tol and 
                abs(c1[1] - c2[1]) <= tol and 
                abs(c1[2] - c2[2]) <= tol)

    def find_window_hwnd(self):
        ROBLOX_CLASS = "WINDOWSCLIENT"

        def callback(hwnd, result):
            if win32gui.IsWindowVisible(hwnd):
                if win32gui.GetClassName(hwnd) == ROBLOX_CLASS:
                    result.append(hwnd)

        result = []
        win32gui.EnumWindows(callback, result)
        return result[0] if result else None

    def focus_hwnd(self, hwnd):
        if hwnd is None:
            print("No HWND to focus")
            return False

        # 1. Restore if minimized
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # 2. Bypass focus-stealing prevention
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys('%')  # Simulate ALT press

        # 3. Attach input threads
        try:
            fg = win32gui.GetForegroundWindow()
            fg_thread = win32process.GetWindowThreadProcessId(fg)[0]
            target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]

            win32process.AttachThreadInput(fg_thread, target_thread, True)
            win32gui.SetForegroundWindow(hwnd)
            win32process.AttachThreadInput(fg_thread, target_thread, False)
            return True
        
    def focus_roblox(self):
        try:
            # Find the Roblox window and bring it to the front safely
            roblox = gw.getWindowsWithTitle('Roblox')[0]
            roblox.activate()
        except Exception as e:
            print("Could not pull window to front. Please click it manually.")

        except Exception as e:
            print("Focus failed:", e)
            return False

    def play_fishing_cycle(self):
        self.focus_roblox()
        """The main fishing loop logic extracted from the AHK DoMouseMove."""
        
        # 1. Cast the fishing rod
        # Move near the button first
        pydirectinput.moveTo(CAST_ROD_POS[0], CAST_ROD_POS[1] - 50)
        time.sleep(0.1)

        # Slide onto the button using DirectX input
        pydirectinput.moveTo(CAST_ROD_POS[0], CAST_ROD_POS[1], duration=0.2)
        time.sleep(0.1)

        pydirectinput.mouseDown()
        time.sleep(0.05)
        pydirectinput.mouseUp()

        time.sleep(0.3)
        
        print("Waiting for bite...")
        start_wait = time.time()
        bar_color = None
        
        # 2. Wait for the White Pixel indicating a bite
        while time.time() - start_wait < MAX_WAIT_FOR_BITE:
            if not self.is_running: return # Exit early if paused
            
            # Check for white pixel at specific coordinate
            pixel = pyautogui.pixel(*BITE_INDICATOR_POS)
            if self.colors_match(pixel, (255, 255, 255), tol=5):
                # We got a bite! Quickly sample the bar color
                pyautogui.moveTo(950, 880)
                time.sleep(0.05)
                bar_color = pyautogui.pixel(*BAR_COLOR_POS)
                print(f"Bite! Bar color detected: {bar_color}")
                break
            
            time.sleep(0.05)
            
        if not bar_color:
            print("Fishing timeout or no bite detected. Retrying...")
            return

        # 3. Play the Mini-Game
        print("Playing mini-game...")
        minigame_start = time.time()
        
        while time.time() - minigame_start < MAX_MINIGAME_TIME:
            if not self.is_running: return # Exit early if paused
            
            # Take a rapid screenshot of just the minigame bar
            img = pyautogui.screenshot(region=MINIGAME_REGION)
            pixels = img.load()
            
            bar_found = False
            # Scan image stepping by 3 pixels to improve performance
            for x in range(0, img.width, 3):
                for y in range(0, img.height, 3):
                    if self.colors_match(pixels[x, y], bar_color):
                        bar_found = True
                        break
                if bar_found:
                    break
            
            # Normal Detection Logic: If we CANNOT find the bar color in the zone,
            # it means the bar is falling out. Click to pull it back in.
            if not bar_found:
                pyautogui.click()
                time.sleep(0.01) # Tiny sleep to prevent clicking too fast

        # SAFEGUARD: Release the mouse just in case the minigame loop left it held down
        pydirectinput.mouseUp()
        
        # 4. Claim the Fish
        print("Mini-game finished. Waiting for Claim button to spawn...")
        
        # Wait 1.5 seconds to ensure the minigame animation is 100% over 
        # and the Claim button is fully rendered on screen
        time.sleep(1.5)
        
        # Teleport to the top-left corner of your screen to "reset" the mouse
        pydirectinput.moveTo(10, 10)
        time.sleep(0.1)
        
        # Now teleport 50 pixels above the Claim button
        pydirectinput.moveTo(CLAIM_FISH_POS[0], CLAIM_FISH_POS[1] - 50)
        time.sleep(0.1)
        
        # Slide onto the Claim button to trigger the hover state
        pydirectinput.moveTo(*CLAIM_FISH_POS, duration=0.2)
        time.sleep(0.3)
        
        # Hardware-level Click
        pydirectinput.mouseDown()
        time.sleep(0.1)
        pydirectinput.mouseUp()
        
        time.sleep(0.5)

    def start(self):
        """Starts the background keyboard listeners and the main loop."""
        print("--- Python FishSol Script ---")
        print("Press F1 to Start")
        print("Press F2 to Pause")
        print("Press F3 to Exit")
        
        # Bind Hotkeys
        keyboard.add_hotkey('f1', self.toggle_on)
        keyboard.add_hotkey('f2', self.toggle_off)
        keyboard.add_hotkey('f3', self.exit_script)

        # Main Loop
        while not self.should_exit:
            if self.is_running:
                self.play_fishing_cycle()
            else:
                time.sleep(0.1) # Sleep to save CPU when paused

    def toggle_on(self):
        if not self.is_running:
            print("[System] Macro Started!")
            self.is_running = True

    def toggle_off(self):
        if self.is_running:
            print("[System] Macro Paused!")
            self.is_running = False

    def exit_script(self):
        print("[System] Exiting Script...")
        self.is_running = False
        self.should_exit = True

if __name__ == "__main__":
    # Ensure pyautogui processes clicks quickly without default delays
    pyautogui.PAUSE = 0.0  
    bot = FishSolBot()
    bot.start()