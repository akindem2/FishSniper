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
ROBLOX_PROTOCOL_REGEX = r"roblox://[^\s)]+"


def _roblox_error_detail(response):
    """Return a short, safe-to-log explanation from a Roblox HTTP response."""
    status = f"HTTP {response.status_code} {response.reason}".strip()
    try:
        payload = response.json()
        errors = payload.get("errors", []) if isinstance(payload, dict) else []
        if errors:
            messages = [
                f"{error.get('code', 'unknown')}: {error.get('message', 'no message')}"
                for error in errors
                if isinstance(error, dict)
            ]
            if messages:
                return f"{status} — {'; '.join(messages)}"
    except ValueError:
        pass

    # Roblox occasionally returns a plain-text error. Limit it so logs stay
    # useful and never include request headers (which contain credentials).
    body = " ".join(response.text.split())[:300]
    return f"{status}{f' — {body}' if body else ''}"

# If you ever support multiple games, make this configurable.
DEFAULT_PLACE_ID = "15532962292"  # FishSol placeId (update if needed)

LOG_JOIN_CONFIRM_TIMEOUT = 150
LOG_SCANNER_START_DELAY = 20
LOG_POLL_INTERVAL = 0.1

# How long _confirm_biome_session will block waiting for fish_loop to finish
# capturing the join screenshot before giving up and sending the "Joined"
# embed without one. Generous enough to comfortably cover the longest
# legitimate capture path (10s load wait + up to 60s polling for the
# in-game Start button + a few seconds of click delay) — this should only
# ever trip when a screenshot was never going to be taken for this session
# at all (e.g. the Start button check was bypassed or timed out), not
# because a normal capture is just running a little late.
JOIN_SCREENSHOT_WAIT_TIMEOUT = 90

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
    {"name": "BLAZING SUN", "title": "Blazing Sun", "asset id": 70580600109957},
    # Incinerator's RPC largeImage asset id collides with Heaven/Eggland/
    # Singularity (all 107114559110957), so that id is ambiguous and excluded
    # from asset-id detection — Incinerator is matched by its "INCINERATOR"
    # RPC hover text instead.
    {"name": "INCINERATOR", "title": "Incinerator", "asset id": 107114559110957},
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
    # Direct roblox:// protocol strings (e.g. a "Protocol (Paste into Browser)"
    # line) are the ground truth for what server to join — they encode the
    # place/instance IDs directly. Generic https:// links (a "Join Server"
    # hyperlink, a wrapper/redirect page, a share link, etc.) are much less
    # reliable, since some of them go through third-party redirectors that
    # don't map cleanly onto Roblox's own join parameters. So protocol
    # strings are always returned first, ahead of any web links.
    protocol_urls = []
    web_urls = []

    def scan_str(s):
        if not s:
            return
        protocol_urls.extend(re.findall(ROBLOX_PROTOCOL_REGEX, s))
        web_urls.extend(re.findall(URL_REGEX, s))
        web_urls.extend(re.findall(MD_LINK_REGEX, s))

    scan_str(message.content)
    for embed in message.embeds:
        scan_str(embed.title)
        scan_str(embed.description)
        for field in embed.fields:
            scan_str(field.name)
            scan_str(field.value)
        if embed.url:
            web_urls.append(embed.url)
    if hasattr(message, "components") and message.components:
        for row in message.components:
            for component in row.children:
                if hasattr(component, "url") and component.url:
                    web_urls.append(component.url)
    return list(dict.fromkeys(protocol_urls + web_urls))


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


def biome_thumbnail_url(biome_name):
    """
    Thumbnail images live at a fixed GitHub raw-content pattern, keyed by a
    lowercase, underscore-separated slug of the biome's canonical title
    (e.g. "Sand Storm" -> "sand_storm", NOT "sandstorm" — spaces become
    underscores rather than being stripped, unlike normalize_biome_name).
    """
    slug = (biome_name or "").strip().lower().replace(" ", "_")
    return f"https://raw.githubusercontent.com/akindem2/thumbnails/refs/heads/main/old_{slug}.png"


# Per-biome Discord embed accent colors (int RGB), keyed by canonical title.
BIOME_EMBED_COLORS = {
    "Normal": 0xC8DED7,
    "Snowy": 0xA6FFFF,
    "Windy": 0x90F6FF,
    "Rainy": 0x4284FF,
    "Sand Storm": 0xFFCB81,
    "Hell": 0x7E1617,
    "Starfall": 0x6085FF,
    "Heaven": 0xD6A22D,
    "Corruption": 0x9143FF,
    "Null": 0x3B3B3B,
    "Glitched": 0x209E2A,
    "Dreamspace": 0xEA9DDA,
    "Cyberspace": 0x1C3266,
    "Singularity": 0xD47111,
    "Blazing Sun": 0xFFFA5C,
    "Incinerator": 0xE97451,
}


def biome_embed_color(biome_name):
    """Returns the Discord embed color (int) for a biome, or None if the biome
    has no configured color (so the caller can fall back to a default)."""
    return BIOME_EMBED_COLORS.get(canonical_biome_title(biome_name))


# Biomes that get an @-ping in their join webhook notification, regardless of
# what priority tier they're configured with in the UI.
PING_BIOME_NORMS = {normalize_biome_name(b) for b in ("Glitched", "Dreamspace", "Cyberspace")}


def biome_should_ping(biome_name):
    return normalize_biome_name(biome_name) in PING_BIOME_NORMS


# NOTE: Check-in screenshots are no longer hardcoded to specific biomes —
# they're configured per-biome in the UI's Biomes tab (an expandable flap
# under each biome card) and pushed in via Scanner.load_settings as
# `checkin_screenshots`: {biome_title: {"enabled": bool, "delay": seconds}}.
# See Scanner.checkin_screenshot_settings.


# NOTE: Priority levels are no longer hardcoded here — they're configured in
# the UI's Priority tab (a tier board) and pushed in via Scanner.load_settings
# as `biome_priority_levels`: {normalized_biome_name: tier_int}. Tier 1 is the
# highest priority; larger numbers are lower priority. A biome with no entry
# is treated as the lowest possible priority (can be interrupted by anything
# with a real tier, but can never itself interrupt).


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


def format_biome_duration(total_seconds):
    """Formats a duration as D:HH:MM:SS, only including the larger units
    once they're actually needed — 'MM:SS' under an hour, 'H:MM:SS' under
    a day, 'D:HH:MM:SS' once it reaches multiple days (and beyond, since
    days keeps growing unbounded for long-running totals)."""
    total_seconds = max(0, int(total_seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days > 0:
        return f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}"
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


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
    Returns (place_id, link_code, share_code, game_instance_id)
    - place_id: string or None
    - link_code: privateServerLinkCode or joinCode or None
    - share_code: share-links code (hex) or None
    - game_instance_id: specific running server GUID (gameInstanceId) or None
    """
    place_id = None
    link_code = None
    share_code = None
    game_instance_id = None

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
        return place_id, link_code, None, None

    # 2. New share-links wrapper:
    #    https://www.roblox.com/share-links?code=abcdef1234...
    m = re.search(r"[?&]code=([a-f0-9]+)", raw_url, re.IGNORECASE)
    if m:
        share_code = m.group(1)
        return None, None, share_code, None

    # 3. Direct game-instance join (a specific already-running server):
    #    roblox://placeID=X&gameInstanceId=XXXX-XXXX-...
    #    or a games/PLACEID/... link carrying ?gameInstanceId=XXXX
    m = re.search(r"gameInstanceId=([\w-]+)", raw_url, re.IGNORECASE)
    if m:
        game_instance_id = m.group(1)
        place_match = re.search(r"place[iI][dD]=(\d+)", raw_url) or re.search(
            r"games/(\d+)", raw_url, re.IGNORECASE
        )
        if place_match:
            place_id = place_match.group(1)
        return place_id, None, None, game_instance_id

    # 4. Some bots send just the roblox:// deep link
    #    roblox://placeID=...&linkCode=...
    m = re.search(r"placeID=(\d+)", raw_url, re.IGNORECASE)
    if m:
        place_id = m.group(1)
    m2 = re.search(r"linkCode=([\w-]+)", raw_url, re.IGNORECASE)
    if m2:
        link_code = m2.group(1)

    return place_id, link_code, None, None


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
    registered as a URL handler. Uses the modern
    roblox://experiences/start?placeId=...&privateServerLinkCode=... scheme
    — the older roblox://placeID=...&linkCode=... form isn't reliably
    recognized by current Roblox clients, which was silently breaking
    private-server launches every time this fallback got used.
    """
    url = f"roblox://experiences/start?placeId={place_id}&privateServerLinkCode={link_code}"
    print(f"[Roblox Launcher] Launching via deep link: {url}")
    os.startfile(url)
    return True


def _launch_instance_deeplink(place_id: str, game_instance_id: str):
    """
    Deep link launcher for joining a specific already-running server
    instance (not a private server). Uses the same modern
    roblox://experiences/start URI scheme.
    """
    url = f"roblox://experiences/start?placeId={place_id}&gameInstanceId={game_instance_id}"
    print(f"[Roblox Launcher] Launching instance via deep link: {url}")
    os.startfile(url)
    return True


def _launch_instance(place_id: str, game_instance_id: str, cookie: str):
    """
    Joins a specific running server instance. Uses PlaceLauncher's
    RequestGameJob mode (the instance-join equivalent of RequestGame)
    when a cookie is available; falls back to the roblox:// deep link
    otherwise or on any failure along the way.
    """
    if not cookie or cookie.strip() == "":
        return _launch_instance_deeplink(place_id, game_instance_id)

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
            csrf_res = xsrf_res

        if not csrf_token:
            print(
                "[Roblox Launcher] Failed to obtain X-CSRF token: "
                f"{_roblox_error_detail(csrf_res)}. Falling back to deep link."
            )
            return _launch_instance_deeplink(place_id, game_instance_id)

        headers = {
            "X-CSRF-TOKEN": csrf_token,
            "Referer": "https://www.roblox.com",
            "Content-Type": "application/json",
        }

        ticket_res = session.post(
            "https://auth.roblox.com/v1/authentication-ticket",
            headers=headers,
            json={},
        )
        ticket = ticket_res.headers.get("rbx-authentication-ticket")

        if not ticket:
            print(
                "[Roblox Launcher] Roblox did not issue an authentication ticket: "
                f"{_roblox_error_detail(ticket_res)}. Falling back to deep link."
            )
            return _launch_instance_deeplink(place_id, game_instance_id)

        launcher_url = (
            "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestGameJob&placeId={place_id}"
            f"&gameInstanceId={game_instance_id}&isPlayTogetherGame=false"
        )
        encoded_launcher_url = urllib.parse.quote(launcher_url)

        launch_time = int(time.time() * 1000)
        launch_str = (
            "roblox:1"
            f"+launchmode:play"
            f"+gameinfo:{ticket}"
            f"+launchtime:{launch_time}"
            f"+placelauncherurl:{encoded_launcher_url}"
            "+robloxLocale:en_us"
            "+gameLocale:en_us"
            "+channel:"
        )

        print("[Roblox Launcher] Launching instance using Cookie Auth + PlaceLauncher (RequestGameJob)...")
        os.startfile(launch_str)
        return True

    except Exception as e:
        print(f"[Roblox Launcher] Fatal error during instance launch: {e}")
        print("[Roblox Launcher] Falling back to deep link.")
        return _launch_instance_deeplink(place_id, game_instance_id)


def resolve_and_launch_with_cookie(raw_url, cookie):
    """
    Robust resolver:
    - Handles direct private server links
    - Handles share-links via Roblox API
    - Uses cookie + auth ticket when possible
    - Falls back to deep link if cookie invalid/missing
    """
    print(f"[Roblox Launcher] Processing link: {raw_url}")

    place_id, link_code, share_code, game_instance_id = _parse_roblox_link(raw_url)

    # Direct game-instance join — highest priority. Let Roblox handle its own
    # native deep link; the custom PlaceLauncher ticket flow can discard the
    # requested instance and put the player in a different server.
    if game_instance_id and place_id:
        print(f"[Roblox Launcher] Detected Game Instance: {game_instance_id} (place {place_id})")
        return _launch_instance_deeplink(place_id, game_instance_id)

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
            csrf_res = xsrf_res

        if not csrf_token:
            print(
                "[Roblox Launcher] Failed to obtain X-CSRF token: "
                f"{_roblox_error_detail(csrf_res)}. Falling back to deep link."
            )
            return _launch_deeplink(place_id, link_code)

        headers = {
            "X-CSRF-TOKEN": csrf_token,
            "Referer": "https://www.roblox.com",
            "Content-Type": "application/json",
        }

        ticket_res = session.post(
            "https://auth.roblox.com/v1/authentication-ticket",
            headers=headers,
            json={},
        )
        ticket = ticket_res.headers.get("rbx-authentication-ticket")


        if not ticket:
            print(
                "[Roblox Launcher] Roblox did not issue an authentication ticket: "
                f"{_roblox_error_detail(ticket_res)}. Falling back to deep link."
            )
            return _launch_deeplink(place_id, link_code)

        launcher_url = (
            "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestGame&placeId={place_id}"
            f"&isPlayTogetherGame=false&privateServerLinkCode={link_code}"
        )
        encoded_launcher_url = urllib.parse.quote(launcher_url)

        launch_time = int(time.time() * 1000)
        launch_str = (
            "roblox:1"
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
        self.biome_priority_levels = {}  # {normalized_biome_name: tier_int}, tier 1 = highest priority
        self.discord_ping_user_id = None  # Discord user ID to @-ping on priority biome joins
        self.pending_join_url = None  # link/protocol used for the join currently being verified
        self.pending_join_is_priority_interrupt = False
        self.pending_join_detected_at = None  # time.time() when the triggering Discord message was seen
        self.session_join_url = None  # same, but pinned to the confirmed active_biome_session
        self.session_is_priority_interrupt = False
        self.session_detected_at = None  # same, but pinned to the confirmed active_biome_session
        self.log_monitor_thread = None
        self.log_monitor_stop = threading.Event()
        self.log_monitor_lock = threading.Lock()
        self.log_biome_confirmed = False
        self.assigned_log = None
        self._checkin_followup_stop_event = None  # identity of the stop_event we've already scheduled a follow-up for
        self.checkin_screenshot_settings = {}  # {normalized_biome_name: {"enabled": bool, "delay": seconds}}
        self.fishing_enabled_biomes = {}  # {normalized_biome_name: bool}; missing entries default to enabled
        self.auto_items = []  # [{"enabled": bool, "name": str, "quantity": int, "biomes": [biome_title, ...]}]
        # At most one automation-driven action (a join, or the disconnect
        # recovery rejoin) that got deferred because a gauntlet swap was in
        # progress when it would otherwise have fired. Only the action that
        # would actually change what's on screen needs to wait — see
        # _launch_and_track_join() and _rejoin_random_public_server().
        self._deferred_action = None
        self.log_watchdog_thread = None
        self.log_watchdog_stop = None

        # Time-in-biome tracking. Runs continuously for the whole time the
        # bot is actively in a server, independent of which biome is the
        # current Discord target — so time spent waiting in a non-target
        # biome between announcements still counts. Totals persist and
        # accumulate indefinitely (never reset on their own); only an
        # explicit reset_biome_time_totals() call clears them.
        self.biome_time_totals = {}  # {biome_title: total_seconds (float)}
        self._biome_time_current = None  # biome title currently being timed, or None
        self._biome_time_started_at = None  # aware datetime when current timing segment began
        self.biome_time_thread = None
        self.biome_time_stop = None
        self.biome_time_updated_callback = None  # callback(biome_title, new_total_seconds)

    def biome_priority_level(self, biome_name):
        """
        Returns the configured priority tier for a biome (1 = highest).
        Biomes with no configured tier are treated as the lowest possible
        priority — they can be interrupted by anything with a real tier, but
        can never interrupt anything themselves.
        """
        if not biome_name:
            return float("inf")
        return self.biome_priority_levels.get(normalize_biome_name(biome_name), float("inf"))

    async def on_ready(self):
        print(f"Logged in as {self.user}")

    async def on_message(self, message):
        if not self.is_running:
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
                    canonical_new_biome = canonical_biome_title(biome)
                    message_detected_at = time.time()

                    is_priority_interrupt = False

                    if self.active_biome_session:
                        # Already mid-session. Normally the Discord scanner stays
                        # quiet while the Roblox log monitor verifies and tracks
                        # the biome we already joined — the one exception is a
                        # strictly higher-priority biome showing up (a lower tier
                        # number, per biome_priority_level), which jumps the
                        # queue immediately.
                        current_level = self.biome_priority_level(self.active_biome_session)
                        new_level = self.biome_priority_level(canonical_new_biome)

                        if new_level >= current_level:
                            return

                        is_priority_interrupt = True

                        print(
                            f"[Discord Scanner] Higher-priority biome '{canonical_new_biome}' "
                            f"(tier {new_level}) detected while fishing '{self.active_biome_session}' "
                            f"(tier {current_level}). Interrupting current session..."
                        )
                        self._interrupt_for_priority_biome(self.active_biome_session, canonical_new_biome)

                    print(f"[Discord Scanner] Target Biome STARTED: {biome}")

                    urls = extract_urls(message)
                    
                    if len(urls) > 0:
                        raw_url = urls[0] # Grab the first link found

                        if self.fish_loop and self.fish_loop.gauntlet_swap_in_progress:
                            # A gauntlet swap is atomic and uninterruptible by
                            # design — launching a new server mid-swap would
                            # pull the game state out from under it (a fresh
                            # load screen appearing over the still-open
                            # inventory), so this join waits for the swap to
                            # finish instead of firing immediately.
                            print(
                                "[Discord Scanner] Gauntlet swap in progress — deferring this join "
                                "until it finishes."
                            )
                            self._deferred_action = {
                                "type": "join",
                                "raw_url": raw_url,
                                "biome": biome,
                                "canonical_new_biome": canonical_new_biome,
                                "is_priority_interrupt": is_priority_interrupt,
                                "message_detected_at": message_detected_at,
                            }
                            return

                        self._launch_and_track_join(
                            raw_url, biome, canonical_new_biome, is_priority_interrupt, message_detected_at
                        )
                        return
                    else:
                        print(f"[Discord Scanner] Biome '{biome}' started, but no links were found in the message.")

    def _launch_and_track_join(self, raw_url, biome, canonical_new_biome, is_priority_interrupt,
                                message_detected_at):
        """Resolves and launches a join, and sets up everything that
        depends on it (fishing toggle, auto-items, log monitoring). Called
        directly from on_message for a normal join, or later by
        handle_gauntlet_swap_finished() if it had to be deferred."""
        if self.fish_loop:
            self.fish_loop.toggle_off()

        # Let Roblox resolve it and launch!
        success = resolve_and_launch_with_cookie(raw_url, self.roblox_cookie)

        if success and self.fish_loop:
            self.fish_loop.begin_server_session()
            self.fish_loop.prepare_for_server_join()
            # Apply the expected biome's fishing toggle now, from the
            # Discord message itself, rather than waiting for log
            # confirmation (which can take 20+ seconds) — otherwise the bot
            # would still walk to the spot and sell before finding out it
            # should have just sat at spawn instead. _confirm_biome_session()
            # re-applies this once the real biome is confirmed from the
            # logs, in case this guess needs correcting.
            expected_norm = normalize_biome_name(canonical_new_biome)
            self.fish_loop.set_biome_fishing_enabled(
                self.fishing_enabled_biomes.get(expected_norm, True)
            )
            # Same reasoning applies to auto-items: resolve against the
            # expected biome now, since they need to run before pathing
            # starts — long before log confirmation would ever arrive.
            matched_auto_items = [
                {"name": item["name"], "quantity": item["quantity"]}
                for item in self.auto_items
                if item.get("enabled")
                and expected_norm in {normalize_biome_name(b) for b in item.get("biomes", [])}
            ]
            self.fish_loop.set_pending_auto_items(matched_auto_items)
            self.fish_loop.toggle_on(reset_initial_pathing=False)

        if success:
            self.pending_join_url = raw_url
            self.pending_join_is_priority_interrupt = is_priority_interrupt
            self.pending_join_detected_at = message_detected_at
            self._start_log_monitor(biome)

    def _interrupt_for_priority_biome(self, old_biome, new_biome):
        """
        Immediately abandons the current lower-priority biome session —
        stopping the log monitor and the fishing loop mid-action — so we're
        clear to join the just-detected higher-priority biome.
        """
        with self.log_monitor_lock:
            self.log_monitor_stop.set()
            self.active_biome_session = None
            self.log_biome_confirmed = False

        if self.fish_loop:
            self.fish_loop.toggle_off()

        print(f"[Discord Scanner] Abandoned '{old_biome}' to chase priority biome '{new_biome}'.")

        if self.ui_reference:
            self.ui_reference.update_status(f"Interrupting {old_biome} for priority biome {new_biome}...")

        if self.webhook_url:
            from webhook import Webhook
            Webhook(self.webhook_url).send_priority_interrupt(old_biome, new_biome)

    def _start_log_monitor(self, biome):
        canonical_biome = canonical_biome_title(biome)

        with self.log_monitor_lock:
            self.log_monitor_stop.set()
            self.log_monitor_stop = threading.Event()
            self.active_biome_session = canonical_biome
            self.log_biome_confirmed = False
            self.session_join_url = self.pending_join_url
            self.session_is_priority_interrupt = self.pending_join_is_priority_interrupt
            self.session_detected_at = self.pending_join_detected_at

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
                self._confirm_biome_session(current_biome, stop_event)
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
                                self._confirm_biome_session(detected_biome, stop_event)
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

    def _wait_for_join_screenshot(self, stop_event=None, poll_interval=0.5,
                                   timeout=JOIN_SCREENSHOT_WAIT_TIMEOUT):
        """Blocks until fish_loop has captured this session's join screenshot,
        so the "Joined" embed always goes out with one attached rather than
        firing without it just because confirmation happened first. Bails out
        early (returning None) if this session gets abandoned while waiting —
        a priority interrupt, the bot/scanner stopping, etc. — and gives up
        after `timeout` seconds so a session that was never going to get a
        screenshot (Start button check bypassed or timed out) can't hang this
        thread forever."""
        deadline = time.time() + timeout
        while True:
            if self.fish_loop and getattr(self.fish_loop, "last_join_screenshot", None):
                return self.fish_loop.last_join_screenshot
            if stop_event is not None and stop_event.is_set():
                return None
            if not self.is_running:
                return None
            if not self.fish_loop or not self.fish_loop.is_running:
                return None
            if time.time() >= deadline:
                print(
                    f"[Discord Scanner] Gave up waiting for the join screenshot after "
                    f"{timeout}s; sending the Joined embed without one."
                )
                return None
            time.sleep(poll_interval)

    def _schedule_checkin_screenshot(self, biome, stop_event, delay):
        """Captures and sends a second screenshot `delay` seconds after a
        Glitched/Dreamspace/Cyberspace confirmation — but only if that same
        biome session is still active at that point. If it ends (biome
        change, priority interrupt, bot/scanner stop) before the delay
        elapses, this exits quietly without capturing or sending anything."""

        def still_this_session():
            return not stop_event.is_set() and self.active_biome_session == biome and self.is_running

        def wait_then_send():
            deadline = time.time() + delay
            while time.time() < deadline:
                if not still_this_session():
                    print(f"[Discord Scanner] {biome} ended before the check-in mark; skipping the follow-up screenshot.")
                    return
                time.sleep(0.5)

            if not still_this_session():
                print(f"[Discord Scanner] {biome} ended before the check-in mark; skipping the follow-up screenshot.")
                return

            if not self.fish_loop:
                return

            screenshot_bytes = self.fish_loop.capture_screenshot()
            if not screenshot_bytes:
                print(f"[Discord Scanner] Could not capture the {biome} check-in screenshot.")
                return

            # Re-check right before sending — the capture itself takes a
            # moment, and we don't want to post a shot for a session that
            # just ended.
            if not still_this_session():
                print(f"[Discord Scanner] {biome} ended just as the check-in screenshot finished; discarding it.")
                return

            if self.webhook_url:
                from webhook import Webhook
                Webhook(self.webhook_url).send_screenshot(
                    screenshot_bytes, title=f"{biome}: Check-in Screenshot (+{delay}s)"
                )

        threading.Thread(target=wait_then_send, daemon=True).start()

    def _confirm_biome_session(self, biome, stop_event=None):
        if self.log_biome_confirmed and self.active_biome_session == biome:
            return

        self.log_biome_confirmed = True
        self.active_biome_session = biome
        print(f"[Log Scanner] Confirmed active biome from Roblox logs: {biome}")
        if self.fish_loop:
            self.fish_loop.request_gauntlet_for_biome(biome)
        if self.ui_reference:
            self.ui_reference.update_status(f"Fishing in {biome}...")
        if self.webhook_url:
            from webhook import Webhook
            screenshot_bytes = self._wait_for_join_screenshot(stop_event)
            Webhook(self.webhook_url).send_biome_joined(
                biome,
                join_url=self.session_join_url,
                is_priority_interrupt=self.session_is_priority_interrupt,
                ping_user_id=self.discord_ping_user_id,
                screenshot_bytes=screenshot_bytes,
            )

        norm = normalize_biome_name(biome)

        if self.fish_loop:
            fishing_enabled = self.fishing_enabled_biomes.get(norm, True)
            self.fish_loop.set_biome_fishing_enabled(fishing_enabled)

        biome_checkin_config = self.checkin_screenshot_settings.get(norm)
        if (biome_checkin_config
                and biome_checkin_config.get("enabled")
                and biome_checkin_config.get("delay")
                and stop_event is not None
                and self._checkin_followup_stop_event is not stop_event):
            self._checkin_followup_stop_event = stop_event
            self._schedule_checkin_screenshot(biome, stop_event, int(biome_checkin_config["delay"]))

    # ------------------------------------------------------------------
    # Log health watchdog — runs for the whole time the scanner is on,
    # independent of whether a specific biome is currently being tracked.
    # The per-biome log monitor (_monitor_joined_biome_log) only exists
    # while actively confirming/tracking one target biome; the moment that
    # ends, its thread stops entirely, which would otherwise leave no one
    # watching the log during a "keep fishing while scanning for the next
    # biome" stretch. This watchdog covers that gap by watching whichever
    # log is currently relevant on its own, the whole time the bot is on.
    # ------------------------------------------------------------------

    LOG_DISCONNECT_THRESHOLD = 60  # seconds of no log writes = assume Roblox disconnected
    LOG_WATCHDOG_POLL_INTERVAL = 5
    LOG_WATCHDOG_REFRESH_EVERY = 6  # re-identify the log every ~30s, so log rotation is picked up

    def _start_log_watchdog(self):
        self.log_watchdog_stop = threading.Event()
        self.log_watchdog_thread = threading.Thread(
            target=self._log_watchdog_loop, args=(self.log_watchdog_stop,), daemon=True,
        )
        self.log_watchdog_thread.start()

    def _log_watchdog_loop(self, stop_event):
        log_path = None
        poll_count = 0

        while self.is_running and not stop_event.is_set():
            if stop_event.wait(self.LOG_WATCHDOG_POLL_INTERVAL):
                return
            if not self.is_running:
                return

            if not self.fish_loop or not self.fish_loop.is_running:
                # Nothing actually in a server right now — nothing to watch.
                log_path = None
                poll_count = 0
                continue

            poll_count += 1
            if log_path is None or poll_count % self.LOG_WATCHDOG_REFRESH_EVERY == 0:
                candidate = identify_roblox_log(self.roblox_cookie)
                if candidate:
                    log_path = candidate

            if not log_path:
                continue

            try:
                age = time.time() - log_path.stat().st_mtime
            except OSError:
                continue

            if age < self.LOG_DISCONNECT_THRESHOLD:
                continue

            print(f"[Log Scanner] No Roblox log activity for {int(age)}s — assuming a disconnect.")
            self._handle_disconnect()

            # Give the newly (re)joined session a fresh window before
            # checking staleness again, and force a fresh log lookup.
            log_path = None
            poll_count = 0
            stop_event.wait(self.LOG_DISCONNECT_THRESHOLD)

    def _handle_disconnect(self):
        """Called by the log watchdog after a sustained silence from the
        Roblox log. Unlike a normal "biome ended" (which now deliberately
        keeps fishing in place — see _finish_biome_session), a disconnect
        means there's no live game session left to fish in at all, so this
        always stops the fish loop first.
        - If a specific biome was being tracked, that tracking ends and
          Discord scanning resumes (equivalent to "start scanning again").
        - If no biome was being tracked (already just scanning/fishing in
          place with no target), "scanning again" would be a no-op, so
          instead this rejoins a random public server on the same place,
          ignoring any specific job/instance ID, to get unstuck.
        """
        was_tracking_biome = self.active_biome_session

        with self.log_monitor_lock:
            self.active_biome_session = None
            self.log_biome_confirmed = False
            self.log_monitor_stop.set()

        if was_tracking_biome:
            print(
                f"[Log Scanner] Roblox appears to have disconnected while fishing "
                f"'{was_tracking_biome}'. Stopping and resuming Discord scan."
            )
            if self.fish_loop:
                self.fish_loop.toggle_off()
            if self.ui_reference:
                self.ui_reference.update_status("Scanning for biomes...")
        else:
            print("[Log Scanner] Roblox appears to have disconnected. Rejoining a random public server...")
            self._rejoin_random_public_server()

    def _rejoin_random_public_server(self):
        """Rejoins a random public server for the configured place, ignoring
        any specific job/instance ID (i.e. normal public matchmaking rather
        than a targeted join) — used to recover when the bot wasn't
        tracking a specific target biome, so there's nothing more specific
        to fall back on, but the Roblox log has still gone stale."""
        if self.fish_loop and self.fish_loop.gauntlet_swap_in_progress:
            # Same reasoning as the join case above: a gauntlet swap can't
            # tolerate the game state changing out from under it.
            print("[Discord Scanner] Gauntlet swap in progress — deferring the recovery rejoin until it finishes.")
            self._deferred_action = {"type": "rejoin_public"}
            return

        if self.fish_loop:
            self.fish_loop.toggle_off()

        url = f"roblox://experiences/start?placeId={DEFAULT_PLACE_ID}"
        print(f"[Log Scanner] Launching recovery join: {url}")
        try:
            os.startfile(url)
        except Exception as e:
            print(f"[Log Scanner] Failed to launch recovery join: {e}")
            return

        if self.fish_loop:
            self.fish_loop.begin_server_session()
            self.fish_loop.prepare_for_server_join()
            self.fish_loop.set_biome_fishing_enabled(True)  # unknown biome — default to fishing normally
            self.fish_loop.toggle_on(reset_initial_pathing=False)

        if self.ui_reference:
            self.ui_reference.update_status("Reconnecting to a public server...")

    def handle_gauntlet_swap_finished(self):
        """Called by fish_loop once a gauntlet swap finishes — whether it
        completed normally or was cut short by a user stop. Applies
        whatever automation-driven action, if any, got deferred while the
        swap's lock was held. At most one action is ever remembered; if
        several would have fired during the swap, only the most recent
        matters once it's over."""
        action = self._deferred_action
        self._deferred_action = None
        if not action or not self.is_running:
            return

        if action["type"] == "join":
            print(f"[Discord Scanner] Gauntlet swap finished — resuming the deferred join for '{action['biome']}'.")
            self._launch_and_track_join(
                action["raw_url"], action["biome"], action["canonical_new_biome"],
                action["is_priority_interrupt"], action["message_detected_at"],
            )
        elif action["type"] == "rejoin_public":
            print("[Discord Scanner] Gauntlet swap finished — resuming the deferred recovery rejoin.")
            self._rejoin_random_public_server()

    # ------------------------------------------------------------------
    # Time-in-biome tracking — a second continuous, independent thread
    # (same "runs the whole time the bot is on" shape as the log watchdog
    # above) that tails the current log for ANY biome appearing in it, not
    # just the current Discord target, so waiting time in a non-target
    # biome between announcements still counts. It's kept as its own
    # thread rather than merged into the watchdog to avoid touching that
    # thread's already-correct staleness logic.
    # ------------------------------------------------------------------

    BIOME_TIME_POLL_INTERVAL = 1.0

    def set_biome_time_updated_callback(self, callback):
        """callback(biome_title, new_total_seconds) — fired every time a
        timing segment for a biome is committed to its running total."""
        self.biome_time_updated_callback = callback

    def _start_biome_time_tracker(self):
        self.biome_time_stop = threading.Event()
        self.biome_time_thread = threading.Thread(
            target=self._biome_time_tracker_loop, args=(self.biome_time_stop,), daemon=True,
        )
        self.biome_time_thread.start()

    def _biome_time_tracker_loop(self, stop_event):
        log_path = None
        last_pos = 0

        while self.is_running and not stop_event.is_set():
            if stop_event.wait(self.BIOME_TIME_POLL_INTERVAL):
                break
            if not self.is_running:
                break

            if not self.fish_loop or not self.fish_loop.is_running:
                # Not actively in a server (or the session just ended) —
                # close out whatever was being timed. Usually already
                # closed via the session_end_callback by this point; this
                # is just a safety net (a no-op if so).
                self._close_biome_time_segment()
                log_path = None
                last_pos = 0
                continue

            try:
                if log_path is None:
                    candidate = identify_roblox_log(self.roblox_cookie)
                    if not candidate:
                        continue
                    log_path = candidate
                    # Start tailing from the current end rather than
                    # replaying the whole file — biome lines only start
                    # appearing once actually in-game post-Start-button
                    # anyway, so this naturally only picks up lines from
                    # this point forward.
                    last_pos = os.path.getsize(log_path)
                    continue

                current_size = os.path.getsize(log_path)

                if current_size < last_pos:
                    # Log rotated/truncated — re-identify and resume from
                    # the end of whatever log is current now.
                    candidate = identify_roblox_log(self.roblox_cookie)
                    log_path = candidate
                    last_pos = os.path.getsize(log_path) if log_path else 0
                    continue

                if current_size > last_pos:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(last_pos)
                        new_data = f.read(current_size - last_pos)
                    last_pos = current_size
                    self._process_biome_time_lines(new_data)

            except Exception as e:
                print(f"[Biome Timer] Error while tailing log: {e}")

        self._close_biome_time_segment()

    def _process_biome_time_lines(self, data):
        """Scans a batch of newly-read log text for biome RPC lines in
        order, closing out and starting timing segments for each
        transition found — so several biome changes within one poll
        interval are all accounted for individually using their own log
        timestamps, rather than only the last one being noticed."""
        for line in data.splitlines():
            detected_title = detect_biome_from_rpc_line(line)
            if not detected_title or detected_title == self._biome_time_current:
                continue

            line_timestamp = parse_log_timestamp(line.split(",", 1)[0].strip())
            event_time = line_timestamp or datetime.now(timezone.utc)

            self._close_biome_time_segment(end_time=event_time)
            self._biome_time_current = detected_title
            self._biome_time_started_at = event_time

    def _close_biome_time_segment(self, end_time=None):
        """Commits the elapsed time for whichever biome is currently being
        timed (if any) into its running total, and clears the in-progress
        timer. Safe to call even when nothing is in progress (no-op)."""
        if self._biome_time_current is None or self._biome_time_started_at is None:
            return

        end_time = end_time or datetime.now(timezone.utc)
        elapsed = (end_time - self._biome_time_started_at).total_seconds()
        biome = self._biome_time_current
        self._biome_time_current = None
        self._biome_time_started_at = None

        if elapsed <= 0:
            return

        new_total = self.biome_time_totals.get(biome, 0.0) + elapsed
        self.biome_time_totals[biome] = new_total
        print(f"[Biome Timer] +{format_biome_duration(elapsed)} to {biome} "
              f"(total: {format_biome_duration(new_total)}).")
        if self.biome_time_updated_callback:
            self.biome_time_updated_callback(biome, new_total)

    def handle_fish_loop_session_ending(self):
        """Called by fish_loop right when a server session is ending — any
        toggle_off, whether that's a join transition, a disconnect, a
        priority interrupt, or a full manual stop — so time-in-biome
        tracking closes out whatever was in progress immediately instead
        of waiting for the tracker thread's next poll."""
        self._close_biome_time_segment()

    def reset_biome_time_totals(self):
        """Clears all recorded time-in-biome totals. Does not interrupt
        any timing segment currently in progress — it just zeroes the
        ledger, so an active segment's next commit starts a fresh total
        for that biome rather than being lost."""
        self.biome_time_totals = {}
        print("[Biome Timer] All biome time totals have been reset.")

    def _finish_biome_session(self, biome, reason, observed_biome=None, detail=None):
        with self.log_monitor_lock:
            if self.active_biome_session != biome:
                return

            self.active_biome_session = None
            self.log_biome_confirmed = False
            self.log_monitor_stop.set()

        if reason == "ended":
            # The biome genuinely ended (the log now shows something else,
            # or the fish loop already stopped on its own for an unrelated
            # reason) — rather than stopping the bot while the Discord
            # scanner looks for the next target biome, let it keep fishing
            # right where it is. The moment a new biome is detected and a
            # fresh join begins, on_message's own toggle_off() takes over
            # from there, so this doesn't fight with that.
            if self.fish_loop:
                self.fish_loop.set_biome_fishing_enabled(True)
            observed = f" New biome: {observed_biome}." if observed_biome else ""
            print(f"[Log Scanner] Biome ended: {biome}.{observed} Continuing to fish while scanning for a new biome.")
            duration_seconds = (
                time.time() - self.session_detected_at if self.session_detected_at is not None else None
            )
            if self.webhook_url:
                from webhook import Webhook
                Webhook(self.webhook_url).send_biome_ended(biome, duration_seconds=duration_seconds)
            if self.ui_reference:
                self.ui_reference.update_status("Fishing while scanning for biomes...")
        else:
            # A "fake" biome means the join itself was never real to begin
            # with (wrong link, stale announcement, etc.) — unlike a real
            # ending, there's nothing worth continuing here, so the bot
            # still stops and Discord scanning resumes on its own.
            if self.fish_loop:
                self.fish_loop.toggle_off()
            observed = f" Observed: {observed_biome}." if observed_biome else ""
            extra = f" {detail}." if detail else ""
            print(f"[Log Scanner] Fake biome detected for {biome}.{observed}{extra} Resuming Discord scan.")
            if self.ui_reference:
                self.ui_reference.update_status("Scanning for biomes...")

    def load_settings(self, token, biomes, cookie, mappings, webhook_url, ui_ref=None, biome_priority_levels=None,
                       discord_ping_user_id=None, checkin_screenshots=None, fishing_enabled_biomes=None,
                       auto_items=None):
        self.token = token
        self.selected_biomes = [canonical_biome_title(biome) for biome in biomes]
        self.roblox_cookie = cookie
        self.guild_mappings = mappings
        self.webhook_url = webhook_url
        self.ui_reference = ui_ref
        self.discord_ping_user_id = discord_ping_user_id.strip() if discord_ping_user_id else None
        if biome_priority_levels is not None:
            self.biome_priority_levels = {
                normalize_biome_name(biome): level for biome, level in biome_priority_levels.items()
            }
        if checkin_screenshots is not None:
            self.checkin_screenshot_settings = {
                normalize_biome_name(biome): {
                    "enabled": bool(config.get("enabled", False)),
                    "delay": int(config.get("delay", 0) or 0),
                }
                for biome, config in checkin_screenshots.items()
            }
        if fishing_enabled_biomes is not None:
            self.fishing_enabled_biomes = {
                normalize_biome_name(biome): bool(enabled) for biome, enabled in fishing_enabled_biomes.items()
            }
        if auto_items is not None:
            self.auto_items = list(auto_items)

    def toggle_on(self):
        print("[Discord Scanner] Started")
        self.is_running = True
        self.active_biome_session = None
        self.log_biome_confirmed = False
        self._start_log_watchdog()
        self._start_biome_time_tracker()
        if self.ui_reference:
            self.ui_reference.update_status("Scanning for biomes...")

    def toggle_off(self):
        print("[Discord Scanner] Paused")
        self.is_running = False
        self.active_biome_session = None
        self.log_biome_confirmed = False
        self.log_monitor_stop.set()
        if self.log_watchdog_stop:
            self.log_watchdog_stop.set()
        if self.biome_time_stop:
            self.biome_time_stop.set()
        self._close_biome_time_segment()

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