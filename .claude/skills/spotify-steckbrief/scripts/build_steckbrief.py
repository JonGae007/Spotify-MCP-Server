#!/usr/bin/env python3
"""Build a Spotify "Steckbrief" (profile card) as a self-contained HTML page.

Two steps:

  1. facts:  python3 build_steckbrief.py facts DATA.json [DATA.json ...] -o facts.json
     Reads raw JSON saved from the Spotify MCP tools (get_listening_summary,
     get_top_items, get_recently_played_tracks, get_current_user_profile) and
     computes hard facts: top artists, decades, explicit share, listening
     session times, overlap between time ranges.

  2. render: python3 build_steckbrief.py render facts.json hypotheses.json -o steckbrief.html
     Combines the facts with the hypotheses Claude wrote (see SKILL.md for the
     schema) into one HTML card with light and dark mode.

Only the Python standard library is used.
"""

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RANGES = ("short_term", "medium_term", "long_term")
RANGE_LABELS = {
    "short_term": "~4 Wochen",
    "medium_term": "~6 Monate",
    "long_term": "Gesamt",
}
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_sources(paths):
    """Sort every input file into tracks/artists per range, recent plays, profile."""
    data = {
        "tracks": {r: [] for r in RANGES},
        "artists": {r: [] for r in RANGES},
        "recent": [],
        "profile": None,
    }
    for path in paths:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(obj, dict) and "top_tracks" in obj:
            for r in RANGES:
                data["tracks"][r] += obj.get("top_tracks", {}).get(r, [])
                data["artists"][r] += obj.get("top_artists", {}).get(r, [])
            data["recent"] += obj.get("recently_played", [])
        elif isinstance(obj, dict) and "cursors" in obj:
            data["recent"] += obj.get("items", [])
        elif isinstance(obj, dict) and "/me/top/" in obj.get("href", ""):
            href = obj["href"]
            rng = next((r for r in RANGES if r in href), "medium_term")
            kind = "artists" if "/me/top/artists" in href else "tracks"
            data[kind][rng] += obj.get("items", [])
        elif isinstance(obj, dict) and obj.get("type") == "user":
            data["profile"] = obj
        else:
            print(f"warning: unrecognised file skipped: {path}", file=sys.stderr)

    # De-duplicate by id while keeping rank order.
    for kind in ("tracks", "artists"):
        for r in RANGES:
            seen, unique = set(), []
            for item in data[kind][r]:
                if item.get("id") not in seen:
                    seen.add(item.get("id"))
                    unique.append(item)
            data[kind][r] = unique
    seen, recent = set(), []
    for play in data["recent"]:
        if play.get("played_at") not in seen:
            seen.add(play.get("played_at"))
            recent.append(play)
    data["recent"] = sorted(recent, key=lambda p: p["played_at"])
    return data


# --------------------------------------------------------------------------- #
# Facts
# --------------------------------------------------------------------------- #
def artist_names(track):
    return [a["name"] for a in track.get("artists", [])]


def compute_facts(data, tz_name):
    tz = ZoneInfo(tz_name)
    facts = {"timezone": tz_name, "ranges": {}}

    profile = data["profile"] or {}
    facts["display_name"] = profile.get("display_name")
    facts["followers"] = (profile.get("followers") or {}).get("total")

    all_tracks = []
    for r in RANGES:
        tracks = data["tracks"][r]
        artists = data["artists"][r]
        all_tracks += tracks
        counter = Counter(n for t in tracks for n in artist_names(t)[:1])
        facts["ranges"][r] = {
            "label": RANGE_LABELS[r],
            "track_count": len(tracks),
            "artist_count": len(artists),
            "top_artists": [a["name"] for a in artists[:10]],
            "artists_by_track_count": counter.most_common(8),
            "top_tracks": [
                f'{t["name"]} – {", ".join(artist_names(t)[:2])}' for t in tracks[:10]
            ],
        }

    # Decades across all top tracks (unique).
    unique_tracks = {t["id"]: t for t in all_tracks}.values()
    decades = Counter()
    explicit = remix = 0
    durations = []
    for t in unique_tracks:
        year = (t.get("album", {}).get("release_date") or "")[:4]
        if year.isdigit():
            decades[f"{year[:3]}0er"] += 1
        explicit += bool(t.get("explicit"))
        name = t.get("name", "").lower()
        remix += any(k in name for k in ("remix", "sped up", "mix", "edit", "rmx"))
        durations.append(t.get("duration_ms", 0))
    n = max(len(durations), 1)
    facts["decades"] = sorted(decades.items())
    facts["explicit_share"] = round(100 * explicit / n)
    facts["remix_share"] = round(100 * remix / n)
    facts["avg_duration"] = round(sum(durations) / n / 1000)
    facts["unique_tracks"] = len(durations)

    # Overlap: tracks that appear in more than one range.
    ids = {r: {t["id"] for t in data["tracks"][r]} for r in RANGES}
    facts["overlap"] = {
        "medium_long": len(ids["medium_term"] & ids["long_term"]),
        "short_medium": len(ids["short_term"] & ids["medium_term"]),
    }
    stable = [a["name"] for a in data["artists"]["long_term"]
              if a["name"] in {x["name"] for x in data["artists"]["medium_term"]}]
    facts["stable_artists"] = stable

    # Recent plays → sessions in local time.
    plays = []
    for p in data["recent"]:
        ts = datetime.fromisoformat(p["played_at"].replace("Z", "+00:00"))
        plays.append((ts.astimezone(tz), p["track"]))
    hours = Counter(ts.hour for ts, _ in plays)
    weekdays = Counter(WEEKDAYS[ts.weekday()] for ts, _ in plays)
    sessions = []
    for ts, track in plays:
        if sessions and (ts - sessions[-1]["end"]).total_seconds() < 45 * 60:
            sessions[-1]["end"] = ts
            sessions[-1]["count"] += 1
        else:
            sessions.append({"start": ts, "end": ts, "count": 1})
    facts["recent"] = {
        "count": len(plays),
        "first": plays[0][0].isoformat() if plays else None,
        "last": plays[-1][0].isoformat() if plays else None,
        "hours": [hours.get(h, 0) for h in range(24)],
        "weekdays": [weekdays.get(d, 0) for d in WEEKDAYS],
        "sessions": [
            {
                "start": WEEKDAYS[s["start"].weekday()] + s["start"].strftime(" %d.%m. %H:%M"),
                "end": s["end"].strftime("%H:%M"),
                "count": s["count"],
            }
            for s in sessions
        ],
        "tracks": [
            f'{ts.strftime("%H:%M")} {t["name"]} – {", ".join(artist_names(t)[:2])}'
            for ts, t in plays
        ],
        "unique_artists": len({n for _, t in plays for n in artist_names(t)[:1]}),
    }
    days_since = None
    if plays:
        days_since = (datetime.now(timezone.utc) - plays[-1][0]).days
    facts["recent"]["days_since_last"] = days_since
    facts["generated"] = datetime.now(tz).strftime("%d.%m.%Y")
    return facts


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
CSS = """
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d1d1b;--muted:#6b6862;--line:#e6e2d9;
--accent:#1db954;--accent-soft:#e3f6ea;--low:#c2410c;--low-bg:#fdeee4;
--mid:#a16207;--mid-bg:#fdf5dc;--high:#15803d;--high-bg:#e3f4e8;--bar:#1db954;--bar2:#9ad9b0}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121212;--card:#1c1c1c;
--ink:#f2f2f2;--muted:#a3a3a3;--line:#2e2e2e;--accent-soft:#16301f;--low:#fb923c;--low-bg:#3a2014;
--mid:#facc15;--mid-bg:#352d10;--high:#4ade80;--high-bg:#13301d;--bar2:#2f6b44}}
:root[data-theme="dark"]{--bg:#121212;--card:#1c1c1c;--ink:#f2f2f2;--muted:#a3a3a3;--line:#2e2e2e;
--accent-soft:#16301f;--low:#fb923c;--low-bg:#3a2014;--mid:#facc15;--mid-bg:#352d10;--high:#4ade80;
--high-bg:#13301d;--bar2:#2f6b44}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:28px 16px 48px}
header{display:flex;gap:20px;align-items:center;margin-bottom:20px;flex-wrap:wrap}
.avatar{width:84px;height:84px;border-radius:50%;background:var(--accent);color:#fff;
display:grid;place-items:center;font-size:36px;font-weight:700;flex:none}
h1{margin:0;font-size:30px;letter-spacing:-.02em}.tag{color:var(--muted);margin:2px 0 0}
.note{font-size:12.5px;color:var(--muted);background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:10px 14px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;
grid-column:span 12;min-width:0}
@media(min-width:760px){.s6{grid-column:span 6}.s4{grid-column:span 4}.s8{grid-column:span 8}}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 10px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
.kpi b{display:block;font-size:24px;letter-spacing:-.02em}.kpi span{font-size:12.5px;color:var(--muted)}
.field{display:grid;grid-template-columns:150px 1fr auto;gap:4px 12px;padding:9px 0;
border-top:1px solid var(--line);align-items:baseline}.field:first-of-type{border-top:0}
.field .k{color:var(--muted);font-size:13px}.field .v{font-weight:600}
.field .e{grid-column:2/4;font-size:12.5px;color:var(--muted)}
@media(max-width:560px){.field{grid-template-columns:1fr auto}.field .k{grid-column:1/3}
.field .e{grid-column:1/3}}
.pill{font-size:11px;font-weight:600;padding:2px 8px;border-radius:99px;white-space:nowrap}
.gering{color:var(--low);background:var(--low-bg)}.mittel{color:var(--mid);background:var(--mid-bg)}
.hoch{color:var(--high);background:var(--high-bg)}
.bar{display:grid;grid-template-columns:120px 1fr 38px;gap:8px;align-items:center;margin:5px 0;
font-size:13px}.bar i{display:block;height:10px;border-radius:5px;background:var(--bar)}
.bar .t{background:var(--line);border-radius:5px}.bar .n{text-align:right;color:var(--muted)}
ol,ul{margin:0;padding-left:20px}li{margin:3px 0}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.cols h3{font-size:14px;margin:0 0 6px}.small{font-size:13px;color:var(--muted)}
.hours{display:flex;align-items:flex-end;gap:3px;height:90px;margin-top:6px}
.hours div{flex:1;background:var(--bar);border-radius:3px 3px 0 0;min-height:2px}
.hours div.z{background:var(--line)}
.hl{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:4px}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{background:var(--accent-soft);
border-radius:99px;padding:3px 10px;font-size:13px}
.portrait{font-size:15.5px;line-height:1.65}
footer{margin-top:22px;font-size:12px;color:var(--muted);text-align:center}
"""


def esc(value):
    return html.escape(str(value)) if value is not None else ""


def bars(rows, max_value=None):
    if not rows:
        return '<p class="small">Keine Daten.</p>'
    max_value = max_value or max(v for _, v in rows) or 1
    out = []
    for label, value in rows:
        width = round(100 * value / max_value)
        out.append(
            f'<div class="bar"><span>{esc(label)}</span><span class="t">'
            f'<i style="width:{width}%"></i></span><span class="n">{esc(value)}</span></div>'
        )
    return "".join(out)


def li(items):
    return "".join(f"<li>{esc(i)}</li>" for i in items)


def render(facts, hyp):
    name = hyp.get("name") or facts.get("display_name") or "Spotify-Profil"
    rec = facts["recent"]
    long_r = facts["ranges"]["long_term"]
    med_r = facts["ranges"]["medium_term"]

    kpis = [
        (long_r["top_artists"][0] if long_r["top_artists"] else "–", "Top-Künstler gesamt"),
        (
            med_r["artists_by_track_count"][0][0] if med_r["artists_by_track_count"] else "–",
            "Top-Künstler ~6 Monate",
        ),
        (f'{facts["unique_tracks"]}', "Top-Titel ausgewertet"),
        (f'{facts["explicit_share"]} %', "Explicit-Anteil"),
        (f'{facts["remix_share"]} %', "Remix / Sped-up / Edit"),
        (f'{facts["avg_duration"] // 60}:{facts["avg_duration"] % 60:02d}', "Ø Titellänge"),
    ]
    kpi_html = "".join(f'<div class="kpi"><b>{esc(v)}</b><span>{esc(k)}</span></div>' for v, k in kpis)

    fields = "".join(
        f'<div class="field"><span class="k">{esc(f["label"])}</span>'
        f'<span class="v">{esc(f["value"])}</span>'
        f'<span class="pill {esc(f.get("confidence", "gering"))}">{esc(f.get("confidence", "gering"))}</span>'
        f'<span class="e">{esc(f.get("evidence", ""))}</span></div>'
        for f in hyp.get("fields", [])
    )

    genres = bars([(g["name"], g["share"]) for g in hyp.get("genres", [])], 100)
    decades = bars(facts["decades"])

    range_cols = "".join(
        f'<div><h3>{esc(facts["ranges"][r]["label"])}</h3>'
        f'<p class="small">{facts["ranges"][r]["track_count"]} Titel · '
        f'{facts["ranges"][r]["artist_count"]} Künstler</p><ol>'
        + li(
            facts["ranges"][r]["top_artists"][:6]
            if len(facts["ranges"][r]["top_artists"]) >= 5
            else [f"{a} ({c} Titel)" for a, c in facts["ranges"][r]["artists_by_track_count"][:6]]
        )
        + "</ol></div>"
        for r in RANGES
    )

    max_h = max(rec["hours"]) or 1
    hours = "".join(
        f'<div class="{"z" if v == 0 else ""}" style="height:{max(2, round(88 * v / max_h))}px" '
        f'title="{h}:00 – {v} Titel"></div>'
        for h, v in enumerate(rec["hours"])
    )
    sessions = li(f'{s["start"]}–{s["end"]} · {s["count"]} Titel' for s in rec["sessions"])
    chips = "".join(f'<span class="chip">{esc(a)}</span>' for a in facts["stable_artists"]) or (
        '<span class="small">Keine Überschneidung messbar.</span>'
    )

    initial = esc(name[:1].upper())
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spotify Steckbrief</title><style>{CSS}</style></head><body><div class="wrap">
<header><div class="avatar">{initial}</div><div><h1>{esc(name)}</h1>
<p class="tag">{esc(hyp.get("tagline", ""))}</p></div></header>
<div class="note">Explorative Hypothesen aus Spotify-Daten, keine Fakten. Musikgeschmack ist kein
verlässlicher Hinweis auf persönliche Eigenschaften. Sicherheit:
<span class="pill gering">gering</span> <span class="pill mittel">mittel</span>
<span class="pill hoch">hoch</span></div>
<div class="grid">
<section class="card"><h2>Auf einen Blick</h2><div class="kpis">{kpi_html}</div></section>
<section class="card s8"><h2>Steckbrief</h2>{fields}</section>
<section class="card s4"><h2>Genre-Mix (geschätzt, %)</h2>{genres}
<h2 style="margin-top:18px">Jahrzehnte der Top-Titel</h2>{decades}</section>
<section class="card"><h2>Top-Künstler nach Zeitraum</h2><div class="cols">{range_cols}</div>
<h2 style="margin-top:16px">Konstant in „~6 Monate“ und „Gesamt“</h2><div class="chips">{chips}</div></section>
<section class="card s6"><h2>Zuletzt gehört – Uhrzeit ({esc(facts["timezone"])})</h2>
<div class="hours">{hours}</div><div class="hl"><span>0</span><span>6</span><span>12</span>
<span>18</span><span>23</span></div><p class="small" style="margin-top:10px">{rec["count"]} Wiedergaben ·
{rec["unique_artists"]} Künstler · zuletzt vor {esc(rec["days_since_last"])} Tagen</p>
<ul class="small">{sessions}</ul></section>
<section class="card s6"><h2>Porträt</h2><p class="portrait">{esc(hyp.get("portrait", ""))}</p></section>
<section class="card s6"><h2>Auffällige Hörmuster</h2><ol>{li(hyp.get("patterns", []))}</ol></section>
<section class="card s6"><h2>Könnte passen</h2><ul>{li(hyp.get("recommendations", []))}</ul></section>
<section class="card s6"><h2>Nicht ableitbar</h2><ul class="small">{li(hyp.get("not_derivable", []))}</ul></section>
<section class="card s6"><h2>Bitte korrigieren</h2><ol class="small">{li(hyp.get("questions", []))}</ol></section>
</div><footer>Erstellt am {esc(facts["generated"])} mit dem Spotify MCP Server · nur lokal, nicht teilen ohne Zustimmung</footer>
</div></body></html>"""


# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_facts = sub.add_parser("facts", help="compute facts from raw Spotify JSON")
    p_facts.add_argument("inputs", nargs="+")
    p_facts.add_argument("-o", "--output", default="facts.json")
    p_facts.add_argument("--tz", default="Europe/Berlin")
    p_render = sub.add_parser("render", help="render facts + hypotheses to HTML")
    p_render.add_argument("facts")
    p_render.add_argument("hypotheses")
    p_render.add_argument("-o", "--output", default="steckbrief.html")
    args = parser.parse_args()

    if args.cmd == "facts":
        facts = compute_facts(load_sources(args.inputs), args.tz)
        Path(args.output).write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        facts = json.loads(Path(args.facts).read_text(encoding="utf-8"))
        hyp = json.loads(Path(args.hypotheses).read_text(encoding="utf-8"))
        Path(args.output).write_text(render(facts, hyp), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
