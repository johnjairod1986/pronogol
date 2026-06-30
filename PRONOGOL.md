# 🦀 PRONOGOL — Documentación del Proyecto

> Sistema profesional de pronósticos de fútbol con IA
> Creado: 2026-06-29
> Propietario: John Jairo De La Hoz (@Johnky)

---

## 📊 Stack Tecnológico

| Componente | Tecnología | Estado |
|---|---|---|
| **Base de datos** | Supabase (PostgreSQL) | ✅ Creado |
| **Autenticación** | Supabase Auth | ✅ Listo |
| **Backend** | Python / FastAPI | Pendiente |
| **Frontend Web** | Next.js | Pendiente |
| **App Móvil** | React Native (Expo) | Pendiente |
| **Motor IA** | DeepSeek (API propia) — ÚNICO modelo autorizado | Pendiente |
| **Pagos** | Stripe | Pendiente |
| **Sincronización** | n8n (VPS) | Pendiente |
| **Monitoreo** | Sentry | Pendiente |
| **CDN** | Cloudflare | Pendiente |
| **CI/CD** | GitHub Actions | Pendiente |

---

## 🗄️ Base de Datos — Supabase

### Proyecto
- **URL:** https://kisfitwdpmfcqsgllcll.supabase.co
- **Ref:** kisfitwdpmfcqsgllcll
- **Región:** us-east-1
- **DB Host:** db.kisfitwdpmfcqsgllcll.supabase.co:5432
- **DB Name:** postgres
- **DB User:** postgres
- **PAT Token:** (en .env.local)

### Tablas (12 creadas)

| Tabla | Propósito | RLS |
|---|---|---|
| **leagues** | Ligas de fútbol | Lectura pública |
| **teams** | Equipos por liga | Lectura pública |
| **matches** | Partidos con fecha UTC | Lectura pública |
| **match_stats** | Estadísticas detalladas (xG, posesión, etc) | Lectura pública |
| **predictions** | 🧠 Pronósticos generados por IA | Lectura pública |
| **prediction_results** | ✅ Resultados reales de cada pronóstico | Lectura pública |
| **profiles** | Perfiles de usuario (vinculado a Auth) | Solo propio |
| **subscriptions** | Planes Free / Premium | Solo propio |
| **payments** | Pagos vía Stripe | Solo propio |
| **user_favorites** | Equipos/ligas favoritos | Solo propio |
| **audit_logs** | 🔐 Registro de seguridad | Solo service_role |
| **sync_log** | Control sincronización Foosty | Solo service_role |

### Features de seguridad
- ✅ RLS activado en TODAS las tablas
- ✅ Trigger: perfil + suscripción free automática al registrarse
- ✅ Timestamps inmutables en predicciones (auditables)
- ✅ Sin claves en código fuente

---

## 🗂️ Estructura del Proyecto

```
pronogol/
├── supabase/
│   └── migrations/
│       └── 001_schema_inicial.sql    ✅ Ejecutada
├── apps/
│   ├── mobile/                        # React Native (Expo)
│   └── web/                           # Next.js
├── packages/
│   ├── engine/                        # Motor de predicciones IA
│   ├── database/                      # Cliente DB compartido
│   └── shared/                        # Tipos y utilidades
├── scripts/                           # Scripts de utilidad
├── docs/                              # Documentación
├── .env.local                         # Variables de entorno locales
└── .gitignore
```

---

## 🔑 API Keys & Credenciales

### Supabase
| Key | Valor |
|---|---|
| Project URL | `https://kisfitwdpmfcqsgllcll.supabase.co` |
| Anon Key | (ver .env.local) |
| Service Role | (ver .env.local) |
| DB Password | (ver .env.local) |
| PAT Token | (ver .env.local) |

### FootyStats
| Key | Valor |
|---|---|
| API Key | Ver .env.local |
| Season ID (Mundial) | 16494 |

### DeepSeek
| Key | Valor |
|---|---|
| API Key | Ver .env.local |

---

## 📋 Para hacer (Fase 0)

- [x] Crear proyecto Supabase
- [x] Ejecutar migración 001 (12 tablas + RLS + triggers)
- [x] Inicializar Git repo
- [ ] Crear GitHub Actions workflow (CI/CD)
- [ ] Configurar Autenticación en Supabase Dashboard
- [ ] Documentar API endpoints

## 📋 Para hacer (Fase 1)
- [ ] Conectar con n8n (VPS)
- [ ] Script de sincronización Foosty → Supabase
- [ ] Motor de predicciones básico
- [ ] Endpoints API

---

## 🚀 Próximos Pasos

1. ✅ Base de datos creada
2. ⏳ Crear repo en GitHub y push
3. ⏳ Configurar GitHub Actions
4. ⏳ Activar Autenticación en Supabase
5. ⏳ Desarrollar motor de predicciones

---

> 📝 Documentación mantenida por Clawbot 🦀
> Última actualización: 2026-06-29
