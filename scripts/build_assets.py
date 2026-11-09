#!/usr/bin/env python3
"""Generates the profile README visuals as self-contained SVG files.

  assets/hero.svg              terminal-style card with live GitHub stats
  assets/activity.svg          12-month contribution heatmap card
  assets/header.svg            animated aurora header with rotating tagline and waves
  assets/orbit.svg             rotating tech-stack orbit
  assets/rhythm.svg            monthly momentum + weekday chart
  assets/divider.svg           animated section divider
  assets/footer.svg            animated wave footer
  assets/projects/<slug>.svg   one designed card per featured project

Run locally:   python3 scripts/build_assets.py
In Actions:    GITHUB_TOKEN is used for the API (higher limits + contribution count).
If the API is unreachable, data/stats.json (the last good snapshot) is used.
"""
import json
import math
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

# ------------------------------------------------------- animated extras ---

def _wave(width, base, amp, period, phase=0.0, bottom=400):
    pts = []
    for x in range(0, int(width + period) + 20, 12):
        y = base + amp * math.sin(2 * math.pi * (x / period) + phase)
        pts.append(f"{x},{y:.1f}")
    return "M" + " L".join(pts) + f" L{int(width + period) + 20},{bottom} L0,{bottom} Z"


def header_svg():
    waves = ""
    specs = [(228, 12, 420, 0.0, "#58a6ff", .16, 16), (238, 14, 600, 1.7, "#a371f7", .20, 22), (248, 10, 300, 3.1, "#f778ba", .22, 12)]
    for base, amp, period, ph, col, op, dur in specs:
        waves += (f'<g class="wv" style="animation-duration:{dur}s;--shift:-{period}px">'
                  f'<path d="{_wave(900, base, amp, period, ph, 300)}" fill="{col}" fill-opacity="{op}"/></g>')
    phrases = ["Swift apps that run on-device", "Deep learning I measure honestly", "Security systems that fight back"]
    tag = ""
    for i, ph in enumerate(phrases):
        tag += (f'<text class="ph ph{i}" x="64" y="186" font-family="{MONO}" font-size="20" fill="url(#acc)">'
                f'<tspan fill="{MUTED}">&gt; </tspan>{escape(ph)}</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300" role="img" aria-label="{NAME}. Swift apps, deep learning, security systems.">
  <style>
    .blob {{ animation: drift 14s ease-in-out infinite alternate; }}
    .b2 {{ animation-duration: 18s; animation-direction: alternate-reverse; }}
    .b3 {{ animation-duration: 22s; }}
    .wv {{ animation: slide linear infinite; }}
    .ph {{ opacity: 0; animation: cycle 12s infinite; }}
    .ph0 {{ opacity: 1; }}
    .ph1 {{ animation-delay: 4s; }} .ph2 {{ animation-delay: 8s; }}
    .name {{ animation: rise 1.1s cubic-bezier(.2,.7,.2,1) backwards; }}
    .chip {{ animation: rise 1.1s .3s cubic-bezier(.2,.7,.2,1) backwards; }}
    .shine {{ animation: shine 5s ease-in-out 1.4s infinite; }}
    @keyframes drift {{ from {{ transform: translate(-40px,-10px); }} to {{ transform: translate(60px,25px); }} }}
    @keyframes slide {{ from {{ transform: translateX(0); }} to {{ transform: translateX(var(--shift)); }} }}
    @keyframes cycle {{ 0% {{ opacity: 0; transform: translateY(10px); }} 6%,30% {{ opacity: 1; transform: none; }} 36%,100% {{ opacity: 0; transform: translateY(-10px); }} }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes shine {{ 0% {{ transform: translateX(-260px); }} 60%,100% {{ transform: translateX(980px); }} }}
  </style>
  <defs>
    <clipPath id="cp"><rect width="900" height="300" rx="14"/></clipPath>
    <filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="55"/></filter>
    <filter id="soft" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>
    <linearGradient id="nm" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#cfe3ff"/><stop offset="1" stop-color="#e2c9ff"/></linearGradient>
    <linearGradient id="acc" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#79c0ff"/><stop offset=".55" stop-color="#d2a8ff"/><stop offset="1" stop-color="#ff9bd2"/></linearGradient>
    <linearGradient id="sh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#fff" fill-opacity=".07"/></pattern>
    <clipPath id="nameclip"><text x="60" y="124" font-family="{SANS}" font-size="68" font-weight="800" letter-spacing="-2">{NAME}</text></clipPath>
  </defs>
  <g clip-path="url(#cp)">
    <rect width="900" height="300" fill="#080b14"/>
    <g filter="url(#blur)" opacity=".95">
      <circle class="blob" cx="170" cy="70" r="120" fill="#3b82f6" fill-opacity=".55"/>
      <circle class="blob b2" cx="520" cy="40" r="130" fill="#8b5cf6" fill-opacity=".55"/>
      <circle class="blob b3" cx="800" cy="150" r="120" fill="#ec4899" fill-opacity=".40"/>
    </g>
    <rect width="900" height="300" fill="url(#dots)"/>
    <g class="chip">
      <rect x="64" y="32" width="224" height="26" rx="13" fill="#ffffff" fill-opacity=".07" stroke="#ffffff" stroke-opacity=".16"/>
      <circle cx="82" cy="45" r="4" fill="#3fb950"/>
      <text x="96" y="50" font-family="{MONO}" font-size="12" fill="#c9d1d9">B.Sc. Computer Science, HIT</text>
    </g>
    <g class="name">
      <text x="60" y="124" font-family="{SANS}" font-size="68" font-weight="800" letter-spacing="-2" fill="url(#nm)">{NAME}</text>
      <g clip-path="url(#nameclip)"><rect class="shine" x="0" y="50" width="120" height="90" fill="url(#sh)" transform="skewX(-20)"/></g>
    </g>
    {tag}
    {waves}
  </g>
  <rect x=".5" y=".5" width="899" height="299" rx="14" fill="none" stroke="#ffffff" stroke-opacity=".12"/>
</svg>
"""


ORBIT = [
    # ring label, radius, direction, seconds, colour, techs (label, brand colour)
    ("Apple", 96, 1, 46, "#f05138", [("Swift", "#f05138"), ("HealthKit", "#ff5c8a"), ("macOS", "#9ca3af")]),
    ("ML & Data", 158, -1, 62, "#a371f7", [("Python", "#3776ab"), ("PyTorch", "#ee4c2c"), ("NumPy", "#4dabcf"), ("Jupyter", "#f37626")]),
    ("Backend & Security", 218, 1, 84, "#58a6ff", [("TypeScript", "#3178c6"), ("C#", "#9b4f96"), ("Docker", "#2496ed"), ("MongoDB", "#47a248"), ("Socket.IO", "#9ca3af")]),
]


def orbit_svg():
    cx, cy = 450, 250
    rings, css = "", ""
    for ri, (label, r, direction, secs, col, techs) in enumerate(ORBIT):
        nodes = ""
        for i, (name, c) in enumerate(techs):
            ang = 2 * math.pi * i / len(techs) - math.pi / 2 + ri * 0.55
            x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
            w = len(name) * 7.6 + 30
            nodes += (f'<g transform="translate({x:.1f},{y:.1f})"><g class="up u{ri}">'
                      f'<rect x="{-w / 2:.1f}" y="-14" width="{w:.1f}" height="28" rx="14" fill="#0d1117" stroke="{c}" stroke-opacity=".85"/>'
                      f'<circle cx="{-w / 2 + 14:.1f}" cy="0" r="4" fill="{c}"/>'
                      f'<text x="{-w / 2 + 25:.1f}" y="4.5" font-family="{MONO}" font-size="12" fill="{FG}">{escape(name)}</text></g></g>')
        d = "normal" if direction > 0 else "reverse"
        css += (f".r{ri} {{ transform-origin: {cx}px {cy}px; animation: spin {secs}s linear infinite {d}; }}"
                f".u{ri} {{ transform-box: fill-box; transform-origin: center; animation: spin {secs}s linear infinite "
                f"{'reverse' if direction > 0 else 'normal'}; }}\n    ")
        rings += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-opacity=".28" stroke-dasharray="3 7"/>'
                  f'<g class="r{ri}">{nodes}</g>')
    legend = "".join(
        f'<circle cx="34" cy="{402 + i * 24}" r="5" fill="{col}"/><text x="48" y="{406 + i * 24}" font-family="{MONO}" font-size="12" fill="{MUTED}">{escape(label)}</text>'
        for i, (label, _, _, _, col, _) in enumerate(ORBIT)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500" viewBox="0 0 900 500" role="img" aria-label="Tech stack: Apple (Swift, HealthKit, macOS), ML and data (Python, PyTorch, NumPy, Jupyter), backend and security (TypeScript, C#, Docker, MongoDB, Socket.IO).">
  <style>
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    @keyframes pulse {{ 0% {{ transform: scale(1); opacity: .55; }} 100% {{ transform: scale(2.3); opacity: 0; }} }}
    .pl {{ transform-box: fill-box; transform-origin: center; animation: pulse 3.2s ease-out infinite; }}
    .pl2 {{ animation-delay: 1.6s; }}
    {css}
  </style>
  <defs>
    <clipPath id="cp"><rect width="900" height="500" rx="14"/></clipPath>
    <radialGradient id="core" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#a371f7"/><stop offset="1" stop-color="#3b82f6"/></radialGradient>
    <radialGradient id="bgl" cx=".5" cy=".5" r=".6"><stop offset="0" stop-color="#7c3aed" stop-opacity=".22"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
  </defs>
  <g clip-path="url(#cp)"><rect width="900" height="500" fill="{BG}"/><rect width="900" height="500" fill="url(#bgl)"/></g>
  <rect x=".5" y=".5" width="899" height="499" rx="14" fill="none" stroke="{BORDER}"/>
  <text x="32" y="38" font-family="{MONO}" font-size="14" font-weight="600" fill="{FG}"><tspan fill="{GREEN}">$</tspan> ls ~/stack --orbit</text>
  {rings}
  <circle class="pl" cx="{cx}" cy="{cy}" r="30" fill="none" stroke="#a371f7" stroke-width="2"/>
  <circle class="pl pl2" cx="{cx}" cy="{cy}" r="30" fill="none" stroke="#58a6ff" stroke-width="2"/>
  <circle cx="{cx}" cy="{cy}" r="30" fill="url(#core)"/>
  <text x="{cx}" y="{cy + 7}" text-anchor="middle" font-family="{SANS}" font-size="20" font-weight="800" fill="#fff">YB</text>
  {legend}
</svg>
"""


def _smooth(points):
    """Catmull-Rom spline through points -> SVG cubic path."""
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        c1, c2 = (c1[0], min(c1[1], 230)), (c2[0], min(c2[1], 230))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def rhythm_svg(stats):
    cal = stats.get("calendar")
    if not cal:
        return None
    start = date.fromisoformat(cal["start"])
    months, weekdays = {}, [0] * 7
    for i, c in enumerate(cal["counts"]):
        d = start + timedelta(days=i)
        months[(d.year, d.month)] = months.get((d.year, d.month), 0) + c
        weekdays[(d.weekday() + 1) % 7] += c
    keys = sorted(months)
    if len(keys) > 12:          # drop the oldest, partial month
        keys = keys[-12:]
    vals = [months[k] for k in keys]
    top = max(vals) or 1
    x0, x1, y0, y1 = 48, 560, 70, 230
    pts = [(x0 + (x1 - x0) * i / (len(vals) - 1), y1 - (y1 - y0) * math.sqrt(v / top)) for i, v in enumerate(vals)]
    line = _smooth(pts)
    area = line + f" L{pts[-1][0]:.1f},{y1} L{pts[0][0]:.1f},{y1} Z"
    peak_i = vals.index(top)
    labels = "".join(
        f'<text x="{x:.1f}" y="254" text-anchor="middle" class="s" fill="{MUTED}">{date(k[0], k[1], 1).strftime("%b")}</text>'
        for (x, _), k in zip(pts, keys)
    )
    grid = "".join(f'<line x1="{x0}" y1="{y1 - (y1 - y0) * f:.1f}" x2="{x1}" y2="{y1 - (y1 - y0) * f:.1f}" stroke="{BORDER}" stroke-opacity=".6" stroke-dasharray="2 6"/>' for f in (0, .5, 1))
    px, py = pts[peak_i]
    ex, ey = pts[-1]

    names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    wmax = max(weekdays) or 1
    bars = ""
    for i, (n, v) in enumerate(zip(names, weekdays)):
        y = 84 + i * 26
        w = 190 * v / wmax
        bars += (f'<text x="610" y="{y + 12}" class="s" fill="{MUTED}">{n}</text>'
                 f'<rect x="646" y="{y}" width="190" height="14" rx="7" fill="#161b22"/>'
                 f'<rect class="bar" style="animation-delay:{.15 * i + .4:.2f}s" x="646" y="{y}" width="{max(w, 3):.1f}" height="14" rx="7" fill="url(#bg2)"/>'
                 f'<text x="{646 + max(w, 3) + 8:.1f}" y="{y + 12}" class="s" fill="{FG}">{fmt(v)}</text>')
    best_day = names[weekdays.index(max(weekdays))]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300" role="img" aria-label="Contribution momentum by month and by weekday. Busiest month {date(keys[peak_i][0], keys[peak_i][1], 1).strftime('%B')} with {fmt(top)} contributions; busiest weekday {best_day}.">
  <style>
    .s {{ font: 11px {MONO}; }}
    .ln {{ stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 2.4s ease-out .2s forwards; }}
    .ar {{ animation: fadein 1.4s ease-out 1.4s backwards; }}
    .bar {{ transform-box: fill-box; transform-origin: left center; animation: grow .9s cubic-bezier(.2,.7,.2,1) backwards; }}
    .dot {{ transform-box: fill-box; transform-origin: center; animation: beat 2s ease-in-out 2.6s infinite; }}
    @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
    @keyframes fadein {{ from {{ opacity: 0; }} }}
    @keyframes grow {{ from {{ transform: scaleX(0); }} }}
    @keyframes beat {{ 0%,100% {{ transform: scale(1); }} 50% {{ transform: scale(1.8); }} }}
  </style>
  <defs>
    <clipPath id="cp"><rect width="900" height="300" rx="14"/></clipPath>
    <linearGradient id="la" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#58a6ff"/><stop offset=".55" stop-color="#a371f7"/><stop offset="1" stop-color="#f778ba"/></linearGradient>
    <linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a371f7" stop-opacity=".38"/><stop offset="1" stop-color="#a371f7" stop-opacity="0"/></linearGradient>
    <linearGradient id="bg2" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#58a6ff"/><stop offset="1" stop-color="#d2a8ff"/></linearGradient>
    <filter id="glow" x="-10%" y="-30%" width="120%" height="160%"><feGaussianBlur stdDeviation="3.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <g clip-path="url(#cp)"><rect width="900" height="300" fill="{BG}"/><rect width="900" height="2" fill="url(#la)" fill-opacity=".8"/></g>
  <rect x=".5" y=".5" width="899" height="299" rx="14" fill="none" stroke="{BORDER}"/>
  <text x="32" y="38" font-family="{MONO}" font-size="14" font-weight="600" fill="{FG}"><tspan fill="{GREEN}">$</tspan> ./rhythm --monthly --weekday</text>
  <text x="48" y="62" class="s" fill="{MUTED}">contributions per month (sqrt scale)</text>
  <text x="610" y="62" class="s" fill="{MUTED}">contributions per weekday</text>
  {grid}
  <path class="ar" d="{area}" fill="url(#ag)"/>
  <path class="ln" pathLength="1" d="{line}" fill="none" stroke="url(#la)" stroke-width="3" stroke-linecap="round" filter="url(#glow)"/>
  <circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="#fff"/>
  <text x="{px:.1f}" y="{py - 12:.1f}" text-anchor="middle" class="s" fill="{FG}">{fmt(top)}</text>
  <circle class="dot" cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="#f778ba"/>
  {labels}
  {bars}
</svg>
"""


def divider_svg():
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="28" viewBox="0 0 900 28" role="presentation" aria-hidden="true">
  <style>
    .sp {{ animation: run 5.5s ease-in-out infinite; }}
    @keyframes run {{ 0% {{ transform: translateX(-140px); opacity: 0; }} 15%,85% {{ opacity: 1; }} 100% {{ transform: translateX(900px); opacity: 0; }} }}
  </style>
  <defs>
    <linearGradient id="d" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#58a6ff" stop-opacity="0"/><stop offset=".5" stop-color="#a371f7" stop-opacity=".7"/><stop offset="1" stop-color="#f778ba" stop-opacity="0"/></linearGradient>
    <linearGradient id="s" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  </defs>
  <rect x="0" y="13" width="900" height="2" fill="url(#d)"/>
  <rect class="sp" x="0" y="12" width="140" height="4" fill="url(#s)"/>
</svg>
"""


def footer_svg():
    waves = ""
    for base, amp, period, ph, col, op, dur in [(70, 9, 380, 0.4, "#58a6ff", .18, 15), (82, 12, 520, 2.2, "#a371f7", .22, 20), (92, 8, 290, 4.0, "#f778ba", .24, 11)]:
        waves += (f'<g class="wv" style="animation-duration:{dur}s;--shift:-{period}px"><path d="{_wave(900, base, amp, period, ph, 130)}" fill="{col}" fill-opacity="{op}"/></g>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="130" viewBox="0 0 900 130" role="img" aria-label="Let's build something.">
  <style>
    .wv {{ animation: slide linear infinite; }}
    @keyframes slide {{ from {{ transform: translateX(0); }} to {{ transform: translateX(var(--shift)); }} }}
    .tx {{ animation: fade 1.2s ease-out backwards; }}
    @keyframes fade {{ from {{ opacity: 0; transform: translateY(8px); }} }}
  </style>
  <defs><clipPath id="cp"><rect width="900" height="130" rx="14"/></clipPath>
    <linearGradient id="a" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#79c0ff"/><stop offset=".55" stop-color="#d2a8ff"/><stop offset="1" stop-color="#ff9bd2"/></linearGradient></defs>
  <g clip-path="url(#cp)"><rect width="900" height="130" fill="#080b14"/>{waves}</g>
  <text class="tx" x="450" y="50" text-anchor="middle" font-family="{SANS}" font-size="26" font-weight="700" fill="url(#a)">Let's build something.</text>
  <rect x=".5" y=".5" width="899" height="129" rx="14" fill="none" stroke="#ffffff" stroke-opacity=".12"/>
</svg>
"""

# ------------------------------------------------------------------- main ---

def main():
    stats = load_stats()
    (ROOT / "assets" / "projects").mkdir(parents=True, exist_ok=True)
    (ROOT / "assets" / "hero.svg").write_text(hero_svg(stats), encoding="utf-8")
    for name, svg in (("header", header_svg()), ("orbit", orbit_svg()), ("divider", divider_svg()),
                      ("footer", footer_svg()), ("rhythm", rhythm_svg(stats))):
        if svg:
            (ROOT / "assets" / f"{name}.svg").write_text(svg, encoding="utf-8")
    act = activity_svg(stats)
    if act:
        (ROOT / "assets" / "activity.svg").write_text(act, encoding="utf-8")
    for p in PROJECTS:
        (ROOT / "assets" / "projects" / f"{p['slug']}.svg").write_text(project_svg(p), encoding="utf-8")
    print("assets written")


if __name__ == "__main__":
    main()
