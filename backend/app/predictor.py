"""
PronoGol - AI Predictor
Generates predictions from real FootyStats data.
Uses proper FootyStats field names (competition_id, date_unix, home_name, etc.)
"""
import os, json, time, re
from datetime import datetime, timedelta
import requests

DATA_DIR = os.environ.get("PRONOGOL_DATA_DIR", "/app/data")
FOOTYSTATS_KEY = "1abc780710040e043b218e141869d4b664aac69ed8b97ff98dc96da9ca420f72"
FOOTYSTATS_URL = "https://api.football-data-api.com"
SEASON_IDS = {16494: 16494}  # comp_id: season_id

# League names mapped from competition_id
LEAGUES = {
    16494: "Mundial 2026",
    16718: "Chile Copa Chile",
    16572: "Finland Veikkausliiga",
    17128: "UEFA Champions League - Clasificación",
    17130: "UEFA Conference League - Clasificación",
    16927: "Bolivia - Liga Profesional",
    16783: "Brasil - Serie B",
}

# Team logo CDN
LOGO_CDN = "https://media.api-sports.io/football/teams"

def api_get(endpoint, timeout=10):
    """Call FootyStats API"""
    sep = "&" if "?" in endpoint else "?"
    url = f"{FOOTYSTATS_URL}{endpoint}{sep}key={FOOTYSTATS_KEY}"
    r = requests.get(url, timeout=timeout)
    return r.json()

def load_teams(season_id=16494):
    """Load team rankings from FootyStats for the World Cup."""
    try:
        data = api_get(f"/league-teams?season_id={season_id}")
        if data.get("success", 0) == 1:
            teams = {}
            for t in data.get("data", []):
                tid = t.get("team_id") or t.get("id")
                if tid:
                    teams[tid] = t
                # Also index by name for matching
                name = (t.get("cleanName") or t.get("name") or "").lower().strip()
                if name:
                    teams[name] = t
            return teams
    except Exception as e:
        print(f"Error loading teams: {e}")
    return {}

def resolve_team_info(match, teams_dict):
    """Get team info by trying ID first, then name matching."""
    result = {"name": "", "id": 0, "rank": 30, "risk": 100, "logo": ""}
    
    for side in ["home", "away"]:
        name = match.get(f"{side}_name", "")
        tid = match.get(f"{side}ID") or match.get(f"{side}_id") or 0
        
        # Try by numeric ID first
        info = teams_dict.get(tid, {}) if tid else {}
        if not info:
            # Try by name
            key = name.lower().replace("national team", "").replace(" men", "").strip()
            info = teams_dict.get(key, {})
        
        rank = info.get("performance_rank", 30)
        risk = info.get("risk", 100)
        
        if side == "home":
            result = {
                "name": name,
                "id": tid or info.get("team_id") or info.get("id", 0),
                "rank": rank,
                "risk": risk,
                "logo": f"{LOGO_CDN}/{tid}.png" if tid else "",
            }
        else:
            result_away = {
                "name": name,
                "id": tid or info.get("team_id") or info.get("id", 0),
                "rank": rank,
                "risk": risk,
                "logo": f"{LOGO_CDN}/{tid}.png" if tid else "",
            }
    
    return result, result_away

def get_match_detail(mid):
    """Fetch match stats (xG, H2H, PPG)."""
    try:
        data = api_get(f"/match?match_id={mid}&include=stats", timeout=8)
        if data.get("success", 0) == 1:
            return data.get("data", {})
    except:
        pass
    return {}

def generate_predictions():
    """Main prediction generator."""
    print(f"🤖 PronoGol Predictor running at {datetime.utcnow().isoformat()}")
    
    # Load team rankings
    all_teams = {}
    for comp_id, season_id in SEASON_IDS.items():
        teams = load_teams(season_id)
        all_teams[comp_id] = teams
        print(f"📊 {LEAGUES.get(comp_id, '?')}: loaded {len(teams)} teams")
    
    # Fetch today's matches (include=all gives more fields)
    try:
        data = api_get("/todays-matches?include=all")
        matches = data.get("data", []) if data.get("success", 0) == 1 else []
        print(f"📅 Found {len(matches)} matches today")
    except Exception as e:
        print(f"Error fetching matches: {e}")
        matches = []
    
    predictions = []
    
    for match in matches[:50]:
        comp_id = match.get("competition_id", 0)
        mid = match.get("id", "")
        
        # Resolve team info
        home_name = match.get("home_name", "")
        away_name = match.get("away_name", "")
        home_id = match.get("homeID") or match.get("home_id") or 0
        away_id = match.get("awayID") or match.get("away_id") or 0
        
        team_pool = all_teams.get(comp_id, {})
        
        # Home team
        ht = team_pool.get(home_id, team_pool.get(home_name.lower().strip(), {}))
        if not ht:
            ht = team_pool.get('anything', {})
        
        home_rank = ht.get("performance_rank", 30) if ht else 30
        home_risk = ht.get("risk", 100) if ht else 100
        
        # Away team
        at = team_pool.get(away_id, team_pool.get(away_name.lower().strip(), {}))
        away_rank = at.get("performance_rank", 30) if at else 30
        away_risk = at.get("risk", 100) if at else 100
        
        # Match time
        match_time = match.get("date_unix", 0)
        if not match_time:
            match_time = match.get("date", {}).get("startTimestamp", 0)
        
        # Status & scores
        status = match.get("status", "scheduled")
        scores = match.get("scores", {})
        if isinstance(scores, dict):
            home_score = scores.get("home_score")
            away_score = scores.get("away_score")
        else:
            home_score = None; away_score = None
        
        # League name
        league_name = LEAGUES.get(comp_id, match.get("name", match.get("league_name", "Otra liga")))
        
        # Fetch detail for xG (skip if too many matches to avoid rate limits)
        detail = {}
        if len(matches) <= 25:
            detail = get_match_detail(mid)
        
        xg_home = float(detail.get("team_a_xg_prematch") or detail.get("team_a_xg", 0) or 0)
        xg_away = float(detail.get("team_b_xg_prematch") or detail.get("team_b_xg", 0) or 0)
        if not xg_home and not xg_away:
            xg_home = 1.5 if home_rank <= 15 else 1.2
            xg_away = 1.5 if away_rank <= 15 else 1.0
        
        total_xg = round(xg_home + xg_away, 2)
        
        # ---- Probability calculations ----
        rank_diff = home_rank - away_rank
        
        if rank_diff <= -15:
            home_win_pct = 65; draw_pct = 20; away_win_pct = 15
        elif rank_diff <= -8:
            home_win_pct = 55; draw_pct = 25; away_win_pct = 20
        elif rank_diff <= -3:
            home_win_pct = 48; draw_pct = 28; away_win_pct = 24
        elif rank_diff >= 15:
            away_win_pct = 65; draw_pct = 20; home_win_pct = 15
        elif rank_diff >= 8:
            away_win_pct = 55; draw_pct = 25; home_win_pct = 20
        elif rank_diff >= 3:
            away_win_pct = 48; draw_pct = 28; home_win_pct = 24
        else:
            home_win_pct = 40; draw_pct = 30; away_win_pct = 30
        
        trust_penalty = 0
        if home_win_pct >= 45 and (home_risk > 150 or away_risk > 150):
            trust_penalty = 1
        if away_win_pct >= 45 and (away_risk > 150 or home_risk > 150):
            trust_penalty = 1
        
        # Winner
        if home_win_pct >= 45:
            winner_pred = "1"; winner_trust = max(min(round(home_win_pct / 9), 10) - trust_penalty, 3)
        elif away_win_pct >= 45:
            winner_pred = "2"; winner_trust = max(min(round(away_win_pct / 9), 10) - trust_penalty, 3)
        else:
            winner_pred = "X"; winner_trust = 4
        
        # DC
        if home_win_pct >= 40:
            dc_pred = "1X"; dc_trust = min(round((home_win_pct + draw_pct) / 11), 9)
        elif away_win_pct >= 40:
            dc_pred = "X2"; dc_trust = min(round((away_win_pct + draw_pct) / 11), 9)
        else:
            dc_pred = "12"; dc_trust = 6
        
        # O/U & BTTS
        over_15_pct = max(min(round(50 + (total_xg - 1.5) * 25), 92), 35)
        over_25_pct = max(min(round(50 + (total_xg - 2.5) * 25), 88), 20)
        btts_yes_pct = max(min(round(40 + (total_xg - 2.0) * 20), 80), 30)
        
        # Build prediction object
        pred = {
            "match_id": str(mid),
            "match_time": match_time,
            "league": league_name,
            "league_id": comp_id,
            "home_team": home_name,
            "home_logo": f"{LOGO_CDN}/{home_id}.png",
            "away_team": away_name,
            "away_logo": f"{LOGO_CDN}/{away_id}.png",
            "home_score": home_score,
            "away_score": away_score,
            "status": status,
            "total_xg": total_xg,
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
        
        # Best pick: highest trust >= 6
        best = max(pred["markets"].items(), key=lambda kv: kv[1]["trust"])
        if best[1]["trust"] >= 6:
            pred["best_pick"] = {"market": best[0], "prediction": best[1]["prediction"], "confidence": best[1]["trust"]}
        
        predictions.append(pred)
    
    # Sort: best picks first
    predictions.sort(key=lambda x: x["best_pick"]["confidence"], reverse=True)
    
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
    
    print(f"✅ Generated {len(predictions)} predictions for {len(set(p['league'] for p in predictions))} leagues")
    print(f"📁 Saved to {cache_path}")
    return cache

if __name__ == "__main__":
    generate_predictions()
