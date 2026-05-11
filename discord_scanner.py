import discord
import re
import urllib.parse
import requests
import time
import os

URL_REGEX = r"https?://[^\s)]+"
MD_LINK_REGEX = r"\[.*?\]\((https?://[^\s)]+)\)"

# If you ever support multiple games, make this configurable.
DEFAULT_PLACE_ID = "15532962292"  # FishSol placeId (update if needed)


def extract_text(message):
    parts = [message.content or ""]
    for embed in message.embeds:
        if embed.title:
            parts.append(embed.title)
        if embed.description:
            parts.append(embed.description)
        for field in embed.fields:
            parts.append(field.name)
            parts.append(field.value)
    return " ".join(parts).lower()


def extract_urls(message):
    urls = []

    def scan_str(s):
        if not s:
            return
        urls.extend(re.findall(URL_REGEX, s))
        urls.extend(re.findall(MD_LINK_REGEX, s))

    scan_str(message.content)
    for embed in message.embeds:
        scan_str(embed.title)
        scan_str(embed.description)
        for field in embed.fields:
            scan_str(field.name)
            scan_str(field.value)
        if embed.url:
            urls.append(embed.url)
    if hasattr(message, "components") and message.components:
        for row in message.components:
            for component in row.children:
                if hasattr(component, "url") and component.url:
                    urls.append(component.url)
    return list(dict.fromkeys(urls))


def resolve_private_server_from_place(place_id):
    """
    Fallback resolver:
    Queries Roblox's private server list for the given place_id
    and returns the first available invite code (joinCode/linkCode).
    This assumes you're joining your own private server for that game.
    """
    try:
        url = f"https://games.roblox.com/v1/games/{place_id}/private-servers"
        res = requests.get(url).json()
        servers = res.get("data", [])

        if not servers:
            print(f"[Resolver] No private servers found for placeId={place_id}")
            return None

        # Take the first server (your own / primary PS)
        server = servers[0]
        invite = server.get("joinCode") or server.get("linkCode")

        if invite:
            print(
                f"[Resolver] Using private server '{server.get('name', 'Unnamed')}' "
                f"→ invite code {invite}"
            )
            return invite

        print("[Resolver] First private server has no invite code.")
        return None

    except Exception as e:
        print(f"[Resolver] Error resolving private server: {e}")
        return None

def resolve_and_launch_with_cookie(raw_url, cookie):
    """
    Parses any Roblox link (including the new share-links wrapper) 
    and uses the Cookie + AuthTicket API to launch securely.
    """
    print(f"[Roblox Launcher] Processing link: {raw_url}")
    
    place_id = None
    link_code = None
    share_code = None
    
    # 1. Check for standard Private Server Link
    direct_match = re.search(r"games/(\d+)(?:/.*?)?[?&]privateServerLinkCode=([\w-]+)", raw_url, re.IGNORECASE)
    if direct_match:
        place_id = direct_match.group(1)
        link_code = direct_match.group(2)
    else:
        # 2. Check for the new Share Code format
        share_match = re.search(r"code=([a-f0-9]+)", raw_url, re.IGNORECASE)
        if share_match:
            share_code = share_match.group(1)
            print(f"[Roblox Launcher] Detected Share Code: {share_code}. Resolving via API...")
            try:
                # Use the resolving API present in your original sniper code
                res = requests.post(f"https://api-priv.vexsys.site/api/endpoints/roblox/resolve-link?linkId={share_code}", timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    place_id = data.get("placeId")
                    link_code = data.get("privateServerLinkCode")
                else:
                    print(f"[Roblox Launcher] Private API failed to resolve share code. HTTP {res.status_code}")
            except Exception as e:
                print(f"[Roblox Launcher] Error calling resolving API: {e}")

    # Fallback if we have a Share Code but the API failed to convert it
    if not place_id or not link_code:
        if share_code:
            # Launch using Roblox's native share deep link handler
            url = f"roblox://navigation/share_links?code={share_code}&type=Server"
            print(f"[Roblox Launcher] Could not resolve IDs. Falling back to Share Code Deep Link: {url}")
            os.startfile(url)
            return True
        else:
            print("[Roblox Launcher] Failed to extract any valid Roblox joining data from the URL.")
            return False

    # Proceed to launch via Cookie Injection
    if not cookie or cookie.strip() == "":
        url = f"roblox://placeID={place_id}&linkCode={link_code}"
        print(f"[Roblox Launcher] No cookie provided. Launching via deep link: {url}")
        os.startfile(url)
        return True

    try:
        session = requests.Session()
        session.cookies[".ROBLOSECURITY"] = cookie
        
        csrf_res = session.post("https://auth.roblox.com/v1/authentication-ticket")
        csrf_token = csrf_res.headers.get("x-csrf-token")
        
        if not csrf_token:
            csrf_res = session.post("https://api.roblox.com/v1/xsrf-token")
            csrf_token = csrf_res.headers.get("x-csrf-token")
            
        headers = {
            "X-CSRF-TOKEN": csrf_token,
            "Referer": "https://www.roblox.com"
        }
        
        ticket_res = session.post("https://auth.roblox.com/v1/authentication-ticket", headers=headers)
        ticket = ticket_res.headers.get("rbx-authentication-ticket")
        
        if not ticket:
            print("[Roblox Launcher] Cookie is invalid or expired! Falling back to deep link...")
            url = f"roblox://placeID={place_id}&linkCode={link_code}"
            os.startfile(url)
            return True
            
        launcher_url = f"https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGame&placeId={place_id}&isPlayTogetherGame=false&privateServerLinkCode={link_code}"
        encoded_launcher_url = urllib.parse.quote(launcher_url)
        
        launch_time = int(time.time() * 1000)
        launch_str = f"roblox-player:1+launchmode:play+gameinfo:{ticket}+launchtime:{launch_time}+placelauncherurl:{encoded_launcher_url}+robloxLocale:en_us+gameLocale:en_us+channel:"
        
        os.startfile(launch_str)
        print(f"[Roblox Launcher] Successfully launched Roblox using Cookie Auth!")
        return True

    except Exception as e:
        print(f"[Roblox Launcher] Fatal error during resolution/launch: {e}")
        return False


class Scanner(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = None
        self.selected_biomes = []
        self.is_running = False
        self.guild_mappings = []  # Dict list updated from settings text box
        self.fish_loop = None  # Reference to the active FishSolBot instance
        self.active_biome_session = (
            None  # None = Hunting, string = name of active biome we are in
        )
        self.roblox_cookie = None
        self.scanner_paused_until = 0  # Timestamp when scanner can resume
        self.ui_reference = None  # Reference to UI for status updates
        self.webhook_url = None
        self.monitor_thread = None

    async def on_ready(self):
        print(f"Logged in as {self.user}")

    async def on_message(self, message):
        if not self.is_running:
            return

        # Check if scanner is temporarily paused
        if time.time() < self.scanner_paused_until:
            return

        if message.webhook_id is None and not message.author.bot:
            return

        # Map filtering
        guild_id_str = str(message.guild.id) if message.guild else None
        channel_id_str = str(message.channel.id)
        category_id_str = str(getattr(message.channel, "category_id", ""))

        matched_mapping = False
        for mapping in self.guild_mappings:
            m_guild = str(mapping.get("guild_id", ""))
            if m_guild and m_guild == guild_id_str:
                m_channels = [str(cid) for cid in mapping.get("channel_ids", [])]
                m_categories = [str(cat_id) for cat_id in mapping.get("category_ids", [])]
                if channel_id_str in m_channels or category_id_str in m_categories:
                    matched_mapping = True
                    break

        if not matched_mapping:
            return

        clean_text = extract_text(message)

        if ("started" in clean_text or "detected" in clean_text) and not (
            "ended" in clean_text or "test" in clean_text
        ):
            for biome in self.selected_biomes:
                if re.search(r"\b" + re.escape(biome.lower()) + r"\b", clean_text):
                    print(f"[Discord Scanner] Target Biome STARTED: {biome}")

                    urls = extract_urls(message)
                    
                    if len(urls) > 0:
                        raw_url = urls[0] # Grab the first link found
                        
                        if self.fish_loop:
                            self.fish_loop.toggle_off()
                        
                        # Let Roblox resolve it and launch!
                        success = resolve_and_launch_with_cookie(raw_url, self.roblox_cookie)
                        
                        if success and self.fish_loop:
                            self.fish_loop.is_waiting_for_start_button = True
                            self.fish_loop.has_done_initial_pathing = False
                            self.fish_loop.toggle_on()
                        
                        # Use predefined biome duration to pause the scanner
                        from ui import BIOME_PAUSE_DURATIONS
                        
                        # Match the biome name exact casing if needed, but 'biome' should match keys already
                        duration = BIOME_PAUSE_DURATIONS.get(biome, 1200) # Default 20 mins if not found
                        self.scanner_paused_until = time.time() + duration
                        self.active_biome_session = biome
                        print(f"[Discord Scanner] Pausing scanner for {duration} seconds (for biome {biome})")
                        
                        if self.webhook_url:
                            from webhook import Webhook
                            Webhook(self.webhook_url).send_biome_joined(biome)
                        
                        return
                    else:
                        print(f"[Discord Scanner] Biome '{biome}' started, but no links were found in the message.")

    def load_settings(self, token, biomes, cookie, mappings, webhook_url, ui_ref=None):
        self.token = token
        self.selected_biomes = biomes
        self.roblox_cookie = cookie
        self.guild_mappings = mappings
        self.webhook_url = webhook_url
        self.ui_reference = ui_ref

    def toggle_on(self):
        print("[Discord Scanner] Started")
        self.is_running = True
        self.scanner_paused_until = 0  # Clear any pause when starting
        if self.ui_reference:
            self.ui_reference.update_status("Scanning for biomes...")

    def toggle_off(self):
        print("[Discord Scanner] Paused")
        self.is_running = False
        self.active_biome_session = None
        self.scanner_paused_until = 0

    def start_scanner(self):
        """Start the Discord scanner"""
        import threading
        if not self.monitor_thread:
            self.monitor_thread = threading.Thread(target=self._monitor_pause, daemon=True)
            self.monitor_thread.start()

        if self.token:
            print("Starting Discord scanner...")
            self.run(self.token)
        else:
            print("No Discord token provided. Scanner not started.")

    def _monitor_pause(self):
        """Background thread to monitor scanner pause and trigger webhook on end"""
        import time
        while True:
            time.sleep(1)
            if self.is_running and self.scanner_paused_until > 0:
                if time.time() >= self.scanner_paused_until:
                    # Pause is over!
                    self.scanner_paused_until = 0
                    if self.webhook_url and self.active_biome_session:
                        from webhook import Webhook
                        Webhook(self.webhook_url).send_biome_ended(self.active_biome_session)
                    self.active_biome_session = None
                    print("[Discord Scanner] Resuming active background scan")
                    if self.ui_reference:
                        self.ui_reference.update_status("Scanning for biomes...")


# Global instance
scanner = Scanner(
    chunk_guilds_at_startup=False,
    member_cache_flags=discord.MemberCacheFlags.none(),
)