#!/usr/bin/env python3
"""Generates the profile README visuals as self-contained SVG files.

  assets/hero.svg              terminal-style card with live GitHub stats
  assets/activity.svg          12-month contribution heatmap card
  assets/projects/<slug>.svg   one designed card per featured project

Run locally:   python3 scripts/build_assets.py
In Actions:    GITHUB_TOKEN is used for the API (higher limits + contribution count).
If the API is unreachable, data/stats.json (the last good snapshot) is used.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, timedelta
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER = "yanivbahalul"
NAME = "Yaniv Bahalul"
CACHE = ROOT / "data" / "stats.json"

# ---------------------------------------------------------------- content ---
# Edit this list to change the project cards. Keep metric short (<= 17 chars).
PROJECTS = [
    {
        "slug": "honeyshield",
        "title": "HoneyShield",
        "tag": "Active cyber-deception platform",
        "metric": "Team of 4",
        "desc": "Decoy careers portal that lures attackers into traps (SQLi, XSS, SSRF, honey tokens) "
                "with a live analyst console. I built the admin panel, secure APIs and the attack-map dashboard.",
        "chips": ["TypeScript", "Docker", "MongoDB", "Socket.IO"],
        "accent": "#3178c6",
    },
    {
        "slug": "riddick",
        "title": "Riddick",
        "tag": "Low-light image & video enhancement",
        "metric": "3.55x less noise",
        "desc": "Built from scratch in PyTorch toward a live night camera. Multi-frame merging cuts noise "
                "3.55x from 72 frames at ~45 fps. The write-up keeps the failed experiments too.",
        "chips": ["Python", "PyTorch", "Raspberry Pi"],
        "accent": "#ee4c2c",
    },
    {
        "slug": "fitness-google-sync",
        "title": "fitness-google-sync",
        "tag": "Google Health to Apple Health",
        "metric": "17 data types",
        "desc": "iOS app that syncs a fitness band into Apple Health, with a Hebrew food diary, "
                "AI meal photos and calorie balance. Fully on-device, no server.",
        "chips": ["Swift", "HealthKit", "iOS"],
        "accent": "#f05138",
    },
    {
        "slug": "myinstants-macos",
        "title": "Myinstants-MacOS",
        "tag": "Native soundboard for macOS",
        "metric": "Ad-free",
        "desc": "Unofficial app for myinstants.com: browse, play, favorite, upload and delete sound "
                "buttons, with automatic upload prep and bundled ffmpeg.",
        "chips": ["Swift", "macOS", "ffmpeg"],
        "accent": "#bf5af2",
    },
    {
        "slug": "noodles-simulator",
        "title": "Noodles Simulator",
        "tag": "OOP practice quiz, live online",
        "metric": "25 stars",
        "desc": "Practice OOP questions with image-based multiple choice: live progress stats, "
                "minimized repeats and a global leaderboard.",
        "chips": ["C#", "Web", "Render"],
        "accent": "#34a853",
    },
    {
        "slug": "election-sms-classifier",
        "title": "Election SMS Classifier",
        "tag": "Hebrew NLP",
        "metric": "10-model ensemble",
        "desc": "Classifies campaign SMS as political or not. Multinomial Naive Bayes written from scratch "
                "in NumPy, with train-only cross-validation and an untouched test split.",
        "chips": ["Python", "NumPy", "Jupyter"],
        "accent": "#f37626",
    },
]

# Languages shown in the hero bar (markup/config languages are ignored).
LANG_COLORS = {
    "C#": "#178600", "JavaScript": "#f1e05a", "Jupyter Notebook": "#da5b0b",
    "Swift": "#f05138", "TypeScript": "#3178c6", "Python": "#3572a5",
    "Java": "#b07219", "Go": "#00add8", "Rust": "#dea584", "C++": "#f34b7d",
}

MONO = "'SF Mono','Menlo','Consolas','DejaVu Sans Mono','Liberation Mono',monospace"
SANS = "-apple-system,'Segoe UI','Helvetica Neue',Helvetica,Arial,sans-serif"

BG, BG2, BORDER = "#0d1117", "#161b22", "#30363d"
FG, MUTED, GREEN = "#e6edf3", "#8b949e", "#7ee787"
BLUE, PURPLE, ORANGE, PINK = "#79c0ff", "#d2a8ff", "#ffa657", "#ff7b72"

# ------------------------------------------------------------------ stats ---

def _get(url, token=None, data=None):
    headers = {"User-Agent": "profile-readme-builder", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def fetch_stats(token=None):
    user = _get(f"https://api.github.com/users/{USER}", token)
    repos = _get(f"https://api.github.com/users/{USER}/repos?per_page=100", token)
    langs = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        for k, v in _get(repo["languages_url"], token).items():
            langs[k] = langs.get(k, 0) + v
    stats = {
        "repos": user["public_repos"],
        "stars": sum(r["stargazers_count"] for r in repos if not r.get("fork")),
        "followers": user["followers"],
        "languages": langs,
    }
    if token:
        q = {"query": "query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{"
                      "totalContributions weeks{contributionDays{date contributionCount}}}}}}",
             "variables": {"u": USER}}
        try:
            res = _get("https://api.github.com/graphql", token, q)
            cal = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            days = sorted((d["date"], d["contributionCount"])
                          for w in cal["weeks"] for d in w["contributionDays"])
            stats["contributions"] = cal["totalContributions"]
            stats["calendar"] = {"start": days[0][0], "counts": [c for _, c in days]}
        except Exception as exc:  # keep the previous snapshot
            print("contribution calendar lookup failed:", exc, file=sys.stderr)
    return stats


def load_stats():
    cached = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    try:
        fresh = fetch_stats(os.environ.get("GITHUB_TOKEN"))
        cached.update(fresh)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cached, indent=2, ensure_ascii=False) + "\n")
        print("stats refreshed from the GitHub API")
    except Exception as exc:
        print("API unavailable, using cached stats:", exc, file=sys.stderr)
    return cached

# -------------------------------------------------------------------- svg ---

def wrap(text, width):
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + (1 if cur else 0) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def fmt(n):
    return f"{n:,}"


def hero_svg(stats):
    langs = {k: v for k, v in stats["languages"].items() if k in LANG_COLORS}
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)[:6]
    top_total = sum(v for _, v in top)

    bar_x, bar_w = 32, 836
    segs, x = [], bar_x
    for i, (name, val) in enumerate(top):
        w = bar_w * val / top_total
        segs.append(f'<rect x="{x:.1f}" y="0" width="{max(w - 2, 1):.1f}" height="14" fill="{LANG_COLORS[name]}"/>')
        x += w
    legend = []
    for i, (name, val) in enumerate(top):
        col, row = i % 3, i // 3
        lx, ly = 32 + col * 282, 322 + row * 26
        short = "Jupyter" if name == "Jupyter Notebook" else name
        legend.append(
            f'<circle cx="{lx + 5}" cy="{ly - 5}" r="5" fill="{LANG_COLORS[name]}"/>'
            f'<text x="{lx + 18}" y="{ly}" class="m" fill="{FG}">{escape(short)}</text>'
            f'<text x="{lx + 18 + (len(short) + 1) * 9.2:.0f}" y="{ly}" class="m" fill="{MUTED}">{val / top_total * 100:.0f}%</text>'
        )

    contrib = stats.get("contributions")
    contrib_part = (
        f'<tspan fill="{ORANGE}">{fmt(contrib)}</tspan> <tspan fill="{MUTED}">contributions / yr</tspan>'
        if contrib else ""
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="404" viewBox="0 0 900 404" role="img" aria-label="{NAME}: Computer Science student at HIT. Swift apps, deep learning, security systems.">
  <style>
    .m {{ font: 15px {MONO}; }}
    .t {{ font: 600 13px {SANS}; }}
    .l {{ animation: rise .6s ease-out backwards; }}
    .l1 {{ animation-delay: .1s }} .l2 {{ animation-delay: .5s }} .l3 {{ animation-delay: .9s }}
    .l4 {{ animation-delay: 1.3s }} .l5 {{ animation-delay: 1.7s }} .l6 {{ animation-delay: 2.1s }}
    .grow {{ transform-box: fill-box; transform-origin: left center; animation: grow 1.1s ease-out 2.2s backwards; }}
    .cur {{ animation: blink 1.1s steps(1) infinite; }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
    @keyframes blink {{ 50% {{ opacity: 0; }} }}
  </style>
  <defs>
    <clipPath id="win"><rect width="900" height="404" rx="14"/></clipPath>
    <clipPath id="bar"><rect x="{bar_x}" y="0" width="{bar_w}" height="14" rx="7"/></clipPath>
    <linearGradient id="glow" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#58a6ff" stop-opacity=".0"/>
      <stop offset=".5" stop-color="#a371f7" stop-opacity=".9"/>
      <stop offset="1" stop-color="#f778ba" stop-opacity=".0"/>
    </linearGradient>
  </defs>
  <g clip-path="url(#win)">
    <rect width="900" height="404" fill="{BG}"/>
    <rect width="900" height="40" fill="{BG2}"/>
    <rect y="40" width="900" height="1" fill="{BORDER}"/>
    <rect y="0" width="900" height="2" fill="url(#glow)"/>
    <circle cx="26" cy="20" r="6" fill="#ff5f56"/><circle cx="46" cy="20" r="6" fill="#ffbd2e"/><circle cx="66" cy="20" r="6" fill="#27c93f"/>
    <text x="450" y="25" text-anchor="middle" class="t" fill="{MUTED}">{USER}@hit : ~/profile : zsh</text>

    <g class="l l1">
      <text x="32" y="82" class="m"><tspan fill="{GREEN}">$</tspan> <tspan fill="{FG}">whoami</tspan></text>
      <text x="32" y="108" class="m" fill="{FG}"><tspan font-weight="700" font-size="19">{NAME}</tspan><tspan fill="{MUTED}">   B.Sc. Computer Science, HIT</tspan></text>
    </g>
    <g class="l l2">
      <text x="32" y="144" class="m"><tspan fill="{GREEN}">$</tspan> <tspan fill="{FG}">cat focus.txt</tspan></text>
      <text x="32" y="170" class="m"><tspan fill="{ORANGE}">Swift apps</tspan><tspan fill="{MUTED}">  +  </tspan><tspan fill="{BLUE}">deep learning</tspan><tspan fill="{MUTED}">  +  </tspan><tspan fill="{PINK}">security systems</tspan></text>
    </g>
    <g class="l l3">
      <text x="32" y="206" class="m"><tspan fill="{GREEN}">$</tspan> <tspan fill="{FG}">gh stats {USER}</tspan></text>
      <text x="32" y="232" class="m"><tspan fill="{BLUE}">{fmt(stats['repos'])}</tspan> <tspan fill="{MUTED}">repos</tspan>   <tspan fill="{ORANGE}">{fmt(stats['stars'])}</tspan> <tspan fill="{MUTED}">stars</tspan>   <tspan fill="{PURPLE}">{fmt(stats['followers'])}</tspan> <tspan fill="{MUTED}">followers</tspan>   {contrib_part}</text>
    </g>
    <g class="l l4">
      <text x="32" y="266" class="m" fill="{MUTED}"># languages by bytes</text>
    </g>
    <g class="grow">
      <g transform="translate(0,280)" clip-path="url(#bar)">{''.join(segs)}</g>
    </g>
    <g class="l l5">
      <g transform="translate(0,0)">{''.join(legend)}</g>
    </g>
    <g class="l l6">
      <text x="32" y="386" class="m"><tspan fill="{GREEN}">$</tspan> <tspan class="cur" fill="{FG}">_</tspan></text>
    </g>
  </g>
  <rect x=".5" y=".5" width="899" height="403" rx="14" fill="none" stroke="{BORDER}"/>
</svg>
"""


def _chips(chips, x0, y):
    out, x = [], x0
    for c in chips:
        w = len(c) * 7.4 + 20
        out.append(
            f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="24" rx="12" fill="#21262d" stroke="{BORDER}"/>'
            f'<text x="{x + w / 2:.1f}" y="{y + 16}" text-anchor="middle" font-family="{MONO}" font-size="12" fill="{MUTED}">{escape(c)}</text>'
        )
        x += w + 8
    return "".join(out)


def project_svg(p):
    lines = wrap(p["desc"], 56)[:4]
    desc = "".join(
        f'<text x="26" y="{110 + i * 19}" font-family="{SANS}" font-size="13" fill="{FG}" fill-opacity=".86">{escape(l)}</text>'
        for i, l in enumerate(lines)
    )
    a = p["accent"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="460" height="232" viewBox="0 0 460 232" role="img" aria-label="{escape(p['title'])}: {escape(p['tag'])}">
  <defs><clipPath id="c"><rect width="460" height="232" rx="14"/></clipPath>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{a}" stop-opacity=".15"/></linearGradient>
    <radialGradient id="r" cx="1" cy="0" r="1"><stop offset="0" stop-color="{a}" stop-opacity=".22"/><stop offset="1" stop-color="{a}" stop-opacity="0"/></radialGradient>
  </defs>
  <g clip-path="url(#c)">
    <rect width="460" height="232" fill="{BG}"/>
    <rect width="460" height="232" fill="url(#r)"/>
    <rect width="460" height="4" fill="url(#g)"/>
  </g>
  <rect x=".5" y=".5" width="459" height="231" rx="14" fill="none" stroke="{BORDER}"/>
  <circle cx="30" cy="38" r="5" fill="{a}"/>
  <text x="44" y="43" font-family="{SANS}" font-size="19" font-weight="700" fill="{FG}">{escape(p['title'])}</text>
  <text x="434" y="43" text-anchor="end" font-family="{MONO}" font-size="12" fill="{a}">{escape(p['metric'])}</text>
  <text x="26" y="72" font-family="{SANS}" font-size="13" fill="{MUTED}">{escape(p['tag'])}</text>
  <line x1="26" y1="84" x2="434" y2="84" stroke="{BORDER}"/>
  {desc}
  {_chips(p['chips'], 26, 192)}
</svg>
"""

HEAT = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


def activity_svg(stats):
    cal = stats.get("calendar")
    if not cal:
        return None
    counts, start = cal["counts"], date.fromisoformat(cal["start"])
    days = [(start + timedelta(days=i), c) for i, c in enumerate(counts)]

    nz = sorted(c for c in counts if c)
    q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.75)] if nz else [1, 2, 3]

    def level(c):
        return 0 if c == 0 else 1 + sum(c > t for t in q)

    # streaks
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    cur, i = 0, len(counts) - 1
    if counts and counts[i] == 0:
        i -= 1
    while i >= 0 and counts[i]:
        cur += 1
        i -= 1
    best_d, best_c = max(days, key=lambda t: t[1])
    active = sum(1 for c in counts if c)
    total = sum(counts)

    x0, y0, pitch, cell = 62, 84, 15, 12
    first_sun = start - timedelta(days=(start.weekday() + 1) % 7)
    cells, months, last_m = [], [], None
    for d, c in days:
        col = (d - first_sun).days // 7
        row = (d.weekday() + 1) % 7
        cells.append(
            f'<rect class="c" style="animation-delay:{col * 0.025:.2f}s" x="{x0 + col * pitch}" y="{y0 + row * pitch}" '
            f'width="{cell}" height="{cell}" rx="3" fill="{HEAT[level(c)]}"/>'
        )
        if row == 0 and d.month != last_m and (d - start).days >= 0:
            if last_m is not None or d.day <= 21:
                months.append(f'<text x="{x0 + col * pitch}" y="74" class="s" fill="{MUTED}">{d.strftime("%b")}</text>')
            last_m = d.month
    cols = (days[-1][0] - first_sun).days // 7 + 1
    width_used = x0 + cols * pitch

    day_labels = "".join(
        f'<text x="32" y="{y0 + r * pitch + 10}" class="s" fill="{MUTED}">{n}</text>'
        for r, n in ((1, "Mon"), (3, "Wed"), (5, "Fri"))
    )
    legend = "".join(
        f'<rect x="{746 + i * 17}" y="203" width="12" height="12" rx="3" fill="{HEAT[i]}"/>' for i in range(5)
    )

    def stat(x, big, label, color):
        return (f'<text x="{x}" y="262" class="big" fill="{color}">{big}</text>'
                f'<text x="{x}" y="282" class="s" fill="{MUTED}">{label}</text>')

    stats_row = (
        stat(32, fmt(total), "contributions", BLUE)
        + stat(232, str(active), "active days", PURPLE)
        + stat(432, f"{longest}d", "longest streak", ORANGE)
        + stat(632, f"{best_c}", f"busiest day, {best_d.strftime('%b %-d')}", GREEN)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="306" viewBox="0 0 900 306" role="img" aria-label="{fmt(total)} contributions in the last 12 months, {active} active days, longest streak {longest} days.">
  <style>
    .m {{ font: 600 14px {MONO}; }}
    .s {{ font: 11px {MONO}; }}
    .big {{ font: 700 24px {SANS}; }}
    .c {{ animation: pop .5s ease-out backwards; }}
    @keyframes pop {{ from {{ opacity: 0; transform: scale(.4); }} to {{ opacity: 1; transform: none; }} }}
    .c {{ transform-box: fill-box; transform-origin: center; }}
  </style>
  <defs>
    <clipPath id="w"><rect width="900" height="306" rx="14"/></clipPath>
    <linearGradient id="glow" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#58a6ff" stop-opacity="0"/><stop offset=".5" stop-color="#a371f7" stop-opacity=".9"/><stop offset="1" stop-color="#f778ba" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <g clip-path="url(#w)">
    <rect width="900" height="306" fill="{BG}"/>
    <rect width="900" height="2" fill="url(#glow)"/>
  </g>
  <rect x=".5" y=".5" width="899" height="305" rx="14" fill="none" stroke="{BORDER}"/>
  <text x="32" y="38" class="m" fill="{FG}"><tspan fill="{GREEN}">$</tspan> git log --since="12 months ago" --graph</text>
  <text x="868" y="38" text-anchor="end" class="s" fill="{MUTED}">updated daily</text>
  {''.join(months)}
  {day_labels}
  {''.join(cells)}
  <text x="728" y="213" text-anchor="end" class="s" fill="{MUTED}">Less</text>
  {legend}
  <text x="836" y="213" class="s" fill="{MUTED}">More</text>
  <line x1="32" y1="232" x2="868" y2="232" stroke="{BORDER}"/>
  {stats_row}
</svg>
"""

# ------------------------------------------------------------------- main ---

def main():
    stats = load_stats()
    (ROOT / "assets" / "projects").mkdir(parents=True, exist_ok=True)
    (ROOT / "assets" / "hero.svg").write_text(hero_svg(stats), encoding="utf-8")
    act = activity_svg(stats)
    if act:
        (ROOT / "assets" / "activity.svg").write_text(act, encoding="utf-8")
    for p in PROJECTS:
        (ROOT / "assets" / "projects" / f"{p['slug']}.svg").write_text(project_svg(p), encoding="utf-8")
    print("assets written")


if __name__ == "__main__":
    main()
