import json
import requests
import discord
from discord_scanner import biome_thumbnail_url, biome_should_ping, biome_embed_color


def _format_duration(seconds):
    """Formats a duration in seconds as e.g. '45s', '3m 12s', or '1h 02m 03s'."""
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class Webhook:
    def __init__(self, url):
        self.url = url

    def _send(self, embed, content=None, files=None):
        if not self.url or not self.url.startswith("http"):
            return False

        data = {"embeds": [embed]}
        if content:
            data["content"] = content

        try:
            if files:
                # Multipart upload: JSON payload goes in the payload_json field
                # alongside the file part(s), since a plain JSON body can't
                # carry binary attachments.
                response = requests.post(
                    self.url, data={"payload_json": json.dumps(data)}, files=files, timeout=10
                )
            else:
                # Short timeout to avoid blocking the caller too long
                response = requests.post(self.url, json=data, timeout=3)
            response.raise_for_status()
            print(f"[Webhook] Successfully sent: {embed.get('title')}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"[Webhook Error] Failed to send webhook: {e}")
            return False

    def send_test(self):
        """Sends a lightweight test embed so a user can confirm their webhook
        URL actually works before relying on it. Returns True/False so the
        UI's Test button can report real success/failure rather than just
        assuming it worked."""
        return self._send({
            "title": "FishSniper Webhook Test",
            "description": "If you can see this, your webhook is configured correctly!",
            "color": discord.Color.purple().value,
        })

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

    def send_biome_joined(self, biome, join_url=None, is_priority_interrupt=False, ping_user_id=None,
                           screenshot_bytes=None):
        fields = []
        if join_url:
            fields.append({"name": "Server Link", "value": f"`{join_url}`", "inline": False})
        if is_priority_interrupt:
            fields.append({"name": "Priority Interrupt", "value": "Jumped the queue for this biome", "inline": False})

        embed = {
            "title": f"Joining: {biome}",
            "color": biome_embed_color(biome) or discord.Color.blue().value,
            "thumbnail": {"url": biome_thumbnail_url(biome)},
        }
        if fields:
            embed["fields"] = fields

        files = None
        if screenshot_bytes:
            filename = "join_screenshot.jpg"
            embed["image"] = {"url": f"attachment://{filename}"}
            files = {"file": (filename, screenshot_bytes, "image/jpeg")}

        content = None
        if ping_user_id and biome_should_ping(biome):
            content = f"<@{ping_user_id}>"

        self._send(embed, content=content, files=files)

    def send_screenshot(self, image_bytes, title="Screenshot", filename="screenshot.jpg"):
        """Uploads a standalone screenshot embed, independent of the Joined
        embed — e.g. the delayed Cyberspace check-in shot."""
        embed = {
            "title": title,
            "color": discord.Color.teal().value,
            "image": {"url": f"attachment://{filename}"},
        }
        files = {"file": (filename, image_bytes, "image/jpeg")}
        self._send(embed, files=files)

    def send_failsafe_triggered(self, failsafe_count, switched_path=False, screenshot_bytes=None,
                                 triggered_sell=False):
        """Alerts when no bite was detected within the wait window and a
        failsafe recovery kicked in — useful for spotting a stuck or
        misconfigured session remotely."""
        description = f"No bite detected — failsafe {failsafe_count}/2 on this server."
        if switched_path:
            description += " Switched to the next path profile."
        if triggered_sell:
            description += " 5 failsafes in a row — selling off inventory and restarting the fishing cycle."

        embed = {
            "title": "Repeated Failsafes — Selling & Restarting" if triggered_sell else "No-Bite Failsafe Triggered",
            "description": description,
            "color": discord.Color.red().value if triggered_sell else discord.Color.orange().value,
        }

        files = None
        if screenshot_bytes:
            filename = "failsafe_screenshot.jpg"
            embed["image"] = {"url": f"attachment://{filename}"}
            files = {"file": (filename, screenshot_bytes, "image/jpeg")}

        self._send(embed, files=files)

    def send_item_purchased(self, item_name, quantity):
        self._send({
            "title": "Item Purchased",
            "description": f"Bought {quantity}x {item_name}.",
            "color": discord.Color.gold().value,
        })

    def send_biome_ended(self, biome, duration_seconds=None):
        embed = {
            "title": f"Biome Ended: {biome}",
            "description": "Resuming background scan.",
            "color": biome_embed_color(biome) or discord.Color.orange().value,
        }
        if duration_seconds is not None:
            embed["fields"] = [{
                "name": "Duration",
                "value": _format_duration(duration_seconds),
                "inline": True,
            }]
        self._send(embed)

    def send_priority_interrupt(self, old_biome, new_biome):
        self._send({
            "title": f"Priority Interrupt: {new_biome}",
            "color": biome_embed_color(new_biome) or discord.Color.gold().value,
            "fields": [{"name": "Abandoning", "value": old_biome, "inline": False}],
        })