import customtkinter as ctk
from fishing import FishSolBot
import threading

fish_loop = FishSolBot()

class FishSniperUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FishSniper")
        self.geometry("400x300")

        self.label = ctk.CTkLabel(self, text="Welcome to FishSniper!")
        self.label.pack(pady=20)

        self.start_button = ctk.CTkButton(self, text="Start Fishing", command=self.start_sniping)
        self.start_button.pack(pady=10)

        self.stop_button = ctk.CTkButton(self, text="Stop Fishing", command=self.stop_sniping)
        self.stop_button.pack(pady=10)

        # Start the bot loop in the background
        threading.Thread(target=fish_loop.start, daemon=True).start()

    def start_sniping(self):
        fish_loop.toggle_on()
        print("Fishing started")

    def stop_sniping(self):
        fish_loop.toggle_off()
        print("Fishing stopped")

app = FishSniperUI()
app.mainloop()