#!/usr/bin/env python3
"""
OUTS AND ODDS — 2025 MLB Pitcher Study
Builds a comprehensive database of pitcher K and Outs performance.
"""
import json, urllib.request, time, statistics

BASE = "https://statsapi.mlb.com/api/v1"

def api(path):
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "OutsAndOdds/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  [ERROR] {url[:80]}... → {e}")
        return None

print("=" * 60)
print("  OUTS AND ODDS — 2025 MLB PITCHER STUDY")
print("=" * 60)
print()

# ============================================================
# STEP 1: Get all qualified starting pitchers (2025 season)
# ============================================================
print("[1/5] Fetching 2025 starting pitcher stats...")

# Get top pitchers by strikeouts
data = api("/stats?stats=season&season=2025&group=pitching&gameType=R&playerPool=qualified&sortStat=strikeouts&order=desc&limit=100")

pitchers = []
if data and data.get("stats"):
    for stat_group in data["stats"]:
        for split in stat_group.get("splits", []):
            p = split.get("player", {})
            s = split.get("stat", {})
            team = split.get("team", {})
            
            gs = int(s.get("gamesStarted", 0))
            if gs < 5:  # Skip relievers / low sample
                continue
            
            ip = float(s.get("inningsPitched", "0"))
            total_k = int(s.get("strikeOuts", 0))
            games = gs
            
            k9 = float(s.get("strikeoutsPer9Inn", 0))
            bb9 = float(s.get("walksPer9Inn", 0))
            era = float(s.get("era", "99"))
            whip = float(s.get("whip", "9.99"))
            
            k_per_start = total_k / max(games, 1)
            ip_per_start = ip / max(games, 1)
            outs_per_start = ip_per_start * 3
            
            # K% (strikeouts / batters faced)
            bf = int(s.get("battersFaced", 0))
            k_pct = (total_k / bf * 100) if bf > 0 else 0
            
            pitchers.append({
                "id": p.get("id"),
                "name": p.get("fullName", "Unknown"),
                "team": team.get("name", "Unknown"),
                "team_id": team.get("id"),
                "games_started": gs,
                "ip": ip,
                "total_k": total_k,
                "k9": round(k9, 2),
                "k_pct": round(k_pct, 1),
                "k_per_start": round(k_per_start, 1),
                "ip_per_start": round(ip_per_start, 1),
                "outs_per_start": round(outs_per_start, 1),
                "era": era,
                "whip": whip,
                "bb9": round(bb9, 2),
                "bf": bf,
            })

print(f"  Found {len(pitchers)} qualifying starters")

# ============================================================
# STEP 2: Get game logs for top pitchers (consistency check)
# ============================================================
print()
print("[2/5] Fetching game logs for top 30 K pitchers (consistency analysis)...")

# Sort by K/9 and take top 30
top_k = sorted(pitchers, key=lambda x: x["k9"], reverse=True)[:30]

for i, p in enumerate(top_k):
    pid = p["id"]
    logs = api(f"/people/{pid}/stats?stats=gameLog&season=2025&group=pitching&gameType=R")
    
    if logs and logs.get("stats"):
        k_list = []
        ip_list = []
        for stat_group in logs["stats"]:
            for split in stat_group.get("splits", []):
                s = split.get("stat", {})
                gs = int(s.get("gamesStarted", 0))
                if gs > 0:  # Only starts
                    k_list.append(int(s.get("strikeOuts", 0)))
                    ip_list.append(float(s.get("inningsPitched", "0")))
        
        if len(k_list) >= 3:
            p["k_median"] = round(statistics.median(k_list), 1)
            p["k_stdev"] = round(statistics.stdev(k_list), 2) if len(k_list) > 1 else 0
            p["k_min"] = min(k_list)
            p["k_max"] = max(k_list)
            p["k_over5"] = sum(1 for k in k_list if k >= 5)
            p["k_over6"] = sum(1 for k in k_list if k >= 6)
            p["k_over7"] = sum(1 for k in k_list if k >= 7)
            p["k_starts"] = len(k_list)
            p["ip_median"] = round(statistics.median(ip_list), 1)
            p["ip_stdev"] = round(statistics.stdev(ip_list), 2) if len(ip_list) > 1 else 0
            p["consistency_score"] = round(p["k_median"] / max(p["k_stdev"], 0.5), 2)
            
            pct5 = round(p["k_over5"] / len(k_list) * 100)
            pct6 = round(p["k_over6"] / len(k_list) * 100)
            print(f"  {p['name']:25s} | K/start: {p['k_per_start']:4.1f} | Median K: {p['k_median']:4.1f} | StDev: {p['k_stdev']:4.2f} | 5+K: {pct5}% | 6+K: {pct6}%")
    
    time.sleep(0.2)

# ============================================================
# STEP 3: Team strikeout rates (opponent analysis)
# ============================================================
print()
print("[3/5] Fetching 2025 team batting stats (opponent K%)...")

teams_data = api("/teams?sportId=1&season=2025")
team_k_rates = {}

if teams_data:
    for team in teams_data.get("teams", []):
        tid = team["id"]
        tname = team["name"]
        
        stats = api(f"/teams/{tid}/stats?stats=season&season=2025&group=hitting&gameType=R")
        if stats and stats.get("stats"):
            for sg in stats["stats"]:
                for split in sg.get("splits", []):
                    s = split.get("stat", {})
                    ab = int(s.get("atBats", 0))
                    k = int(s.get("strikeOuts", 0))
                    pa = int(s.get("plateAppearances", 0))
                    
                    k_pct_ab = (k / ab * 100) if ab > 0 else 0
                    k_pct_pa = (k / pa * 100) if pa > 0 else 0
                    
                    team_k_rates[tid] = {
                        "name": tname,
                        "k_pct_ab": round(k_pct_ab, 1),
                        "k_pct_pa": round(k_pct_pa, 1),
                        "total_k": k,
                        "ab": ab,
                        "pa": pa,
                    }
        time.sleep(0.15)

# Sort teams by K%
team_ranked = sorted(team_k_rates.values(), key=lambda x: x["k_pct_ab"], reverse=True)

print(f"  Found {len(team_ranked)} teams")
print()
print("  TOP 10 TEAMS THAT STRIKE OUT THE MOST (best opponents for K props):")
for i, t in enumerate(team_ranked[:10]):
    print(f"    #{i+1:2d} {t['name']:30s} | K%: {t['k_pct_ab']:.1f}% | Total K: {t['total_k']}")

print()
print("  BOTTOM 5 TEAMS THAT STRIKE OUT THE LEAST (worst opponents for K props):")
for t in team_ranked[-5:]:
    print(f"    {t['name']:30s} | K%: {t['k_pct_ab']:.1f}% | Total K: {t['total_k']}")

# ============================================================
# STEP 4: Build tier rankings
# ============================================================
print()
print("[4/5] Building pitcher tier rankings...")

# K Tier: sorted by K/9 with consistency filter
k_tier = sorted([p for p in pitchers if p.get("k_starts", p["games_started"]) >= 10], 
                key=lambda x: x["k9"], reverse=True)

print()
print("  🔥 ELITE K TIER (K/9 ≥ 10.0):")
for p in k_tier:
    if p["k9"] >= 10.0:
        con = p.get("consistency_score", "N/A")
        print(f"    {p['name']:25s} ({p['team']:20s}) | K/9: {p['k9']:5.2f} | K%: {p['k_pct']:4.1f}% | K/start: {p['k_per_start']:4.1f} | Consistency: {con}")

print()
print("  ✅ STRONG K TIER (K/9 8.5-9.99):")
count = 0
for p in k_tier:
    if 8.5 <= p["k9"] < 10.0:
        print(f"    {p['name']:25s} ({p['team']:20s}) | K/9: {p['k9']:5.2f} | K%: {p['k_pct']:4.1f}% | K/start: {p['k_per_start']:4.1f}")
        count += 1
        if count >= 15:
            break

# Outs Tier: sorted by IP per start
outs_tier = sorted([p for p in pitchers if p["games_started"] >= 10], 
                   key=lambda x: x["ip_per_start"], reverse=True)

print()
print("  📋 ELITE OUTS TIER (IP/start ≥ 6.0):")
for p in outs_tier:
    if p["ip_per_start"] >= 6.0:
        print(f"    {p['name']:25s} ({p['team']:20s}) | IP/start: {p['ip_per_start']:4.1f} | Outs/start: {p['outs_per_start']:5.1f} | ERA: {p['era']:4.2f} | WHIP: {p['whip']:4.2f}")

# ============================================================
# STEP 5: Save everything
# ============================================================
print()
print("[5/5] Saving database...")

database = {
    "season": 2025,
    "generated": "2026-03-27",
    "pitchers": pitchers,
    "top_k_detailed": top_k,
    "team_k_rates": team_k_rates,
    "team_k_ranked": team_ranked,
    "tiers": {
        "elite_k": [p for p in k_tier if p["k9"] >= 10.0],
        "strong_k": [p for p in k_tier if 8.5 <= p["k9"] < 10.0],
        "elite_outs": [p for p in outs_tier if p["ip_per_start"] >= 6.0],
    }
}

with open("2025-pitcher-database.json", "w") as f:
    json.dump(database, f, indent=2)

print(f"  Saved {len(pitchers)} pitchers + {len(team_ranked)} teams to 2025-pitcher-database.json")
print()
print("=" * 60)
print("  STUDY COMPLETE")
print("=" * 60)
