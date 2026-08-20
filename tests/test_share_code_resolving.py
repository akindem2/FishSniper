from urllib.parse import parse_qs, unquote, urlparse
import requests


def resolve_roblox_share_link(short_url: str):
    try:
        # 1. Fetch the short link response without allowing redirects
        response = requests.get(short_url, allow_redirects=False, timeout=10)
        resolved_url = (
            response.headers.get("Location")
            if response.status_code in [301, 302]
            else short_url
        )

        # 2. Parse the primary AppsFlyer tracking URL parameters
        parsed_url = urlparse(resolved_url)
        primary_params = parse_qs(parsed_url.query)

        # 3. Pull the deep link strings nested inside the tracking parameters
        af_dp = primary_params.get("af_dp", [None])[0]
        af_web_dp = primary_params.get("af_web_dp", [None])[0]

        # Prefer the native app deep link string ('af_dp'), fallback to web deep link ('af_web_dp')
        nested_target_url = af_dp or af_web_dp

        code = None
        link_type = None
        launch_data = None

        if nested_target_url:
            # 4. Deep link URLs require a second round of unquoting and parsing
            decoded_nested_url = unquote(nested_target_url)
            nested_parsed = urlparse(decoded_nested_url)
            nested_params = parse_qs(nested_parsed.query)

            # Extract the actual parameters packed by Roblox
            code = nested_params.get("code", [None])[0]
            link_type = nested_params.get("type", [None])[0]
            launch_data = nested_params.get("launchData", [None])[0]

        return {
            "resolved_url": resolved_url,
            "code": code,
            "type": link_type,
            "launchData": launch_data,
        }

    except requests.exceptions.RequestException as e:
        print(f"Network error handling link: {e}")
        return None


# --- Test using your resolved URL layout ---
if __name__ == "__main__":
    test_url = "https://ro.blox.com/Ebh5?pid=Server&is_retargeting=false&af_dp=roblox%3A%2F%2Fnavigation%2Fshare_links%3Fcode%3Da74d2b120b3e9b4ab6aa593cc17116dc%26type%3DServer&deep_link_value=roblox%3A%2F%2Fnavigation%2Fshare_links%3Fcode%3Da74d2b120b3e9b4ab6aa593cc17116dc%26type%3DServer"

    data = resolve_roblox_share_link(test_url)

    if data:
        print("--- Extracted Roblox Metadata ---")
        print(f"Share Code: {data['code']}")
        print(f"Link Type:  {data['type']}")
        print(f"LaunchData: {data['launchData']}")
