# Spotify MCP Server

Lokaler FastMCP-Server, der Spotify-Hördaten über den Benutzer-Login bereitstellt und
Claude die Top-Künstler, Top-Titel und kürzlich abgespielten Titel zugänglich macht.
Der Server verwendet Authorization Code mit PKCE. Es wird kein Spotify-Client-Secret benötigt.

## Projektaufbau

```text
.
├── authorization.py                  # Spotify-Anmeldung (PKCE) und Token-Verwaltung
├── main.py                           # MCP-Server und Spotify-Tools
├── example.env                       # Vorlage für die lokale Konfiguration
├── requirements.txt                  # Python-Abhängigkeiten
├── .claude/
│   └── skills/
│       └── spotify-steckbrief/
│           ├── SKILL.md              # Anleitung für den Steckbrief-Skill
│           └── scripts/
│               └── build_steckbrief.py
├── steckbrief/                       # Erzeugte Profildaten und HTML-Karte (lokal)
│   ├── facts.json
│   ├── hypotheses.json
│   └── <profil>/
│       ├── raw/                      # Rohdaten aus den Spotify-Tools
│       └── steckbrief.html
├── .gitignore
└── README.md
```

Die lokale Konfiguration (`.env`), der Spotify-Token-Cache
(`.spotify_tokens.json`) und die persönlichen Steckbriefdaten unter `steckbrief/`
werden nicht in Git eingecheckt.

## Voraussetzungen

- macOS
- Python 3.10 oder neuer
- Ein Spotify-Konto
- Eine Spotify-App im [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
- Claude Desktop oder Claude mit MCP-Unterstützung

## 1. Projekt installieren

```bash
cd "/Users/jonasgartner/Documents/GitHub/Spotify MCP Server"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Alternativ ohne virtuelle Umgebung:

```bash
python3 -m pip install -r requirements.txt
```

## 2. Spotify-App einrichten

1. Öffne das [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Erstelle eine App.
3. Öffne die App-Einstellungen.
4. Füge unter **Redirect URIs** genau diese Adresse hinzu:

   ```text
   http://127.0.0.1:3000
   ```

5. Kopiere die **Client ID** der App.

Im Projektordner:

```bash
cp example.env .env
```

Trage in `.env` Deine Client ID ein:

```env
SPOTIFY_CLIENT_ID=deine-client-id
SPOTIFY_REDIRECT_URI=http://127.0.0.1:3000
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_PATH=/mcp
```

Die Datei `.env` und die gespeicherten Spotify-Tokens sind lokal und werden durch
`.gitignore` vom Git-Commit ausgeschlossen.

## 3. MCP-Server starten

```bash
cd "/Users/jonasgartner/Documents/GitHub/Spotify MCP Server"
source .venv/bin/activate
python3 main.py
```

Der MCP-Endpunkt läuft unter:

```text
http://<server-ip>:8000/mcp
```

Das Terminal muss während der Nutzung geöffnet bleiben.

Der MCP-Server bindet standardmäßig an `0.0.0.0` und ist damit über die Netzwerkadresse
des Rechners erreichbar. Port und Pfad können in `.env` über `MCP_PORT` und `MCP_PATH`
angepasst werden.
Der Spotify-Callback bleibt separat auf `127.0.0.1:3000`.

## 4. In Claude einrichten

### Claude Desktop oder Claude App

Öffne in den Einstellungen die MCP-/Connector-Verwaltung und füge einen benutzerdefinierten
Connector hinzu:

```text
Name: Spotify MCP
MCP-Server-URL: http://<server-ip>:8000/mcp
```

Starte Claude danach neu. Der Connector benötigt keinen öffentlichen HTTPS-Tunnel,
solange Claude auf demselben Mac läuft und der lokale Server aktiv ist.

### Claude Code

Bei laufendem Server:

```bash
claude mcp add --transport http --scope user spotify http://<server-ip>:8000/mcp
claude mcp list
```

Entfernen:

```bash
claude mcp remove --scope user spotify
```

## 5. Spotify einmalig autorisieren

Beim ersten Aufruf eines geschützten Tools wird die Autorisierung gestartet:

1. Der Browser öffnet die Spotify-Anmeldung.
2. Melde Dich an und erteile der App die Zustimmung.
3. Spotify ruft `http://127.0.0.1:3000` auf.
4. Der Token wird lokal in `.spotify_tokens.json` gespeichert.
5. Access-Tokens werden danach mit dem Refresh-Token erneuert.

Die angefragten Scopes sind auf die benötigten Hördaten beschränkt:

- `user-top-read`
- `user-read-recently-played`

## Verfügbare Tools

- `auth`: Autorisiert und gibt das aktuelle Spotify-Profil zurück.
- `get_current_user_profile`: Gibt das Profil des angemeldeten Kontos zurück.
- `get_top_items`: Gibt Top-Künstler oder Top-Titel für 4 Wochen, 6 Monate oder Gesamt zurück.
- `get_recently_played_tracks`: Gibt kürzlich abgespielte Titel zurück.
- `get_listening_summary`: Sammelt Top-Künstler, Top-Titel und aktuelle Wiedergaben.
- `search_spotify`: Sucht Katalogdaten für Alben, Künstler, Wiedergabelisten, Titel und andere Typen.

Das MCP-Tool `search_spotify` verwendet den offiziellen Spotify-Endpunkt
`GET https://api.spotify.com/v1/search`.

## Spotify-Steckbrief erzeugen

Das Projekt enthält den Claude-Skill `.claude/skills/spotify-steckbrief/`.
Claude kann ihn automatisch laden, wenn Du beispielsweise fragst:

```text
Erstelle einen Musik-Steckbrief aus meinem Spotify-Hörprofil.
```

Der Skill ruft die MCP-Tools ab und berechnet eine Profilkarte unter
`steckbrief/steckbrief.html`. Das Skript kann auch manuell ausgeführt werden:

```bash
python3 .claude/skills/spotify-steckbrief/scripts/build_steckbrief.py \
  facts steckbrief/raw/*.json \
  -o steckbrief/facts.json

python3 .claude/skills/spotify-steckbrief/scripts/build_steckbrief.py \
  render steckbrief/facts.json steckbrief/hypotheses.json \
  -o steckbrief/steckbrief.html
```

Die Dateien in `steckbrief/` enthalten persönliche Hördaten und sind durch
`.gitignore` ausgeschlossen. Nicht ohne Zustimmung veröffentlichen oder committen.

## Sicherheit und Datenschutz

- Kein Spotify-Client-Secret in diesem Projekt.
- Kein Commit von `.env`, `.spotify_tokens.json` oder `steckbrief/`.
- PKCE-Code-Verifier und OAuth-State werden nur während der Anmeldung lokal verwendet.
- Ergebnisse sind explorative Hörprofil-Hypothesen, keine belastbaren Aussagen über
  Persönlichkeit, Alter, Gesundheit, Herkunft oder Lebensumstände.
- Der MCP-Server bindet standardmäßig an `0.0.0.0`; verwende bei Bedarf eine Firewall,
  um den Zugriff auf vertrauenswürdige Netzwerke oder Geräte zu beschränken.
