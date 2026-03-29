#!/usr/bin/env python3
"""
OUTS AND ODDS — Daily Picks Engine v1.0
Combines 2025 pitcher data + current DK/FD lines to find edge plays.
"""
import json, urllib.request, time
from datetime import datetime

API_KEY = 'da906835e59052b0da670c3f6a9aa22e'

# Load 2025 database
try:
    with open('2025-pitcher-database.json', 'r') as f:
        db = json.load(f)
except:
    db = {"pitchers": [], "team_k_rates": {}}

pitcher_map = {p['name'].lower().replace('.', '').replace('-', ' '): p for p in db.get('pitchers', [])}

def odds_api(path):
    url = f"https://api.the-odds-api.com/v4{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "OutsAndOdds/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

def mlb_api(path):
    url = f"https://statsapi.mlb.com/api/v1{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "OutsAndOdds/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except:
        return None

def get_todays_games():
    """Get today's games from MLB API with probable pitchers"""
    today = datetime.now().strftime('%Y-%m-%d')
    data = mlb_api(f"/schedule/games/?sportId=1&date={today.replace('-', '/')}&hydrate=probablePitcher")
    if not data or not data.get('dates'):
        return []
    
    games = []
    for g in data['dates'][0].get('games', []):
        away = g['teams']['away']
        home = g['teams']['home']
        
        away_pitcher = away.get('probablePitcher', {})
        home_pitcher = home.get('probablePitcher', {})
        
        games.append({
            'id': g['gamePk'],
            'event_id': None,  # Will match with Odds API
            'away_team': away['team']['name'],
            'home_team': home['team']['name'],
            'away_team_id': away['team']['id'],
            'home_team_id': home['team']['id'],
            'away_pitcher': away_pitcher.get('fullName'),
            'away_pitcher_id': away_pitcher.get('id'),
            'home_pitcher': home_pitcher.get('fullName'),
            'home_pitcher_id': home_pitcher.get('id'),
            'time': g['gameDate'],
        })
    return games

def get_odds_events():
    """Get event IDs from Odds API"""
    data = odds_api("/sports/baseball_mlb/events")
    if not data:
        return {}
    
    events = {}
    for e in data:
        key = f"{e.get('away_team')} @ {e.get('home_team')}"
        events[key] = e['id']
    return events

def get_pitcher_k_lines(event_id):
    """Get pitcher strikeout props for an event"""
    data = odds_api(f"/sports/baseball_mlb/events/{event_id}/odds?regions=us&markets=pitcher_strikeouts&bookmakers=draftkings,fanduel")
    if not data:
        return None
    
    lines = {}
    for bm in data.get('bookmakers', []):
        book = bm['key']
        for market in bm.get('markets', []):
            if market.get('key') == 'pitcher_strikeouts':
                for outcome in market.get('outcomes', []):
                    pitcher_name = outcome.get('name', '').lower().replace('.', '').replace('-', ' ')
                    if pitcher_name not in lines:
                        lines[pitcher_name] = {}
                    if book not in lines[pitcher_name]:
                        lines[pitcher_name][book] = []
                    lines[pitcher_name][book].append({
                        'over_under': outcome.get('description', ''),  # Over or Under
                        'point': outcome.get('point', 0),
                        'price': outcome.get('price', 0),
                        'side': 'over' if 'over' in outcome.get('name', '').lower() else 'under',
                    })
    return lines

def find_pitcher_data(name):
    """Match pitcher name to 2025 data"""
    if not name:
        return None
    name_clean = name.lower().replace('.', '').replace('-', ' ')
    
    # Exact match
    if name_clean in pitcher_map:
        return pitcher_map[name_clean]
    
    # Partial match
    for key, p in pitcher_map.items():
        if name_clean in key or key in name_clean:
            return p
    
    return None

def score_matchup(pitcher, opponent_team_id):
    """Score a pitcher matchup based on 2025 data"""
    if not pitcher:
        return None
    
    # Base K projection from 2025
    k9 = pitcher.get('k9', 0)
    k_per_start = pitcher.get('k_per_start', 0)
    
    # Opponent adjustment
    opp_k_rate = 22.0  # league average
    team_rates = db.get('team_k_rates', {})
    if str(opponent_team_id) in team_rates:
        opp_k_rate = team_rates[str(opponent_team_id)].get('k_pct_ab', 22.0)
    
    # Adjust projection: pitcher K% vs opponent K rate
    k_pct = pitcher.get('k_pct', 22.0)
    adjustment = (opp_k_rate - 22.0) * 0.15  # 15% weight to opponent
    adjusted_k9 = k9 + adjustment
    
    # Project K's over 5-6 innings (typical start)
    proj_k_low = round(adjusted_k9 * 5 / 9, 1)  # 5 IP
    proj_k_high = round(adjusted_k9 * 6 / 9, 1)  # 6 IP
    proj_k_avg = round((proj_k_low + proj_k_high) / 2, 1)
    
    return {
        'pitcher_name': pitcher['name'],
        'team': pitcher['team'],
        'k9_2025': k9,
        'k_per_start_2025': k_per_start,
        'opp_k_rate': opp_k_rate,
        'proj_k_low': proj_k_low,
        'proj_k_high': proj_k_high,
        'proj_k_avg': proj_k_avg,
        'consistency_5k_pct': pitcher.get('k_over5', 0) / max(pitcher.get('k_starts', 10), 1) * 100,
        'confidence': 'high' if k9 >= 9.0 else 'medium' if k9 >= 8.0 else 'low',
    }

def find_best_line(lines, pitcher_name):
    """Find the best over line for a pitcher across DK/FD"""
    if not lines:
        return None
    
    name_clean = pitcher_name.lower().replace('.', '').replace('-', ' ')
    pitcher_lines = None
    
    for key in lines:
        if name_clean in key or key in name_clean:
            pitcher_lines = lines[key]
            break
    
    if not pitcher_lines:
        return None
    
    best = None
    for book, outcomes in pitcher_lines.items():
        for o in outcomes:
            if o['side'] == 'over':
                if not best or o['point'] < best['point'] or (o['point'] == best['point'] and o['price'] > best['price']):
                    best = {
                        'book': book,
                        'line': o['point'],
                        'odds': o['price'],
                        'book_display': 'DraftKings' if book == 'draftkings' else 'FanDuel'
                    }
    return best

def format_discord_picks(picks):
    """Generate Discord-formatted picks"""
    lines = []
    lines.append("```")
    lines.append("╔════════════════════════════════════════════════════╗")
    lines.append("║     ⚾  OUTS AND ODDS — DAILY K PROP PICKS  ⚾    ║")
    lines.append(f"║          {datetime.now().strftime('%A, %B %d, %Y'):^35}  ║")
    lines.append("╚════════════════════════════════════════════════════╝")
    lines.append("```")
    lines.append("")
    
    if not picks:
        lines.append("❌ No high-confidence plays today.")
        return "\n".join(lines)
    
    lines.append("## 🔥 TOP PLAYS")
    lines.append("")
    
    for i, pick in enumerate(picks[:3], 1):
        m = pick['matchup']
        l = pick['line']
        edge = pick['edge']
        
        emoji = "🔥" if edge >= 1.5 else "✅" if edge >= 1.0 else "⚠️"
        
        lines.append(f"**{i}. {m['pitcher_name']}** ({m['team']} vs {pick['opponent']})")
        lines.append(f"> {emoji} **O {l['line']} K's** @ {l['odds']} on {l['book_display']}")
        lines.append(f"> Model projects: **{m['proj_k_low']}-{m['proj_k_high']} K's** (avg {m['proj_k_avg']})")
        lines.append(f"> Edge: **+{edge:.1f} K's** over the line")
        lines.append(f"> 2025: {m['k9_2025']} K/9 | Hit 5+ K in {m['consistency_5k_pct']:.0f}% of starts")
        lines.append("")
    
    lines.append("---")
    lines.append("*Model: 2025 stats + opponent K% + line comparison | Not financial advice*")
    lines.append("*⚾ Data-driven pitcher K props daily*")
    
    return "\n".join(lines)

def main():
    print("=" * 60)
    print("  OUTS AND ODDS — DAILY PICKS ENGINE")
    print("=" * 60)
    print()
    
    # Get today's games
    print("[1/4] Fetching today's MLB slate...")
    games = get_todays_games()
    print(f"  Found {len(games)} games")
    
    # Get Odds API events
    print("[2/4] Matching games to betting lines...")
    events = get_odds_events()
    
    # Match games to events
    for g in games:
        key = f"{g['away_team']} @ {g['home_team']}"
        key2 = f"{g['away_team'].split()[-1]} @ {g['home_team'].split()[-1]}"  # Short names
        
        if key in events:
            g['event_id'] = events[key]
        elif key2 in events:
            g['event_id'] = events[key2]
    
    games_with_lines = [g for g in games if g['event_id']]
    print(f"  Matched {len(games_with_lines)} games with betting lines")
    
    # Get lines and score each matchup
    print("[3/4] Analyzing pitcher matchups...")
    picks = []
    
    for g in games_with_lines:
        lines = get_pitcher_k_lines(g['event_id'])
        time.sleep(0.5)  # Rate limit
        
        # Analyze both pitchers
        for side in ['away', 'home']:
            pitcher_name = g.get(f'{side}_pitcher')
            opponent_id = g['home_team_id'] if side == 'away' else g['away_team_id']
            opponent_name = g['home_team'] if side == 'away' else g['away_team']
            
            if not pitcher_name:
                continue
            
            pitcher_data = find_pitcher_data(pitcher_name)
            if not pitcher_data:
                print(f"  ⚠️ No 2025 data for {pitcher_name}")
                continue
            
            matchup = score_matchup(pitcher_data, opponent_id)
            if not matchup:
                continue
            
            line_info = find_best_line(lines, pitcher_name)
            if not line_info:
                continue
            
            # Calculate edge
            edge = matchup['proj_k_avg'] - line_info['line']
            
            # Only include if edge > 0.5 and confidence not low
            if edge >= 0.5 and matchup['confidence'] != 'low':
                picks.append({
                    'matchup': matchup,
                    'opponent': opponent_name,
                    'line': line_info,
                    'edge': edge,
                    'game_time': g['time'],
                })
                print(f"  ✅ {pitcher_name}: {matchup['proj_k_avg']} proj vs {line_info['line']} line (edge +{edge:.1f})")
    
    # Sort by edge
    picks.sort(key=lambda x: x['edge'], reverse=True)
    
    print()
    print(f"[4/4] Generated {len(picks)} picks")
    print()
    
    # Format output
    output = format_discord_picks(picks)
    print(output)
    
    # Save
    with open('daily-picks-discord.txt', 'w') as f:
        f.write(output)
    
    with open('daily-picks-data.json', 'w') as f:
        json.dump(picks, f, indent=2)
    
    print()
    print("💾 Saved to daily-picks-discord.txt and daily-picks-data.json")

if __name__ == "__main__":
    main()
