"""PronoGol - Backend API v2"""
import os, json, uuid, secrets, hashlib, hmac, time, requests, smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from typing import Optional
import time
from collections import defaultdict
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
import time
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="PronoGol API", description="API de pronosticos de futbol con IA", version="2.0.0")
# ======================== RATE LIMITING ========================
class RateLimiter:
    """Simple in-memory rate limiter."""
    def __init__(self):
        self.requests = defaultdict(list)
    
    def is_allowed(self, key: str, max_requests: int = 60, window_seconds: int = 60) -> bool:
        now = time.time()
        window_start = now - window_seconds
        # Clean old entries
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        if len(self.requests[key]) >= max_requests:
            return False
        self.requests[key].append(now)
        return True

rate_limiter = RateLimiter()

# ===================== SECURITY HEADERS =======================
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
}

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Skip rate limiting for static files and health check
    path = request.url.path
    if path in ("/health", "/", "/favicon.ico") or path.startswith("/static/"):
        return await call_next(request)
    
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    
    # Different limits for different endpoints
    if path.startswith("/api/v2/predictions"):
        max_req = 100  # 100 req/min for predictions
    elif path.startswith("/api/v2/auth"):
        max_req = 20   # 20 req/min for auth
    elif path.startswith("/api/v2/admin"):
        max_req = 30   # 30 req/min for admin
    else:
        max_req = 60   # 60 req/min default
    
    if not rate_limiter.is_allowed(client_ip, max_requests=max_req, window_seconds=60):
        return JSONResponse(
            status_code=429,
            content={"detail": "Demasiadas solicitudes. Intenta de nuevo en 60 segundos."},
            headers={"Retry-After": "60", "X-RateLimit-Limit": str(max_req)},
        )
    
    # Add cache headers for predictions
    response = await call_next(request)
    if path.startswith("/api/v2/predictions"):
        response.headers["Cache-Control"] = "public, max-age=300, s-maxage=300"
        response.headers["X-Cache-TTL"] = "300"
    elif path.startswith("/api/v2/matches"):
        response.headers["Cache-Control"] = "public, max-age=600, s-maxage=600"
    elif path.startswith("/api/v2/auth/me"):
        response.headers["Cache-Control"] = "private, no-cache"
    
    return response

# ==================== REQUEST LOGGING =========================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    print(f"[{start:.0f}] {request.method} {request.url.path} -> {response.status_code} ({elapsed:.2f}s)")
    return response


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

supabase: Client | None = None
DATA_DIR = os.environ.get("PRONOGOL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data"))

# --- SMTP Email Config ---
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.hostinger.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "bienvenida@pronogol.app")
SMTP_PASS = os.environ.get("SMTP_PASS", "@2013zX08dani@")
SMTP_FROM = os.environ.get("SMTP_FROM", "PronoGol <bienvenida@pronogol.app>")

def send_welcome_email(to_email: str, user_name: str):
    """Send welcome email to newly registered user."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Bienvenido a PronoGol!"
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        
        # Plain text version
        text = f"""Hola {user_name}!

Bienvenido a PronoGol 🎯

Te has registrado exitosamente en nuestra plataforma de analisis estadistico y pronosticos deportivos.

Que te ofrece PronoGol?
• Pronosticos generados por inteligencia artificial basados en datos historicos
• Analisis detallado de partidos de futbol
• Estadisticas y tendencias actualizadas

Importante: PronoGol es una herramienta informativa y de entretenimiento.
No somos una casa de apuestas ni recomendamos apostar.

Gracias por confiar en nosotros!

El equipo de PronoGol
https://pronogol.app"""

        # HTML version
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0b0b1a;font-family:'Inter',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0b0b1a;padding:30px 15px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#111128;border-radius:16px;border:1px solid rgba(45,215,191,0.15)">
<tr><td style="padding:40px 30px 30px;text-align:center">
<h1 style="margin:0;font-size:28px;font-weight:800;background:linear-gradient(135deg,#00ff87,#60efff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">⚽ PronoGol</h1>
<p style="color:#5a6380;font-size:14px;margin:8px 0 0">Analisis deportivo con IA</p>
</td></tr>
<tr><td style="padding:0 30px 20px;text-align:center">
<h2 style="color:#e8e8f0;font-size:22px;margin:0 0 10px">Bienvenido, {user_name}! 🎯</h2>
<p style="color:#c8c8e0;font-size:15px;line-height:1.6;margin:0 0 20px">Te has registrado exitosamente en PronoGol. Ahora puedes acceder a pronosticos generados por inteligencia artificial, analisis detallados de partidos y estadisticas actualizadas.</p>
</td></tr>
<tr><td style="padding:0 30px 20px">
<table width="100%" cellpadding="15" cellspacing="0" style="background:rgba(45,215,191,0.06);border-radius:12px;border:1px solid rgba(45,215,191,0.1)">
<tr><td>
<p style="color:#2dd4bf;font-size:14px;font-weight:700;margin:0 0 8px">Que encontraras en PronoGol?</p>
<p style="color:#c8c8e0;font-size:13px;line-height:1.5;margin:0">🤖 Pronosticos con IA basados en datos historicos<br>📊 Analisis estadistico de cada partido<br>📈 Tendencias y estadisticas actualizadas<br>⚽ Cobertura del Mundial 2026 y mas ligas</p>
</td></tr>
</table>
</td></tr>
<tr><td style="padding:0 30px 20px;text-align:center">
<a href="https://pronogol.app" style="display:inline-block;padding:14px 40px;background:linear-gradient(135deg,#2dd4bf,#22d3ee);color:#0a0e1a;text-decoration:none;border-radius:12px;font-size:15px;font-weight:700">Ir a PronoGol</a>
</td></tr>
<tr><td style="padding:0 30px 30px">
<p style="color:#5a6380;font-size:11px;line-height:1.5;margin:0;text-align:center">
PronoGol es una herramienta de contenido informativo y analisis deportivo.<br>
No somos una casa de apuestas. No recomendamos apostar. Prohibido para menores de 18 anos.<br><br>
<a href="https://pronogol.app/terminos.html" style="color:#2dd4bf;text-decoration:none">Terminos</a> ·
<a href="https://pronogol.app/privacidad.html" style="color:#2dd4bf;text-decoration:none">Privacidad</a> ·
<a href="https://pronogol.app/habeas-data.html" style="color:#2dd4bf;text-decoration:none">Habeas Data</a>
</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [to_email], msg.as_string())
        server.quit()

        print(f"WELCOME EMAIL SENT to {to_email}")
        return True
    except Exception as e:
        print(f"WELCOME EMAIL FAILED for {to_email}: {e}")
        return False

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


class RegisterRequest(BaseModel):
    email: str
    name: str
    phone: str = ""
    age_confirmed: bool = False
    terms_accepted: bool = False


class ProfileUpdate(BaseModel):
    phone: str = ""
    city: str = ""
    birth_date: str = ""

class ForgotPasswordRequest(BaseModel):
    email: str

class ChangePasswordRequest(BaseModel):
    current_password: str = ""
    new_password: str = ""

class UserInfo(BaseModel):
    id: int
    email: str
    name: str
    avatar_url: str
    premium_until: Optional[str] = None
    is_premium: bool = False

# --- Password helpers ---
def send_reset_email(to_email, user_name, reset_link):
    """Send password reset email."""
    try:
        import smtplib
        from email.mime.text import MIMEText
        html_body = '<!DOCTYPE html>\n<html><head><meta charset="UTF-8"><style>\nbody{font-family:Arial,sans-serif;background:#0a0e1a;color:#e0e0e0;margin:0;padding:0}\n.container{max-width:600px;margin:auto;padding:20px}\n.header{text-align:center;padding:30px 0}\n.header h1{color:#00e5a0;font-size:28px;margin:0}\n.content{background:#12162a;border-radius:12px;padding:30px;border:1px solid #1e2740}\n.reset-btn{display:inline-block;padding:14px 32px;margin:20px 0;\n  background:linear-gradient(135deg,#00e5a0,#00c4f4);color:#0a0e1a;\n  text-decoration:none;border-radius:8px;font-weight:700;font-size:16px}\n.footer{text-align:center;padding:20px;color:#666;font-size:12px}\n</style></head><body>\n<div class="container">\n<div class="header"><h1>PronoGol</h1></div>\n<div class="content">\n<h2>Hola NAME_PLACEHOLDER,</h2>\n<p>Recibimos una solicitud para restablecer tu contraseña.</p>\n<p>Haz clic en el botón de abajo para crear una nueva contraseña. Este enlace expira en 1 hora.</p>\n<div style="text-align:center">\n<a href="LINK_PLACEHOLDER" class="reset-btn">Restablecer Contraseña</a>\n</div>\n<p style="margin-top:20px;font-size:13px;color:#999">Si no solicitaste esto, ignora este correo.</p>\n</div>\n<div class="footer">\n<p>PronoGol - Pronósticos deportivos con IA</p>\n<p><a href="https://pronogol.app" style="color:#00e5a0">pronogol.app</a></p>\n</div>\n</div></body></html>'
        html_body = html_body.replace("NAME_PLACEHOLDER", user_name).replace("LINK_PLACEHOLDER", reset_link)
        msg = MIMEText(html_body, 'html')
        msg['Subject'] = 'Restablece tu contrasena - PronoGol'
        msg['From'] = 'bienvenida@pronogol.app'
        msg['To'] = to_email
        import ssl
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with smtplib.SMTP('smtp.hostinger.com', 587, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login('bienvenida@pronogol.app', '@2013zX08dani@')
            server.send_message(msg)
    except Exception as e:
        import logging
        logging.error(f"Reset email send failed: {e}")

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

def _ensure_predictions_cache():
    """Download predictions from GitHub if cache is missing."""
    cache_path = os.path.join(DATA_DIR, "predictions_cache.json")
    if os.path.exists(cache_path):
        print(f"Predictions cache already exists at {cache_path}")
        return True
    
    urls = [
        "https://raw.githubusercontent.com/johnjairod1986/pronogol/master/data/predictions_cache.json",
        "https://raw.githubusercontent.com/johnjairod1986/pronogol/main/data/predictions_cache.json",
    ]
    for url in urls:
        try:
            print(f"Downloading predictions from {url}...")
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("predictions"):
                    os.makedirs(DATA_DIR, exist_ok=True)
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"Downloaded {len(data['predictions'])} predictions from GitHub!")
                    return True
        except Exception as e:
            print(f"GitHub download failed: {e}")
    
    # Try auto-generate as last resort
    try:
        print("Trying to auto-generate predictions...")
        from app.predictor import generate_predictions
        result = generate_predictions()
        print(f"Auto-generated {len(result.get('predictions', []))} predictions!")
        return True
    except Exception as e:
        print(f"Auto-generation failed: {e}")
    
    print("WARNING: Could not load or generate predictions!")
    return False

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
    # Ensure predictions cache
    _ensure_predictions_cache()

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
    return {"ok": True, "token": token, "user": _user_response(user)}

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
    return {"ok": True, "token": token, "user": _user_response(found)}



# --- Email-only Register (free, no password) ---
@app.post("/api/v2/auth/register")
async def email_register(data: RegisterRequest):
    """Register a new user with just email (no password)."""
    if not data.email or "@" not in data.email or "." not in data.email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Email invalido")
    if not data.name or len(data.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    if not data.age_confirmed:
        raise HTTPException(status_code=400, detail="Debes confirmar que eres mayor de 18 anos")
    if not data.terms_accepted:
        raise HTTPException(status_code=400, detail="Debes aceptar los terminos y condiciones")
    
    db = _read_db("users.json")
    users = db["users"]
    
    for uid, u in users.items():
        if u.get("email") == data.email.strip().lower():
            raise HTTPException(status_code=409, detail="Este email ya esta registrado")
    
    uid = db["next_id"]
    db["next_id"] = uid + 1
    
    user = {
        "id": uid,
        "email": data.email.strip().lower(),
        "name": data.name.strip(),
        "phone": data.phone.strip() if data.phone else "",
        "age_confirmed": True,
        "terms_accepted": True,
        "auth_method": "email_only",
        "role": "user",
        "premium_until": None,
        "created_at": datetime.utcnow().isoformat(),
        "ip": "",
    }
    users[str(uid)] = user
    _write_db("users.json", db)
    
    print("NEW REGISTRATION:", user.get("name",""), "<" + user.get("email","") + ">", "phone:", user.get("phone",""))
    
    # Send welcome email (synchronous)
    try:
        send_welcome_email(user["email"], user.get("name", ""))
    except Exception:
        pass
    
    return {"ok": True, "user_id": uid, "email": user["email"]}# --- Google Auth ---
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
    return {"ok": True, "token": token, "user": _user_response(user)}

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

# --- User Profile ---
@app.get("/api/v2/user/profile")
async def get_user_profile(authorization: Optional[str] = Header(None)):
    """Get authenticated user profile with optional fields."""
    user = _require_role(authorization)
    db = _read_db("users.json")
    uid = str(user["id"])
    u = db["users"].get(uid, {})
    return {
        "id": user["id"],
        "email": u.get("email", ""),
        "name": u.get("name", ""),
        "phone": u.get("phone", ""),
        "city": u.get("city", ""),
        "birth_date": u.get("birth_date", ""),
        "auth_method": u.get("auth_method", "email"),
        "role": u.get("role", "user"),
        "created_at": u.get("created_at", ""),
    }

@app.put("/api/v2/user/profile")
async def update_user_profile(data: ProfileUpdate, authorization: Optional[str] = Header(None)):
    """Update user profile fields."""
    user = _require_role(authorization)
    db = _read_db("users.json")
    uid = str(user["id"])
    if uid not in db["users"]:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    for key in ("phone", "city", "birth_date"):
        val = getattr(data, key, "")
        if val:
            db["users"][uid][key] = val.strip()
    _write_db("users.json", db)
    return {"ok": True}

# --- Forgot Password ---
@app.post("/api/v2/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    """Send password reset email if user exists."""
    db = _read_db("users.json")
    for uid, u in db["users"].items():
        if u.get("email", "").lower() == data.email.strip().lower():

            # Generate reset token
            reset_token = _make_token()
            db["users"][uid]["reset_token"] = reset_token
            db["users"][uid]["reset_expires"] = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            _write_db("users.json", db)
            try:
                reset_link = f"https://pronogol.app/reset-password?token={reset_token}"
                send_reset_email(data.email, u.get("name", "Usuario"), reset_link)
            except Exception as e:
                import logging
                logging.error(f"Failed to send reset email to {data.email}: {e}")
            found = True

            break
    else:
        found = False
        print(f"FORGOT DEBUG: found=False (no match)")  # DEBUG
    # Return token so frontend can show password fields immediately
    if found:
        return {"ok": True, "reset_token": reset_token}
    return {"ok": True}

# --- Change Password (authenticated) ---
@app.post("/api/v2/auth/change-password")
async def change_password(data: ChangePasswordRequest, authorization: Optional[str] = Header(None)):
    """Change password for authenticated user."""
    user = _require_role(authorization)
    db = _read_db("users.json")
    uid = str(user["id"])
    u = db["users"].get(uid, {})
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # If user has existing password, verify current
    if u.get("password_salt") and u.get("password_hash"):
        if not data.current_password:
            raise HTTPException(status_code=400, detail="Debes proporcionar tu contraseña actual")
        if not _verify_password(data.current_password, u["password_salt"], u["password_hash"]):
            raise HTTPException(status_code=401, detail="Contraseña actual incorrecta")
    
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 6 caracteres")
    
    salt, pwd_hash = _hash_password(data.new_password)
    db["users"][uid]["password_salt"] = salt
    db["users"][uid]["password_hash"] = pwd_hash
    _write_db("users.json", db)
    return {"ok": True}


@app.post("/api/v2/auth/reset-password")
async def reset_password(data: dict):
    """Reset password using reset token (from email link)."""
    token = data.get("token", "")
    new_password = data.get("new_password", "")
    
    if not token or len(token) < 10:
        raise HTTPException(status_code=400, detail="Token invalido")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="La contrasena debe tener al menos 6 caracteres")
    
    db = _read_db("users.json")
    found_uid = None
    for uid, u in db["users"].items():
        if u.get("reset_token") == token:
            expires = u.get("reset_expires", "")
            if expires:
                try:
                    exp = datetime.fromisoformat(expires)
                    if exp < datetime.utcnow():
                        raise HTTPException(status_code=400, detail="El token ha expirado. Solicita un nuevo restablecimiento.")
                except:
                    pass
            found_uid = uid
            break
    
    if not found_uid:
        raise HTTPException(status_code=400, detail="Token invalido o ya utilizado")
    
    salt, pwd_hash = _hash_password(new_password)
    db["users"][found_uid]["password_salt"] = salt
    db["users"][found_uid]["password_hash"] = pwd_hash
    db["users"][found_uid].pop("reset_token", None)
    db["users"][found_uid].pop("reset_expires", None)
    _write_db("users.json", db)
    
    return {"ok": True, "message": "Contrasena restablecida exitosamente"}

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

@app.post("/api/v2/predictions/upload")
async def upload_predictions(data: dict):
    """Upload predictions data directly (requires secret key)."""
    upload_key = data.get("key", "")
    expected = os.getenv("PRONOGOL_UPLOAD_KEY", "clawbot2026")
    if upload_key != expected:
        raise HTTPException(status_code=403, detail="Invalid upload key")
    
    predictions = data.get("predictions", [])
    if not predictions:
        raise HTTPException(status_code=400, detail="No predictions data")
    
    cache = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dates": {},
        "predictions": predictions,
        "count": len(predictions),
        "total_matches_fetched": data.get("total_matches_fetched", len(predictions)),
    }
    
    # Build dates index
    for p in predictions:
        d = p.get("date", "")
        if d:
            if d not in cache["dates"]:
                cache["dates"][d] = {"count": 0, "leagues": []}
            cache["dates"][d]["count"] += 1
            if p.get("league", "") not in cache["dates"][d]["leagues"]:
                cache["dates"][d]["leagues"].append(p["league"])
    
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, "predictions_cache.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    print(f"Uploaded {len(predictions)} predictions to cache!")
    return {"ok": True, "count": len(predictions)}

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


# ======================== PREDICTION RESULTS ========================
@app.get("/api/v2/predictions/results")
async def predictions_results(date: Optional[str] = None):
    """Verify results of past predictions.
    For each prediction where match_time has passed, check with API-Football.
    Returns win/loss/pending for each prediction.
    """
    today = date or datetime.utcnow().strftime("%Y-%m-%d")
    
    # Load predictions
    predictions_file = os.path.join(DATA_DIR, "predictions_cache.json")
    if not os.path.exists(predictions_file):
        return {"date": today, "predictions": [], "message": "No hay predicciones cacheadas"}
    
    with open(predictions_file, encoding='utf-8') as f:
        cache = json.load(f)
    
    all_predictions = cache.get("predictions", [])
    
    # Filter by date if specified
    if date:
        preds_for_date = [p for p in all_predictions if p.get("date") == date]
    else:
        preds_for_date = all_predictions
    
    bogota_tz = timezone(timedelta(hours=-5))
    now_ts = int(datetime.now(bogota_tz).timestamp())
    
    # Load results cache
    results_cache_path = os.path.join(DATA_DIR, "results_cache.json")
    results_cache = {}
    if os.path.exists(results_cache_path):
        try:
            with open(results_cache_path, encoding='utf-8') as f:
                results_cache = json.load(f)
        except:
            results_cache = {}
    
    results = []
    predictions_to_check = [p for p in preds_for_date if p.get("match_time", 0) <= now_ts]
    predictions_to_skip = [p for p in preds_for_date if p.get("match_time", 0) > now_ts]
    
    # Skip fixtures that haven't started yet
    for p in predictions_to_skip:
        mid = str(p.get("match_id", ""))
        results.append({
            "match_id": mid,
            "home_team": p.get("home_team", ""),
            "away_team": p.get("away_team", ""),
            "match_time": p.get("match_time", 0),
            "date": p.get("date", ""),
            "league": p.get("league", ""),
            "status": "scheduled",
            "markets": p.get("markets", {}),
            "best_pick": p.get("best_pick", {}),
            "home_score": None,
            "away_score": None,
            "results": {k: "pending" for k in p.get("markets", {})},
            "result": "pending"
        })
    
    # Check each finished fixture
    changed = False
    for p in predictions_to_check:
        mid = str(p.get("match_id", ""))
        
        # Check if already cached
        cached = results_cache.get(mid)
        if cached and cached.get("api_result") == "done":
            results.append(cached.get("data", {}))
            continue
        
        # Call API-Football to get fixture data
        try:
            api_key = os.environ.get("API_FOOTBALL_KEY", "b79676c9916a6b82de0f91fe3aceb46d")
            api_url = "https://v3.football.api-sports.io"
            headers = {"x-apisports-key": api_key}
            r = requests.get(f"{api_url}/fixtures?id={mid}", headers=headers, timeout=10)
            data = r.json()
            
            fixture_data = None
            for resp in data.get("response", []):
                fixture_data = resp
                break
            
            if fixture_data:
                goals = fixture_data.get("goals", {})
                home_score = goals.get("home")
                away_score = goals.get("away")
                status_long = fixture_data.get("fixture", {}).get("status", {}).get("long", "scheduled")
                status_short = fixture_data.get("fixture", {}).get("status", {}).get("short", "")
                
                # Check if match is finished
                is_finished = status_short in ("FT", "AET", "PEN", "AWD", "WO")
                
                if is_finished or (status_long == "Match Finished"):
                    markets_results = {}
                    home_score = int(home_score) if home_score is not None else 0
                    away_score = int(away_score) if away_score is not None else 0
                    total_goals = home_score + away_score
                    
                    for mkt_name, mkt_data in p.get("markets", {}).items():
                        pred_val = mkt_data.get("prediction", "")
                        if not pred_val:
                            markets_results[mkt_name] = "pending"
                            continue
                        
                        if mkt_name == "match_winner":
                            if home_score > away_score:
                                actual = "1"
                            elif home_score == away_score:
                                actual = "X"
                            else:
                                actual = "2"
                            markets_results[mkt_name] = "win" if pred_val == actual else "loss"
                            
                        elif mkt_name == "double_chance":
                            if home_score > away_score:
                                actual = "1"
                            elif home_score == away_score:
                                actual = "X"
                            else:
                                actual = "2"
                            if pred_val == "1X":
                                markets_results[mkt_name] = "win" if actual in ("1", "X") else "loss"
                            elif pred_val == "12":
                                markets_results[mkt_name] = "win" if actual in ("1", "2") else "loss"
                            elif pred_val == "X2":
                                markets_results[mkt_name] = "win" if actual in ("X", "2") else "loss"
                            else:
                                markets_results[mkt_name] = "pending"
                                
                        elif mkt_name == "btts":
                            both_scored = home_score > 0 and away_score > 0
                            if pred_val == "Si":
                                markets_results[mkt_name] = "win" if both_scored else "loss"
                            elif pred_val == "No":
                                markets_results[mkt_name] = "win" if not both_scored else "loss"
                            else:
                                markets_results[mkt_name] = "pending"
                                
                        elif mkt_name in ("over_under_1.5", "over_under_2.5"):
                            threshold = 1.5 if mkt_name == "over_under_1.5" else 2.5
                            if pred_val.startswith(">"):
                                markets_results[mkt_name] = "win" if total_goals > threshold else "loss"
                            elif pred_val.startswith("<"):
                                markets_results[mkt_name] = "win" if total_goals < threshold else "loss"
                            else:
                                markets_results[mkt_name] = "pending"
                    
                    # Determine overall best_pick result
                    bp = p.get("best_pick", {})
                    bp_market = bp.get("market", "")
                    overall_result = "pending"
                    if bp_market and bp_market in markets_results:
                        overall_result = markets_results[bp_market]
                    elif markets_results:
                        # Use first market
                        first_win = [v for v in markets_results.values() if v != "pending"]
                        overall_result = first_win[0] if first_win else "pending"
                    
                    entry = {
                        "match_id": mid,
                        "home_team": p.get("home_team", ""),
                        "away_team": p.get("away_team", ""),
                        "match_time": p.get("match_time", 0),
                        "date": p.get("date", ""),
                        "league": p.get("league", ""),
                        "status": "finished",
                        "markets": p.get("markets", {}),
                        "best_pick": p.get("best_pick", {}),
                        "home_score": home_score,
                        "away_score": away_score,
                        "results": markets_results,
                        "result": overall_result
                    }
                    
                    results.append(entry)
                    
                    # Cache the result
                    results_cache[mid] = {
                        "api_result": "done",
                        "data": entry,
                        "cached_at": datetime.utcnow().isoformat()
                    }
                    changed = True
                else:
                    # Match started but not finished
                    entry = {
                        "match_id": mid,
                        "home_team": p.get("home_team", ""),
                        "away_team": p.get("away_team", ""),
                        "match_time": p.get("match_time", 0),
                        "date": p.get("date", ""),
                        "league": p.get("league", ""),
                        "status": "live",
                        "markets": p.get("markets", {}),
                        "best_pick": p.get("best_pick", {}),
                        "home_score": home_score if home_score is not None else 0,
                        "away_score": away_score if away_score is not None else 0,
                        "results": {k: "pending" for k in p.get("markets", {})},
                        "result": "pending"
                    }
                    results.append(entry)
            else:
                # Fixture not found on API, mark as pending
                entry = {
                    "match_id": mid,
                    "home_team": p.get("home_team", ""),
                    "away_team": p.get("away_team", ""),
                    "match_time": p.get("match_time", 0),
                    "date": p.get("date", ""),
                    "league": p.get("league", ""),
                    "status": "unknown",
                    "markets": p.get("markets", {}),
                    "best_pick": p.get("best_pick", {}),
                    "home_score": None,
                    "away_score": None,
                    "results": {k: "pending" for k in p.get("markets", {})},
                    "result": "pending"
                }
                results.append(entry)
        except Exception as e:
            print(f"Error checking fixture {mid}: {e}")
            entry = {
                "match_id": mid,
                "home_team": p.get("home_team", ""),
                "away_team": p.get("away_team", ""),
                "match_time": p.get("match_time", 0),
                "date": p.get("date", ""),
                "league": p.get("league", ""),
                "status": "error",
                "markets": p.get("markets", {}),
                "best_pick": p.get("best_pick", {}),
                "home_score": None,
                "away_score": None,
                "results": {k: "pending" for k in p.get("markets", {})},
                "result": "error",
                "error": str(e)
            }
            results.append(entry)
    
    # Save results cache if changed
    if changed:
        try:
            with open(results_cache_path, "w", encoding="utf-8") as f:
                json.dump(results_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving results cache: {e}")
    
    # Count stats
    wins = sum(1 for r in results if r.get("result") == "win")
    losses = sum(1 for r in results if r.get("result") == "loss")
    pending = sum(1 for r in results if r.get("result") == "pending")
    
    return {
        "date": today,
        "total": len(results),
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "predictions": results
    }


# ======================== COMBO CALCULATOR ========================
class ComboSelection(BaseModel):
    match_id: str
    market: str
    prediction: str
    bookmaker_odd: float

class ComboRequest(BaseModel):
    selections: list[ComboSelection]

@app.post("/api/v2/combo/calculate")
async def combo_calculate(data: ComboRequest):
    """Calculate combined probability and edge for a parlay.
    Returns statistical analysis - NOT gambling advice.
    """
    if not data.selections or len(data.selections) < 2:
        raise HTTPException(status_code=400, detail="Se requieren al menos 2 selecciones")
    
    # Load predictions cache
    predictions_file = os.path.join(DATA_DIR, "predictions_cache.json")
    if not os.path.exists(predictions_file):
        raise HTTPException(status_code=404, detail="No hay predicciones cargadas")
    
    with open(predictions_file, encoding='utf-8') as f:
        cache = json.load(f)
    
    all_preds = cache.get("predictions", [])
    preds_by_id = {p.get("match_id", ""): p for p in all_preds}
    
    detail = []
    combined_prob = 1.0
    combined_odd = 1.0
    errors = []
    
    for sel in data.selections:
        match = preds_by_id.get(sel.match_id)
        if not match:
            errors.append(f"Partido {sel.match_id} no encontrado")
            continue
        
        mkt_data = match.get("markets", {}).get(sel.market)
        if not mkt_data:
            errors.append(f"Mercado '{sel.market}' no encontrado para partido {sel.match_id}")
            continue
        
        # Get probability for the specific prediction
        prob = 0
        
        if sel.market == "match_winner":
            if sel.prediction == "1":
                prob = mkt_data.get("home_pct", 0)
            elif sel.prediction == "X":
                prob = mkt_data.get("draw_pct", 0)
            elif sel.prediction == "2":
                prob = mkt_data.get("away_pct", 0)
        elif sel.market == "double_chance":
            if sel.prediction == "1X":
                prob = mkt_data.get("1X_pct", 0)
            elif sel.prediction == "12":
                prob = mkt_data.get("12_pct", 0)
            elif sel.prediction == "X2":
                prob = mkt_data.get("X2_pct", 0)
        elif sel.market == "btts":
            if sel.prediction == "Si":
                prob = mkt_data.get("yes_pct", 0)
            elif sel.prediction == "No":
                prob = mkt_data.get("no_pct", 0)
        elif sel.market == "over_under_1.5":
            if sel.prediction == ">1.5":
                prob = mkt_data.get("over_pct", 0)
            elif sel.prediction == "<1.5":
                prob = mkt_data.get("under_pct", 0)
        elif sel.market == "over_under_2.5":
            if sel.prediction == ">2.5":
                prob = mkt_data.get("over_pct", 0)
            elif sel.prediction == "<2.5":
                prob = mkt_data.get("under_pct", 0)
        
        prob_decimal = prob / 100.0
        
        detail.append({
            "match_id": sel.match_id,
            "home_team": match.get("home_team", ""),
            "away_team": match.get("away_team", ""),
            "market": sel.market,
            "prediction": sel.prediction,
            "probabilidad": prob,
            "bookmaker_odd": sel.bookmaker_odd,
            "odd_justa": round(1.0 / prob_decimal, 2) if prob_decimal > 0 else 0
        })
        
        combined_prob *= prob_decimal
        combined_odd *= sel.bookmaker_odd
    
    if not detail:
        raise HTTPException(status_code=400, detail="No se pudieron procesar las selecciones: " + "; ".join(errors))
    
    # Calculate fair odds
    fair_odd = 1.0 / combined_prob if combined_prob > 0 else 0
    
    # Calculate edge: (prob_combinada / (1 / odd_combinada_casa)) - 1
    # More simply: edge = (combined_prob * combined_odd) - 1
    edge = (combined_prob * combined_odd) - 1
    edge_pct = edge * 100
    
    if edge_pct > 5:
        recomendacion = "value"
    elif edge_pct >= -5:
        recomendacion = "fair"
    else:
        recomendacion = "no_value"
    
    return {
        "probabilidad": round(combined_prob * 100, 1),
        "odd_justa": round(fair_odd, 2),
        "odd_casa": round(combined_odd, 2),
        "ventaja": f"{'+' if edge_pct >= 0 else ''}{round(edge_pct, 1)}%",
        "recomendacion": recomendacion,
        "selecciones": detail,
        "nota": len(errors) if errors else None,
        "errores": errors if errors else None,
        "disclaimer": "ESTADÍSTICA INFORMATIVA - NO RECOMENDACIÓN DE APUESTA. PronoGol es una herramienta de análisis estadístico. Los pronósticos no garantizan resultados. El usuario asume toda responsabilidad. Prohibido para menores de 18 años."
    }


# ======================== RESULTS CACHE STATUS ========================
@app.get("/api/v2/predictions/results/stats")
async def results_stats():
    """Get summary stats of verified results."""
    results_cache_path = os.path.join(DATA_DIR, "results_cache.json")
    if not os.path.exists(results_cache_path):
        return {"total": 0, "wins": 0, "losses": 0, "pending": 0}
    
    try:
        with open(results_cache_path, encoding='utf-8') as f:
            cache = json.load(f)
        
        wins = 0
        losses = 0
        pending = 0
        for mid, entry in cache.items():
            data = entry.get("data", {})
            r = data.get("result", "pending")
            if r == "win":
                wins += 1
            elif r == "loss":
                losses += 1
            else:
                pending += 1
        
        return {
            "total": len(cache),
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "accuracy": round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
        }
    except Exception as e:
        return {"error": str(e)}

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
