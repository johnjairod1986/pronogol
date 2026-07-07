"""
PronoGol - AI Predictor
Generates predictions from FootyStats data, stores cache for API.
"""
import os, json, time
from datetime import datetime, timedelta
import requests

DATA_DIR = os.environ.get("PRONOGOL_DATA_DIR", "/app/data")
FOOTYSTATS_KEY = "1abc780710040e043b218e141869d4b664aac69ed8b97ff98dc96da9ca420f72"
FOOTYSTATS_URL = "https://api.football-data-api.com"
SEASON_ID = "16494"

def load_teams():
    """Load team rankings from FootyStats. Handles both team_id and id fields."""
    try:
        r = requests.get(f"{FOOTYSTATS_URL}/league-teams?season_id={SEASON_ID}&key={FOOTYSTATS_KEY}", timeout=10)
        data = r.json()
        if data.get("success", 0) == 1:
            team_list = data.get("data", [])
            teams = {}
            for t in team_list:
                tid = t.get("team_id") or t.get("id")
                if tid:
                    teams[tid] = t
            return teams
    except Exception as e:
        print(f"Error loading teams: {e}")
    return {}

def get_match_detail(match_id):
    """Fetch detailed match stats including xG and lineups."""
    try:
        r = requests.get(
            f"{FOOTYSTATS_URL}/match?match_id={match_id}&include=stats&key={FOOTYSTATS_KEY}",
            timeout=10
        )
        md = r.json()
        if md.get("success", 0) == 1:
            return md.get("data", {})
    except:
        pass
    return {}

def generate_predictions():
    """Main prediction generator - creates match predictions from real FootyStats data."""
    print(f"🤖 PronoGol Predictor running at {datetime.utcnow().isoformat()}")
    
    teams = load_teams()
    print(f"📊 Loaded {len(teams)} teams with rankings")
    
    # Get today's matches from FootyStats
    try:
        r = requests.get(f"{FOOTYSTATS_URL}/todays-matches?season_id={SEASON_ID}&key={FOOTYSTATS_KEY}", timeout=10)
        data = r.json()
        matches = data.get("data", []) if data.get("success", 0) == 1 else []
        print(f"📅 Found {len(matches)} matches today")
    except Exception as e:
        print(f"Error fetching matches: {e}")
        matches = []
    
    predictions = []
    
    for match in matches[:40]:  # Limit to 40 matches
        home_id = match.get("homeID") or match.get("home_id") or 0
        away_id = match.get("awayID") or match.get("away_id") or 0
        
        home_team = teams.get(home_id, {})
        away_team = teams.get(away_id, {})
        
        home_rank = home_team.get("performance_rank", 30)
        away_rank = away_team.get("performance_rank", 30)
        home_risk = home_team.get("risk", 100)
        away_risk = away_team.get("risk", 100)
        
        # Team names from match data or teams dict
        home_name = home_team.get("name") or match.get("home_name") or match.get("home_team_name") or f"Local #{home_id}"
        away_name = away_team.get("name") or match.get("away_name") or match.get("away_team_name") or f"Visitante #{away_id}"
        
        # Get match time (Unix timestamp)
        match_time = 0
        date_data = match.get("date", {})
        if isinstance(date_data, dict):
            match_time = date_data.get("startTimestamp", 0)
        elif isinstance(date_data, str):
            try:
                dt = datetime.fromisoformat(date_data.replace("Z", "+00:00"))
                match_time = int(dt.timestamp())
            except:
                pass
        if not match_time:
            match_time = match.get("startTimestamp", 0)
        
        # Get match details for xG (sparingly - respect rate limits)
        match_detail = get_match_detail(match.get("id", ""))
        
        # Probabilities based on rank difference
        rank_diff = home_rank - away_rank  # Negative = home stronger
        
        if rank_diff <= -15:
            home_win_pct = 60; draw_pct = 23; away_win_pct = 17
        elif rank_diff <= -8:
            home_win_pct = 55; draw_pct = 25; away_win_pct = 20
        elif rank_diff <= -3:
            home_win_pct = 48; draw_pct = 28; away_win_pct = 24
        elif rank_diff >= 15:
            away_win_pct = 60; draw_pct = 23; home_win_pct = 17
        elif rank_diff >= 8:
            away_win_pct = 55; draw_pct = 25; home_win_pct = 20
        elif rank_diff >= 3:
            away_win_pct = 48; draw_pct = 28; home_win_pct = 24
        else:
            home_win_pct = 40; draw_pct = 30; away_win_pct = 30
        
        # xG-based adjustments
        xg_home = float(match_detail.get("team_a_xg", 0) or 0) if match_detail else (
            1.5 if home_win_pct >= 55 else (1.2 if home_win_pct >= 45 else 1.0)
        )
        xg_away = float(match_detail.get("team_b_xg", 0) or 0) if match_detail else (
            1.5 if away_win_pct >= 55 else (1.2 if away_win_pct >= 45 else 1.0)
        )
        total_xg = round(xg_home + xg_away, 2)
        
        # Risk reduces trust
        trust_penalty = 0
        if home_win_pct >= 45 and (home_risk > 150 or away_risk > 150):
            trust_penalty = 1
        if away_win_pct >= 45 and (away_risk > 150 or home_risk > 150):
            trust_penalty = 1
        
        # Market calculations
        if home_win_pct >= 45:
            winner_pred = "1"
            winner_trust = min(max(round(home_win_pct / 9), 4), 10) - trust_penalty
        elif away_win_pct >= 45:
            winner_pred = "2"
            winner_trust = min(max(round(away_win_pct / 9), 4), 10) - trust_penalty
        else:
            winner_pred = "X"
            winner_trust = 4
        
        if home_win_pct >= 40:
            dc_pred = "1X"
        elif away_win_pct >= 40:
            dc_pred = "X2"
        else:
            dc_pred = "12"
        dc_trust = min(max(round((home_win_pct + draw_pct) / 11), 5), 9) if home_win_pct >= 40 else min(max(round((away_win_pct + draw_pct) / 11), 5), 9)
        
        over_15_pct = min(round(50 + (total_xg - 1.5) * 25), 92)
        over_25_pct = min(round(50 + (total_xg - 2.5) * 25), 88)
        btts_yes_pct = min(round(40 + (total_xg - 2.0) * 20), 80)
        
        over_15_pct = max(over_15_pct, 30)
        over_25_pct = max(over_25_pct, 15)
        btts_yes_pct = max(btts_yes_pct, 20)
        
        pred = {
            "match_id": str(match.get("id", "")),
            "match_time": match_time,
            "league": match.get("league_name") or match.get("name") or "Mundial 2026",
            "league_id": match.get("league_id", 0),
            "home_team": home_name,
            "home_logo": f"https://media.api-sports.io/football/teams/{home_id}.png",
            "away_team": away_name,
            "away_logo": f"https://media.api-sports.io/football/teams/{away_id}.png",
            "home_score": match.get("scores", {}).get("home_score") if isinstance(match.get("scores"), dict) else None,
            "away_score": match.get("scores", {}).get("away_score") if isinstance(match.get("scores"), dict) else None,
            "status": match.get("status", "scheduled"),
            "total_xg": total_xg,
            "markets": {
                "match_winner": {
                    "prediction": winner_pred,
                    "home_pct": round(home_win_pct),
                    "draw_pct": round(draw_pct),
                    "away_pct": round(away_win_pct),
                    "trust": winner_trust,
                },
                "double_chance": {
                    "1X_pct": round(home_win_pct + draw_pct),
                    "12_pct": round(home_win_pct + away_win_pct),
                    "X2_pct": round(draw_pct + away_win_pct),
                    "prediction": dc_pred,
                    "trust": dc_trust,
                },
                "btts": {
                    "yes_pct": round(btts_yes_pct),
                    "no_pct": round(100 - btts_yes_pct),
                    "prediction": "Si" if btts_yes_pct >= 50 else "No",
                    "trust": min(max(round(btts_yes_pct / 11), 3), 8),
                },
                "over_under_1.5": {
                    "over_pct": round(over_15_pct),
                    "under_pct": round(100 - over_15_pct),
                    "prediction": ">1.5" if over_15_pct >= 55 else "<1.5",
                    "trust": min(max(round(over_15_pct / 13), 3), 9),
                },
                "over_under_2.5": {
                    "over_pct": round(over_25_pct),
                    "under_pct": round(100 - over_25_pct),
                    "prediction": ">2.5" if over_25_pct >= 50 else "<2.5",
                    "trust": min(max(round(over_25_pct / 13), 2), 8),
                },
            },
            "best_pick": {"market": "", "prediction": "", "confidence": 0},
        }
        
        # Best pick: highest trust >= 6
        best_confidence = 0
        for mkt_key, mkt_data in pred["markets"].items():
            trust = mkt_data.get("trust", 0)
            if trust >= best_confidence and trust >= 6:
                best_confidence = trust
                pred["best_pick"] = {"market": mkt_key, "prediction": mkt_data["prediction"], "confidence": trust}
        
        predictions.append(pred)
    
    # Sort by confidence descending
    predictions.sort(key=lambda x: x["best_pick"]["confidence"], reverse=True)
    
    cache = {
        "generated_at": datetime.utcnow().isoformat(),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "predictions": predictions,
        "count": len(predictions),
    }
    
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "predictions_cache.json"), "w") as f:
        json.dump(cache, f, indent=2)
    
    print(f"✅ Generated {len(predictions)} predictions")
    return cache

if __name__ == "__main__":
    generate_predictions()
