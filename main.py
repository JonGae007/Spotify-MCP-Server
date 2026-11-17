import random
import time
import os

import requests
from fastmcp import FastMCP
from dotenv import load_dotenv

from authorization import get_access_token


mcp = FastMCP("Spotify MCP Server")
load_dotenv()


def spotify_request(method, path, params=None):
    tokens = get_access_token()
    url = f"https://api.spotify.com/v1{path}"

    for attempt in range(4):
        response = requests.request(
            method,
            url,
            headers={"Authorization": "Bearer " + tokens["access_token"]},
            params=params,
            timeout=30,
        )

        if response.status_code != 429:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                try:
                    spotify_error = response.json().get("error", {})
                    message = spotify_error.get("message")
                except requests.JSONDecodeError:
                    message = None

                detail = message or response.text or "Spotify API request failed"
                raise RuntimeError(
                    f"Spotify API HTTP {response.status_code}: {detail}"
                ) from exc
            return response.json()

        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            delay = float(retry_after)
        else:
            delay = (2**attempt) + random.uniform(0, 0.25)

        if attempt == 3:
            raise RuntimeError(
                "Spotify API rate limit exceeded. Retry after "
                f"{int(delay)} seconds."
            )
        time.sleep(delay)


@mcp.tool
def auth() -> dict:
    """Authorize the app once and return the current Spotify profile."""
    return spotify_request("GET", "/me")


@mcp.tool
def get_current_user_profile() -> dict:
    """Get the current user's Spotify profile."""
    return spotify_request("GET", "/me")


@mcp.tool
def get_top_items(
    item_type: str,
    time_range: str = "medium_term",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Get top artists or tracks for short, medium, or long listening periods."""
    if item_type not in {"artists", "tracks"}:
        raise ValueError("item_type must be 'artists' or 'tracks'")
    if time_range not in {"short_term", "medium_term", "long_term"}:
        raise ValueError(
            "time_range must be 'short_term', 'medium_term', or 'long_term'"
        )
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if not 0 <= offset <= 1000:
        raise ValueError("offset must be between 0 and 1000")

    return spotify_request(
        "GET",
        f"/me/top/{item_type}",
        {
            "time_range": time_range,
            "limit": limit,
            "offset": offset,
        },
    )


@mcp.tool
def get_recently_played_tracks(limit: int = 20) -> dict:
    """Get recently played tracks, excluding podcast episodes."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")

    return spotify_request(
        "GET",
        "/me/player/recently-played",
        {"limit": limit},
    )


@mcp.tool
def get_listening_summary(limit: int = 20) -> dict:
    """Collect top tracks, top artists, and recent plays for listening analysis."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")

    return {
        "top_tracks": {
            time_range: get_top_items("tracks", time_range, limit)["items"]
            for time_range in ("short_term", "medium_term", "long_term")
        },
        "top_artists": {
            time_range: get_top_items("artists", time_range, limit)["items"]
            for time_range in ("short_term", "medium_term", "long_term")
        },
        "recently_played": get_recently_played_tracks(limit)["items"],
    }


@mcp.tool
def search_spotify(
    query: str,
    item_types: list[str],
    limit: int = 5,
    offset: int = 0,
    market: str | None = None,
) -> dict:
    """Search Spotify using the official /search endpoint."""
    if not query.strip():
        raise ValueError("query must not be empty")

    allowed_types = {
        "album",
        "artist",
        "playlist",
        "track",
        "show",
        "episode",
        "audiobook",
    }
    if not item_types:
        raise ValueError("item_types must contain at least one type")
    invalid = set(item_types) - allowed_types
    if invalid:
        raise ValueError("Unsupported item type(s): " + ", ".join(sorted(invalid)))
    if not 0 <= limit <= 10:
        raise ValueError("limit must be between 0 and 10")
    if not 0 <= offset <= 1000:
        raise ValueError("offset must be between 0 and 1000")

    params = {
        "q": query,
        "type": ",".join(item_types),
        "limit": limit,
        "offset": offset,
    }
    if market:
        params["market"] = market

    return spotify_request("GET", "/search", params)


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8000")),
        path=os.getenv("MCP_PATH", "/mcp"),
    )
