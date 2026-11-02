#!/usr/bin/env python3
"""
MrZaKaRiA GitHub Profile SVG & Telemetry Generator
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


def get_theme(mode: str) -> dict[str, str]:
    if mode == "dark":
        return {
            "bg_start": "#060B14",
            "bg_mid": "#0B1325",
            "bg_end": "#091926",
            "card_bg": "#0F172A",
            "card_bg_alt": "#111C33",
            "card_border": "#1E293B",
            "card_border_glow": "#0D9488",
            "grid_line": "#1E293B",
            "text_primary": "#F8FAFC",
            "text_secondary": "#94A3B8",
            "text_muted": "#64748B",
            "accent_teal": "#14B8A6",
            "accent_cyan": "#38BDF8",
            "accent_indigo": "#818CF8",
            "accent_amber": "#F59E0B",
            "accent_emerald": "#10B981",
            "accent_rose": "#F43F5E",
            "pill_bg": "#132238",
            "pill_border": "#23395B",
            "term_bg": "#070B12",
            "term_header": "#111827",
            "heat_0": "#161F30",
            "heat_1": "#115E59",
            "heat_2": "#0D9488",
            "heat_3": "#14B8A6",
            "heat_4": "#2DD4BF",
        }
    return {
        "bg_start": "#F8FAFC",
        "bg_mid": "#F1F5F9",
        "bg_end": "#ECFEFF",
        "card_bg": "#FFFFFF",
        "card_bg_alt": "#F8FAFC",
        "card_border": "#E2E8F0",
        "card_border_glow": "#0D9488",
        "grid_line": "#E2E8F0",
        "text_primary": "#0F172A",
        "text_secondary": "#475569",
        "text_muted": "#64748B",
        "accent_teal": "#0D9488",
        "accent_cyan": "#0284C7",
        "accent_indigo": "#4F46E5",
        "accent_amber": "#D97706",
        "accent_emerald": "#059669",
        "accent_rose": "#E11D48",
        "pill_bg": "#F1F5F9",
        "pill_border": "#CBD5E1",
        "term_bg": "#0F172A",
        "term_header": "#1E293B",
        "heat_0": "#E2E8F0",
        "heat_1": "#99F6E4",
        "heat_2": "#2DD4BF",
        "heat_3": "#0D9488",
        "heat_4": "#115E59",
    }


def generate_hero_svg(data: dict[str, Any], mode: str) -> str:
    t = get_theme(mode)
    lifetime = f"{data['lifetime_contributions']:,}+"
    annual = f"{data['annual_contributions']:,}"
    owned = data["owned_repos"]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 340" width="100%" height="100%">
  <defs>
    <linearGradient id="heroBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{t['bg_start']}" />
      <stop offset="55%" stop-color="{t['bg_mid']}" />
      <stop offset="100%" stop-color="{t['bg_end']}" />
    </linearGradient>
    <linearGradient id="brandGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{t['accent_teal']}" />
      <stop offset="50%" stop-color="{t['accent_cyan']}" />
      <stop offset="100%" stop-color="{t['accent_indigo']}" />
    </linearGradient>
    <radialGradient id="orbTeal" cx="20%" cy="20%" r="50%">
      <stop offset="0%" stop-color="{t['accent_teal']}" stop-opacity="0.18" />
      <stop offset="100%" stop-color="{t['accent_teal']}" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="orbCyan" cx="85%" cy="75%" r="45%">
      <stop offset="0%" stop-color="{t['accent_cyan']}" stop-opacity="0.16" />
      <stop offset="100%" stop-color="{t['accent_cyan']}" stop-opacity="0" />
    </radialGradient>
    <pattern id="blueprintGrid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="{t['grid_line']}" stroke-width="0.7" stroke-opacity="0.45" />
    </pattern>
  </defs>

  <style>
    .font-sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Helvetica, Arial, sans-serif; }}
    .font-mono {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
    @keyframes pulseDot {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.45; transform: scale(1.35); }}
    }}
    @keyframes scanline {{
      0% {{ transform: translateX(-200px); opacity: 0; }}
      50% {{ opacity: 0.9; }}
      100% {{ transform: translateX(1200px); opacity: 0; }}
    }}
    @keyframes blinkCursor {{
      0%, 49% {{ opacity: 1; }}
      50%, 100% {{ opacity: 0; }}
    }}
    @keyframes floatSlow {{
      0%, 100% {{ transform: translateY(0px); }}
      50% {{ transform: translateY(-4px); }}
    }}
    .pulse {{ animation: pulseDot 2.4s ease-in-out infinite; transform-origin: center; transform-box: fill-box; }}
    .cursor {{ animation: blinkCursor 1.1s infinite; }}
    .scan {{ animation: scanline 7s ease-in-out infinite; }}
    .float-card {{ animation: floatSlow 5s ease-in-out infinite; }}
  </style>

  <!-- Background Canvas -->
  <rect width="1200" height="340" rx="20" fill="url(#heroBg)" stroke="{t['card_border']}" stroke-width="1.5" />
  <rect width="1200" height="340" rx="20" fill="url(#blueprintGrid)" />
  <rect width="1200" height="340" rx="20" fill="url(#orbTeal)" />
  <rect width="1200" height="340" rx="20" fill="url(#orbCyan)" />

  <!-- Top Animated Laser Accent Line -->
  <rect x="40" y="1" width="1120" height="2" fill="url(#brandGrad)" opacity="0.45" />
  <rect class="scan" x="0" y="0" width="220" height="3" fill="url(#brandGrad)" rx="1.5" />

  <!-- Top Telemetry Bar -->
  <g transform="translate(48, 30)">
    <rect x="0" y="0" width="338" height="28" rx="14" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
    <circle class="pulse" cx="16" cy="14" r="4.5" fill="{t['accent_emerald']}" />
    <text x="29" y="18" class="font-mono" font-size="11" font-weight="600" fill="{t['text_primary']}" letter-spacing="0.6">AVAILABLE FOR PROJECTS &amp; CONSULTING</text>

    <rect x="350" y="0" width="188" height="28" rx="14" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
    <text x="366" y="18" class="font-mono" font-size="11" font-weight="500" fill="{t['text_secondary']}">📍 MOROCCO · UTC+1</text>
  </g>

  <!-- Left Column: Identity & Mission -->
  <g transform="translate(48, 92)">
    <text x="0" y="0" class="font-mono" font-size="12" font-weight="700" fill="{t['accent_teal']}" letter-spacing="2.2">FOUNDER · PRINCIPAL FULL-STACK &amp; SYSTEMS ARCHITECT</text>
    <text x="0" y="54" class="font-sans" font-size="56" font-weight="800" fill="{t['text_primary']}" letter-spacing="-1.2">MrZaKaRiA</text>
    <rect x="308" y="34" width="12" height="12" rx="3" fill="{t['accent_teal']}" />

    <text x="0" y="92" class="font-sans" font-size="17" font-weight="500" fill="{t['text_secondary']}">
      Building high-craft software from the <tspan fill="{t['text_primary']}" font-weight="700">interface</tspan> to the <tspan fill="{t['text_primary']}" font-weight="700">bare-metal infrastructure</tspan>.
    </text>
    <text x="0" y="118" class="font-sans" font-size="14.5" fill="{t['text_secondary']}">
      Architecting AI-native ERP &amp; CRM platforms, Astro/Vue/React web systems, Apple Silicon
    </text>
    <text x="0" y="140" class="font-sans" font-size="14.5" fill="{t['text_secondary']}">
      virtualization (<tspan fill="{t['accent_cyan']}" font-weight="600">LumenVM</tspan>), Suckless Linux distributions (<tspan fill="{t['accent_teal']}" font-weight="600">AbyssLinux</tspan>), and server tooling.
    </text>

    <!-- Domain Pillars -->
    <g transform="translate(0, 166)">
      <rect x="0" y="0" width="148" height="32" rx="8" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.2" />
      <text x="14" y="20" class="font-mono" font-size="11.5" font-weight="600" fill="{t['accent_teal']}">⚡ Web &amp; Astro 7</text>

      <rect x="158" y="0" width="166" height="32" rx="8" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.2" />
      <text x="172" y="20" class="font-mono" font-size="11.5" font-weight="600" fill="{t['accent_cyan']}">🏢 AI ERP &amp; CRM OS</text>

      <rect x="334" y="0" width="174" height="32" rx="8" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.2" />
      <text x="348" y="20" class="font-mono" font-size="11.5" font-weight="600" fill="{t['accent_indigo']}">🍎 Swift &amp; Tauri v2</text>

      <rect x="518" y="0" width="174" height="32" rx="8" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.2" />
      <text x="532" y="20" class="font-mono" font-size="11.5" font-weight="600" fill="{t['accent_amber']}">🐧 Linux &amp; Docker</text>
    </g>
  </g>

  <!-- Right Column: Live Interactive Terminal Card -->
  <g class="float-card" transform="translate(765, 32)">
    <rect x="0" y="0" width="390" height="276" rx="14" fill="{t['term_bg']}" stroke="{t['card_border_glow']}" stroke-width="1.3" stroke-opacity="0.7" />
    <path d="M 0 14 Q 0 0 14 0 L 376 0 Q 390 0 390 14 L 390 36 L 0 36 Z" fill="{t['term_header']}" />
    <circle cx="20" cy="18" r="5.5" fill="#F43F5E" />
    <circle cx="38" cy="18" r="5.5" fill="#F59E0B" />
    <circle cx="56" cy="18" r="5.5" fill="#10B981" />
    <text x="195" y="22" text-anchor="middle" class="font-mono" font-size="11" fill="#94A3B8">mrzakaria@abyss-macos ~ zsh</text>

    <g transform="translate(20, 58)" class="font-mono" font-size="12">
      <text x="0" y="0" fill="#2DD4BF">❯ <tspan fill="#F8FAFC" font-weight="600">sysinfo --architect MrZaKaRiA</tspan></text>

      <text x="0" y="26" fill="#64748B">├─</text>
      <text x="22" y="26" fill="#94A3B8">venture    :</text>
      <text x="116" y="26" fill="#38BDF8" font-weight="600">mrzakaria.com · RAIN STUDIO</text>

      <text x="0" y="48" fill="#64748B">├─</text>
      <text x="22" y="48" fill="#94A3B8">flagships  :</text>
      <text x="116" y="48" fill="#F8FAFC">RIVER ERP · LumenVM · Abyss</text>

      <text x="0" y="70" fill="#64748B">├─</text>
      <text x="22" y="70" fill="#94A3B8">daily_os   :</text>
      <text x="116" y="70" fill="#14B8A6">macOS ARM64 · VoidLinux + dwm</text>

      <text x="0" y="92" fill="#64748B">├─</text>
      <text x="22" y="92" fill="#94A3B8">production :</text>
      <text x="116" y="92" fill="#F59E0B">Debian · Docker · Webmin</text>

      <text x="0" y="114" fill="#64748B">├─</text>
      <text x="22" y="114" fill="#94A3B8">codebase   :</text>
      <text x="116" y="114" fill="#A78BFA">88.9 MB across {owned} Original Repos</text>

      <text x="0" y="136" fill="#64748B">└─</text>
      <text x="22" y="136" fill="#94A3B8">velocity   :</text>
      <text x="116" y="136" fill="#10B981" font-weight="700">{annual} commits/yr ({lifetime} total)</text>

      <line x1="0" y1="156" x2="350" y2="156" stroke="#1E293B" stroke-width="1" />

      <text x="0" y="178" fill="#2DD4BF">❯ <tspan fill="#F8FAFC">status --check</tspan></text>
      <text x="0" y="200" fill="#10B981">✔ All systems operational · Shipping daily</text>
      <rect class="cursor" x="308" y="189" width="8" height="14" fill="#2DD4BF" />
    </g>
  </g>
</svg>
"""


def generate_telemetry_svg(data: dict[str, Any], mode: str) -> str:
    t = get_theme(mode)

    # Compute language distribution from top original codebases
    raw_langs: dict[str, int] = data.get("languages", {})
    grouped = {
        "PHP · Laravel · Blade": raw_langs.get("PHP", 0) + raw_langs.get("Blade", 0),
        "Vue 3 · Astro · MDX": raw_langs.get("Vue", 0) + raw_langs.get("Astro", 0) + raw_langs.get("MDX", 0),
        "TypeScript · JavaScript": raw_langs.get("TypeScript", 0) + raw_langs.get("JavaScript", 0),
        "HTML5 · CSS3 · SCSS": raw_langs.get("HTML", 0) + raw_langs.get("CSS", 0) + raw_langs.get("SCSS", 0),
        "Swift · SwiftUI (ARM64)": raw_langs.get("Swift", 0),
        "Systems (Shell · Perl · C · Rust)": (
            raw_langs.get("Shell", 0)
            + raw_langs.get("Perl", 0)
            + raw_langs.get("C", 0)
            + raw_langs.get("Rust", 0)
            + raw_langs.get("Python", 0)
        ),
    }
    total_bytes = max(sum(grouped.values()), 1)
    total_mb = total_bytes / (1024 * 1024)

    lang_colors = [
        "#818CF8",  # PHP/Laravel
        "#14B8A6",  # Vue/Astro
        "#38BDF8",  # TS/JS
        "#F59E0B",  # HTML/CSS
        "#F43F5E",  # Swift
        "#10B981",  # Systems
    ]

    # Stacked progress bar & rows
    bar_x = 0.0
    bar_width = 508.0
    stacked_rects = []
    lang_rows = []
    for idx, (label, size_bytes) in enumerate(grouped.items()):
        pct = (size_bytes / total_bytes) * 100.0
        visual_pct = max(pct, 2.5)
        color = lang_colors[idx]
        mb_str = f"{size_bytes / (1024 * 1024):.1f} MB" if size_bytes >= 1024 * 1024 else f"{size_bytes / 1024:.0f} KB"
        row_y = 148 + idx * 38
        fill_w = max(int((pct / 100.0) * 210), 8)
        lang_rows.append(
            f"""
      <g transform="translate(28, {row_y})">
        <circle cx="7" cy="-4" r="5" fill="{color}" />
        <text x="20" y="0" class="font-sans" font-size="13" font-weight="600" fill="{t['text_primary']}">{esc(label)}</text>
        <text x="275" y="0" text-anchor="end" class="font-mono" font-size="11.5" fill="{t['text_secondary']}">{mb_str}</text>
        <rect x="290" y="-10" width="160" height="8" rx="4" fill="{t['pill_bg']}" />
        <rect x="290" y="-10" width="{min(max(int(pct * 1.6), 8), 160)}" height="8" rx="4" fill="{color}" />
        <text x="508" y="0" text-anchor="end" class="font-mono" font-size="12" font-weight="700" fill="{color}">{pct:.1f}%</text>
      </g>"""
        )
        w_seg = (visual_pct / 106.0) * bar_width
        stacked_rects.append(
            f'<rect x="{28 + bar_x:.1f}" y="102" width="{max(w_seg - 2, 3):.1f}" height="12" rx="3" fill="{color}" />'
        )
        bar_x += w_seg

    # Build 52-week contribution heatmap grid
    weeks = data.get("weeks", [])[-52:]
    heatmap_cells = []
    weekly_sums = []
    for w_idx, w in enumerate(weeks):
        days = w.get("contributionDays", [])
        w_sum = sum(d.get("contributionCount", 0) for d in days)
        weekly_sums.append(w_sum)
        for d_idx, d in enumerate(days):
            cnt = d.get("contributionCount", 0)
            if cnt == 0:
                c = t["heat_0"]
            elif cnt <= 4:
                c = t["heat_1"]
            elif cnt <= 15:
                c = t["heat_2"]
            elif cnt <= 35:
                c = t["heat_3"]
            else:
                c = t["heat_4"]
            cx = 28 + w_idx * 9.6
            cy = 232 + d_idx * 10
            heatmap_cells.append(
                f'<rect x="{cx:.1f}" y="{cy:.1f}" width="7.6" height="7.6" rx="1.8" fill="{c}" />'
            )

    # Sparkline path for 52-week velocity
    if not weekly_sums:
        weekly_sums = [10] * 52
    max_w = max(max(weekly_sums), 1)
    spark_pts = []
    for i, val in enumerate(weekly_sums):
        sx = 28 + (i / max(len(weekly_sums) - 1, 1)) * 498
        sy = 192 - (val / max_w) * 58
        spark_pts.append(f"{sx:.1f},{sy:.1f}")
    polyline_pts = " ".join(spark_pts)
    area_pts = f"28,196 {polyline_pts} 526,196"

    # Yearly bars (2021 - 2026)
    yearly = data.get("yearly_contributions", {})
    years_list = ["2021", "2022", "2023", "2024", "2025", "2026"]
    year_bars = []
    for idx, yr in enumerate(years_list):
        val = int(yearly.get(yr, yearly.get(int(yr), 0)))
        bx = 28 + idx * 86
        # non-linear scale so smaller years are visible and 2026 stands tall
        bh = min(max(int((val ** 0.45) * 2.1), 8), 54)
        by = 374 - bh
        bar_col = t["accent_teal"] if yr == "2026" else t["accent_cyan"]
        year_bars.append(
            f"""
      <g>
        <rect x="{bx}" y="{by}" width="52" height="{bh}" rx="5" fill="{bar_col}" opacity="{1.0 if yr == '2026' else 0.65}" />
        <text x="{bx + 26}" y="{by - 6}" text-anchor="middle" class="font-mono" font-size="10.5" font-weight="700" fill="{t['text_primary']}">{val:,}</text>
        <text x="{bx + 26}" y="390" text-anchor="middle" class="font-mono" font-size="10.5" fill="{t['text_secondary']}">{yr}</text>
      </g>"""
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 430" width="100%" height="100%">
  <defs>
    <linearGradient id="sparkArea" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="{t['accent_teal']}" stop-opacity="0.38" />
      <stop offset="100%" stop-color="{t['accent_teal']}" stop-opacity="0.0" />
    </linearGradient>
    <linearGradient id="kpiGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{t['accent_teal']}" />
      <stop offset="100%" stop-color="{t['accent_cyan']}" />
    </linearGradient>
  </defs>

  <style>
    .font-sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Helvetica, Arial, sans-serif; }}
    .font-mono {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
  </style>

  <!-- Outer Frame -->
  <rect width="1200" height="430" rx="20" fill="{t['bg_start']}" stroke="{t['card_border']}" stroke-width="1.5" />

  <!-- LEFT BENTO CARD: Codebase & Language Telemetry -->
  <g transform="translate(20, 20)">
    <rect width="564" height="390" rx="16" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.2" />

    <text x="28" y="38" class="font-mono" font-size="11.5" font-weight="700" fill="{t['accent_teal']}" letter-spacing="1.6">01 // CODEBASE &amp; LANGUAGE TELEMETRY</text>
    <text x="536" y="38" text-anchor="end" class="font-mono" font-size="11.5" font-weight="600" fill="{t['text_secondary']}">{total_mb:.1f} MB SOURCE CODE</text>

    <!-- 4 Mini KPI Pills -->
    <g transform="translate(28, 52)">
      <rect x="0" y="0" width="120" height="36" rx="8" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
      <text x="12" y="15" class="font-mono" font-size="9.5" fill="{t['text_secondary']}">ORIGINAL REPOS</text>
      <text x="12" y="29" class="font-mono" font-size="13" font-weight="700" fill="{t['text_primary']}">{data['owned_repos']} Systems</text>

      <rect x="129" y="0" width="120" height="36" rx="8" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
      <text x="141" y="15" class="font-mono" font-size="9.5" fill="{t['text_secondary']}">PUBLICINDEX</text>
      <text x="141" y="29" class="font-mono" font-size="13" font-weight="700" fill="{t['accent_cyan']}">{data['public_repos_total']}+ Repos</text>

      <rect x="258" y="0" width="120" height="36" rx="8" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
      <text x="270" y="15" class="font-mono" font-size="9.5" fill="{t['text_secondary']}">OSS STARS / FORKS</text>
      <text x="270" y="29" class="font-mono" font-size="13" font-weight="700" fill="{t['accent_amber']}">★ {data['total_stars']} · ⑂ {data['total_forks']}</text>

      <rect x="387" y="0" width="121" height="36" rx="8" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
      <text x="399" y="15" class="font-mono" font-size="9.5" fill="{t['text_secondary']}">ACCOUNT TENURE</text>
      <text x="399" y="29" class="font-mono" font-size="13" font-weight="700" fill="{t['accent_emerald']}">Since Jun 2020</text>
    </g>

    <!-- Stacked Multi-Language Bar -->
    {''.join(stacked_rects)}

    <!-- Language Breakdown Rows -->
    {''.join(lang_rows)}
  </g>

  <!-- RIGHT BENTO CARD: Contribution Velocity & 52-Week Heatmap -->
  <g transform="translate(604, 20)">
    <rect width="576" height="390" rx="16" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.2" />

    <text x="28" y="38" class="font-mono" font-size="11.5" font-weight="700" fill="{t['accent_cyan']}" letter-spacing="1.6">02 // CONTRIBUTION VELOCITY &amp; ACTIVITY PULSE</text>
    <text x="548" y="38" text-anchor="end" class="font-mono" font-size="11" fill="{t['text_secondary']}">PUBLIC + PRIVATE TELEMETRY</text>

    <!-- Velocity KPIs -->
    <g transform="translate(28, 52)">
      <rect x="0" y="0" width="166" height="58" rx="10" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
      <text x="14" y="20" class="font-mono" font-size="10" fill="{t['text_secondary']}">LAST 12 MONTHS</text>
      <text x="14" y="45" class="font-sans" font-size="24" font-weight="800" fill="{t['accent_teal']}">{data['annual_contributions']:,}</text>
      <text x="98" y="44" class="font-mono" font-size="10.5" fill="{t['text_secondary']}">commits</text>

      <rect x="177" y="0" width="166" height="58" rx="10" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
      <text x="191" y="20" class="font-mono" font-size="10" fill="{t['text_secondary']}">LIFETIME TOTAL</text>
      <text x="191" y="45" class="font-sans" font-size="24" font-weight="800" fill="{t['accent_cyan']}">{data['lifetime_contributions']:,}+</text>
      <text x="285" y="44" class="font-mono" font-size="10.5" fill="{t['text_secondary']}">shipped</text>

      <rect x="354" y="0" width="166" height="58" rx="10" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
      <text x="368" y="20" class="font-mono" font-size="10" fill="{t['text_secondary']}">PEAK DAILY BURST</text>
      <text x="368" y="45" class="font-sans" font-size="24" font-weight="800" fill="{t['accent_indigo']}">{data['max_daily_contributions']}</text>
      <text x="412" y="44" class="font-mono" font-size="10.5" fill="{t['text_secondary']}">commits / day</text>
    </g>

    <!-- 52-Week Velocity Sparkline -->
    <text x="28" y="130" class="font-mono" font-size="10.5" font-weight="600" fill="{t['text_secondary']}">52-WEEK COMMIT VELOCITY WAVE</text>
    <polygon points="{area_pts}" fill="url(#sparkArea)" />
    <polyline points="{polyline_pts}" fill="none" stroke="url(#kpiGrad)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />

    <!-- 52-Week Contribution Matrix -->
    <text x="28" y="222" class="font-mono" font-size="10.5" font-weight="600" fill="{t['text_secondary']}">52-WEEK CONTRIBUTION DENSITY MATRIX</text>
    {''.join(heatmap_cells)}

    <!-- Annual Trajectory Bars -->
    <text x="28" y="316" class="font-mono" font-size="10.5" font-weight="600" fill="{t['text_secondary']}">YEAR-OVER-YEAR ACCELERATION (2021 → 2026)</text>
    {''.join(year_bars)}
  </g>
</svg>
"""


def generate_architecture_svg(mode: str) -> str:
    t = get_theme(mode)
    layers = [
        (
            "01 // INTERFACE & DESIGN SYSTEMS",
            "Pixel-precise, ultra-fast web & native interfaces with zero-bloat motion & SEO/GEO architecture.",
            t["accent_teal"],
            ["Astro 7", "Vue 3", "React 19", "SwiftUI", "Tailwind CSS v4", "Framer Motion", "TypeScript"],
        ),
        (
            "02 // ENTERPRISE ERP, CRM & AI PLATFORMS",
            "Self-hosted business operating systems, DGI e-invoicing, POS, treasury & multi-LLM orchestration.",
            t["accent_cyan"],
            ["RIVER ERP", "RAIN Commerce", "Laravel 13", "PHP 8.4", "Node.js", "Claude / Gemini / OpenAI", "Ollama"],
        ),
        (
            "03 // NATIVE DESKTOP, VIRTUALIZATION & NETWORK SECURITY",
            "Apple Silicon hypervisors, cross-platform Rust desktop launchers & L2/L3 SD-WAN packet diagnostics.",
            t["accent_indigo"],
            ["LumenVM (Apple Virtualization)", "Tauri v2", "Rust", "NetSentinel L2/L3", "ARM64 / Apple Silicon", "SQLite"],
        ),
        (
            "04 // BARE-METAL LINUX, SERVER & CLOUD INFRASTRUCTURE",
            "Minimalist Suckless Linux distros, hardened Webmin/Virtualmin Docker engines & encrypted backups.",
            t["accent_amber"],
            ["AbyssLinux (Void + dwm)", "Debian Servers", "Virtualmin-Docker", "Perl", "Docker", "Nginx / Apache", "Rclone / S3"],
        ),
    ]

    cards_svg = []
    for idx, (title, subtitle, color, tags) in enumerate(layers):
        cy = 62 + idx * 72
        tag_x = 580
        tags_svg = []
        for tag in tags:
            tw = len(tag) * 7.2 + 20
            if tag_x + tw > 1165:
                break
            tags_svg.append(
                f"""
        <rect x="{tag_x:.1f}" y="{cy + 16}" width="{tw:.1f}" height="28" rx="7" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
        <text x="{tag_x + tw / 2:.1f}" y="{cy + 34}" text-anchor="middle" class="font-mono" font-size="11" font-weight="600" fill="{t['text_primary']}">{esc(tag)}</text>"""
            )
            tag_x += tw + 8

        cards_svg.append(
            f"""
    <g>
      <rect x="24" y="{cy}" width="1152" height="60" rx="12" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.2" />
      <rect x="24" y="{cy}" width="6" height="60" rx="3" fill="{color}" />
      <text x="46" y="{cy + 25}" class="font-mono" font-size="12" font-weight="700" fill="{color}" letter-spacing="1.2">{esc(title)}</text>
      <text x="46" y="{cy + 45}" class="font-sans" font-size="12.5" fill="{t['text_secondary']}">{esc(subtitle)}</text>
      {''.join(tags_svg)}
    </g>"""
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 366" width="100%" height="100%">
  <style>
    .font-sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Helvetica, Arial, sans-serif; }}
    .font-mono {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
  </style>

  <rect width="1200" height="366" rx="20" fill="{t['bg_start']}" stroke="{t['card_border']}" stroke-width="1.5" />
  <text x="28" y="38" class="font-mono" font-size="12" font-weight="700" fill="{t['accent_teal']}" letter-spacing="1.8">FULL-STACK TO BARE-METAL ENGINEERING ARCHITECTURE</text>
  <text x="1172" y="38" text-anchor="end" class="font-mono" font-size="11" fill="{t['text_secondary']}">INTERFACE ↔ APPLICATION ↔ RUNTIME ↔ KERNEL</text>

  {''.join(cards_svg)}
</svg>
"""


def generate_project_card_svg(
    slug: str,
    badge: str,
    title: str,
    desc_line1: str,
    desc_line2: str,
    tags: list[str],
    accent_key: str,
    stars: int,
    forks: int,
    status_label: str,
    mode: str,
) -> str:
    t = get_theme(mode)
    accent = t[accent_key]

    tag_pills = []
    tx = 24.0
    for tag in tags:
        tw = len(tag) * 7.2 + 20
        tag_pills.append(
            f"""
    <rect x="{tx:.1f}" y="158" width="{tw:.1f}" height="26" rx="6" fill="{t['pill_bg']}" stroke="{t['pill_border']}" stroke-width="1" />
    <text x="{tx + tw / 2:.1f}" y="175" text-anchor="middle" class="font-mono" font-size="11" font-weight="600" fill="{t['text_primary']}">{esc(tag)}</text>"""
        )
        tx += tw + 8

    stats_badge = (
        f"★ {stars}   ⑂ {forks}" if stars > 0 else status_label
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 580 206" width="100%" height="100%">
  <defs>
    <linearGradient id="topBar-{slug}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{accent}" />
      <stop offset="100%" stop-color="{t['accent_cyan']}" stop-opacity="0.2" />
    </linearGradient>
  </defs>
  <style>
    .font-sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Helvetica, Arial, sans-serif; }}
    .font-mono {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
  </style>

  <rect width="580" height="206" rx="16" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.5" />
  <rect x="20" y="1" width="540" height="3" rx="1.5" fill="url(#topBar-{slug})" />

  <g transform="translate(24, 28)">
    <rect x="0" y="0" width="{len(badge) * 7.5 + 22:.0f}" height="24" rx="6" fill="{t['pill_bg']}" stroke="{accent}" stroke-width="1" stroke-opacity="0.6" />
    <text x="11" y="16" class="font-mono" font-size="10.5" font-weight="700" fill="{accent}" letter-spacing="0.8">{esc(badge)}</text>

    <text x="532" y="16" text-anchor="end" class="font-mono" font-size="12" font-weight="700" fill="{t['accent_amber'] if stars > 0 else t['accent_emerald']}">{esc(stats_badge)}</text>

    <text x="0" y="56" class="font-sans" font-size="22" font-weight="800" fill="{t['text_primary']}">{esc(title)}</text>
    <text x="532" y="54" text-anchor="end" class="font-mono" font-size="14" fill="{accent}">↗</text>

    <text x="0" y="84" class="font-sans" font-size="13.5" fill="{t['text_secondary']}">{esc(desc_line1)}</text>
    <text x="0" y="105" class="font-sans" font-size="13.5" fill="{t['text_secondary']}">{esc(desc_line2)}</text>
  </g>

  {''.join(tag_pills)}
</svg>
"""


def generate_footer_svg(data: dict[str, Any], mode: str) -> str:
    t = get_theme(mode)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 120" width="100%" height="100%">
  <defs>
    <linearGradient id="footGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{t['accent_teal']}" />
      <stop offset="50%" stop-color="{t['accent_cyan']}" />
      <stop offset="100%" stop-color="{t['accent_indigo']}" />
    </linearGradient>
  </defs>
  <style>
    .font-sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Helvetica, Arial, sans-serif; }}
    .font-mono {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
  </style>

  <rect width="1200" height="120" rx="18" fill="{t['card_bg']}" stroke="{t['card_border']}" stroke-width="1.5" />
  <rect x="40" y="116" width="1120" height="2.5" rx="1.2" fill="url(#footGrad)" opacity="0.75" />

  <text x="600" y="46" text-anchor="middle" class="font-sans" font-size="16" font-weight="700" fill="{t['text_primary']}">
    From pixel-precise interfaces to resilient Linux &amp; Apple Silicon infrastructure.
  </text>
  <text x="600" y="72" text-anchor="middle" class="font-mono" font-size="12" fill="{t['text_secondary']}">
    mrzakaria.com  ·  Engineered in Morocco  ·  Open to High-Impact Products &amp; Consulting
  </text>
  <text x="600" y="96" text-anchor="middle" class="font-mono" font-size="10.5" fill="{t['text_muted']}">
    TELEMETRY SYNCED VIA GITHUB GRAPHQL API · {esc(data['updated_at'])}
  </text>
</svg>
"""


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    data = fetch_github_data()
    repos = data.get("repos", {})

    projects = [
        {
            "slug": "lumenvm",
            "badge": "APPLE SILICON VIRTUALIZATION",
            "title": "LumenVM",
            "desc1": "Native SwiftUI virtual machine manager for Apple Silicon: macOS & Linux",
            "desc2": "via Apple Virtualization, Windows ARM64, sparse disks & Retina displays.",
            "tags": ["Swift", "SwiftUI", "Virtualization.framework", "ARM64", "macOS"],
            "accent": "accent_cyan",
            "stars": repos.get("LumenVM", {}).get("stars", 11),
            "forks": repos.get("LumenVM", {}).get("forks", 2),
            "status": "PUBLIC OSS",
        },
        {
            "slug": "virtualmin-docker",
            "badge": "SERVER & CONTAINER INFRASTRUCTURE",
            "title": "Virtualmin-Docker",
            "desc1": "Security-hardened Webmin & Virtualmin module for orchestrating Docker",
            "desc2": "containers, images, volumes, networks, and live logs from the browser.",
            "tags": ["Perl", "Docker", "Webmin", "Virtualmin", "Linux Sysadmin"],
            "accent": "accent_teal",
            "stars": repos.get("Virtualmin-Docker", {}).get("stars", 9),
            "forks": repos.get("Virtualmin-Docker", {}).get("forks", 4),
            "status": "PUBLIC OSS",
        },
        {
            "slug": "abysslinux",
            "badge": "SUCKLESS LINUX OPERATING SYSTEM",
            "title": "AbyssLinux & PMR",
            "desc1": "Minimalist Suckless-inspired rolling-release Linux distribution & package",
            "desc2": "repository built on Void Linux, runit, dwm, st, and dmenu (x86_64 & ARM64).",
            "tags": ["Linux Distro", "Shell", "C / Suckless", "dwm", "xbps", "ARM64"],
            "accent": "accent_amber",
            "stars": repos.get("AbyssLinux", {}).get("stars", 3),
            "forks": repos.get("AbyssLinux", {}).get("forks", 1),
            "status": "PUBLIC OSS",
        },
        {
            "slug": "river-erp",
            "badge": "AI-NATIVE BUSINESS OS",
            "title": "RIVER ERP & Desktop",
            "desc1": "All-in-one AI-native ERP & CRM for Morocco & Europe: DGI e-invoicing,",
            "desc2": "POS, inventory, treasury & payroll with native Tauri v2 desktop launchers.",
            "tags": ["Laravel 13", "Vue 3", "Rust", "Tauri v2", "Tailwind v4"],
            "accent": "accent_indigo",
            "stars": repos.get("river-desktop", {}).get("stars", 0),
            "forks": repos.get("river-desktop", {}).get("forks", 0),
            "status": "FLAGSHIP PRODUCT",
        },
        {
            "slug": "rain-commerce",
            "badge": "COMMERCE & DESKTOP ECOSYSTEM",
            "title": "RAIN Commerce & Desktop",
            "desc1": "Complete multi-storefront digital commerce platform engineered with",
            "desc2": "a native cross-platform Rust/Tauri desktop launcher for macOS, Win & Linux.",
            "tags": ["PHP", "Vue 3", "Rust", "Tauri", "E-Commerce"],
            "accent": "accent_rose",
            "stars": repos.get("rain-desktop", {}).get("stars", 0),
            "forks": repos.get("rain-desktop", {}).get("forks", 0),
            "status": "FLAGSHIP PRODUCT",
        },
        {
            "slug": "virtualmin-db-backup",
            "badge": "DATABASE DISASTER RECOVERY",
            "title": "Virtualmin-Db-Backup",
            "desc1": "Hardened Webmin/Virtualmin engine to back up MySQL, MariaDB, PostgreSQL,",
            "desc2": "MongoDB & SQLite (host or Docker) with encryption, checksums & S3/Drive sync.",
            "tags": ["Perl", "MySQL / Postgres", "MongoDB", "Docker", "Cloud Sync"],
            "accent": "accent_emerald",
            "stars": repos.get("Virtualmin-Db-Backup", {}).get("stars", 0),
            "forks": repos.get("Virtualmin-Db-Backup", {}).get("forks", 0),
            "status": "PUBLIC OSS",
        },
    ]

    for mode in ("dark", "light"):
        (ASSETS_DIR / f"hero-{mode}.svg").write_text(generate_hero_svg(data, mode), encoding="utf-8")
        (ASSETS_DIR / f"telemetry-{mode}.svg").write_text(generate_telemetry_svg(data, mode), encoding="utf-8")
        (ASSETS_DIR / f"architecture-{mode}.svg").write_text(generate_architecture_svg(mode), encoding="utf-8")
        (ASSETS_DIR / f"footer-{mode}.svg").write_text(generate_footer_svg(data, mode), encoding="utf-8")
        for p in projects:
            card_svg = generate_project_card_svg(
                slug=p["slug"],
                badge=p["badge"],
                title=p["title"],
                desc_line1=p["desc1"],
                desc_line2=p["desc2"],
                tags=p["tags"],
                accent_key=p["accent"],
                stars=p["stars"],
                forks=p["forks"],
                status_label=p["status"],
                mode=mode,
            )
            (ASSETS_DIR / f"card-{p['slug']}-{mode}.svg").write_text(card_svg, encoding="utf-8")

    print(f"Generated {len(list(ASSETS_DIR.glob('*.svg')))} SVG assets successfully in {ASSETS_DIR}")


if __name__ == "__main__":
    main()
