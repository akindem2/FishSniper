import time
import pyautogui
import keyboard
from PIL import ImageGrab

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

class FishSolBot:
    def __init__(self):
        self.is_running = False
        self.should_exit = False

    def colors_match(self, c1, c2, tol=TOLERANCE):
        """Helper to check if two RGB colors are similar."""
        return (abs(c1[0] - c2[0]) <= tol and 
                abs(c1[1] - c2[1]) <= tol and 
                abs(c1[2] - c2[2]) <= tol)

    def play_fishing_cycle(self):
        """The main fishing loop logic extracted from the AHK DoMouseMove."""
        
        # 1. Cast the fishing rod
        pyautogui.moveTo(*CAST_ROD_POS)
        time.sleep(0.05)
        pyautogui.click()
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

        # 4. Claim the Fish
        print("Mini-game finished. Claiming fish...")
        time.sleep(0.3)
        pyautogui.moveTo(*CLAIM_FISH_POS)
        time.sleep(0.7)
        pyautogui.click()
        time.sleep(0.3)

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