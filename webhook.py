import requests

webhook_url = " "

def send_join_webhook(biome):
    embed = {
        "title": f"Joining {biome} biome",
        "color": 0x1c2c87,
    }