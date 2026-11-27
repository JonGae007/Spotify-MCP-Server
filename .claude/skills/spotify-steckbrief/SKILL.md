---
name: spotify-steckbrief
description: Erstellt aus den Daten des Spotify MCP Servers einen grafischen "Steckbrief" (Profilkarte als HTML) mit vorsichtigen, hypothetischen Angaben zu Altersgruppe, Lebensphase, Stimmung, Energielevel, Sprachen, Lieblingsgenres und -künstlern, Geschmackswandel über die Zeiträume sowie Empfehlungen. Verwenden, wenn der Nutzer sein Spotify-Hörprofil analysieren, einen Steckbrief, ein Musik-Porträt oder eine Hörprofil-Grafik haben möchte.
---

# Spotify-Steckbrief

Erzeugt eine Profilkarte (`steckbrief.html`) zum **eigenen** Spotify-Konto des Nutzers.
Die Grafik enthält Kennzahlen, die sich hart aus den Daten berechnen lassen, und
Hypothesen, die Claude formuliert. Jede Hypothese hat eine Sicherheitsstufe und Belege.
Die ausführlichen Erklärungen gehören in den Chat, die Grafik bleibt kompakt.

## Grundregeln

- Nur das Konto des Nutzers selbst analysieren, das über den MCP-Server angemeldet ist.
  Keine Profile Dritter.
- Alles ist **explorativ**. Jede Angabe bekommt eine Sicherheit (`gering`, `mittel`, `hoch`).
  Altersgruppen nur grob: 13–17, 18–24, 25–34, 35–44, 45+.
- Keine Aussagen zu Geschlecht, sexueller Orientierung, Herkunft, Religion, Gesundheit oder
  psychischen Erkrankungen. Diese Punkte stehen in „Nicht ableitbar“.
- Die Datengrenzen offen nennen: Spotify liefert nur Ranglisten ohne Abspielzahlen, das
  Genre-Feld ist oft leer, und `recently_played` umfasst höchstens 50 Titel, die oft von
  einem einzigen Abend stammen.
- Die erzeugten Dateien enthalten persönliche Daten. Sie liegen in `steckbrief/`, und dieser
  Ordner ist per `.gitignore` ausgeschlossen. Nicht committen und nicht veröffentlichen,
  außer der Nutzer will das ausdrücklich.

## Ablauf

### 1. Daten holen

Diese MCP-Tools parallel aufrufen:

| Tool | Parameter |
|---|---|
| `get_current_user_profile` | – |
| `get_top_items` | `item_type=artists`, `time_range` = `short_term`, `medium_term`, `long_term`, jeweils `limit=50` |
| `get_top_items` | `item_type=tracks`, alle drei `time_range`, `limit=50` |
| `get_recently_played_tracks` | `limit=50` |

`get_listening_summary(limit=50)` liefert Top-Titel, Top-Künstler und letzte Wiedergaben in
einem Aufruf und kann die Einzelaufrufe ersetzen.

Jede Antwort **unverändert** als JSON-Datei in `steckbrief/raw/` speichern. Wenn die Antwort
zu groß war, hat der Client sie bereits als Datei abgelegt; dann diese Datei verwenden.
Das Skript erkennt am Inhalt, um welche Antwort es sich handelt; der Dateiname ist egal.

### 2. Fakten berechnen

```bash
python3 .claude/skills/spotify-steckbrief/scripts/build_steckbrief.py facts steckbrief/raw/*.json -o steckbrief/facts.json
```

Option `--tz` (Standard `Europe/Berlin`) für die Ortszeit der Wiedergaben.

`facts.json` enthält:

- `ranges.<range>`: Top-Künstler, Künstler nach Anzahl ihrer Top-Titel, Top-Titel
- `decades`: Erscheinungsjahrzehnte der Top-Titel
- `explicit_share`, `remix_share`, `avg_duration`
- `overlap` und `stable_artists`: wie viel sich zwischen den Zeiträumen deckt
- `recent`: Verteilung nach Uhrzeit und Wochentag, Hörsessions (Lücke unter 45 min),
  Tage seit der letzten Wiedergabe

Zusätzlich die Rohdaten selbst lesen (Titel, Künstler, Reihenfolge der Wiedergaben), um
Muster zu erkennen, die das Skript nicht misst, etwa Sprachen, Stimmungen oder Ausreißer.

### 3. Hypothesen schreiben: `steckbrief/hypotheses.json`

```json
{
  "name": "Anzeigename",
  "tagline": "Kurzformel des Profils, z. B. 'EDM-Fundament · Deutsch-Indie · Party-Nostalgie'",
  "fields": [
    {"label": "Altersgruppe", "value": "18–24", "confidence": "gering",
     "evidence": "konkrete Künstler/Titel/Zahlen aus den Daten"}
  ],
  "genres": [{"name": "EDM / Dance", "share": 30}],
  "portrait": "ca. 100 Wörter",
  "patterns": ["auffälliges Hörmuster mit Zahl"],
  "recommendations": ["Genre: Künstler, Künstler"],
  "not_derivable": ["…"],
  "questions": ["Rückfrage an den Nutzer zur Korrektur"]
}
```

Für `fields` mindestens diese Labels abdecken: Altersgruppe, Bildung / Alltag, Lebensphase,
Stimmung, Energielevel, Sprachen, Kultureller Rahmen, Lieblingskünstler, Geschmackswandel,
Aktuelles Hörverhalten, Interessen, Lifestyle.

`genres[].share` ist eine Schätzung in Prozent und sollte zusammen etwa 100 ergeben. Das
Genre-Feld von Spotify ist häufig leer, deshalb ordnet Claude die Künstler selbst zu.

Zahlen in `patterns` immer aus `facts.json` übernehmen, nicht schätzen.

### 4. Grafik rendern

```bash
python3 .claude/skills/spotify-steckbrief/scripts/build_steckbrief.py render steckbrief/facts.json steckbrief/hypotheses.json -o steckbrief/steckbrief.html
```

Die Seite ist eine einzelne HTML-Datei ohne externe Abhängigkeiten, mit Hell- und
Dunkelmodus und lesbar bis Handybreite. Danach die Datei dem Nutzer zeigen.

### 5. Erklärungen im Chat

Die Details kommen in den Chat, nicht in die Grafik. Für jedes Feld:

1. Hypothese
2. Wichtigste Datenpunkte
3. Sicherheit (gering, mittel oder hoch)
4. Warum die Daten die Hypothese nur teilweise stützen
5. Alternative Erklärungen

Danach kurz die Datengrenzen nennen und mit den Rückfragen aus `questions` enden. Wenn der
Nutzer Angaben korrigiert, `hypotheses.json` anpassen und nur Schritt 4 erneut ausführen.
