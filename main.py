import ui
import fishing

def main():
    # Launches UI which coordinates state variables & starting background loops
    app = ui.FishSniperUI()
    
    ctk_instance = ui.ctk
    ctk_instance.set_appearance_mode("dark")
    ctk_instance.set_default_color_theme("blue")
    
    app.mainloop()

if __name__ == "__main__":
    main()