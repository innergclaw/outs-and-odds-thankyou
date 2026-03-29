#!/usr/bin/env python3
"""
OUTS AND ODDS — Daily MLB Pitcher K & Outs Picks
Pulls today's slate, pitcher stats, opponent K%, and scores matchups.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

TODAY = "03/27/2026"
SEASON_STATS = "2025"  # Use last full season as baseline (2026 just started)

def api_get(url):
    """Fetch JSON from MLB Stats API"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OutsAndOdds/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [API ERROR] {url[:80]}... → {e}")
        return None

def get_schedule():
    """Get today's games with probable pitchers"""
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={TODAY}&hydrate=probablePitcher(note),team"
    data = api_get(url)
    if not data or not data.get("dates"):
        return []
    return data["dates"][0].get("games", [])

def get_pitcher_stats(player_id):
    """Get pitcher's season stats"""
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&season={SEASON_STATS}&group=pitching"
    data = api_get(url)
    if not data:
        return None
    try:
        stats_list = data.get("stats", [])
        for s in stats_list:
            splits = s.get("splits", [])
            if splits:
                return splits[0].get("stat", {})
    except:
        pass
    return None

def get_team_stats(team_id):
    """Get team batting stats (for opponent K%)"""
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&season={SEASON_STATS}&group=hitting"
    data = api_get(url)
    if not data:
        return None
    try:
        stats_list = data.get("stats", [])
        for s in stats_list:
            splits = s.get("splits", [])
            if splits:
                return splits[0].get("stat", {})
    except:
        pass
    return None

def calculate_score(pitcher_stats, opponent_stats, pitcher_name):
    """Score a pitcher matchup for K and Outs potential"""
    if not pitcher_stats:
        return None

    # Extract pitcher metrics
    k9 = float(pitcher_stats.get("strikeoutsPer9Inn", 0))
    ip = float(pitcher_stats.get("inningsPitched", "0"))
    total_k = int(pitcher_stats.get("strikeOuts", 0))
    games = int(pitcher_stats.get("gamesStarted", 0) or pitcher_stats.get("gamesPitched", 0) or 1)
    era = float(pitcher_stats.get("era", "5.00"))
    whip = float(pitcher_stats.get("whip", "1.50"))

    # Calculate per-start averages
    k_per_start = total_k / max(games, 1)
    ip_per_start = ip / max(games, 1)
    outs_per_start = ip_per_start * 3

    # Opponent K tendency
    opp_k_pct = 0.22  # league average default
    if opponent_stats:
        opp_ab = int(opponent_stats.get("atBats", 0))
        opp_k = int(opponent_stats.get("strikeOuts", 0))
        if opp_ab > 0:
            opp_k_pct = opp_k / opp_ab

    # K Score (higher = better K prop bet)
    k_score = 0
    k_score += (k9 - 8.0) * 2.0          # Above avg K/9 (league ~8.0)
    k_score += (opp_k_pct - 0.22) * 30   # Opponent K tendency vs avg
    k_score += (k_per_start - 5.5) * 1.5 # Historical K per start
    if era < 3.50:
        k_score += 1.5                     # Elite pitcher bonus
    elif era < 4.00:
        k_score += 0.5

    # Outs Score (higher = more outs/deeper into games)
    outs_score = 0
    outs_score += (ip_per_start - 5.0) * 2.0   # Deeper than avg
    outs_score += (1.30 - whip) * 5.0           # Lower WHIP = more efficient
    if era < 3.50:
        outs_score += 2.0
    elif era < 4.00:
        outs_score += 1.0

    return {
        "pitcher": pitcher_name,
        "k9": k9,
        "k_per_start": round(k_per_start, 1),
        "ip_per_start": round(ip_per_start, 1),
        "outs_per_start": round(outs_per_start, 1),
        "era": era,
        "whip": whip,
        "opp_k_pct": round(opp_k_pct * 100, 1),
        "k_score": round(k_score, 2),
        "outs_score": round(outs_score, 2),
        "total_score": round(k_score + outs_score, 2),
        "games": games,
        "total_k": total_k,
        "ip": ip,
    }

def confidence_emoji(score):
    if score >= 6:
        return "🔥"
    elif score >= 3:
        return "✅"
    elif score >= 0:
        return "⚠️"
    else:
        return "🚫"

def format_discord(matchups):
    """Generate Discord-formatted output"""
    now = datetime.now()
    date_str = "March 27, 2026"

    lines = []
    lines.append("```")
    lines.append("╔══════════════════════════════════════════╗")
    lines.append("║     ⚾  OUTS AND ODDS — DAILY PICKS  ⚾  ║")
    lines.append(f"║           {date_str}               ║")
    lines.append("╚══════════════════════════════════════════╝")
    lines.append("```")
    lines.append("")

    # Sort by total score
    ranked = sorted(matchups, key=lambda x: x["score"]["total_score"] if x["score"] else -99, reverse=True)

    # Top K Props
    lines.append("## 🎯 TOP STRIKEOUT PROPS")
    lines.append("")

    k_ranked = sorted([m for m in matchups if m["score"]], key=lambda x: x["score"]["k_score"], reverse=True)

    for i, m in enumerate(k_ranked[:5]):
        s = m["score"]
        emoji = confidence_emoji(s["k_score"])
        lines.append(f"**{i+1}. {s['pitcher']}** — {m['team']} vs {m['opponent']}")
        lines.append(f"> {emoji} K Score: **{s['k_score']}** | K/9: {s['k9']} | Avg K/Start: {s['k_per_start']}")
        lines.append(f"> Opp K%: {s['opp_k_pct']}% | ERA: {s['era']} | WHIP: {s['whip']}")
        lines.append(f"> 📊 {SEASON_STATS} Stats: {s['total_k']}K in {s['ip']}IP ({s['games']} starts)")
        lines.append("")

    # Top Outs Props
    lines.append("## 📋 TOP PITCHER OUTS PROPS")
    lines.append("")

    outs_ranked = sorted([m for m in matchups if m["score"]], key=lambda x: x["score"]["outs_score"], reverse=True)

    for i, m in enumerate(outs_ranked[:5]):
        s = m["score"]
        emoji = confidence_emoji(s["outs_score"])
        lines.append(f"**{i+1}. {s['pitcher']}** — {m['team']} vs {m['opponent']}")
        lines.append(f"> {emoji} Outs Score: **{s['outs_score']}** | Avg IP/Start: {s['ip_per_start']} | Avg Outs: {s['outs_per_start']}")
        lines.append(f"> ERA: {s['era']} | WHIP: {s['whip']} | Opp K%: {s['opp_k_pct']}%")
        lines.append("")

    # Full Slate
    lines.append("## 📊 FULL SLATE RANKINGS")
    lines.append("")

    for i, m in enumerate(ranked):
        if m["score"]:
            s = m["score"]
            emoji = confidence_emoji(s["total_score"])
            lines.append(f"{emoji} **{s['pitcher']}** ({m['team']} vs {m['opponent']}) — Total: **{s['total_score']}** (K: {s['k_score']} | Outs: {s['outs_score']})")
        else:
            lines.append(f"❓ **{m['pitcher_name']}** ({m['team']} vs {m['opponent']}) — No {SEASON_STATS} data")

    lines.append("")
    lines.append("---")
    lines.append("*Stats based on 2025 season | Model v1.0 | OUTS AND ODDS*")
    lines.append("*⚾ Pitcher K props + Outs — data-driven, daily.*")

    return "\n".join(lines)

def main():
    print("⚾ OUTS AND ODDS — Fetching today's slate...")
    print()

    games = get_schedule()
    if not games:
        print("❌ No games found for today.")
        return

    print(f"📅 Found {len(games)} games for {TODAY}")
    print()

    matchups = []

    for g in games:
        away = g["teams"]["away"]
        home = g["teams"]["home"]

        # Process both pitchers in each game
        for side, opp_side in [("away", "home"), ("home", "away")]:
            team_data = g["teams"][side]
            opp_data = g["teams"][opp_side]
            pitcher = team_data.get("probablePitcher", {})

            if not pitcher.get("id"):
                continue

            pitcher_name = pitcher.get("fullName", "TBD")
            pitcher_id = pitcher["id"]
            team_name = team_data["team"]["name"]
            opp_name = opp_data["team"]["name"]
            opp_id = opp_data["team"]["id"]

            print(f"  Fetching: {pitcher_name} ({team_name} vs {opp_name})...")

            p_stats = get_pitcher_stats(pitcher_id)
            o_stats = get_team_stats(opp_id)
            score = calculate_score(p_stats, o_stats, pitcher_name)

            matchups.append({
                "pitcher_name": pitcher_name,
                "pitcher_id": pitcher_id,
                "team": team_name,
                "opponent": opp_name,
                "opp_id": opp_id,
                "pitcher_stats": p_stats,
                "opp_stats": o_stats,
                "score": score,
            })

    print()
    print(f"✅ Processed {len(matchups)} pitcher matchups")
    print()

    # Generate Discord content
    discord_output = format_discord(matchups)
    print("=" * 60)
    print("DISCORD OUTPUT:")
    print("=" * 60)
    print(discord_output)

    # Save to file
    with open("daily-picks-output.md", "w") as f:
        f.write(discord_output)
    print()
    print("💾 Saved to daily-picks-output.md")

    # Also save raw data
    raw_data = []
    for m in matchups:
        raw_data.append({
            "pitcher": m["pitcher_name"],
            "team": m["team"],
            "opponent": m["opponent"],
            "score": m["score"],
        })
    with open("daily-picks-data.json", "w") as f:
        json.dump(raw_data, f, indent=2)
    print("💾 Saved raw data to daily-picks-data.json")

if __name__ == "__main__":
    main()
