"""PronoGol - Backend API v2"""
import os, json, uuid, secrets, hashlib, hmac, time, requests
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="PronoGol API", description="API de pronosticos de futbol con IA", version="2.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

supabase: Client | None = None
DATA_DIR = os.environ.get("PRONOGOL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data"))

# --- Models ---
class GoogleAuth(BaseModel):
    credential: str
    client_id: str

class EmailSignup(BaseModel):
    name: str
    email: str
    password: str
    marketing_opt_in: bool = False

class EmailLogin(BaseModel):
    email: str
    password: str

class UserInfo(BaseModel):
    id: int
    email: str
    name: str
    avatar_url: str
    premium_until: Optional[str] = None
    is_premium: bool = False

# --- Password helpers ---
def _hash_password(password: str) -> tuple:
    salt = secrets.token_hex(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    return salt, pwd_hash

def _verify_password(password: str, salt: str, stored_hash: str) -> bool:
    check = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    return check == stored_hash

def _make_token():
    return secrets.token_urlsafe(48)

def _create_session(user_id: int) -> str:
    token = _make_token()
    sessions_db = _read_db("sessions.json")
    sessions_db["sessions"][token] = {
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
    }
    _write_db("sessions.json", sessions_db)
    return token

def _user_response(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "avatar_url": user.get("avatar_url", ""),
        "is_premium": bool(user.get("premium_until") and user["premium_until"] > datetime.utcnow().isoformat()),
        "premium_until": user.get("premium_until"),
        "marketing_opt_in": user.get("marketing_opt_in", False),
        "role": user.get("role", "user"),
    }

# --- Role helpers ---
ROLES = {"admin": 100, "analyst": 50, "premium": 30, "user": 10}

def _require_role(authorization: Optional[str], min_role: str = "user"):
    """Get current user and check minimum role. Returns user dict or raises 401/403."""
    if not authorization:
        raise HTTPException(status_code=401, detail="No autorizado")
    token = authorization.replace("Bearer ", "")
    sessions_db = _read_db("sessions.json")
    session = sessions_db["sessions"].get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Sesion invalida")
    exp = session.get("expires_at", "")
    if exp < datetime.utcnow().isoformat():
        del sessions_db["sessions"][token]
        _write_db("sessions.json", sessions_db)
        raise HTTPException(status_code=401, detail="Sesion expirada")
    users_db = _read_db("users.json")
    user = users_db["users"].get(str(session["user_id"]))
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    user["id"] = user.get("id", session["user_id"])
    user_role = user.get("role", "user")
    if ROLES.get(user_role, 0) < ROLES.get(min_role, 0):
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return user

def _user_response_full(user: dict) -> dict:
    resp = _user_response(user)
    resp["role"] = user.get("role", "user")
    resp["login_count"] = user.get("login_count", 0)
    resp["created_at"] = user.get("created_at", "")
    resp["auth_method"] = user.get("auth_method", "")
    return resp

# --- File DB helpers ---
def _db_path(name):
    return os.path.join(DATA_DIR, name)

def _read_db(name):
    path = _db_path(name)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)

def _write_db(name, data):
    path = _db_path(name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _gen_token():
    return secrets.token_urlsafe(48)

@app.on_event("startup")
async def startup():
    global supabase
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if url and key:
        supabase = create_client(url, key)
    os.makedirs(DATA_DIR, exist_ok=True)
    # Init DB files
    if not os.path.exists(_db_path("users.json")):
        _write_db("users.json", {"next_id": 1, "users": {}})
    if not os.path.exists(_db_path("sessions.json")):
        _write_db("sessions.json", {"sessions": {}})

# --- Email Auth ---
@app.post("/api/v2/auth/signup")
async def signup(data: EmailSignup):
    """Register with email + password."""
    if len(data.email) < 5 or "@" not in data.email:
        raise HTTPException(status_code=400, detail="Email invalido")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Contrasena muy corta (min 6)")
    
    db = _read_db("users.json")
    users = db["users"]
    
    # Check duplicate email
    for u in users.values():
        if u.get("email") == data.email:
            raise HTTPException(status_code=409, detail="Email ya registrado")
    
    uid = db["next_id"]
    db["next_id"] = uid + 1
    salt, pwd_hash = _hash_password(data.password)
    
    user = {
        "id": uid,
        "email": data.email,
        "name": data.name or data.email.split("@")[0],
        "avatar_url": "",
        "password_salt": salt,
        "password_hash": pwd_hash,
        "auth_method": "email",
        "marketing_opt_in": data.marketing_opt_in,
        "signup_ip": "",
        "last_login": datetime.utcnow().isoformat(),
        "login_count": 1,
        "premium_until": None,
        "created_at": datetime.utcnow().isoformat(),
    }
    users[str(uid)] = user
    _write_db("users.json", db)
    
    token = _create_session(uid)
    user["id"] = uid
    return {"token": token, "user": _user_response(user)}

@app.post("/api/v2/auth/login")
async def login(data: EmailLogin):
    """Login with email + password."""
    db = _read_db("users.json")
    users = db["users"]
    
    found = None
    for uid, u in users.items():
        if u.get("email") == data.email:
            found = u
            found["id"] = int(uid)
            break
    
    if not found:
        raise HTTPException(status_code=401, detail="Email no registrado")
    
    salt = found.get("password_salt", "")
    stored = found.get("password_hash", "")
    if not salt or not stored or not _verify_password(data.password, salt, stored):
        raise HTTPException(status_code=401, detail="Contrasena incorrecta")
    
    # Update login stats
    found["last_login"] = datetime.utcnow().isoformat()
    found["login_count"] = found.get("login_count", 0) + 1
    db["users"][str(found["id"])] = found
    _write_db("users.json", db)
    
    token = _create_session(found["id"])
    return {"token": token, "user": _user_response(found)}

# --- Google Auth ---
def _verify_google_token(credential: str, client_id: str) -> Optional[dict]:
    """Verify Google ID token and return user info."""
    try:
        # Use Python's stdlib to decode JWT without external lib
        # JWT is 3 base64 parts separated by dots
        parts = credential.split(".")
        if len(parts) != 3:
            return None
        # Decode payload
        payload_b64 = parts[1]
        # Add padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        import base64
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        
        # Verify audience
        if payload.get("aud") != client_id:
            return None
        # Check expiry
        if payload.get("exp", 0) < time.time():
            return None
        
        return {
            "sub": payload.get("sub", ""),
            "email": payload.get("email", ""),
            "name": payload.get("name", ""),
            "picture": payload.get("picture", ""),
        }
    except Exception as e:
        print(f"Token verify error: {e}")
        return None

@app.post("/api/v2/auth/google")
async def auth_google(data: GoogleAuth):
    """Login or register with Google credential."""
    info = _verify_google_token(data.credential, data.client_id)
    if not info:
        raise HTTPException(status_code=401, detail="Token invalido")
    
    db = _read_db("users.json")
    users = db["users"]
    
    # Find existing user by google_id
    user = None
    for uid, u in users.items():
        if u.get("google_id") == info["sub"]:
            user = u
            user["id"] = int(uid)
            break
    
    # Or by email
    if not user:
        for uid, u in users.items():
            if u.get("email") == info["email"]:
                user = u
                user["id"] = int(uid)
                user["google_id"] = info["sub"]
                break
    
    # Create new user
    if not user:
        uid = db["next_id"]
        db["next_id"] = uid + 1
        user = {
            "id": uid,
            "email": info["email"],
            "name": info["name"],
            "avatar_url": info["picture"],
            "google_id": info["sub"],
            "premium_until": None,
            "role": "user",
            "created_at": datetime.utcnow().isoformat(),
            "marketing_opt_in": True,
            "login_count": 1,
        }
        users[str(uid)] = user
        _write_db("users.json", db)
    
    # Update name/avatar if changed
    if user["name"] != info["name"] or user["avatar_url"] != info["picture"]:
        users[str(user["id"])]["name"] = info["name"]
        users[str(user["id"])]["avatar_url"] = info["picture"]
        _write_db("users.json", db)
    
    # Create session
    token = _create_session(user["id"])
    return {"token": token, "user": _user_response(user)}

@app.get("/api/v2/auth/me")
async def get_me(authorization: Optional[str] = Header(None)):
    """Get current user from session token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="No autorizado")
    
    token = authorization.replace("Bearer ", "")
    sessions_db = _read_db("sessions.json")
    session = sessions_db["sessions"].get(token)
    
    if not session:
        raise HTTPException(status_code=401, detail="Sesion invalida")
    
    # Check expiry
    exp = session.get("expires_at", "")
    if exp < datetime.utcnow().isoformat():
        del sessions_db["sessions"][token]
        _write_db("sessions.json", sessions_db)
        raise HTTPException(status_code=401, detail="Sesion expirada")
    
    users_db = _read_db("users.json")
    user = users_db["users"].get(str(session["user_id"]))
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    
    user["id"] = user.get("id", session["user_id"])
    return {"user": _user_response(user)}

@app.post("/api/v2/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if not authorization:
        return {"ok": True}
    token = authorization.replace("Bearer ", "")
    sessions_db = _read_db("sessions.json")
    if token in sessions_db["sessions"]:
        del sessions_db["sessions"][token]
        _write_db("sessions.json", sessions_db)
    return {"ok": True}

@app.get("/api/v2/premium/status")
async def premium_status():
    """Get premium pricing info."""
    return {
        "tiers": [
            {
                "id": "free",
                "name": "Gratis",
                "price": 0,
                "features": ["Ver resultados del dia", "Estadisticas basicas", "3 pronosticos/semana"],
            },
            {
                "id": "premium_monthly",
                "name": "Premium Mensual",
                "price": 15000,
                "currency": "COP",
                "features": [
                    "Todos los partidos",
                    "Pronosticos IA ilimitados",
                    "Alertas en tiempo real",
                    "Estadisticas avanzadas",
                    "Sin anuncios",
                    "Acceso a historial",
                ],
            },
            {
                "id": "premium_yearly",
                "name": "Premium Anual",
                "price": 120000,
                "currency": "COP",
                "features": [
                    "Todo de Premium Mensual",
                    "2 meses gratis",
                    "Soporte prioritario",
                    "Acceso a beta features",
                ],
            },
        ]
    }

# --- Admin Endpoints (role: admin required) ---

@app.get("/api/v2/admin/users")
async def admin_list_users(authorization: Optional[str] = Header(None)):
    """Admin: List all users with their data."""
    admin = _require_role(authorization, "admin")
    db = _read_db("users.json")
    users_list = []
    for uid, u in db["users"].items():
        u["id"] = int(uid)
        # Remove sensitive fields
        u.pop("password_salt", None)
        u.pop("password_hash", None)
        users_list.append(_user_response_full(u))
    users_list.sort(key=lambda x: x["id"])
    return {"users": users_list, "count": len(users_list)}


@app.post("/api/v2/admin/users/{user_id}/role")
async def admin_update_role(user_id: int, role_data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Update user role (admin/analyst/premium/user)."""
    admin = _require_role(authorization, "admin")
    new_role = role_data.get("role", "")
    if new_role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Rol invalido: {new_role}. Roles: {', '.join(ROLES.keys())}")
    db = _read_db("users.json")
    user = db["users"].get(str(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user["role"] = new_role
    db["users"][str(user_id)] = user
    _write_db("users.json", db)
    user["id"] = user_id
    return {"ok": True, "user": _user_response_full(user)}


@app.post("/api/v2/admin/users/{user_id}/premium")
async def admin_set_premium(user_id: int, premium_data: dict, authorization: Optional[str] = Header(None)):
    """Admin: Set premium until date. Send {"days": 30} or {"until": "2099-12-31"}"""
    admin = _require_role(authorization, "admin")
    db = _read_db("users.json")
    user = db["users"].get(str(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    days = premium_data.get("days")
    until = premium_data.get("until")
    if days:
        premium_until = (datetime.utcnow() + timedelta(days=int(days))).isoformat()
    elif until:
        premium_until = until
    else:
        premium_until = (datetime.utcnow() + timedelta(days=30)).isoformat()
    user["premium_until"] = premium_until
    db["users"][str(user_id)] = user
    _write_db("users.json", db)
    user["id"] = user_id
    return {"ok": True, "user": _user_response_full(user)}


@app.get("/api/v2/admin/marketing-emails")
async def admin_marketing_emails(authorization: Optional[str] = Header(None)):
    """Admin: Get list of marketing-opt-in emails for campaigns."""
    admin = _require_role(authorization, "admin")
    db = _read_db("users.json")
    emails = []
    for u in db["users"].values():
        if u.get("marketing_opt_in", True):
            emails.append({
                "email": u["email"],
                "name": u.get("name", ""),
                "is_premium": bool(u.get("premium_until") and u["premium_until"] > datetime.utcnow().isoformat()),
                "role": u.get("role", "user"),
                "signup_date": u.get("created_at", "")[:10],
            })
    return {"emails": emails, "count": len(emails)}


@app.get("/api/v2/admin/stats")
async def admin_stats(authorization: Optional[str] = Header(None)):
    """Admin: Get platform statistics."""
    admin = _require_role(authorization, "admin")
    db = _read_db("users.json")
    sessions_db = _read_db("sessions.json")
    users = db.get("users", {})
    total = len(users)
    premium = sum(1 for u in users.values() if u.get("premium_until") and u["premium_until"] > datetime.utcnow().isoformat())
    active_sessions = sum(1 for s in sessions_db.get("sessions", {}).values() if s.get("expires_at", "") > datetime.utcnow().isoformat())
    roles = {}
    for u in users.values():
        r = u.get("role", "user")
        roles[r] = roles.get(r, 0) + 1
    return {
        "total_users": total,
        "premium_users": premium,
        "active_sessions": active_sessions,
        "users_by_role": roles,
    }


# --- Prediction Endpoints ---

PREDICTION_MARKETS = [
    {"id": "match_winner", "name": "Ganador", "options": ["1", "X", "2"]},
    {"id": "double_chance", "name": "Doble Oportunidad", "options": ["1X", "12", "X2"]},
    {"id": "btts", "name": "Ambos Anotan", "options": ["Si", "No"]},
    {"id": "over_under_1.5", "name": "Más/Menos 1.5", "options": [">1.5", "<1.5"]},
    {"id": "over_under_2.5", "name": "Más/Menos 2.5", "options": [">2.5", "<2.5"]},
    {"id": "over_under_3.5", "name": "Más/Menos 3.5", "options": [">3.5", "<3.5"]},
]

@app.get("/api/v2/predictions/markets")
async def get_prediction_markets():
    return {"markets": PREDICTION_MARKETS}


@app.get("/api/v2/predictions/today")
async def predictions_today(date: Optional[str] = None, market: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Get predictions for today's matches."""
    user = None
    if authorization:
        try:
            user = _require_role(authorization, "user")
        except:
            pass
    
    is_premium = user and bool(user.get("premium_until") and user["premium_until"] > datetime.utcnow().isoformat())
    
    # Mock predictions - in production these come from FootyStats + AI
    # This will be replaced with real data from the auto_combo_v3.py system
    
    today = date or datetime.utcnow().strftime("%Y-%m-%d")
    
    # Load from FootyStats cache if available
    predictions_file = os.path.join(DATA_DIR, "predictions_cache.json")
    if os.path.exists(predictions_file):
        with open(predictions_file, encoding='utf-8') as f:
            cache = json.load(f)
        return cache
    
    return {
        "date": today,
        "predictions": [],
        "message": "No hay predicciones cacheadas. Ejecuta el script de predicciones primero."
    }


@app.post("/api/v2/predictions/generate")
async def generate_predictions_now(authorization: Optional[str] = Header(None)):
    """Admin: Generate predictions now."""
    admin = _require_role(authorization, "admin")
    try:
        from app.predictor import generate_predictions
        result = generate_predictions()
        return {"ok": True, "message": f"Predicciones generadas: {result['count']} partidos", "count": result["count"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando predicciones: {str(e)}")

# Serve frontend static files
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "apps", "web")

@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"app": "PronoGol", "version": "2.0.0", "status": "ok"}

@app.get("/health")
async def health():
    db_ok = supabase is not None
    return {"status": "healthy" if db_ok else "degraded", "supabase": "connected" if db_ok else "not configured"}

@app.get("/api/v1/leagues")
async def get_leagues():
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    data = supabase.table("leagues").select("*").execute()
    return {"leagues": data.data if data else []}

@app.get("/api/v1/matches")
async def get_matches(league_id: Optional[int] = None, limit: int = 50, date: Optional[str] = None):
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    query = supabase.table("matches").select(
        "*, home_team:teams!home_team_id(name), away_team:teams!away_team_id(name)"
    ).order("match_date_utc").limit(limit)
    if league_id:
        query = query.eq("league_id", league_id)
    if date:
        query = query.gte("match_date_utc", date).lt("match_date_utc", date.replace("T", "T23:59:59"))
    data = query.execute()
    rows = []
    for m in (data.data or []):
        ht, at = m.get("home_team"), m.get("away_team")
        if isinstance(ht, list) and ht: m["home_team_name"] = ht[0]["name"]
        elif isinstance(ht, dict): m["home_team_name"] = ht.get("name", "")
        if isinstance(at, list) and at: m["away_team_name"] = at[0]["name"]
        elif isinstance(at, dict): m["away_team_name"] = at.get("name", "")
        rows.append(m)
    return {"matches": rows, "count": len(rows)}

@app.get("/api/v1/predictions")
async def get_predictions(limit: int = 10):
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    data = supabase.table("predictions").select(
        "id, match_id, market, predicted_value, probability, model_version, created_at"
    ).order("created_at", desc=True).limit(limit).execute()
    return {"predictions": data.data if data else []}

@app.get("/api/v2/matches/calendar")
async def matches_calendar():
    """Get dates that have matches for the calendar."""
    if not supabase:
        return {"dates": []}
    data = supabase.table("matches").select("match_date_utc").execute()
    dates = sorted(set(d[:10] for d in (m.get("match_date_utc", "") for m in (data.data or [])) if d[:10]))
    return {"dates": dates}
