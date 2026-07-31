# FishSniper

FishSniper is a powerful, automated fishing tool designed for Roblox, featuring a modern GUI, a Discord biome scanner with configurable priority tiers, and smart selling logic.

## Features

- **Automated Fishing**: Intelligent fishing logic that detects bites and plays the mini-game automatically.
- **Smart Selling**: Automatically walks to the merchant and sells fish when inventory is full or limits are reached.
- **Discord Biome Scanner**: Scans Discord channels for specific biome announcements and automatically joins the corresponding server. Supports direct private-server links, share-code links (resolved via Roblox's API), and direct game-instance joins — and prefers a `roblox://` protocol string over a plain web link when a message contains both.
- **Configurable Priority Tiers**: A drag-and-drop tier board (the Priority tab) lets you rank biomes into tiers, where Tier 1 is the highest priority. If a higher-tier biome is detected while you're already fishing a lower-tier one, FishSniper immediately abandons the current session and joins the higher-priority biome instead. Every enabled biome must be assigned a tier before FishSniper can start.
- **Webhook Integration**: Rich Discord embeds with real-time updates — biome joined/ended, the server link used, whether a join was a priority interrupt, and a biome thumbnail. Optionally @-pings a configured Discord user ID when joining Glitched, Dreamspace, or Cyberspace.
- **Custom UI**: A dark-themed, card-based interface built with `CustomTkinter`, with biome thumbnails throughout.
- **Flexible Configuration**: Adjustable pathing speeds (Vip / Non-Vip), resolution support (1080p, 1440p, 1366x768), and per-biome selection across 13 biomes (Rainy, Snowy, Windy, Hell, Heaven, Corruption, Starfall, Sand Storm, Null, Glitched, Dreamspace, Cyberspace, Singularity).
- **Persistent Settings**: All settings — credentials, biome selection, priority tiers, and server mappings — are saved to `%LOCALAPPDATA%\FishSniper\settings.json` and reloaded automatically on the next launch.

## App Tabs

- **📋 Dashboard** — live application logs.
- **⚙️ Settings** — Roblox cookie, Discord user token, Discord webhook URL, and the Discord user ID to ping on priority biome joins.
- **🌍 Biomes** — toggle which biomes FishSniper should watch for.
- **🏆 Priority** — drag enabled biomes into tiers to control which ones interrupt which.
- **💬 Servers** — map Discord servers/channels/categories to scan for biome announcements.

## Getting Started

### Prerequisites

- Python 3.10+
- Roblox (logged in)
- Required Python packages:
  ```bash
  pip install customtkinter pydirectinput pyautogui requests discord.py-self pillow pywin32
  ```

### Running the App

To start FishSniper, simply run the `main.py` script:

```bash
python main.py
```

## Building from Source

If you want to create a standalone executable for Windows, you can use PyInstaller with the provided `FishSniper.spec` file:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Build the executable:
   ```bash
   pyinstaller FishSniper.spec
   ```
3. The executable will be generated in the `dist` folder.

## Disclaimer

This tool is for educational and personal use only. Use it at your own risk. Automated tools can violate terms of service; ensure you understand the risks involved before using.

## 📄 License

This project is licensed under the terms of the license included in the repository.
