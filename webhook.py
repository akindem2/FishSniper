import requests
import discord

class Webhook:
    def __init__(self, url):
        self.url = url

    def _send_payload(self, content, color):
        if not self.url or not self.url.startswith("http"):
            return
            
        data = {
            "embeds": [
                {
                    "description": content,
                    "color": color
                }
            ]
        }
        try:
            # Short timeout to avoid blocking the caller too long
            response = requests.post(self.url, json=data, timeout=3)
            response.raise_for_status()
            print(f"[Webhook] Successfully sent: {content}")
        except requests.exceptions.RequestException as e:
            print(f"[Webhook Error] Failed to send webhook: {e}")

    def send_app_started(self):
        self._send_payload("🟢 **FishSniper has started!** Scanning for biomes...", discord.Color.green().value)

    def send_app_stopped(self):
        self._send_payload("🔴 **FishSniper has stopped!** All systems paused.", discord.Color.red().value)

    def send_biome_joined(self, biome):
        self._send_payload(f"🎣 **Joined Biome:** `{biome}`\nFishSniper is actively fishing!", discord.Color.blue().value)

    def send_biome_ended(self, biome):
        self._send_payload(f"⏳ **Biome Ended:** `{biome}`\nResuming background scan.", discord.Color.orange().value)