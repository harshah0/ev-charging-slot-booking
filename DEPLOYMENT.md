# Deployment Guide (Production)

This guide prepares the EV Charging Slot Booking platform for production deployment.

1) Why SQLite is unsuitable for production
- SQLite is file-based, lacks concurrent write scalability, and doesn't support robust connection pooling.
- Use PostgreSQL for multi-worker, multi-process deployments.

2) Configuration
- Use environment variables to store secrets (do not commit `.env` into VCS).
- Copy `.env.example` to `.env` locally for testing, but set env vars via platform in production.

3) PostgreSQL setup
- Provide `DATABASE_URL` in the environment (Render/Heroku provide this).
- Example: `postgresql://user:pass@host:5432/dbname`
- The application normalizes `postgres://` to `postgresql://` in `config.build_database_uri()`.

4) Gunicorn setup
- We include `gunicorn` in `requirements.txt` and `Procfile` for platform start command.
- Default run: `gunicorn -w 4 -k gthread -b 0.0.0.0:$PORT app:app`
- Optional `gunicorn_conf.py` provided for tuning.

5) Static files
- Use `whitenoise` to serve static files from Flask when platform does not handle static hosting.
- WhiteNoise is enabled by default when `USE_WHITENOISE=true` and `FLASK_ENV=production`.

6) Migrations
- Use Flask-Migrate/Alembic to manage schema changes.
- Run migrations after setting `DATABASE_URL`:

```bash
flask db upgrade
```

7) Health-check
- `/health` endpoint exists for platform checks.

8) Database connection tuning
- Optional env vars: `SQLALCHEMY_POOL_SIZE`, `SQLALCHEMY_MAX_OVERFLOW`.
- These are read by `config.build_engine_options` and set in `SQLALCHEMY_ENGINE_OPTIONS`.

9) Render deployment
- `render.yaml` present for quick render service configuration.
- Use Render's managed Postgres service and set secrets in Render dashboard.

10) Secrets
- `SECRET_KEY` must be set to a secure random value in production.
- Use platform secret management (Render/GCP/AWS) to inject env vars.

11) Checklist
- [ ] Set `DATABASE_URL` to a managed Postgres instance
- [ ] Set `SECRET_KEY`
- [ ] Run `pip install -r requirements.txt`
- [ ] Run `flask db upgrade`
- [ ] Start `gunicorn` (platform will do this)
- [ ] Verify `/health` returns 200

