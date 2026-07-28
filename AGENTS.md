# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

"Sage" is a university accounting records application. It is a full-stack monorepo consisting of:
- **Backend**: Django + Django REST Framework (port 8082)
- **Frontend**: Angular 17 standalone-component app (port 4200)
- **Database**: Neo4j 5 graph database (bolt port 7687, browser port 7474) for domain models; SQLite for Django auth/admin only

All three services are orchestrated via Docker Compose.

## Running the Project

**With Docker (recommended):**
```bash
docker-compose up --build
```

**Backend only (local dev):**
```bash
cd backend
source venv/bin/activate
python manage.py runserver 0.0.0.0:8082
```

**Frontend only (local dev):**
```bash
cd frontend/sage-frontend
npm install
npm start         # ng serve → http://localhost:4200
```

**Tests:**
```bash
# Backend
cd backend && python manage.py test

# Frontend
cd frontend/sage-frontend && npm test
```

## Architecture

### Dual-database pattern
This is the most important architectural decision: Django's ORM (SQLite) is used **only** for built-in apps (auth, admin, sessions). All domain models (`Account`, `BankAccount`) are `neomodel.StructuredNode` subclasses stored in Neo4j. Never use `django.db.models.Model` for domain entities.

### Backend apps
| App | Purpose |
|-----|---------|
| `accounts/` | Chart of Accounts — `Account` nodes with `AccountType` enum (Sales, Expenses, Assets, etc.) |
| `banks/` | Bank Accounts — `BankAccount` nodes linked to real bank accounts |
| `reports/` | Planned reporting module (currently empty) |
| `config/` | Django project config, root URL conf |

### API style
Views are plain Django function-based views (not DRF ViewSets). Input is currently read from **GET query params**, not request bodies. All responses are `JsonResponse`. There are no serializers yet — data dicts are built manually in each view.

### URL structure
```
/api/accounts/           → accounts app
/api/banks/              → banks app
/api/reports/            → reports app
/admin/                  → Django admin
```

### Frontend
Angular 17 with standalone components. HTTP calls use **axios** (not Angular's HttpClient). The `ApiService` (`src/app/services/api.service.ts`) is the single API layer. The base URL must match the backend port (8082).

### Environment / secrets
Backend reads from `backend/.env` via `python-decouple`. Required keys: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `NEO4J_BOLT_URL`. The `.env` file is committed to the repo — do not put production secrets there.

### Neomodel conventions
- Use `UniqueIdProperty` for primary keys (not Django PKs).
- Call `python manage.py install_labels` after adding or changing node models so Neo4j indexes are created.
- `updated_at` is set to `default_now=True` on all models but is not auto-updated on save — handle manually if needed.
