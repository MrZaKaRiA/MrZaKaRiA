#!/usr/bin/env python3
"""
MrZaKaRiA profile renderer — "Zellige" design system
Generates dark/light adaptive, animated SVG visualizations from live GitHub GraphQL data.
"""

from __future__ import annotations

import datetime
import html
import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
DATA_SNAPSHOT = ROOT_DIR / "assets" / "telemetry-snapshot.json"

GRAPHQL_QUERY = """
query {
  viewer {
    login
    name
    createdAt
    followers { totalCount }
    following { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        description
        isPrivate
        stargazerCount
        forkCount
        diskUsage
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
    pullRequests { totalCount }
    issues { totalCount }
    starredRepositories { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalIssueContributions
      totalPullRequestContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
    y2026: contributionsCollection(from: "2026-01-01T00:00:00Z", to: "2026-12-31T23:59:59Z") { contributionCalendar { totalContributions } }
    y2025: contributionsCollection(from: "2025-01-01T00:00:00Z", to: "2025-12-31T23:59:59Z") { contributionCalendar { totalContributions } }
    y2024: contributionsCollection(from: "2024-01-01T00:00:00Z", to: "2024-12-31T23:59:59Z") { contributionCalendar { totalContributions } }
    y2023: contributionsCollection(from: "2023-01-01T00:00:00Z", to: "2023-12-31T23:59:59Z") { contributionCalendar { totalContributions } }
    y2022: contributionsCollection(from: "2022-01-01T00:00:00Z", to: "2022-12-31T23:59:59Z") { contributionCalendar { totalContributions } }
    y2021: contributionsCollection(from: "2021-01-01T00:00:00Z", to: "2021-12-31T23:59:59Z") { contributionCalendar { totalContributions } }
    y2020: contributionsCollection(from: "2020-01-01T00:00:00Z", to: "2020-12-31T23:59:59Z") { contributionCalendar { totalContributions } }
  }
}
"""


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def fetch_github_data() -> dict[str, Any]:
    """Fetch live telemetry via gh CLI (preferred, has full user scope) or GITHUB_TOKEN."""
    raw_viewer = None
    try:
        res = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={GRAPHQL_QUERY}"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        payload = json.loads(res.stdout)
        raw_viewer = payload.get("data", {}).get("viewer")
    except Exception:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            try:
                req = urllib.request.Request(
                    "https://api.github.com/graphql",
                    data=json.dumps({"query": GRAPHQL_QUERY}).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "User-Agent": "MrZaKaRiA-Profile-Engine",
                    },
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    raw_viewer = payload.get("data", {}).get("viewer")
            except Exception:
                raw_viewer = None

    # Load previous snapshot as baseline (so private repo byte counts aren't lost in unprivileged CI)
    snapshot: dict[str, Any] = {}
    if DATA_SNAPSHOT.exists():
        try:
            snapshot = json.loads(DATA_SNAPSHOT.read_text(encoding="utf-8"))
        except Exception:
            snapshot = {}

    if not raw_viewer:
        return snapshot

    repos = raw_viewer["repositories"]["nodes"]
    has_private_access = any(r.get("isPrivate") for r in repos)

    langs: dict[str, int] = {}
    repo_map: dict[str, dict[str, Any]] = {}
    total_stars = 0
    total_forks = 0

    for r in repos:
        total_stars += r.get("stargazerCount", 0)
        total_forks += r.get("forkCount", 0)
        repo_map[r["name"]] = {
            "stars": r.get("stargazerCount", 0),
            "forks": r.get("forkCount", 0),
            "description": r.get("description") or "",
            "lang": (r.get("primaryLanguage") or {}).get("name") or "",
        }
        for edge in r.get("languages", {}).get("edges", []):
            lname = edge["node"]["name"]
            langs[lname] = langs.get(lname, 0) + edge["size"]

    cc = raw_viewer["contributionsCollection"]
    cal = cc["contributionCalendar"]
    weeks = cal["weeks"]

    yearly = {
        yr: raw_viewer.get(f"y{yr}", {}).get("contributionCalendar", {}).get("totalContributions", 0)
        for yr in range(2020, 2027)
    }
    lifetime_contributions = sum(yearly.values())

    # Calculate active days, max daily burst, and streaks from calendar
    all_days = [d for w in weeks for d in w["contributionDays"]]
    max_day = max((d["contributionCount"] for d in all_days), default=0)
    active_days = sum(1 for d in all_days if d["contributionCount"] > 0)

    # Preserve rich private telemetry if running in CI without private scope
    if not has_private_access and snapshot:
        owned_count = max(raw_viewer["repositories"]["totalCount"], snapshot.get("owned_repos", 61))
        langs = snapshot.get("languages", langs)
        annual_contributions = max(cal["totalContributions"], snapshot.get("annual_contributions", 2972))
        lifetime_contributions = max(lifetime_contributions, snapshot.get("lifetime_contributions", 3433))
        max_day = max(max_day, snapshot.get("max_daily_contributions", 95))
        yearly = snapshot.get("yearly_contributions", yearly)
        weeks_data = snapshot.get("weeks", weeks)
    else:
        owned_count = raw_viewer["repositories"]["totalCount"]
        annual_contributions = cal["totalContributions"]
        weeks_data = weeks

    result = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "followers": raw_viewer["followers"]["totalCount"],
        "owned_repos": owned_count,
        "public_repos_total": 650,
        "total_stars": max(total_stars, snapshot.get("total_stars", 25)),
        "total_forks": max(total_forks, snapshot.get("total_forks", 9)),
        "annual_contributions": annual_contributions,
        "lifetime_contributions": lifetime_contributions,
        "max_daily_contributions": max_day,
        "active_days_year": max(active_days, snapshot.get("active_days_year", 145)),
        "languages": langs,
        "yearly_contributions": yearly,
        "repos": repo_map,
        "weeks": weeks_data,
    }

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_SNAPSHOT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result




# ════════════════════════════════════════════════════════════════════════════
#  DESIGN SYSTEM — "Zellige"
#  Warm ink & paper, terracotta + Majorelle blue, editorial serif + mono.
#  Motifs: Moroccan horseshoe arches, diamond tile lattices, line icons.
#  No star shapes anywhere, by design.
# ════════════════════════════════════════════════════════════════════════════

import math

SERIF = "'Iowan Old Style','Palatino Linotype',Palatino,'Book Antiqua',Georgia,serif"
MONO = "ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"

THEMES = {
    "dark": {
        "bg": "#0C0B0A", "panel": "#12100E", "ink": "#EFE8DC", "muted": "#8C8377",
        "faint": "#4A443D", "line": "#26221E", "accent": "#E2603B",
        "blue": "#5867E8", "ochre": "#D9A441", "empty": "#1C1916",
    },
    "light": {
        "bg": "#F5EFE4", "panel": "#FBF7F0", "ink": "#1B1815", "muted": "#6F675C",
        "faint": "#B8AD9C", "line": "#DED3C2", "accent": "#C4471F",
        "blue": "#2F3FBF", "ochre": "#B07D1C", "empty": "#E9E0D1",
    },
}

# Line icons in local coordinates, centred on (0, 0), fitting a ~48px radius.
# Each entry: (path d, role) — role "fill" paths get the panel colour to occlude what's behind.
ICONS = {
    "windows": [  # stacked VM windows with a play glyph
        ("M-44 -30 H18 V12 H-44 Z", "line"), ("M-44 -20 H18", "line"),
        ("M-24 -12 H44 V32 H-24 Z", "fill"), ("M-24 -2 H44", "line"),
        ("M4 7 L19 15 L4 23 Z", "accent"),
    ],
    "terminal": [
        ("M-46 -32 H46 V32 H-46 Z", "line"), ("M-46 -20 H46", "line"),
        ("M-32 -6 L-20 4 L-32 14", "accent"), ("M-12 16 H10", "accent"),
    ],
    "river": [
        ("M-46 -18 q11.5 -12 23 0 t23 0 t23 0 t23 0", "line"),
        ("M-46 0 q11.5 -12 23 0 t23 0 t23 0 t23 0", "accent"),
        ("M-46 18 q11.5 -12 23 0 t23 0 t23 0 t23 0", "line"),
    ],
    "containers": [
        ("M-40 6 H-4 V30 H-40 Z", "line"), ("M-28 6 V30 M-16 6 V30", "line"),
        ("M4 6 H40 V30 H4 Z", "line"), ("M16 6 V30 M28 6 V30", "line"),
        ("M-18 -22 H18 V2 H-18 Z", "accent"), ("M-6 -22 V2 M6 -22 V2", "accent"),
    ],
    "cloud": [
        ("M-30 6 A14 14 0 0 1 -22 -20 A18 18 0 0 1 12 -28 A13 13 0 0 1 30 6 Z", "line"),
        ("M-16 18 l-5 12 M0 18 l-5 12 M16 18 l-5 12", "accent"),
    ],
    "database": [
        ("M-34 -26 a34 10 0 1 0 68 0 a34 10 0 1 0 -68 0", "line"),
        ("M-34 -26 V30 a34 10 0 0 0 68 0 V-26", "line"),
        ("M-34 -6 a34 10 0 0 0 68 0", "accent"), ("M-34 12 a34 10 0 0 0 68 0", "accent"),
    ],
}

PROJECTS = [
    {
        "slug": "lumenvm", "repo": "LumenVM", "name": "LumenVM", "kind": "Hypervisor UI",
        "lines": ["A native SwiftUI virtual machine manager", "for Apple Silicon. macOS, Linux and", "Windows ARM64, with sparse disks."],
        "stack": "Swift · SwiftUI · Virtualization.framework", "icon": "windows",
    },
    {
        "slug": "abysslinux", "repo": "AbyssLinux", "name": "AbyssLinux", "kind": "Operating system",
        "lines": ["A suckless, rolling-release Linux", "distribution on Void and runit, with", "dwm, st and dmenu. x86_64 and aarch64."],
        "stack": "C · Shell · xbps · runit", "icon": "terminal",
    },
    {
        "slug": "river", "repo": "river-desktop", "name": "RIVER ERP", "kind": "Business OS",
        "lines": ["Self-hosted ERP and CRM for Morocco", "and the EU: DGI e-invoicing, POS,", "stock, treasury and payroll."],
        "stack": "Rust · Tauri v2 · Laravel · Vue 3", "icon": "river",
    },
    {
        "slug": "virtualmin-docker", "repo": "Virtualmin-Docker", "name": "Virtualmin Docker", "kind": "Server tooling",
        "lines": ["Containers, images, volumes, networks", "and live logs, orchestrated from", "Webmin. Security-hardened."],
        "stack": "Perl · Docker · Webmin", "icon": "containers",
    },
    {
        "slug": "rain", "repo": "rain-desktop", "name": "RAIN", "kind": "Commerce platform",
        "lines": ["A complete commerce platform with a", "native desktop launcher for macOS,", "Windows and Linux."],
        "stack": "Rust · Tauri · PHP · Vue 3", "icon": "cloud",
    },
    {
        "slug": "db-backup", "repo": "Virtualmin-Db-Backup", "name": "Db Backup", "kind": "Disaster recovery",
        "lines": ["MySQL, Postgres, MongoDB and SQLite", "backups, host or Docker. Encrypted,", "checksummed, shipped off-site."],
        "stack": "Perl · Webmin · S3 · rclone", "icon": "database",
    },
]


def polygon(cx: float, cy: float, r: float, n: int, rot: float = -math.pi / 2) -> str:
    """Convex regular polygon (octagon etc.)."""
    pts = [(cx + r * math.cos(rot + i * 2 * math.pi / n), cy + r * math.sin(rot + i * 2 * math.pi / n)) for i in range(n)]
    return "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z"


def arch(x: float, c: float, w: float, base: float) -> str:
    """Moroccan horseshoe arch: a circle of radius w centred at (x, c), opened below, legs down to `base`."""
    lx, rx, sy = x - 0.8 * w, x + 0.8 * w, c + 0.6 * w
    return f"M{lx:.2f} {base:.2f} L{lx:.2f} {sy:.2f} A{w} {w} 0 1 1 {rx:.2f} {sy:.2f} L{rx:.2f} {base:.2f}"


def diamond(x: float, y: float, r: float) -> str:
    return f"M{x:.2f} {y - r:.2f} L{x + r:.2f} {y:.2f} L{x:.2f} {y + r:.2f} L{x - r:.2f} {y:.2f}Z"


def base_style(t: dict[str, str]) -> str:
    return f"""
    .serif {{ font-family: {SERIF}; }}
    .mono {{ font-family: {MONO}; }}
    .draw {{ stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 2.4s cubic-bezier(.65,0,.35,1) forwards; }}
    .fade {{ opacity: 0; animation: fade 1.2s ease forwards; }}
    .rise {{ opacity: 0; animation: rise 1s cubic-bezier(.2,.7,.2,1) forwards; }}
    @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
    @keyframes fade {{ to {{ opacity: 1; }} }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(14px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    @keyframes spinr {{ to {{ transform: rotate(-360deg); }} }}
    @keyframes blink {{ 50% {{ opacity: 0; }} }}
    @keyframes breathe {{ 0%,100% {{ opacity: .55; }} 50% {{ opacity: 1; }} }}
    @keyframes sway {{ 0%,100% {{ transform: rotate(-4deg); }} 50% {{ transform: rotate(4deg); }} }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ animation-duration: 0s !important; animation-delay: 0s !important; animation-iteration-count: 1 !important; }}
    }}"""


# ─── HERO ────────────────────────────────────────────────────────────────────
def render_hero(data: dict[str, Any], mode: str) -> str:
    t = THEMES[mode]
    W, H = 1200, 460
    cx, cy = 930, 230

    # Background: diamond tile lattice, faded by a radial mask
    tile = 56
    h = tile / 2
    tile_d = diamond(h, h, h) + f" M{h - 3} {h} a3 3 0 1 0 6 0 a3 3 0 1 0 -6 0"

    # Rotating border of small diamond tiles
    border = "".join(
        f'<path d="{diamond(cx + 178 * math.cos(i * math.pi / 18), cy + 178 * math.sin(i * math.pi / 18), 5)}" '
        f'fill="{t["accent"] if i % 3 == 0 else t["faint"]}" fill-opacity="{1 if i % 3 == 0 else .7}"/>'
        for i in range(36)
    )

    # Nested horseshoe arches sharing one threshold
    ac, base = cy - 20, cy + 150
    arches = []
    for i, (w, col, sw) in enumerate([(112, t["accent"], 1.8), (86, t["blue"], 1.6), (60, t["ochre"], 1.4)]):
        arches.append(
            f'<path class="draw" pathLength="1" d="{arch(cx, ac, w, base)}" fill="none" stroke="{col}" stroke-width="{sw}" '
            f'stroke-linecap="round" style="animation-delay:{.4 + i * .35:.2f}s;animation-duration:2.6s"/>'
        )
    doorway = f'<path d="{arch(cx, ac, 60, base)} Z" fill="{t["accent"]}" fill-opacity=".10"/>'
    # Hanging lantern inside the doorway
    lantern = (
        f'<g class="lantern">'
        f'<line x1="{cx}" y1="{ac - 60}" x2="{cx}" y2="{ac + 2}" stroke="{t["ink"]}" stroke-width="1"/>'
        f'<path d="M{cx - 9} {ac + 4} H{cx + 9} L{cx + 13} {ac + 22} L{cx} {ac + 34} L{cx - 13} {ac + 22} Z" '
        f'fill="{t["ochre"]}" fill-opacity=".85" stroke="{t["ink"]}" stroke-width="1"/>'
        f'<circle cx="{cx}" cy="{ac + 20}" r="16" fill="{t["ochre"]}" fill-opacity=".18"/></g>'
    )

    name = "MrZaKaRiA"
    name_x = 72
    cmd = "ship --from morocco --to everywhere"
    char_w = 10.84  # approx mono advance @ 18px
    steps = len(cmd)
    typed_vals = ";".join(f"{i * char_w:.1f}" for i in range(steps + 1))
    typed_times = ";".join(f"{i / steps:.3f}" for i in range(steps + 1))

    yr = data.get("annual_contributions", 0)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="MrZaKaRiA — I build business software, operating systems, and the servers they run on.">
  <defs>
    <pattern id="z" width="{tile}" height="{tile}" patternUnits="userSpaceOnUse">
      <path d="{tile_d}" fill="none" stroke="{t['faint']}" stroke-width=".7"/>
    </pattern>
    <radialGradient id="fadeR" cx="{cx / W:.3f}" cy=".5" r=".55">
      <stop offset="0" stop-color="#fff" stop-opacity=".9"/>
      <stop offset=".55" stop-color="#fff" stop-opacity=".25"/>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </radialGradient>
    <mask id="m"><rect width="{W}" height="{H}" fill="url(#fadeR)"/></mask>
    <radialGradient id="glow" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="{t['accent']}" stop-opacity=".22"/>
      <stop offset="1" stop-color="{t['accent']}" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="nameClip"><rect x="0" y="0" width="0" height="{H}">
      <animate attributeName="width" from="0" to="{W}" dur="1.6s" begin=".2s" fill="freeze" calcMode="spline" keySplines=".65 0 .35 1" keyTimes="0;1"/>
    </rect></clipPath>
    <clipPath id="typeClip"><rect x="{name_x + 24}" y="300" width="0" height="40">
      <animate attributeName="width" values="{typed_vals}" keyTimes="{typed_times}" calcMode="discrete" dur="2.2s" begin="1.9s" fill="freeze"/>
    </rect></clipPath>
  </defs>
  <style>{base_style(t)}
    .rot {{ transform-origin: {cx}px {cy}px; animation: spin 120s linear infinite; }}
    .rotr {{ transform-origin: {cx}px {cy}px; animation: spinr 160s linear infinite; }}
    .pulse {{ transform-origin: {cx}px {cy}px; animation: breathe 5s ease-in-out infinite; }}
    .lantern {{ transform-origin: {cx}px {ac - 60}px; animation: sway 6s ease-in-out infinite; }}
    .cursor {{ animation: blink 1s steps(1) infinite; }}
  </style>

  <rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="{t['bg']}" stroke="{t['line']}"/>
  <rect width="{W}" height="{H}" rx="10" fill="url(#z)" mask="url(#m)" opacity=".55"/>
  <circle cx="{cx}" cy="{cy}" r="230" fill="url(#glow)" class="pulse"/>

  <!-- doorway -->
  <circle class="rotr" cx="{cx}" cy="{cy}" r="198" fill="none" stroke="{t['line']}" stroke-width="1" stroke-dasharray="2 6"/>
  <g class="rot fade" style="animation-delay:.2s">{border}</g>
  <path class="draw" pathLength="1" d="{polygon(cx, cy, 160, 8, -math.pi / 2 + math.pi / 8)}" fill="none" stroke="{t['faint']}" stroke-width="1" style="animation-duration:3s"/>
  <g class="fade" style="animation-delay:1.6s">{doorway}</g>
  {''.join(arches)}
  <line class="draw" pathLength="1" x1="{cx - 112}" y1="{base}" x2="{cx + 112}" y2="{base}" stroke="{t['ink']}" stroke-width="1.4" style="animation-delay:.2s;animation-duration:1.2s"/>
  <g class="fade" style="animation-delay:2.4s">{lantern}</g>

  <!-- left column -->
  <g class="mono fade" style="animation-delay:.05s" font-size="13" letter-spacing="2.6" fill="{t['muted']}">
    <text x="{name_x}" y="78">FOUNDER  /  SYSTEMS ENGINEER</text>
  </g>
  <line class="draw" pathLength="1" x1="{name_x}" y1="96" x2="{name_x + 56}" y2="96" stroke="{t['accent']}" stroke-width="2" style="animation-delay:.1s;animation-duration:1s"/>

  <g clip-path="url(#nameClip)">
    <text class="serif" x="{name_x - 4}" y="208" font-size="122" font-weight="500" letter-spacing="-3" fill="{t['ink']}">{name}</text>
  </g>

  <g class="serif rise" style="animation-delay:1.1s" font-size="25" fill="{t['muted']}" font-style="italic">
    <text x="{name_x}" y="256">I build business software, operating systems,</text>
    <text x="{name_x}" y="288">and the servers they run on.</text>
  </g>

  <g class="mono" font-size="18">
    <text class="fade" style="animation-delay:1.7s" x="{name_x}" y="330" fill="{t['accent']}">$</text>
    <g clip-path="url(#typeClip)"><text x="{name_x + 24}" y="330" fill="{t['ink']}">{cmd}</text></g>
    <rect class="cursor" x="{name_x + 24 + steps * char_w + 4:.1f}" y="315" width="10" height="20" fill="{t['accent']}" opacity=".9"/>
  </g>

  <g class="mono fade" style="animation-delay:2.6s" font-size="12.5" letter-spacing="1.6" fill="{t['muted']}">
    <line x1="{name_x}" y1="384" x2="{name_x + 560}" y2="384" stroke="{t['line']}"/>
    <text x="{name_x}" y="412">31°47′N  7°05′W</text>
    <text x="{name_x + 180}" y="412">MOROCCO</text>
    <text x="{name_x + 300}" y="412"><tspan fill="{t['ink']}">{yr:,}</tspan> CONTRIBUTIONS / YR</text>
  </g>
</svg>
"""


# ─── SECTION HEADER ──────────────────────────────────────────────────────────
def render_section(num: str, title: str, meta: str, mode: str) -> str:
    t = THEMES[mode]
    W, H = 1200, 84
    title_w = len(title) * 17.5
    x0 = 150 + title_w + 28
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{esc(title)}">
  <style>{base_style(t)}</style>
  <text class="mono" x="40" y="52" font-size="15" letter-spacing="2" fill="{t['accent']}">§ {num}</text>
  <path d="{arch(118, 40, 9, 56)}" fill="none" stroke="{t['accent']}" stroke-width="1.4" stroke-linecap="round"/>
  <text class="serif" x="148" y="56" font-size="34" fill="{t['ink']}">{esc(title)}</text>
  <line class="draw" pathLength="1" x1="{x0:.0f}" y1="47" x2="{W - 60 - len(meta) * 8.6:.0f}" y2="47" stroke="{t['line']}" stroke-width="1"/>
  <text class="mono" x="{W - 40}" y="52" text-anchor="end" font-size="13" letter-spacing="1.8" fill="{t['muted']}">{esc(meta.upper())}</text>
</svg>
"""


# ─── PROJECT CARD ────────────────────────────────────────────────────────────
def render_card(p: dict[str, Any], idx: int, stars: int, mode: str) -> str:
    t = THEMES[mode]
    W, H = 600, 330
    mx, my = 500, 100
    parts = []
    for i, (d, role) in enumerate(ICONS[p["icon"]]):
        stroke = t["accent"] if role == "accent" else t["ink"]
        fill = t["panel"] if role == "fill" else "none"
        parts.append(
            f'<path class="draw" pathLength="1" d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" style="animation-delay:{.2 + i * .18:.2f}s;animation-duration:1.6s"/>'
        )
    ticks = "".join(
        f'<path d="{diamond(mx + 66 * math.cos(i * math.pi / 6), my + 66 * math.sin(i * math.pi / 6), 3)}" '
        f'fill="{t["accent"] if i % 3 == 0 else t["faint"]}"/>'
        for i in range(12)
    )
    desc = "".join(
        f'<text x="36" y="{176 + i * 30}">{esc(line)}</text>' for i, line in enumerate(p["lines"])
    )
    star_txt = f"{stars} STARS" if stars else "OPEN SOURCE"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{esc(p['name'])} — {esc(' '.join(p['lines']))}">
  <style>{base_style(t)}
    .spin {{ transform-origin: {mx}px {my}px; animation: spin 60s linear infinite; }}
  </style>
  <rect x="6.5" y="6.5" width="{W - 13}" height="{H - 13}" rx="3" fill="{t['panel']}" stroke="{t['line']}"/>
  <circle cx="{mx}" cy="{my}" r="66" fill="none" stroke="{t['line']}"/>
  <g class="spin">{ticks}</g>
  <g transform="translate({mx} {my})">{''.join(parts)}</g>
  <text class="mono" x="36" y="52" font-size="14" letter-spacing="2" fill="{t['muted']}"><tspan fill="{t['accent']}">{idx:02d}</tspan>  ·  {esc(p['kind'].upper())}</text>
  <text class="serif" x="34" y="118" font-size="46" fill="{t['ink']}" letter-spacing="-.5">{esc(p['name'])}</text>
  <g class="serif" font-size="20" fill="{t['muted']}">{desc}</g>
  <line x1="36" y1="270" x2="{W - 36}" y2="270" stroke="{t['line']}"/>
  <text class="mono" x="36" y="300" font-size="14" fill="{t['ink']}">{esc(p['stack'])}</text>
  <text class="mono" x="{W - 36}" y="300" font-size="13" letter-spacing="1.4" text-anchor="end" fill="{t['ochre']}">{star_txt}</text>
</svg>
"""


# ─── LEDGER (numbers + diamond contribution map + languages) ─────────────────
LANG_ALIAS = {"Blade": "PHP", "SCSS": "CSS", "Vue": "Vue", "Go Template": None, "Roff": None, "Makefile": None,
              "HCL": None, "Vim Script": None, "Dockerfile": None, "Raku": None, "PowerShell": None, "MDX": None,
              "HTML": None, "CSS": None, "Kotlin": None, "Objective-C": None, "Solidity": None, "PLpgSQL": None}


def render_ledger(data: dict[str, Any], mode: str) -> str:
    t = THEMES[mode]
    W = 1200
    weeks = data.get("weeks", [])[-53:]
    counts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    nonzero = sorted(c for c in counts if c > 0)

    def q(p: float) -> int:
        return nonzero[min(len(nonzero) - 1, int(len(nonzero) * p))] if nonzero else 1

    q1, q2, q3 = q(.25), q(.5), q(.75)
    peak = max(counts) if counts else 0

    # Stats row
    stats = [
        (f"{data.get('annual_contributions', 0):,}", "contributions, last 12 months"),
        (f"{data.get('active_days_year', 0)}", "days shipping"),
        (f"{data.get('owned_repos', 0)}", "repositories authored"),
        (f"{peak}", "commits on the busiest day"),
    ]
    col = (W - 80) / 4
    stat_svg = "".join(
        f'<g class="rise" style="animation-delay:{.1 + i * .12:.2f}s">'
        f'<text class="serif" x="{40 + i * col:.0f}" y="96" font-size="58" fill="{t["ink"]}" letter-spacing="-1">{v}</text>'
        f'<text class="mono" x="{40 + i * col + 2:.0f}" y="126" font-size="12.5" letter-spacing="1.4" fill="{t["muted"]}">{esc(l.upper())}</text>'
        f'</g>'
        + (f'<line x1="{40 + i * col - 22:.0f}" y1="44" x2="{40 + i * col - 22:.0f}" y2="132" stroke="{t["line"]}"/>' if i else "")
        for i, (v, l) in enumerate(stats)
    )

    # Diamond map
    top = 186
    gx0, step = 52, (W - 104) / max(1, len(weeks) - 1) if weeks else 20
    r = 7.4
    cells = []
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            dow = datetime.date.fromisoformat(d["date"]).weekday()  # Mon=0
            dow = (dow + 1) % 7  # Sun=0 like GitHub
            c = d["contributionCount"]
            x = gx0 + wi * step
            y = top + dow * (step * .92)
            if c == 0:
                fill, op, stroke = t["empty"], 1, "none"
            else:
                lvl = 1 if c <= q1 else 2 if c <= q2 else 3 if c <= q3 else 4
                fill, op, stroke = t["accent"], [0, .28, .5, .75, 1][lvl], "none"
            if c == peak and c > 0:
                fill, op = t["ochre"], 1
            delay = .3 + wi * .028 + dow * .02
            cells.append(
                f'<path class="fade" d="M{x:.1f} {y - r:.1f} L{x + r:.1f} {y:.1f} L{x:.1f} {y + r:.1f} L{x - r:.1f} {y:.1f}Z" '
                f'fill="{fill}" fill-opacity="{op}" style="animation-delay:{delay:.2f}s"><title>{d["date"]}: {c}</title></path>'
            )
    map_h = 6 * step * .92
    # month labels
    months = []
    last = None
    for wi, w in enumerate(weeks):
        m = w["contributionDays"][0]["date"][:7]
        if m != last and wi < len(weeks) - 2:
            last = m
            label = datetime.date.fromisoformat(m + "-01").strftime("%b").upper()
            months.append(f'<text x="{gx0 + wi * step - 4:.0f}" y="{top - 22}">{label}</text>')

    # Languages
    langs: dict[str, int] = {}
    for name, size in data.get("languages", {}).items():
        key = LANG_ALIAS.get(name, name)
        if key:
            langs[key] = langs.get(key, 0) + size
    top_l = sorted(langs.items(), key=lambda kv: -kv[1])[:7]
    total = sum(v for _, v in top_l) or 1
    ly = top + map_h + 78
    bar_w = W - 80
    palette = [t["accent"], t["blue"], t["ochre"], t["ink"], t["muted"], t["faint"], t["line"]]
    x = 40.0
    bars, labels = [], []
    for i, (name, v) in enumerate(top_l):
        w_ = bar_w * v / total
        bars.append(
            f'<rect class="fade" x="{x:.1f}" y="{ly}" width="{max(w_ - 3, 2):.1f}" height="10" fill="{palette[i]}" style="animation-delay:{1.4 + i * .1:.2f}s"/>'
        )
        x += w_
    lx = 40.0
    for i, (name, v) in enumerate(top_l):
        pct = 100 * v / total
        txt = f"{name} {pct:.0f}%" if pct >= 1 else f"{name} <1%"
        labels.append(
            f'<path d="M{lx + 5:.0f} {ly + 31} l5 5 l-5 5 l-5 -5Z" fill="{palette[i]}"/>'
            f'<text x="{lx + 18:.0f}" y="{ly + 41}">{esc(txt)}</text>'
        )
        lx += 30 + len(txt) * 8.2
    H = int(ly + 80)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{data.get('annual_contributions', 0)} contributions in the last year">
  <style>{base_style(t)}</style>
  {stat_svg}
  <g class="mono" font-size="11.5" letter-spacing="1.6" fill="{t['muted']}">{''.join(months)}</g>
  {''.join(cells)}
  <g class="mono" font-size="11.5" letter-spacing="1.4" fill="{t['muted']}">
    <text x="40" y="{ly - 18}">BYTES WRITTEN, BY LANGUAGE</text>
    <text x="{W - 40}" y="{ly - 18}" text-anchor="end">SYNCED {esc(data.get('updated_at', ''))}</text>
  </g>
  {''.join(bars)}
  <g class="mono" font-size="13" fill="{t['ink']}">{''.join(labels)}</g>
</svg>
"""


# ─── FOOTER ──────────────────────────────────────────────────────────────────
def render_footer(mode: str) -> str:
    t = THEMES[mode]
    W, H = 1200, 150
    band = []
    for i in range(0, 36):
        x = 20 + i * 38.6
        col = t["accent"] if i % 4 == 0 else t["faint"]
        band.append(f'<path d="{arch(x, 36, 14, 60)}" fill="none" stroke="{col}" stroke-width="1.2"/>')
        band.append(f'<path d="{diamond(x + 19.3, 26, 4)}" fill="{t["blue"]}" fill-opacity=".6"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Made in Morocco">
  <style>{base_style(t)}
    @keyframes slide {{ to {{ transform: translateX(-154.4px); }} }}
    .band {{ animation: slide 14s linear infinite; }}
  </style>
  <line x1="0" y1="14" x2="{W}" y2="14" stroke="{t['line']}"/>
  <line x1="0" y1="66" x2="{W}" y2="66" stroke="{t['line']}"/>
  <g class="band">{''.join(band)}</g>
  <text class="serif" x="40" y="118" font-size="22" font-style="italic" fill="{t['muted']}">Made in Morocco, shipped everywhere.</text>
  <text class="mono" x="{W - 40}" y="116" text-anchor="end" font-size="13" letter-spacing="2" fill="{t['muted']}">MRZAKARIA.COM</text>
</svg>
"""


SECTIONS = [
    ("01", "Selected work", "flagship open source"),
    ("02", "The last twelve months", "live, synced twice a day"),
    ("03", "Reach me", "open to select work"),
]


def main() -> None:
    data = fetch_github_data()
    repos = data.get("repos", {})
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for mode in THEMES:
        (ASSETS_DIR / f"hero-{mode}.svg").write_text(render_hero(data, mode), encoding="utf-8")
        (ASSETS_DIR / f"ledger-{mode}.svg").write_text(render_ledger(data, mode), encoding="utf-8")
        (ASSETS_DIR / f"footer-{mode}.svg").write_text(render_footer(mode), encoding="utf-8")
        for num, title, meta in SECTIONS:
            (ASSETS_DIR / f"section-{num}-{mode}.svg").write_text(render_section(num, title, meta, mode), encoding="utf-8")
        for i, p in enumerate(PROJECTS, 1):
            stars = repos.get(p["repo"], {}).get("stars", 0)
            (ASSETS_DIR / f"card-{p['slug']}-{mode}.svg").write_text(render_card(p, i, stars, mode), encoding="utf-8")
    print(f"Rendered {len(list(ASSETS_DIR.glob('*.svg')))} SVGs into {ASSETS_DIR}")


if __name__ == "__main__":
    main()
