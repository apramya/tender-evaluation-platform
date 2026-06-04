# Setup Guide

This guide sets up TenderEval for local development and first-time testing.

## Prerequisites

Install:

- Docker Desktop
- Git
- Node.js 18+ if running the frontend outside Docker
- Python 3.11+ if running the backend outside Docker
- Tesseract OCR if testing scanned PDFs outside Docker

Docker Desktop must be running before using `docker compose`.

## Environment Setup

Create local env files from the examples:

```bash
copy .env.example .env
```

Fill at least:

```env
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
JWT_SECRET_KEY=replace-with-a-long-random-secret

GROQ_API_KEY=your-groq-key
GROQ_MODEL=llama-3.3-70b-versatile

ALLOW_PUBLIC_SIGNUP=true
REACT_APP_ALLOW_PUBLIC_SIGNUP=true

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@example.com
SMTP_FROM_NAME=TenderEval

STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=ap-south-1
S3_BUCKET_NAME=your-private-bucket
S3_PREFIX=tendereval-local
```

Public signup is allowed for all email domains after OTP verification. Optional blocklists can still be configured:

```env
BLOCKED_SIGNUP_EMAILS=
BLOCKED_SIGNUP_DOMAINS=
```

## OAuth Setup

### Google

Authorized JavaScript origins:

```text
http://localhost:3000
```

Authorized redirect URI:

```text
http://localhost:8000/api/auth/oauth/google/callback
```

Set:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/oauth/google/callback
```

### LinkedIn

Authorized redirect URL:

```text
http://localhost:8000/api/auth/oauth/linkedin/callback
```

Set:

```env
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_REDIRECT_URI=http://localhost:8000/api/auth/oauth/linkedin/callback
```

The redirect URI must match exactly, including protocol, host, port, path, and trailing slash.

## Start With Docker

Build and start everything:

```bash
docker compose up -d --build postgres redis backend worker frontend
```

Check status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
```

Open:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

## Database Migrations

The project uses Alembic migrations. For development, apply migrations with:

```bash
docker compose exec backend python -m alembic upgrade head
```

For production, keep:

```env
AUTO_CREATE_TABLES=false
```

Do not depend on automatic table creation in production.

If you see a duplicate table error such as `relation "email_verification_codes" already exists`, the database already has that table. Run migrations against the current schema, or reset only your local development database if you intentionally want a clean database.

## Optional Seed Data

Seed data is only for local/demo testing. It is not production data and should not be used for a client deployment.

```bash
docker compose exec backend python -m scripts.seed_data
```

Seed data normally creates demo users for the three current roles:

- `admin`
- `procurement_officer`
- `user`

If `python -m scripts.seed_data` fails, make sure you run it inside the backend container or from the `backend` directory with `PYTHONPATH` configured.

## Frontend Dependency Fix

If the frontend logs show `react-scripts: not found` or a missing module inside `node_modules`, reinstall frontend dependencies:

```bash
docker compose exec frontend npm install
docker compose restart frontend
```

If needed, rebuild:

```bash
docker compose build --no-cache frontend
docker compose up -d frontend
```

## Normal Test Workflow

1. Sign up with OTP or login with a demo account.
2. Upload a tender document.
3. Upload one or more bidder submissions for that tender.
4. Run evaluation for each bidder.
5. Confirm the result shows extracted criteria, evidence, confidence, and method.
6. Export PDF and JSON.
7. Open consolidated tender comparison export.
8. Send report by email if SMTP is configured.
9. Check review queue for low-confidence or manual-review cases.
10. Check audit logs.

## Local Cleanup

Stop containers:

```bash
docker compose down
```

Delete local database and Redis volumes:

```bash
docker compose down -v
```

Warning: `down -v` deletes local database data.

Generated local folders that may be safely recreated:

- `uploads/`
- `logs/`
- `temp/`
- `chroma_db/`
- `frontend/build/`

Do not delete S3 objects unless you intentionally want to remove uploaded client files.

## Common Issues

### Docker API or Linux engine error

Start Docker Desktop and wait until it says the engine is running. Then retry:

```bash
docker compose ps
```

### Groq output says `Method: rules`

The LLM did not produce usable output for that run. Check:

- `GROQ_API_KEY`
- `GROQ_MODEL`
- Groq quota/rate limit
- Backend logs for `Calling Groq model ...`

The rule fallback still runs so the app remains usable.

### OTP email not received

Check:

- SMTP credentials
- App password instead of normal email password
- Spam folder
- Backend logs
- `SMTP_FROM_EMAIL`

### Uploaded data does not show until refresh

Restart the frontend after code/env changes:

```bash
docker compose restart frontend
```

Also confirm the frontend is using the correct API URL.
