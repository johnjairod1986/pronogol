"""
PronoGol - AI Predictor v2.0 (API-Football)
Generates predictions from API-Football data, for today + next 5 days.
"""
import os, json, time, re
from datetime import datetime, timedelta, timezone
import requests

DATA_DIR = os.environ.get("PRONOGOL_DATA_DIR", "/app/data")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "b79676c9916a6b82de0f91fe3aceb46d")
API_FOOTBALL_URL = "https://v3.football.api-sports.io"
DAYS_AHEAD = 5

# Mapeo de IDs de FootyStats a API-Football
LEAGUES = {
    "Mundial 2026": {"league": 1, "season": 2026, "name": "World Cup"},
    "Finlandia - Veikkausliiga": {"league": 244, "season": 2026, "name": "Veikkausliiga"},
    "Chile - Copa Chile": {"league": 267, "season": 2026, "name": "Copa Chile"},
    "Chile - Primera Division": {"league": 265, "season": 2026, "name": "Primera Division"},
    "Chile - Primera B": {"league": 266, "season": 2026, "name": "Primera B"},
    "Australia - A-League": {"league": 188, "season": 2025, "name": "A-League"},
    "Russia - Premier League": {"league": 235, "season": 2026, "name": "Premier League"},
    "Argentina - Liga Profesional": {"league": 128, "season": 2026, "name": "Liga Profesional Argentina"},
    "Brasil - Serie B": {"league": 72, "season": 2026, "name": "Serie B"},
    "China - League One": {"league": 170, "season": 2026, "name": "League One"},
    "Ecuador - Serie A": {"league": 242, "season": 2026, "name": "Liga Pro"},
    "Bolivia - Liga Profesional": {"league": 344, "season": 2026, "name": "Primera Division"},
    "Irlanda - Premier Division": {"league": 357, "season": 2026, "name": "Premier Division"},
    "Noruega - Eliteserien": {"league": 103, "season": 2026, "name": "Eliteserien"},
    "Suecia - Allsvenskan": {"league": 113, "season": 2026, "name": "Allsvenskan"},
    "Suecia - Superettan": {"league": 114, "season": 2026, "name": "Superettan"},
    "UEFA Europa League": {"league": 3, "season": 2026, "name": "UEFA Europa League"},
    "UEFA Champions League": {"league": 2, "season": 2026, "name": "UEFA Champions League"},
    "UEFA Conference League": {"league": 848, "season": 2026, "name": "UEFA Europa Conference League"},
}

LOGO_CDN = "https://media.api-sports.io/football/teams"

# Cache de predicciones para evitar consultas repetidas
_prediction_cache = {}

def api_call(endpoint, timeout=10):
    """Call API-Football"""
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    url = f"{API_FOOTBALL_URL}{endpoint}"
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        return r.json()
    except Exception as e:
        print(f"  API-Football error: {endpoint[:50]} -> {e}")
        return {"response": [], "errors": str(e)}

def get_standings(league_id, season):
    """Get league standings for team rankings"""
    data = api_call(f"/standings?league={league_id}&season={season}")
    standings_data = {}
    for entry in data.get("response", []):
        league_data = entry.get("league", {})
        for standing in league_data.get("standings", []):
            for team in standing:
                tid = team.get("team", {}).get("id", 0)
                standings_data[tid] = team
                standings_data[str(tid)] = team
    return standings_data

def get_predictions(fixture_id):
    """Get predictions for a fixture"""
    if fixture_id in _prediction_cache:
        return _prediction_cache[fixture_id]
    data = api_call(f"/predictions?fixture={fixture_id}")
    result = {}
    for p in data.get("response", []):
        result = p
        break
    _prediction_cache[fixture_id] = result
    return result

def get_fixture_stats(fixture_id):
    """Get match statistics"""
    data = api_call(f"/fixtures/statistics?fixture={fixture_id}")
    stats = {}
    for team_data in data.get("response", []):
        team_name = team_data.get("team", {}).get("name", "")
        tid = team_data.get("team", {}).get("id", 0)
        for stat in team_data.get("statistics", []):
            t = stat.get("type", "")
            v = stat.get("value", 0)
            stats[f"{tid}_{t}"] = v
    return stats

def get_odds(fixture_id, bookmaker_id=11):
    """Get odds for a fixture from Bet365"""
    data = api_call(f"/odds?fixture={fixture_id}&bookmaker={bookmaker_id}")
    odds = {}
    for bm in data.get("response", []):
        bk = bm.get("bookmaker", {})
        for bet in bk.get("bets", []):
            name = bet.get("name", "")
            values = bet.get("values", [])
            odds[name] = {v.get("value", ""): float(v.get("odd", 0)) for v in values}
    return odds

def get_league_name(league_data):
    """Extract league name from fixture"""
    name = league_data.get("name", league_data.get("country", ""))
    season = league_data.get("season", "")
    return f"{name} {season}".strip()

def generate_predictions_for_date(date_str=None):
    """Generate predictions for a specific date"""
    bogota = timezone(timedelta(hours=-5))
    now = datetime.now(bogota)
    
    if date_str is None:
        date_str = now.strftime("%Y-%m-%d")
    
    print(f"Generating predictions for {date_str}...")
    
    # Fetch all fixtures for this date
    data = api_call(f"/fixtures?date={date_str}")
    matches = data.get("response", [])
    
    if not matches:
        print(f"  No matches found for {date_str}")
        return [], 0
    
    print(f"  Raw matches: {len(matches)}")
    
    predictions = []
    for match in matches[:50]:
        fixture = match.get("fixture", {})
        teams = match.get("teams", {})
        league = match.get("league", {})
        goals = match.get("goals", {})
        score = match.get("score", {})
        
        fid = fixture.get("id", 0)
        home_team = teams.get("home", {}).get("name", "")
        away_team = teams.get("away", {}).get("name", "")
        home_id = teams.get("home", {}).get("id", 0)
        away_id = teams.get("away", {}).get("id", 0)
        league_id = league.get("id", 0)
        league_season = league.get("season", 2026)
        
        match_time = int(fixture.get("timestamp", 0))
        status = fixture.get("status", {}).get("long", "scheduled")
        home_score = goals.get("home")
        away_score = goals.get("away")
        ht_score = score.get("halftime", {})
        ht_home = ht_score.get("home") if ht_score else None
        ht_away = ht_score.get("away") if ht_score else None
        
        # League name: find in our mapping or use API name
        league_name = "Otra liga"
        for l_name, l_data in LEAGUES.items():
            if l_data["league"] == league_id:
                league_name = l_name
                break
        if league_name == "Otra liga":
            league_name = get_league_name(league)
        
        # Get standings rankings for this league
        standings = get_standings(league_id, league_season)
        
        # Get home/away team ranks from standings
        home_rank = 15
        away_rank = 15
        home_pts = 0
        away_pts = 0
        h_team_stand = standings.get(home_id) or standings.get(str(home_id), {})
        a_team_stand = standings.get(away_id) or standings.get(str(away_id), {})
        if h_team_stand:
            home_rank = h_team_stand.get("rank", 15)
            home_pts = int(h_team_stand.get("points", 0))
        if a_team_stand:
            away_rank = a_team_stand.get("rank", 15)
            away_pts = int(a_team_stand.get("points", 0))
        
        # Get predictions from API-Football
        pred_data = get_predictions(fid)
        predictions_data = pred_data.get("predictions", {})
        percentages = pred_data.get("percentages", {})
        
        # Default probabilities
        home_win_pct = 42
        draw_pct = 28
        away_win_pct = 30
        
        # Use API-Football predictions if available
        pred_winner = predictions_data.get("winner", {})
        win_or_draw = predictions_data.get("win_or_draw")
        pred_under_over = predictions_data.get("under_over")
        pred_advice = predictions_data.get("advice", "")
        
        # Use percentages from API
        home_pct = percentages.get("home", "")
        draw_pct_val = percentages.get("draw", "")
        away_pct = percentages.get("away", "")
        
        if home_pct and isinstance(home_pct, str) and "%" in home_pct:
            try:
                home_win_pct = int(home_pct.replace("%", ""))
                draw_pct = int(draw_pct_val.replace("%", "")) if draw_pct_val and isinstance(draw_pct_val, str) else 25
                away_win_pct = int(away_pct.replace("%", "")) if away_pct and isinstance(away_pct, str) else 30
            except:
                pass
        
        # Fallback: use standings rank difference
        if not home_pct:
            rank_diff = home_rank - away_rank
            if rank_diff <= -10:
                home_win_pct = 60; draw_pct = 22; away_win_pct = 18
            elif rank_diff <= -5:
                home_win_pct = 50; draw_pct = 27; away_win_pct = 23
            elif rank_diff >= 10:
                away_win_pct = 60; draw_pct = 22; home_win_pct = 18
            elif rank_diff >= 5:
                away_win_pct = 50; draw_pct = 27; home_win_pct = 23
            else:
                home_win_pct = 42; draw_pct = 28; away_win_pct = 30
        
        # Winner prediction
        if home_win_pct >= 45:
            winner_pred = "1"
            winner_trust = max(min(round(home_win_pct / 9), 10), 3)
        elif away_win_pct >= 45:
            winner_pred = "2"
            winner_trust = max(min(round(away_win_pct / 9), 10), 3)
        else:
            winner_pred = "X"
            winner_trust = 4
        
        # DC prediction
        if home_win_pct >= 40:
            dc_pred = "1X"
            dc_trust = min(round((home_win_pct + draw_pct) / 11), 9)
        elif away_win_pct >= 40:
            dc_pred = "X2"
            dc_trust = min(round((away_win_pct + draw_pct) / 11), 9)
        else:
            dc_pred = "12"
            dc_trust = 6
        
        # Use pred_under_over if available
        total_xg = 2.5  # default
        if pred_under_over:
            try:
                if "+" in pred_under_over:
                    total_xg = float(pred_under_over.replace("+", ""))
                else:
                    total_xg = float(pred_under_over.split("+")[0].strip()) if pred_under_over else 2.5
            except:
                pass
        
        over_15_pct = max(min(round(50 + (total_xg - 1.5) * 25), 92), 35)
        over_25_pct = max(min(round(50 + (total_xg - 2.5) * 25), 88), 20)
        
        # Use BTTS from predictions
        btts_pred = predictions_data.get("btts", None)
        if btts_pred:
            btts_yes_pct = 60 if btts_pred else 40
        else:
            btts_yes_pct = max(min(round(40 + (total_xg - 2.0) * 20), 80), 30)
        
        pred = {
            "match_id": str(fid),
            "match_time": match_time,
            "date": date_str,
            "league": league_name,
            "league_id": league_id,
            "home_team": home_team,
            "home_logo": f"{LOGO_CDN}/{home_id}.png",
            "away_team": away_team,
            "away_logo": f"{LOGO_CDN}/{away_id}.png",
            "home_score": home_score,
            "away_score": away_score,
            "status": status,
            "total_xg": round(total_xg, 2),
            "advice": pred_advice,
            "markets": {
                "match_winner": {
                    "prediction": winner_pred,
                    "home_pct": round(home_win_pct), "draw_pct": round(draw_pct), "away_pct": round(away_win_pct),
                    "trust": winner_trust,
                },
                "double_chance": {
                    "1X_pct": round(home_win_pct + draw_pct), "12_pct": round(home_win_pct + away_win_pct), "X2_pct": round(draw_pct + away_win_pct),
                    "prediction": dc_pred,
                    "trust": dc_trust,
                },
                "btts": {
                    "yes_pct": round(btts_yes_pct), "no_pct": round(100 - btts_yes_pct),
                    "prediction": "Si" if btts_yes_pct >= 50 else "No",
                    "trust": min(max(round(btts_yes_pct / 10), 4), 8),
                },
                "over_under_1.5": {
                    "over_pct": round(over_15_pct), "under_pct": round(100 - over_15_pct),
                    "prediction": ">1.5" if over_15_pct >= 55 else "<1.5",
                    "trust": min(max(round(over_15_pct / 12), 4), 9),
                },
                "over_under_2.5": {
                    "over_pct": round(over_25_pct), "under_pct": round(100 - over_25_pct),
                    "prediction": ">2.5" if over_25_pct >= 50 else "<2.5",
                    "trust": min(max(round(over_25_pct / 12), 3), 8),
                },
            },
            "best_pick": {"market": "", "prediction": "", "confidence": 0},
        }
        
        best = max(pred["markets"].items(), key=lambda kv: kv[1]["trust"])
        if best[1]["trust"] >= 6:
            pred["best_pick"] = {"market": best[0], "prediction": best[1]["prediction"], "confidence": best[1]["trust"]}
        
        predictions.append(pred)
    
    predictions.sort(key=lambda x: x["best_pick"]["confidence"], reverse=True)
    return predictions, len(matches)

def generate_predictions():
    """Main generator"""
    bogota = timezone(timedelta(hours=-5))
    now = datetime.now(bogota)
    print(f"PronoGol Predictor v2 (API-Football) running at {now.isoformat()}")
    
    all_predictions = []
    total_fetched = 0
    
    for day_offset in range(DAYS_AHEAD + 1):
        dt = now + timedelta(days=day_offset)
        date_str = dt.strftime("%Y-%m-%d")
        preds, fetched = generate_predictions_for_date(date_str)
        all_predictions.extend(preds)
        total_fetched += fetched
        print(f"  {date_str} ({dt.strftime('%A')}): {len(preds)} predictions from {fetched} matches")
    
    cache = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dates": {},
        "predictions": all_predictions,
        "count": len(all_predictions),
        "total_matches_fetched": total_fetched,
    }
    
    for p in all_predictions:
        d = p.get("date", "")
        if d:
            cache["dates"].setdefault(d, {"count": 0, "leagues": set()})
            cache["dates"][d]["count"] += 1
            cache["dates"][d]["leagues"].add(p["league"])
    
    for d in cache["dates"]:
        cache["dates"][d]["leagues"] = list(cache["dates"][d]["leagues"])
    
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, "predictions_cache.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    leagues_count = len(set(p["league"] for p in all_predictions))
    print(f"Done: {len(all_predictions)} predictions, {leagues_count} leagues, {len(cache['dates'])} dates")
    return cache

if __name__ == "__main__":
    generate_predictions()
