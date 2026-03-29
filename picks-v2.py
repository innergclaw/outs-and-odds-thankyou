#!/usr/bin/env python3
"""
OUTS AND ODDS v2 — Fixed name matching + Pitcher Outs
Pulls directly from MLB API for pitcher data, matches to Odds API lines.
"""
import json, urllib.request, time
from datetime import datetime, timedelta

ODDS_KEY = 'da906835e59052b0da670c3f6a9aa22e'
TODAY = datetime.now().strftime('%m/%d/%Y')
TODAY_ISO = datetime.now().strftime('%Y-%m-%d')
TODAY_LABEL = datetime.now().strftime('%A, %B %d, %Y')

def mlb(path):
    url = f"https://statsapi.mlb.com/api/v1{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "OutsAndOdds/2.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def odds(path):
    url = f"https://api.the-odds-api.com/v4{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "OutsAndOdds/2.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

# Load 2025 database for team K rates
with open('2025-pitcher-database.json') as f:
    db = json.load(f)

team_k_rates = db.get('team_k_rates', {})

print("=" * 65)
print("  ⚾ OUTS AND ODDS v2 — K's + OUTS PICKS")
print("=" * 65)
print()

# ── STEP 1: Get today's games + pitchers from MLB API ──
print("[1/4] Getting today's games + pitchers...")
schedule = mlb(f"/schedule/games/?sportId=1&date={TODAY}&hydrate=probablePitcher,team")
games = schedule['dates'][0]['games'] if schedule.get('dates') else []

pitchers_today = []
for g in games:
    for side in ['away', 'home']:
        opp_side = 'home' if side == 'away' else 'away'
        team = g['teams'][side]
        opp = g['teams'][opp_side]
        sp = team.get('probablePitcher', {})
        
        if sp.get('id'):
            pitchers_today.append({
                'id': sp['id'],
                'name': sp.get('fullName', 'TBD'),
                'team': team['team']['name'],
                'team_id': team['team']['id'],
                'opp_name': opp['team']['name'],
                'opp_id': opp['team']['id'],
            })

print(f"  {len(pitchers_today)} pitchers on today's slate")

# ── STEP 2: Get 2025 stats for each pitcher ──
print("[2/4] Pulling 2025 stats for each pitcher...")

for p in pitchers_today:
    try:
        data = mlb(f"/people/{p['id']}/stats?stats=season&season=2025&group=pitching")
        s = data['stats'][0]['splits'][0]['stat']
        
        gs = int(s.get('gamesStarted', 0))
        ip = float(s.get('inningsPitched', '0'))
        k = int(s.get('strikeOuts', 0))
        k9 = float(s.get('strikeoutsPer9Inn', 0))
        era = float(s.get('era', '99'))
        whip = float(s.get('whip', '9.99'))
        bf = int(s.get('battersFaced', 0))
        
        p['gs'] = gs
        p['ip'] = ip
        p['k'] = k
        p['k9'] = round(k9, 2)
        p['era'] = era
        p['whip'] = whip
        p['k_per_start'] = round(k / max(gs, 1), 1)
        p['ip_per_start'] = round(ip / max(gs, 1), 1)
        p['outs_per_start'] = round((ip / max(gs, 1)) * 3, 1)
        p['k_pct'] = round((k / bf * 100), 1) if bf > 0 else 0
        
        # Opponent K rate
        opp_k = 22.0
        for tid, tdata in team_k_rates.items():
            if tdata.get('name') == p['opp_name']:
                opp_k = tdata['k_pct_ab']
                break
        p['opp_k_pct'] = opp_k
        
        print(f"  ✅ {p['name']:25s} | K/9: {k9:5.2f} | K/start: {p['k_per_start']:4.1f} | IP/start: {p['ip_per_start']:4.1f} | vs {p['opp_name']} ({opp_k}% K)")
        
    except Exception as e:
        p['k9'] = 0
        p['k_per_start'] = 0
        p['ip_per_start'] = 0
        p['outs_per_start'] = 0
        print(f"  ❌ {p['name']:25s} | No 2025 data")
    
    time.sleep(0.15)

# ── STEP 3: Get Odds API events + lines ──
print()
print("[3/4] Pulling DK/FD lines (K's + Outs)...")

events = odds(f"/sports/baseball_mlb/events?apiKey={ODDS_KEY}")
print(f"  {len(events)} events on Odds API")

# Match events to games by team name
def match_event(pitcher, events):
    """Find the Odds API event for this pitcher's game"""
    for e in events:
        away = e.get('away_team', '').lower()
        home = e.get('home_team', '').lower()
        team = pitcher['team'].lower()
        opp = pitcher['opp_name'].lower()
        
        # Check if team names match (partial)
        team_words = team.split()
        opp_words = opp.split()
        
        if any(w in away or w in home for w in team_words[-2:]) and \
           any(w in away or w in home for w in opp_words[-2:]):
            return e['id']
    return None

# Pull lines for each event (cache to avoid duplicate calls)
event_lines = {}

for p in pitchers_today:
    if p['k9'] == 0:
        continue
    
    event_id = match_event(p, events)
    if not event_id:
        continue
    
    p['event_id'] = event_id
    
    if event_id not in event_lines:
        try:
            # Pull both K and Outs markets
            data = odds(f"/sports/baseball_mlb/events/{event_id}/odds?apiKey={ODDS_KEY}&regions=us&markets=pitcher_strikeouts,pitcher_outs&bookmakers=draftkings,fanduel")
            
            lines = {'k': {}, 'outs': {}}
            for bm in data.get('bookmakers', []):
                book = bm['key']
                for m in bm.get('markets', []):
                    market_type = 'k' if 'strikeout' in m.get('key', '') else 'outs'
                    for o in m.get('outcomes', []):
                        pitcher_desc = o.get('description', '')
                        side = 'over' if 'Over' in str(o.get('name', '')) else 'under'
                        
                        if pitcher_desc not in lines[market_type]:
                            lines[market_type][pitcher_desc] = {}
                        if book not in lines[market_type][pitcher_desc]:
                            lines[market_type][pitcher_desc][book] = {}
                        lines[market_type][pitcher_desc][book][side] = {
                            'point': o.get('point', 0),
                            'price': o.get('price', 0)
                        }
            
            event_lines[event_id] = lines
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ❌ Lines error for event {event_id}: {e}")
            event_lines[event_id] = {'k': {}, 'outs': {}}

# ── STEP 4: Calculate edges and generate picks ──
print()
print("[4/4] Calculating edges...")
print()

k_picks = []
outs_picks = []

for p in pitchers_today:
    if p['k9'] == 0 or 'event_id' not in p:
        continue
    
    lines = event_lines.get(p['event_id'], {'k': {}, 'outs': {}})
    
    # Match pitcher name to lines (fuzzy)
    def find_line(market_lines, pitcher_name):
        name_parts = pitcher_name.lower().split()
        last_name = name_parts[-1] if name_parts else ''
        
        for desc, books in market_lines.items():
            if last_name in desc.lower():
                # Get best over
                best = None
                all_books = {}
                for book, sides in books.items():
                    if 'over' in sides:
                        o = sides['over']
                        book_label = 'DK' if book == 'draftkings' else 'FD'
                        all_books[book_label] = {'line': o['point'], 'price': o['price']}
                        if best is None or o['price'] > best['price']:
                            best = {'book': book_label, 'line': o['point'], 'price': o['price']}
                return best, all_books
        return None, {}
    
    # K lines
    k_line, k_books = find_line(lines['k'], p['name'])
    if k_line:
        # Adjusted projection
        opp_adj = (p.get('opp_k_pct', 22) - 22) * 0.08
        proj_k = round(p['k_per_start'] + opp_adj, 1)
        edge = round(proj_k - k_line['line'], 1)
        
        k_picks.append({
            'name': p['name'],
            'team': p['team'],
            'opp': p['opp_name'],
            'k9': p['k9'],
            'k_per_start': p['k_per_start'],
            'opp_k_pct': p.get('opp_k_pct', 22),
            'proj_k': proj_k,
            'line': k_line['line'],
            'price': k_line['price'],
            'book': k_line['book'],
            'all_books': k_books,
            'edge': edge,
            'era': p.get('era', 0),
        })
    
    # Outs lines
    outs_line, outs_books = find_line(lines['outs'], p['name'])
    if outs_line:
        proj_outs = p['outs_per_start']
        edge = round(proj_outs - outs_line['line'], 1)
        
        outs_picks.append({
            'name': p['name'],
            'team': p['team'],
            'opp': p['opp_name'],
            'ip_per_start': p['ip_per_start'],
            'outs_per_start': proj_outs,
            'proj_outs': proj_outs,
            'line': outs_line['line'],
            'price': outs_line['price'],
            'book': outs_line['book'],
            'all_books': outs_books,
            'edge': edge,
            'era': p.get('era', 0),
            'whip': p.get('whip', 0),
        })

# Sort by edge
k_picks.sort(key=lambda x: x['edge'], reverse=True)
outs_picks.sort(key=lambda x: x['edge'], reverse=True)

# ── OUTPUT ──
print("```")
print("╔════════════════════════════════════════════════════════════════╗")
print("║       ⚾  OUTS AND ODDS — DAILY PICKS (K's + OUTS)  ⚾      ║")
print(f"║              {TODAY_LABEL:<44s}║")
print("╚════════════════════════════════════════════════════════════════╝")
print("```")
print()

# K PICKS
print("## 🎯 STRIKEOUT PROPS")
print()

for i, p in enumerate(k_picks[:5], 1):
    emoji = "🔥🔥" if p['edge'] >= 2 else "🔥" if p['edge'] >= 1 else "✅" if p['edge'] >= 0.5 else "⚠️"
    books_str = " | ".join([f"{b}: O {d['line']} @ {d['price']}" for b, d in p['all_books'].items()])
    
    print(f"**{i}. {p['name']}** ({p['team']} vs {p['opp']})")
    print(f"> {emoji} **O {p['line']} K's** @ {p['price']} ({p['book']})")
    print(f"> 2025: {p['k9']} K/9 | {p['k_per_start']} K/start | ERA {p['era']}")
    print(f"> Opp K%: {p['opp_k_pct']}% | Projection: **{p['proj_k']} K's**")
    print(f"> Edge: **+{p['edge']} K's** | {books_str}")
    print()

if not k_picks:
    print("❌ No K prop edges found today.")
    print()

# OUTS PICKS
print("## 📋 PITCHER OUTS PROPS")
print()

for i, p in enumerate(outs_picks[:5], 1):
    emoji = "🔥🔥" if p['edge'] >= 3 else "🔥" if p['edge'] >= 1.5 else "✅" if p['edge'] >= 0.5 else "⚠️"
    books_str = " | ".join([f"{b}: O {d['line']} @ {d['price']}" for b, d in p['all_books'].items()])
    
    print(f"**{i}. {p['name']}** ({p['team']} vs {p['opp']})")
    print(f"> {emoji} **O {p['line']} outs** @ {p['price']} ({p['book']})")
    print(f"> 2025: {p['ip_per_start']} IP/start | {p['outs_per_start']} outs/start | ERA {p['era']}")
    print(f"> Projection: **{p['proj_outs']} outs** | Edge: **+{p['edge']}**")
    print(f"> {books_str}")
    print()

if not outs_picks:
    print("❌ No outs prop lines found (market may not be available yet).")
    print()

print("---")
print(f"*K picks: {len(k_picks)} found | Outs picks: {len(outs_picks)} found*")
print("*2025 stats + opponent K% + DraftKings & FanDuel lines*")
print("*Not financial advice. Bet responsibly.*")

# Save
output = {
    'date': TODAY_ISO,
    'k_picks': k_picks,
    'outs_picks': outs_picks,
}
with open('v2-picks.json', 'w') as f:
    json.dump(output, f, indent=2)
