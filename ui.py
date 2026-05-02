import customtkinter as ctk


class FishSniperUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FishSniper")
        self.geometry("400x300")

        self.label = ctk.CTkLabel(self, text="Welcome to FishSniper!")
        self.label.pack(pady=20)

        self.start_button = ctk.CTkButton(self, text="Start Sniping", command=self.start_sniping)
        self.start_button.pack(pady=10)

    def start_sniping(self):
        # Placeholder for starting the sniping process
        print("Starting FishSniper...")

app = FishSniperUI()
app.mainloop()