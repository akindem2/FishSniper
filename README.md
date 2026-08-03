# FishSniper

FishSniper is a powerful, automated fishing tool designed for Roblox, featuring a modern GUI, a Discord biome scanner with configurable priority tiers, and smart selling logic.

## Features

- **Automated Fishing**: Intelligent fishing logic that detects bites and plays the mini-game automatically.
- **Smart Selling**: Automatically walks to the merchant and sells fish when inventory is full or limits are reached, and always sells off any existing inventory right after joining a new server, before fishing begins.
- **Discord Biome Scanner**: Scans Discord channels for specific biome announcements and automatically joins the corresponding server. Supports direct private-server links, share-code links (resolved via Roblox's API), and direct game-instance joins — and prefers a `roblox://` protocol string over a plain web link when a message contains both.
- **Configurable Priority Tiers**: A drag-and-drop tier board (the Priority tab) lets you rank biomes into tiers, where Tier 1 is the highest priority. If a higher-tier biome is detected while you're already fishing a lower-tier one, FishSniper immediately abandons the current session and joins the higher-priority biome instead. Every enabled biome must be assigned a tier before FishSniper can start.
- **Webhook Integration**: Rich Discord embeds with real-time updates — biome joined/ended, the server link used, whether a join was a priority interrupt, a biome thumbnail, and how long the biome lasted. Joining notifications include a screenshot taken just after you load in, and any biome can optionally be configured to send a second, delayed "check-in" screenshot as well. Optionally @-pings a configured Discord user ID when joining Glitched, Dreamspace, or Cyberspace. A "Test" button in Settings lets you verify your webhook works before relying on it.
- **Failsafe Alerts & Recovery**: If no bite is detected within the wait window, FishSniper sends a Discord alert with a screenshot so you can check in remotely, and automatically switches to a different pathing profile after repeated failures — a switch that now carries over to the next server instead of resetting on every join.
- **Custom UI**: A dark-themed, card-based interface built with `CustomTkinter`, with biome thumbnails throughout and color-coded log messages in the Dashboard for easier troubleshooting.
- **Flexible Configuration**: Adjustable pathing speeds (Vip / Non-Vip), resolution support (1080p, 1440p, 1366x768), and per-biome selection across 13 biomes (Rainy, Snowy, Windy, Hell, Heaven, Corruption, Starfall, Sand Storm, Null, Glitched, Dreamspace, Cyberspace, Singularity).
- **Persistent Settings**: All settings — credentials, biome selection, priority tiers, check-in screenshot preferences, and server mappings — are saved to `%LOCALAPPDATA%\FishSniper\settings.json` and reloaded automatically on the next launch.

## App Tabs

- **Dashboard** — live application logs, color-coded by which part of the app they came from.
- **Settings** — Roblox cookie, Discord user token, Discord webhook URL (with a Test button), and the Discord user ID to ping on priority biome joins.
- **Biomes** — toggle which biomes FishSniper should watch for, and optionally enable a delayed check-in screenshot (with a configurable delay) for any of them.
- **Priority** — drag enabled biomes into tiers to control which ones interrupt which.
- **Servers** — map Discord servers/channels/categories to scan for biome announcements.

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
2. (Optional) Place an `icon.ico` file next to `FishSniper.spec` if you want the built executable to use a custom icon.
3. Build the executable:
   ```bash
   pyinstaller FishSniper.spec
   ```
4. The executable will be generated in the `dist` folder.

## Disclaimer

This tool is for educational and personal use only. Use it at your own risk. Automated tools can violate terms of service; ensure you understand the risks involved before using.

## License

This project is licensed under the terms of the license included in the repository.