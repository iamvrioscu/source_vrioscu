# VRIOSCU website

Official website and account platform for **VRIOSCU — Endpoint Validation & Evidence Capture**.
*Validate. Capture. Document.*

The Windows desktop application is the product: it validates endpoints, captures
evidence, collects local machine/network details and generates PDF reports.
This website is the companion platform: **Discover → Explain → Authenticate → Support → Distribute.**
It never pretends to collect machine or network information from a browser, and
it never receives validation runs, screenshots or reports.

## Stack

| Layer      | Choice | Why |
|------------|--------|-----|
| Web/API    | Python 3.11+, Flask 3, Jinja2 server-rendered pages | Few dependencies, every page works without JavaScript |
| Database   | SQLite (WAL mode) behind a repository layer | No separately managed database; swappable for PostgreSQL later |
| Export     | openpyxl (.xlsx) | Authorised Excel exports |
| App server | gunicorn on 127.0.0.1 | Behind nginx |
| Edge       | nginx + Let's Encrypt on the existing EC2 instance | HTTPS, static files, coarse rate limiting |

Runtime dependencies: `Flask`, `openpyxl`, `gunicorn` (see `requirements.txt`). Nothing else.

## Quick start (development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # defaults work for local development
flask --app wsgi init-db              # applies migrations
flask --app wsgi create-admin         # prompts for username, email, password
flask --app wsgi run --port 5000      # http://127.0.0.1:5000
```

Optional:
- Add the self-hosted fonts described in `app/static/fonts/README.md`.
- Generate the social share image: `pip install pillow && python scripts/make_og_image.py`.

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

99 tests, standard library only (no pytest needed). See `docs/TEST_REPORT.md`.

## Project layout

```
app/
  __init__.py          application factory, request lifecycle, error handling, CLI
  config.py            ALL product & environment configuration (single source of truth)
  db.py                SQLite connections, transactions, migration runner
  security.py          CSRF, rate limiting, security headers, access control
  validation.py        declarative input validation
  forms.py             field sets shared by HTML forms and the JSON API
  repositories/        the only code that contains SQL
  services/            auth/sessions, release rules, Excel export
  routes/              public, auth, account, admin, api (v1)
  templates/ static/   UI
migrations/            numbered .sql migrations
scripts/               backup_db.py, restore_db.py, maintenance.py, make_og_image.py
deploy/                nginx, systemd units, gunicorn config
docs/                  everything else
tests/                 unittest suite
```

## Documentation

| Document | Contents |
|----------|----------|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Boundaries, request flow, layers, PostgreSQL migration path |
| [API](docs/API.md) | Every endpoint, auth, errors |
| [DATABASE](docs/DATABASE.md) | Schema, migrations, data minimisation |
| [ENVIRONMENT](docs/ENVIRONMENT.md) | Every environment variable |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | EC2 step-by-step |
| [SECURITY_CHECKLIST](docs/SECURITY_CHECKLIST.md) | Controls and how each is implemented |
| [BACKUP_RESTORE](docs/BACKUP_RESTORE.md) | Backup, restore, off-host copies |
| [EXCEL_EXPORT](docs/EXCEL_EXPORT.md) | Datasets, columns, safeguards |
| [RELEASE_MANAGEMENT](docs/RELEASE_MANAGEMENT.md) | Publishing installers, update API |
| [TEST_REPORT](docs/TEST_REPORT.md) | What is tested and the latest result |
| [PRODUCTION_READINESS](docs/PRODUCTION_READINESS.md) | Go-live checklist and known gaps |

## Content rules for contributors

- Brand is **VRIOSCU**. Never "Vristu", "Vristu Screenshot Analysis" or "Artifact Validator".
- Don't invent customers, user counts, certifications, integrations, statistics or compliance claims.
- Don't describe the installer as signed, verified or certified unless `INSTALLER_SIGNED=true` is actually true.
- Never tell users to disable SmartScreen, Smart App Control, Defender or other security controls.
- Product values (version, channel, URLs, contacts) come from `app/config.py`; don't hard-code them in templates.
  GDrive - https://drive.google.com/file/d/1zW04Qogu_roVOeBISabjBJknXTVS-nBB/view?usp=sharing
  GDrive (Final_9thOct) - https://drive.google.com/file/d/1Nn9Z1Sur_9uJU_6Ac-5MiMQNgNfB7Ufg/view?usp=sharing
  
