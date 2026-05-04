import customtkinter as ctk
from fishing import FishSolBot
import threading

fish_loop = FishSolBot()

BIOMES = ["Rainy", "Snowy", "Windy", "Hell", "Heaven", "Corruption", "Starfall", "Corruption", "Sand Storm", "Null", "Glitched", "Dreamspace", "Cyberspace"]

class FishSniperUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FishSniper")
        self.geometry("400x850")

        self.title_label = ctk.CTkLabel(self, text="Welcome to FishSniper!")
        self.title_label.pack(pady=20)

        self.start_button = ctk.CTkButton(self, text="Start", command=self.start_sniping)
        self.start_button.pack(pady=10)

        self.pause_button = ctk.CTkButton(self, text="Pause", command=self.pause_sniping)
        self.pause_button.pack(pady=10)

        self.stop_button = ctk.CTkButton(self, text="Stop", command=self.stop_sniping)
        self.stop_button.pack(pady=10)

        self.res_dropdown = ctk.CTkOptionMenu(self, values=["1080p", "1440p", "1366x768"], command=self.save_settings)
        self.res_dropdown.pack(pady=10)

        self.rb_token_entry = ctk.CTkEntry(self, placeholder_text="Enter your Roblox token")
        self.rb_token_entry.pack(pady=10)

        self.ds_token_entry = ctk.CTkEntry(self, placeholder_text="Enter your Discord token")
        self.ds_token_entry.pack(pady=10)

        self.biomes_label = ctk.CTkLabel(self, text="Select Biomes:")
        self.biomes_label.pack(pady=10)

        for biome in BIOMES:
            biome_option = ctk.CTkCheckBox(self, text = biome)
            biome_option.pack(pady=1)

        # Start the bot loop in the background
        threading.Thread(target=fish_loop.start, daemon=True).start()

    def start_sniping(self):
        fish_loop.toggle_on()
        print("Fishing started")

    def pause_sniping(self):
        fish_loop.toggle_off()
        print("Fishing paused")

    def stop_sniping(self):
        fish_loop.stop()
        print("Fishing stopped")

    def save_settings(self):
        global res, biome, ds_token, rb_token
        rb_token = self.rb_token_entry.get()
        ds_token = self.ds_token_entry.get()
        res = self.res_dropdown.get()
        biome = self.biomes_dropdown.get()

        # Save the settings to a file or use them as needed
        print(f"Roblox Token: {rb_token}")
        print(f"Discord Token: {ds_token}")
        print(f"Selected Resolution: {res}")
        print(f"Selected Biome: {biome}")


app = FishSniperUI()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app.mainloop()