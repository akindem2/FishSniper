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

LOG_JOIN_CONFIRM_TIMEOUT = 150
LOG_SCANNER_START_DELAY = 10
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
BIOME_RPC_IMAGE_REGEX = re.compile(
    r'\{\s*"hoverText"\s*:\s*"([A-Z0-9 ]+)"\s*,\s*"assetId"\s*:\s*(\d+)\s*\}'
)


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

_BIOME_TITLES_BY_ASSET_ID = {}
for biome in BIOME_LOG_DATA:
    _BIOME_TITLES_BY_ASSET_ID.setdefault(str(biome["asset id"]), set()).add(biome["title"])

BIOME_TITLE_BY_ASSET_ID = {
    asset_id: next(iter(titles))
    for asset_id, titles in _BIOME_TITLES_BY_ASSET_ID.items()
    if len(titles) == 1
}

BIOME_TITLE_BY_HOVER_TEXT = {}
for biome in BIOME_LOG_DATA:
    BIOME_TITLE_BY_HOVER_TEXT[biome["name"].upper()] = biome["title"]
    BIOME_TITLE_BY_HOVER_TEXT[biome["title"].upper()] = biome["title"]


def canonical_biome_title(name):
    normalized = normalize_biome_name(name)
    return BIOME_TITLE_BY_NORMALIZED.get(normalized, name)


def resolve_biome_title_from_rpc(hover_text, asset_id):
    hover_title = BIOME_TITLE_BY_HOVER_TEXT.get((hover_text or "").upper())
    if hover_title:
        return hover_title
    return BIOME_TITLE_BY_ASSET_ID.get(str(asset_id))


def detect_biome_from_rpc_line(line):
    detected = None
    for match in BIOME_RPC_IMAGE_REGEX.finditer(line):
        detected_title = resolve_biome_title_from_rpc(match.group(1), match.group(2))
        if detected_title:
            detected = detected_title
    return detected


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


def get_roblox_userid_from_cookie(cookie):
    if not cookie or not cookie.strip():
        return None

    try:
        res = requests.get(
            "https://users.roblox.com/v1/users/authenticated",
            cookies={".ROBLOSECURITY": cookie},
            timeout=5,
        )
        if res.status_code == 200:
            return res.json().get("id")
    except Exception as e:
        print(f"[Log Scanner] Could not resolve Roblox userid from cookie: {e}")

    return None


def identify_roblox_log(cookie=None):
    logs = find_roblox_logs()
    if not logs:
        print("[Log Scanner] No Roblox logs found.")
        return None

    userid = get_roblox_userid_from_cookie(cookie)
    if userid:
        print(f"[Log Scanner] Looking for active log for Roblox user ID: {userid}")
    else:
        print("[Log Scanner] Roblox user ID unavailable; using most recent matching log.")

    # Filter candidates to only logs that contain the game marker
    candidates = []
    for log_path in logs:
        data = read_first_5_mb(log_path)
        has_game_marker = any(marker in data for marker in LOG_GAME_MARKERS)
        if has_game_marker:
            candidates.append(log_path)

    selected = None

    # First pass: try to find a very recent log that also matches the user
    for path in candidates:
        last_line = read_last_valid_line(path)
        if not last_line:
            continue
        timestamp = last_line.split(",", 1)[0].strip()
        age = seconds_since(timestamp)
        if age is not None and age <= 120:
            if userid:
                data = read_first_5_mb(path)
                if str(userid) in data:
                    print(f"[Log Scanner] Assigned active Roblox log for user ID {userid}: {path.name}")
                    selected = path
                    break

    # Second pass: try to find any very recent log with the game marker
    if not selected:
        for path in candidates:
            last_line = read_last_valid_line(path)
            if not last_line:
                continue
            timestamp = last_line.split(",", 1)[0].strip()
            age = seconds_since(timestamp)
            if age is not None and age <= 120:
                print(f"[Log Scanner] Assigned active Roblox log: {path.name}")
                selected = path
                break

    if selected:
        return selected

    if candidates:
        fallback = candidates[0]
        print(f"[Log Scanner] No very recent timestamp found; using latest game candidate: {fallback.name}")
        return fallback

    fallback = logs[0]
    print(f"[Log Scanner] No game-specific log found at all; using latest Roblox log: {fallback.name}")
    return fallback


def detect_biome_from_log_text(data, min_time=None):
    """Scan lines of log text and return the last biome detected, or None."""
    detected = None

    for line in data.splitlines():
        if min_time:
            line_timestamp = parse_log_timestamp(line.split(",", 1)[0].strip())
            if not line_timestamp or line_timestamp < min_time:
                continue

        detected_title = detect_biome_from_rpc_line(line)
        if detected_title:
            detected = detected_title

    return detected


def detect_current_biome_from_log(path):
    """Scan the log backwards and return the most recently logged biome, or None."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in reversed(lines):
            detected_title = detect_biome_from_rpc_line(line)
            if detected_title:
                return detected_title
        return None
    except Exception as e:
        print(f"[Log Scanner] Error scanning log backwards: {e}")
        return None


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

def _parse_roblox_link(raw_url: str):
    """
    Returns (place_id, link_code, share_code)
    - place_id: string or None
    - link_code: privateServerLinkCode or joinCode or None
    - share_code: share-links code (hex) or None
    """
    place_id = None
    link_code = None
    share_code = None

    # 1. Direct private server link:
    #    https://www.roblox.com/games/PLACEID/... ?privateServerLinkCode=XXXX
    m = re.search(
        r"games/(\d+)(?:/.*?)?[?&]privateServerLinkCode=([\w-]+)",
        raw_url,
        re.IGNORECASE,
    )
    if m:
        place_id = m.group(1)
        link_code = m.group(2)
        return place_id, link_code, None

    # 2. New share-links wrapper:
    #    https://www.roblox.com/share-links?code=abcdef1234...
    m = re.search(r"[?&]code=([a-f0-9]+)", raw_url, re.IGNORECASE)
    if m:
        share_code = m.group(1)
        return None, None, share_code

    # 3. Some bots send just the roblox:// deep link
    #    roblox://placeID=...&linkCode=...
    m = re.search(r"placeID=(\d+)", raw_url, re.IGNORECASE)
    if m:
        place_id = m.group(1)
    m2 = re.search(r"linkCode=([\w-]+)", raw_url, re.IGNORECASE)
    if m2:
        link_code = m2.group(1)

    return place_id, link_code, None


def _resolve_share_code(share_code: str):
    """
    Uses Roblox's share-links API to resolve a share code into:
    (place_id, link_code) or (None, None) on failure.
    """
    try:
        url = f"https://apis.roblox.com/share-links/v1/share-links/{share_code}"
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"[Roblox Launcher] Share-links API HTTP {res.status_code}")
            return None, None

        data = res.json()
        # Typical structure:
        # {
        #   "targetType": "Experience",
        #   "targetId": 15532962292,
        #   "linkType": "ExperienceInvite",
        #   "data": {
        #       "placeId": 15532962292,
        #       "privateServerLinkCode": "XXXX-XXXX"
        #   }
        # }
        target_id = data.get("targetId")
        payload = data.get("data", {}) or {}
        place_id = str(payload.get("placeId") or target_id or "")
        link_code = payload.get("privateServerLinkCode") or payload.get("joinCode")

        if not place_id or not link_code:
            print("[Roblox Launcher] Share-links API returned incomplete data.")
            return None, None

        print(
            f"[Roblox Launcher] Resolved share code {share_code} → "
            f"placeId={place_id}, linkCode={link_code}"
        )
        return place_id, link_code

    except Exception as e:
        print(f"[Roblox Launcher] Error resolving share code via API: {e}")
        return None, None


def _launch_deeplink(place_id: str, link_code: str):
    """
    Last-resort deep link launcher. Works if Roblox is installed and
    registered as URL handler.
    """
    url = f"roblox://placeID={place_id}&linkCode={link_code}"
    print(f"[Roblox Launcher] Launching via deep link: {url}")
    os.startfile(url)
    return True


def resolve_and_launch_with_cookie(raw_url, cookie):
    """
    Robust resolver:
    - Handles direct private server links
    - Handles share-links via Roblox API
    - Uses cookie + auth ticket when possible
    - Falls back to deep link if cookie invalid/missing
    """
    print(f"[Roblox Launcher] Processing link: {raw_url}")

    place_id, link_code, share_code = _parse_roblox_link(raw_url)

    # If we only have a share code, resolve it via Roblox API
    if share_code and (not place_id or not link_code):
        print(f"[Roblox Launcher] Detected Share Code: {share_code}. Resolving via Roblox API...")
        r_place, r_link = _resolve_share_code(share_code)
        if r_place and r_link:
            place_id, link_code = r_place, r_link

    # If still missing place/link, try a last-resort share deep link
    if not place_id or not link_code:
        if share_code:
            url = f"roblox://navigation/share_links?code={share_code}&type=Server"
            print(f"[Roblox Launcher] Could not fully resolve IDs. Falling back to Share Deep Link: {url}")
            os.startfile(url)
            return True
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

    # At this point we have place_id + link_code
    # If no cookie, just use deep link
    if not cookie or cookie.strip() == "":
        return _launch_deeplink(place_id, link_code)

    # Cookie-based auth ticket flow
    try:
        session = requests.Session()
        session.cookies[".ROBLOSECURITY"] = cookie.strip()

        # First call to get X-CSRF
        csrf_res = session.post("https://auth.roblox.com/v1/authentication-ticket")
        csrf_token = csrf_res.headers.get("x-csrf-token")


        if not csrf_token:
            # Try legacy xsrf endpoint as backup
            xsrf_res = session.post("https://api.roblox.com/v1/xsrf-token")
            csrf_token = xsrf_res.headers.get("x-csrf-token")

        if not csrf_token:
            print("[Roblox Launcher] Failed to obtain X-CSRF token. Falling back to deep link.")
            return _launch_deeplink(place_id, link_code)

        headers = {
            "X-CSRF-TOKEN": csrf_token,
            "Referer": "https://www.roblox.com",
        }

        ticket_res = session.post(
            "https://auth.roblox.com/v1/authentication-ticket",
            headers=headers,
        )
        ticket = ticket_res.headers.get("rbx-authentication-ticket")


        if not ticket:
            print("[Roblox Launcher] Cookie invalid or ticket missing. Falling back to deep link.")
            return _launch_deeplink(place_id, link_code)

        launcher_url = (
            "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestGame&placeId={place_id}"
            f"&isPlayTogetherGame=false&privateServerLinkCode={link_code}"
        )
        encoded_launcher_url = urllib.parse.quote(launcher_url)

        launch_time = int(time.time() * 1000)
        launch_str = (
            "roblox-player:1"
            f"+launchmode:play"
            f"+gameinfo:{ticket}"
            f"+launchtime:{launch_time}"
            f"+placelauncherurl:{encoded_launcher_url}"
            "+robloxLocale:en_us"
            "+gameLocale:en_us"
            "+channel:"
        )

        print("[Roblox Launcher] Launching Roblox using Cookie Auth + PlaceLauncher...")
        os.startfile(launch_str)
        return True

    except Exception as e:
        print(f"[Roblox Launcher] Fatal error during resolution/launch: {e}")
        print("[Roblox Launcher] Falling back to deep link.")
        return _launch_deeplink(place_id, link_code)


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

        print(
            f"[Discord Scanner] Waiting {LOG_SCANNER_START_DELAY}s before watching "
            f"Roblox logs to verify biome: {canonical_biome}"
        )
        if self.ui_reference:
            self.ui_reference.update_status(
                f"Waiting {LOG_SCANNER_START_DELAY}s before verifying {canonical_biome}..."
            )

    def _monitor_joined_biome_log(self, expected_biome, stop_event):
        if stop_event.wait(LOG_SCANNER_START_DELAY):
            return

        selected_norms = {normalize_biome_name(b) for b in self.selected_biomes}

        # ── Phase 1: Assign the log for this server join ──────────────────────
        # A fresh log is located and locked in each time a new server is joined.
        print("[Log Scanner] Searching for Roblox log file...")
        log_path = None
        deadline = time.time() + 120
        while self.is_running and not stop_event.is_set() and time.time() < deadline:
            if not self.fish_loop or not self.fish_loop.is_running:
                self._finish_biome_session(
                    expected_biome, reason="ended",
                    detail="Fish loop stopped while locating log",
                )
                return
            log_path = identify_roblox_log(self.roblox_cookie)
            if log_path:
                break
            print("[Log Scanner] No log file found yet — retrying...")
            time.sleep(2.0)

        if not log_path:
            print("[Log Scanner] Could not find a Roblox log file. Resuming Discord scan.")
            self._finish_biome_session(
                expected_biome, reason="fake",
                detail="Roblox log could not be found",
            )
            return

        self.assigned_log = log_path
        print(f"[Log Scanner] Log assigned: {log_path.name}")

        # ── Phase 2: Scan the assigned log backwards for the current biome ────
        # Done once immediately after assignment. If the game is still loading
        # and no biome entry exists yet, we fall straight through to Phase 3
        # which will catch the biome the moment it first appears in new lines.
        print("[Log Scanner] Scanning log backwards for current biome...")
        current_biome = detect_current_biome_from_log(log_path)

        if current_biome:
            detected_norm = normalize_biome_name(current_biome)
            if detected_norm in selected_norms:
                print(f"[Log Scanner] Current biome confirmed: {current_biome} — starting to fish!")
                self._confirm_biome_session(current_biome)
            else:
                print(f"[Log Scanner] Landed in '{current_biome}' (not a target). Resuming Discord scan.")
                self._finish_biome_session(
                    expected_biome, reason="fake", observed_biome=current_biome,
                    detail="Log shows a different biome than expected",
                )
                return
        else:
            print("[Log Scanner] No biome entry found yet — game may still be loading. Watching new lines...")

        # ── Phase 3: Watch new log lines and react to biome changes ──────────
        last_pos = os.path.getsize(log_path)
        print("[Log Scanner] Monitoring log for biome changes...")

        while self.is_running and not stop_event.is_set():
            if not self.fish_loop or not self.fish_loop.is_running:
                self._finish_biome_session(
                    self.active_biome_session, reason="ended",
                    detail="Fish loop stopped during log monitoring",
                )
                return

            try:
                current_size = os.path.getsize(log_path)

                if current_size < last_pos:
                    print("[Log Scanner] Log file shrank — re-identifying log after rotation...")
                    candidate = identify_roblox_log(self.roblox_cookie)
                    if not candidate:
                        time.sleep(0.5)
                        continue
                    log_path = candidate
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
                        detected_norm = normalize_biome_name(detected_biome)
                        if detected_norm in selected_norms:
                            # Still in a target biome (could be a biome-to-biome transition)
                            if self.active_biome_session != detected_biome:
                                print(f"[Log Scanner] Biome updated to '{detected_biome}' — still a target, continuing to fish.")
                                self._confirm_biome_session(detected_biome)
                        else:
                            # Biome changed to something we don't want — hop servers
                            print(f"[Log Scanner] Biome changed to '{detected_biome}' (not a target). Stopping fishing and resuming Discord scan.")
                            self._finish_biome_session(
                                self.active_biome_session,
                                reason="ended",
                                observed_biome=detected_biome,
                            )
                            return

                time.sleep(LOG_POLL_INTERVAL)

            except Exception as e:
                print(f"[Log Scanner] Error while monitoring log: {e}")
                time.sleep(0.5)

    def _confirm_biome_session(self, biome):
        if self.log_biome_confirmed and self.active_biome_session == biome:
            return

        self.log_biome_confirmed = True
        self.active_biome_session = biome
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
