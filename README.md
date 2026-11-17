# Spotify MCP Server

Install and start the MCP server:

```bash
pip install -r requirements.txt
python3 main.py
```

The server listens locally at `http://127.0.0.1:8000/mcp`. For Claude's custom
MCP connector, enter that URL. The host, port, and path can be changed with
`MCP_HOST`, `MCP_PORT`, and `MCP_PATH` in `.env`.

Copy `example.env` to `.env` and fill in the Spotify app credentials. The redirect URI
must be `http://127.0.0.1:3000` in both this file and the Spotify app settings.

The authorization flow uses Authorization Code with PKCE. The first tool call that
needs authentication opens Spotify consent in the browser. The login is cached in
`.spotify_tokens.json` and renewed automatically with a refresh token.

The server exposes:

- `auth`
- `get_current_user_profile`
- `get_top_items`
- `get_recently_played_tracks`
- `get_listening_summary`
- `search_spotify`

## Skill: Spotify-Steckbrief

`.claude/skills/spotify-steckbrief/` ist ein Claude-Skill, der aus den Daten dieses Servers eine
Profilkarte (`steckbrief/steckbrief.html`) mit vorsichtigen, hypothetischen Angaben zum
eigenen Hörprofil erzeugt. Claude erkennt projektlokale Skills in diesem Ordner automatisch.
Die erzeugten Dateien in `steckbrief/` enthalten persönliche Daten und sind per
`.gitignore` ausgeschlossen.

```bash
python3 .claude/skills/spotify-steckbrief/scripts/build_steckbrief.py facts steckbrief/raw/*.json -o steckbrief/facts.json
python3 .claude/skills/spotify-steckbrief/scripts/build_steckbrief.py render steckbrief/facts.json steckbrief/hypotheses.json -o steckbrief/steckbrief.html
```
