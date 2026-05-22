import discord
import re
import urllib.parse
import requests
import time
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

URL_REGEX = r"https?://[^\s)]+"
MD_LINK_REGEX = r"\[.*?\]\((https?://[^\s)]+)\)"

# If you ever support multiple games, make this configurable.
DEFAULT_PLACE_ID = "15532962292"  # FishSol placeId (update if needed)

LOG_JOIN_CONFIRM_TIMEOUT = 120
LOG_POLL_INTERVAL = 0.1

BIOME_LOG_DATA = [
    {"name": "NORMAL", "title": "Normal", "asset id": 80690294537387},
    {"name": "SNOWY", "title": "Snowy", "asset id": 109912975653138},
    {"name": "WINDY", "title": "Windy", "asset id": 138169499467564},
    {"name": "RAINY", "title": "Rainy", "asset id": 137992545432987},
    {"name": "SAND STORM", "title": "Sand Storm", "asset id": 102180669654341},
    {"name": "HELL", "title": "Hell", "asset id": 89721298978404},
    {"name": "STARFALL", "title": "Starfall", "asset id": 110087292131274},
    {"name": "HEAVEN", "title": "Heaven", "asset id": 107114559110957},
    {"name": "CORRUPTION", "title": "Corruption", "asset id": 137622939436355},
    {"name": "NULL", "title": "Null", "asset id": 120277135407020},
    {"name": "GLITCHED", "title": "Glitched", "asset id": 92180140049616},
    {"name": "DREAMSPACE", "title": "Dreamspace", "asset id": 124768988619166},
    {"name": "CYBERSPACE", "title": "Cyberspace", "asset id": 89000537898277},
    {"name": "EGGLAND", "title": "Eggland", "asset id": 107114559110957},
    {"name": "SINGULARITY", "title": "Singularity", "asset id": 107114559110957},
]

LOG_GAME_MARKERS = ("Sol's RNG", DEFAULT_PLACE_ID)


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


def normalize_biome_name(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


BIOME_TITLE_BY_NORMALIZED = {
    normalize_biome_name(biome["title"]): biome["title"] for biome in BIOME_LOG_DATA
}

BIOME_TITLE_BY_ASSET_ID = {
    str(biome["asset id"]): biome["title"] for biome in BIOME_LOG_DATA
}

BIOME_TITLE_BY_HOVER_TEXT = {
    biome["name"].upper(): biome["title"] for biome in BIOME_LOG_DATA
}


def canonical_biome_title(name):
    normalized = normalize_biome_name(name)
    return BIOME_TITLE_BY_NORMALIZED.get(normalized, name)


def read_first_5_mb(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(5_000_000)
    except Exception as e:
        print(f"[Log Scanner] Error reading {path}: {e}")
        return ""


def read_tail_text(path, max_bytes=1_000_000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            f.seek(max(0, end - max_bytes))
            return f.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[Log Scanner] Error reading tail for {path}: {e}")
        return ""


def parse_log_timestamp(ts):
    if not ts or len(ts) < 10:
        return None

    ts = ts.rstrip("Z")

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def seconds_since(ts):
    log_time = parse_log_timestamp(ts)
    if log_time is None:
        return None
    return (datetime.now(timezone.utc) - log_time).total_seconds()


def read_last_valid_line(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            buffer = b""
            pos = end

            while pos > 0:
                pos -= 1
                f.seek(pos)
                char = f.read(1)

                if char == b"\n":
                    line = buffer[::-1].decode("utf-8", errors="ignore").strip()
                    if line.startswith("20"):
                        return line
                    buffer = b""
                else:
                    buffer += char

    except Exception as e:
        print(f"[Log Scanner] Error reading last line for {path}: {e}")

    return None


def find_roblox_logs():
    localappdata = os.getenv("LOCALAPPDATA")
    if not localappdata:
        print("[Log Scanner] LOCALAPPDATA is not available.")
        return []

    roblox_logs_dir = Path(localappdata) / "Roblox" / "logs"
    if not roblox_logs_dir.exists():
        print("[Log Scanner] Roblox logs folder not found.")
        return []

    logs = [
        log
        for log in roblox_logs_dir.glob("*.log")
        if "installer" not in log.name.lower()
    ]
    logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return logs


def get_roblox_username_from_cookie(cookie):
    if not cookie or not cookie.strip():
        return None

    try:
        res = requests.get(
            "https://users.roblox.com/v1/users/authenticated",
            cookies={".ROBLOSECURITY": cookie},
            timeout=5,
        )
        if res.status_code == 200:
            return res.json().get("name")
    except Exception as e:
        print(f"[Log Scanner] Could not resolve Roblox username from cookie: {e}")

    return None


def identify_roblox_log(cookie=None):
    logs = find_roblox_logs()
    if not logs:
        print("[Log Scanner] No Roblox logs found.")
        return None

    username = get_roblox_username_from_cookie(cookie)
    if username:
        print(f"[Log Scanner] Looking for active log for Roblox user: {username}")
    else:
        print("[Log Scanner] Roblox username unavailable; using most recent matching log.")

    candidates = []
    for log_path in logs:
        data = read_first_5_mb(log_path)
        has_user = not username or username in data
        has_game_marker = any(marker in data for marker in LOG_GAME_MARKERS)
        if has_user and has_game_marker:
            candidates.append(log_path)

    if not candidates:
        print("[Log Scanner] No game-specific log found; falling back to recent Roblox logs.")
        candidates = logs[:5]

    for path in candidates:
        last_line = read_last_valid_line(path)
        if not last_line:
            continue

        timestamp = last_line.split(",", 1)[0].strip()
        age = seconds_since(timestamp)
        if age is not None and age <= 120:
            print(f"[Log Scanner] Assigned active Roblox log: {path.name}")
            return path

    fallback = candidates[0]
    print(f"[Log Scanner] No very recent timestamp found; using latest candidate: {fallback.name}")
    return fallback


def detect_biome_from_log_text(data, min_time=None):
    detected = None

    for line in data.splitlines():
        if min_time:
            line_timestamp = parse_log_timestamp(line.split(",", 1)[0].strip())
            if not line_timestamp or line_timestamp < min_time:
                continue

        hover_match = re.search(r'"hoverText"\s*:\s*"([^"]+)"', line)
        asset_match = re.search(r'"assetId"\s*:\s*(\d+)', line)
        if not hover_match or not asset_match:
            continue

        hover_text = hover_match.group(1).upper()
        asset_id = asset_match.group(1)
        asset_title = BIOME_TITLE_BY_ASSET_ID.get(asset_id)
        hover_title = BIOME_TITLE_BY_HOVER_TEXT.get(hover_text)

        if asset_title and hover_title and asset_title == hover_title:
            detected = asset_title
        elif hover_title:
            detected = hover_title
        elif asset_title:
            detected = asset_title

    return detected


def resolve_private_server_from_place(place_id, cookie=None):
    """
    Fallback resolver:
    Queries Roblox's private server list for the given place_id
    and returns the first available invite code (joinCode/linkCode).
    Requires a valid cookie to access the authenticated user's private servers.
    """
    try:
        url = f"https://games.roblox.com/v1/games/{place_id}/private-servers"

        # Must include the cookie, otherwise this endpoint returns 401 Unauthorized
        cookies = {".ROBLOSECURITY": cookie} if cookie else {}
        res = requests.get(url, cookies=cookies)

        if res.status_code != 200:
            print(f"[Resolver] API returned {res.status_code}. Is cookie valid?")
            return None

        servers = res.json().get("data", [])

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
    Parses any Roblox link (Public, Private, or Share Code)
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
        print(f"[Roblox Launcher] Detected Private Server. Place: {place_id}")
    else:
        # 2. Check for the new Share Code format
        share_match = re.search(r"code=([a-fA-F0-9]+)", raw_url, re.IGNORECASE)
        if share_match:
            share_code = share_match.group(1)
            print(f"[Roblox Launcher] Detected Share Code: {share_code}. Resolving via API...")
            try:
                res = requests.post(f"https://api-priv.vexsys.site/api/endpoints/roblox/resolve-link?linkId={share_code}", timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    place_id = data.get("placeId")
                    link_code = data.get("privateServerLinkCode")
                else:
                    print(f"[Roblox Launcher] Private API failed to resolve share code. HTTP {res.status_code}")
            except Exception as e:
                print(f"[Roblox Launcher] Error calling resolving API: {e}")
        else:
            # 3. Check for standard Public Server Link
            public_match = re.search(r"games/(\d+)", raw_url, re.IGNORECASE)
            if public_match:
                place_id = public_match.group(1)
                print(f"[Roblox Launcher] Detected Public Server. Place: {place_id}")

    # Helper function to generate modern Roblox deep links
    def get_modern_deep_link():
        if share_code and not place_id:
            return f"roblox://navigation/share_links?code={share_code}&type=Server"
        dl = f"roblox://experiences/start?placeId={place_id}"
        if link_code:
            dl += f"&privateServerLinkCode={link_code}"
        return dl

    if not place_id and not share_code:
        print("[Roblox Launcher] Failed to extract any valid Roblox joining data from the URL.")
        return False

    # Proceed to launch via Deep Link if no cookie is provided
    if not cookie or cookie.strip() == "":
        url = get_modern_deep_link()
        print(f"[Roblox Launcher] No cookie provided. Launching via deep link: {url}")
        os.startfile(url)
        return True

    # Proceed to launch via Cookie Injection
    try:
        session = requests.Session()
        session.cookies[".ROBLOSECURITY"] = cookie

        # Roblox strict CSRF requires Referer and Content-Length on this endpoint
        headers = {
            "Referer": "https://www.roblox.com",
            "Content-Length": "0"
        }

        # Request 1: Provoke a 403 to grab the fresh x-csrf-token (api.roblox.com is completely dead)
        csrf_res = session.post("https://auth.roblox.com/v1/authentication-ticket", headers=headers)
        csrf_token = csrf_res.headers.get("x-csrf-token")

        if not csrf_token:
            print("[Roblox Launcher] Failed to retrieve CSRF token. Falling back to deep link...")
            os.startfile(get_modern_deep_link())
            return True

        # Request 2: Use the token to officially request the authentication ticket
        headers["X-CSRF-TOKEN"] = csrf_token
        ticket_res = session.post("https://auth.roblox.com/v1/authentication-ticket", headers=headers)
        ticket = ticket_res.headers.get("rbx-authentication-ticket")

        if not ticket:
            print("[Roblox Launcher] Cookie is invalid or expired! Falling back to deep link...")
            os.startfile(get_modern_deep_link())
            return True

        # Build the launcher URI
        launcher_url = f"https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGame&placeId={place_id}&isPlayTogetherGame=false"
        if link_code:
            launcher_url += f"&privateServerLinkCode={link_code}"

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
        self.ui_reference = None  # Reference to UI for status updates
        self.webhook_url = None
        self.log_monitor_thread = None
        self.log_monitor_stop = threading.Event()
        self.log_monitor_lock = threading.Lock()
        self.log_biome_confirmed = False
        self.assigned_log = None

    async def on_ready(self):
        print(f"Logged in as {self.user}")

    async def on_message(self, message):
        if not self.is_running:
            return

        # The Discord scanner stays quiet while the Roblox log monitor verifies
        # and tracks the biome we already joined.
        if self.active_biome_session:
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
                        
                        if success:
                            self._start_log_monitor(biome)
                        
                        return
                    else:
                        print(f"[Discord Scanner] Biome '{biome}' started, but no links were found in the message.")

    def _start_log_monitor(self, biome):
        canonical_biome = canonical_biome_title(biome)

        with self.log_monitor_lock:
            self.log_monitor_stop.set()
            self.log_monitor_stop = threading.Event()
            self.active_biome_session = canonical_biome
            self.log_biome_confirmed = False

            self.log_monitor_thread = threading.Thread(
                target=self._monitor_joined_biome_log,
                args=(canonical_biome, self.log_monitor_stop),
                daemon=True,
            )
            self.log_monitor_thread.start()

        print(f"[Discord Scanner] Watching Roblox logs to verify biome: {canonical_biome}")
        if self.ui_reference:
            self.ui_reference.update_status(f"Verifying {canonical_biome} in logs...")

    def _monitor_joined_biome_log(self, expected_biome, stop_event):
        joined_at = time.time()
        expected_norm = normalize_biome_name(expected_biome)

        log_path = identify_roblox_log(self.roblox_cookie)
        if not log_path:
            self._finish_biome_session(
                expected_biome,
                reason="fake",
                observed_biome=None,
                detail="Roblox log could not be found",
            )
            return

        self.assigned_log = log_path
        last_pos = 0

        recent_log_cutoff = datetime.fromtimestamp(joined_at - 5, timezone.utc)
        tail_biome = detect_biome_from_log_text(
            read_tail_text(log_path),
            min_time=recent_log_cutoff,
        )
        if tail_biome:
            if normalize_biome_name(tail_biome) == expected_norm:
                self._confirm_biome_session(expected_biome)
            else:
                print(
                    f"[Log Scanner] Latest known log biome is {tail_biome}; "
                    f"waiting for fresh {expected_biome} confirmation."
                )

        try:
            last_pos = os.path.getsize(log_path)
        except OSError:
            last_pos = 0

        while self.is_running and not stop_event.is_set():
            if self.active_biome_session != expected_biome:
                return

            try:
                current_size = os.path.getsize(log_path)

                if current_size < last_pos:
                    print("[Log Scanner] Active Roblox log rotated; re-identifying log.")
                    log_path = identify_roblox_log(self.roblox_cookie)
                    if not log_path:
                        time.sleep(0.5)
                        continue
                    self.assigned_log = log_path
                    last_pos = 0
                    current_size = os.path.getsize(log_path)

                if current_size > last_pos:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(last_pos)
                        new_data = f.read(current_size - last_pos)
                    last_pos = current_size

                    detected_biome = detect_biome_from_log_text(new_data)
                    if detected_biome:
                        if normalize_biome_name(detected_biome) == expected_norm:
                            self._confirm_biome_session(expected_biome)
                        elif self.log_biome_confirmed:
                            self._finish_biome_session(
                                expected_biome,
                                reason="ended",
                                observed_biome=detected_biome,
                            )
                            return
                        else:
                            self._finish_biome_session(
                                expected_biome,
                                reason="fake",
                                observed_biome=detected_biome,
                                detail="Roblox reported a different active biome",
                            )
                            return

                if not self.log_biome_confirmed and time.time() - joined_at > LOG_JOIN_CONFIRM_TIMEOUT:
                    self._finish_biome_session(
                        expected_biome,
                        reason="fake",
                        observed_biome=None,
                        detail="Timed out waiting for log confirmation",
                    )
                    return

                time.sleep(LOG_POLL_INTERVAL)

            except Exception as e:
                print(f"[Log Scanner] Error while monitoring biome log: {e}")
                time.sleep(0.5)

    def _confirm_biome_session(self, biome):
        if self.log_biome_confirmed:
            return

        self.log_biome_confirmed = True
        print(f"[Log Scanner] Confirmed active biome from Roblox logs: {biome}")
        if self.ui_reference:
            self.ui_reference.update_status(f"Fishing in {biome}...")
        if self.webhook_url:
            from webhook import Webhook
            Webhook(self.webhook_url).send_biome_joined(biome)

    def _finish_biome_session(self, biome, reason, observed_biome=None, detail=None):
        with self.log_monitor_lock:
            if self.active_biome_session != biome:
                return

            self.active_biome_session = None
            self.log_biome_confirmed = False
            self.log_monitor_stop.set()

        if self.fish_loop:
            self.fish_loop.toggle_off()

        if reason == "ended":
            observed = f" New biome: {observed_biome}." if observed_biome else ""
            print(f"[Log Scanner] Biome ended: {biome}.{observed} Resuming Discord scan.")
            if self.webhook_url:
                from webhook import Webhook
                Webhook(self.webhook_url).send_biome_ended(biome)
        else:
            observed = f" Observed: {observed_biome}." if observed_biome else ""
            extra = f" {detail}." if detail else ""
            print(f"[Log Scanner] Fake biome detected for {biome}.{observed}{extra} Resuming Discord scan.")

        if self.ui_reference:
            self.ui_reference.update_status("Scanning for biomes...")

    def load_settings(self, token, biomes, cookie, mappings, webhook_url, ui_ref=None):
        self.token = token
        self.selected_biomes = [canonical_biome_title(biome) for biome in biomes]
        self.roblox_cookie = cookie
        self.guild_mappings = mappings
        self.webhook_url = webhook_url
        self.ui_reference = ui_ref

    def toggle_on(self):
        print("[Discord Scanner] Started")
        self.is_running = True
        self.active_biome_session = None
        self.log_biome_confirmed = False
        if self.ui_reference:
            self.ui_reference.update_status("Scanning for biomes...")

    def toggle_off(self):
        print("[Discord Scanner] Paused")
        self.is_running = False
        self.active_biome_session = None
        self.log_biome_confirmed = False
        self.log_monitor_stop.set()

    def start_scanner(self):
        """Start the Discord scanner"""
        if self.token:
            print("Starting Discord scanner...")
            self.run(self.token)
        else:
            print("No Discord token provided. Scanner not started.")



# Global instance
scanner = Scanner(
    chunk_guilds_at_startup=False,
    member_cache_flags=discord.MemberCacheFlags.none(),
)
