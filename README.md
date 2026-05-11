# FishSniper 🎣

FishSniper is a powerful, automated fishing tool designed for Roblox, featuring a modern GUI, biome scanning, and smart selling logic.

## ✨ Features

- **Automated Fishing**: Intelligent fishing logic that detects bites and plays the mini-game automatically.
- **Smart Selling**: Automatically walks to the merchant and sells fish when inventory is full or limits are reached.
- **Discord Biome Scanner**: Scans Discord channels for specific biome announcements and automatically joins the corresponding private servers.
- **Webhook Integration**: Get real-time updates on your fishing progress, including biomes joined and fish caught.
- **Custom UI**: Modern and easy-to-use interface built with `CustomTkinter`.
- **Flexible Configuration**: Adjustable pathing speeds, resolution support (1440p), and customizable biome monitoring.

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Roblox (logged in)
- Required Python packages:
  ```bash
  pip install customtkinter pydirectinput pyautogui requests discord.py-self
  ```

### Running the App

To start FishSniper, simply run the `main.py` script:

```bash
python main.py
```

## 🛠️ Building from Source

If you want to create a standalone executable for Windows, you can use PyInstaller with the provided `.spec` file:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Build the executable:
   ```bash
   pyinstaller FishSniper.spec
   ```
3. The executable will be generated in the `dist` folder.

## ⚠️ Disclaimer

This tool is for educational and personal use only. Use it at your own risk. Automated tools can violate terms of service; ensure you understand the risks involved before using.

## 📄 License

This project is licensed under the terms of the license included in the repository.
