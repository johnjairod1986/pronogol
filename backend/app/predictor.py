"""
PronoGol - AI Predictor
Generates predictions from FootyStats data, stores cache for API.
"""
import os, json, hashlib, time
from datetime import datetime, timedelta
from typing import Optional
import requests

DATA_DIR = os.environ.get("PRONOGOL_DATA_DIR", "/docker/pronogol/data")
FOOTYSTATS_KEY = "1abc780710040e043b218e141869d4b664aac69ed8b97ff98dc96da9ca420f72"
FOOTYSTATS_URL = "https://api.football-data-api.com"
SEASON_ID = "16494"  # World Cup 2026

def load_teams():
    """Load team rankings from FootyStats."""
    try:
        r = requests.get(f"{FOOTYSTATS_URL}/league-teams?season_id={SEASON_ID}&key={FOOTYSTATS_KEY}", timeout=10)
        data = r.json()
        if data.get("success", 0) == 1:
            teams = {t["team_id"]: t for t in data.get("data", [])}
            return teams
    except Exception as e:
        print(f"Error loading teams: {e}")
    return {}

def generate_predictions():
    """Main prediction generator - creates match predictions."""
    print(f"🤖 PronoGol Predictor running at {datetime.utcnow().isoformat()}")
    
    teams = load_teams()
    print(f"📊 Loaded {len(teams)} teams")
    
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
    
    for match in matches[:30]:  # Limit to 30 matches
        home_id = match.get("homeID", 0)
        away_id = match.get("awayID", 0)
        home_team = teams.get(home_id, {})
        away_team = teams.get(away_id, {})
        
        home_rank = home_team.get("performance_rank", 30)
        away_rank = away_team.get("performance_rank", 30)
        home_risk = home_team.get("risk", 100)
        away_risk = away_team.get("risk", 100)
        
        # Get match details for xG
        match_detail = None
        try:
            rd = requests.get(
                f"{FOOTYSTATS_URL}/match?match_id={match.get('id', '')}&include=stats&key={FOOTYSTATS_KEY}",
                timeout=10
            )
            md = rd.json()
            if md.get("success", 0) == 1:
                match_detail = md.get("data", {})
        except:
            pass
        
        # Calculate probabilities
        rank_diff = home_rank - away_rank  # Negative = home stronger
        total_risk = home_risk + away_risk
        
        # Match Winner probabilities
        if rank_diff < -10:  # Home clear favorite
            home_win_pct = 55 + min(abs(rank_diff), 15)
            draw_pct = 25
            away_win_pct = 100 - home_win_pct - draw_pct
        elif rank_diff > 10:  # Away clear favorite
            away_win_pct = 55 + min(abs(rank_diff), 15)
            draw_pct = 25
            home_win_pct = 100 - away_win_pct - draw_pct
        else:  # Even
            home_win_pct = 40
            draw_pct = 30
            away_win_pct = 30
        
        # xG-based adjustments
        xg_home = float(match_detail.get("team_a_xg", 0) or 0) if match_detail else 1.2
        xg_away = float(match_detail.get("team_b_xg", 0) or 0) if match_detail else 1.0
        total_xg = xg_home + xg_away
        
        # Over/Under probabilities based on xG
        if total_xg >= 2.8:
            over_25_pct = 60
            over_15_pct = 82
            btts_yes_pct = 55
        elif total_xg >= 2.2:
            over_25_pct = 48
            over_15_pct = 75
            btts_yes_pct = 48
        else:
            over_25_pct = 35
            over_15_pct = 65
            btts_yes_pct = 40
        
        # Best prediction for each market
        pred = {
            "match_id": match.get("id", ""),
            "match_time": match.get("date", {}).get("startTimestamp", ""),
            "league": match.get("league_name", ""),
            "league_id": match.get("league_id", 0),
            "home_team": home_team.get("name", match.get("home_name", "")),
            "home_logo": f"https://media.180score.com/football/teams/{home_id}.png" if home_id else "",
            "away_team": away_team.get("name", match.get("away_name", "")),
            "away_logo": f"https://media.180score.com/football/teams/{away_id}.png" if away_id else "",
            "home_score": match.get("scores", {}).get("home_score"),
            "away_score": match.get("scores", {}).get("away_score"),
            "status": match.get("status", "scheduled"),
            "total_xg": round(total_xg, 2),
            "markets": {
                "match_winner": {
                    "prediction": "1" if home_win_pct >= 45 else ("2" if away_win_pct >= 45 else "X"),
                    "home_pct": round(home_win_pct),
                    "draw_pct": round(draw_pct),
                    "away_pct": round(away_win_pct),
                    "trust": min(round(home_win_pct / 10), 10) if home_win_pct >= 45 else min(round(away_win_pct / 10), 10),
                },
                "double_chance": {
                    "1X_pct": round(home_win_pct + draw_pct),
                    "12_pct": round(home_win_pct + away_win_pct),
                    "X2_pct": round(draw_pct + away_win_pct),
                    "prediction": "1X" if home_win_pct >= 40 else ("X2" if away_win_pct >= 40 else "12"),
                    "trust": 8 if abs(rank_diff) >= 15 else 6,
                },
                "btts": {
                    "yes_pct": round(btts_yes_pct),
                    "no_pct": round(100 - btts_yes_pct),
                    "prediction": "Si" if btts_yes_pct >= 50 else "No",
                    "trust": min(max(round(btts_yes_pct / 12), 3), 9),
                },
                "over_under_1.5": {
                    "over_pct": round(over_15_pct),
                    "under_pct": round(100 - over_15_pct),
                    "prediction": ">1.5" if over_15_pct >= 50 else "<1.5",
                    "trust": min(max(round(over_15_pct / 12), 3), 9),
                },
                "over_under_2.5": {
                    "over_pct": round(over_25_pct),
                    "under_pct": round(100 - over_25_pct),
                    "prediction": ">2.5" if over_25_pct >= 50 else "<2.5",
                    "trust": min(max(round(over_25_pct / 12), 3), 8),
                },
            },
            "best_pick": {
                "market": "",
                "prediction": "",
                "confidence": 0,
            }
        }
        
        # Find best pick (highest confidence over 75%)
        best_confidence = 0
        for mkt_key, mkt_data in pred["markets"].items():
            trust = mkt_data.get("trust", 0)
            if trust >= best_confidence and trust >= 5:
                best_confidence = trust
                pred["best_pick"] = {
                    "market": mkt_key,
                    "prediction": mkt_data["prediction"],
                    "confidence": trust,
                }
        
        predictions.append(pred)
    
    # Sort by best pick confidence
    predictions.sort(key=lambda x: x["best_pick"]["confidence"], reverse=True)
    
    # Save cache
    cache = {
        "generated_at": datetime.utcnow().isoformat(),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "predictions": predictions,
        "count": len(predictions),
    }
    
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, "predictions_cache.json")
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)
    
    print(f"✅ Generated {len(predictions)} predictions, saved to {cache_path}")
    return cache

if __name__ == "__main__":
    generate_predictions()
