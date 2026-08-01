import requests
import discord
from discord_scanner import biome_thumbnail_url, biome_should_ping


class Webhook:
    def __init__(self, url):
        self.url = url

    def _send(self, embed, content=None):
        if not self.url or not self.url.startswith("http"):
            return

        data = {"embeds": [embed]}
        if content:
            data["content"] = content

        try:
            # Short timeout to avoid blocking the caller too long
            response = requests.post(self.url, json=data, timeout=3)
            response.raise_for_status()
            print(f"[Webhook] Successfully sent: {embed.get('title')}")
        except requests.exceptions.RequestException as e:
            print(f"[Webhook Error] Failed to send webhook: {e}")

    def send_app_started(self):
        self._send({
            "title": "FishSniper Started",
            "description": "Scanning for biomes...",
            "color": discord.Color.green().value,
        })

    def send_app_stopped(self):
        self._send({
            "title": "FishSniper Stopped",
            "description": "All systems paused.",
            "color": discord.Color.red().value,
        })

    def send_biome_joined(self, biome, join_url=None, is_priority_interrupt=False, ping_user_id=None):
        fields = []
        if join_url:
            fields.append({"name": "Server Link", "value": f"`{join_url}", "inline": False})
        if is_priority_interrupt:
            fields.append({"name": "Priority Interrupt", "value": "Jumped the queue for this biome", "inline": False})

        embed = {
            "title": f"Joining: {biome}",
            "color": discord.Color.blue().value,
            "thumbnail": {"url": biome_thumbnail_url(biome)},
        }
        if fields:
            embed["fields"] = fields

        content = None
        if ping_user_id and biome_should_ping(biome):
            content = f"<@{ping_user_id}>"

        self._send(embed, content=content)

    def send_biome_ended(self, biome):
        self._send({
            "title": f"Biome Ended: {biome}",
            "description": "Resuming background scan.",
            "color": discord.Color.orange().value,
        })

    def send_priority_interrupt(self, old_biome, new_biome):
        self._send({
            "title": f"Priority Interrupt: {new_biome}",
            "color": discord.Color.gold().value,
            "fields": [{"name": "Abandoning", "value": old_biome, "inline": False}],
        })
