# Deployment Guide

This guide describes a production/client deployment for the current TenderEval workflow.

## Production Architecture

Recommended services:

- Frontend static site
- Backend FastAPI web service
- Celery worker service
- PostgreSQL database
- Redis instance
- Private S3 bucket for uploaded documents and reports
- SMTP provider for OTP and report email
- Groq API key for LLM extraction/evaluation

Render is supported by `render.yaml`, but the same environment works on a VPS, AWS, Azure, or another container platform.

## What To Commit

Commit source, config templates, migrations, and docs:

- `backend/`
- `frontend/public/`
- `frontend/src/`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `postgres/`
- `scripts/`
- `.github/`
- `.env.example`
- `Dockerfile`
- `Dockerfile.frontend`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `render.yaml`
- `nginx.conf`
- `README.md`
- `SETUP_GUIDE.md`
- `DEPLOYMENT.md`
- `API_DOCUMENTATION.md`
- `QUICK_REFERENCE.md`
- `PROJECT_SUMMARY.md`

Do not commit:

- `.env`
- `.env.production`
- API keys, OAuth secrets, AWS keys, SMTP passwords, JWT secrets
- `uploads/`
- `logs/`
- `temp/`
- `chroma_db/`
- `postgres_data/`
- `frontend/build/`
- `node_modules/`
- `__pycache__/`
- database backups

If your `.gitignore` itself is ignored in a new repository, add it explicitly:

```bash
git add -f .gitignore
```

## Required Production Environment

Backend:

```env
ENVIRONMENT=production
DEBUG=false
AUTO_CREATE_TABLES=false

DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB
SYNC_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB
REDIS_URL=redis://HOST:6379/0

FRONTEND_URL=https://your-frontend-domain.com
ALLOWED_ORIGINS=https://your-frontend-domain.com
JWT_SECRET_KEY=replace-with-long-random-secret
ACCESS_TOKEN_EXPIRE_MINUTES=1440

GROQ_API_KEY=your-groq-key
GROQ_MODEL=llama-3.3-70b-versatile

STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=ap-south-1
S3_BUCKET_NAME=your-private-bucket
S3_PREFIX=tendereval-prod

SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=no-reply@your-domain.com
SMTP_FROM_NAME=TenderEval

ALLOW_PUBLIC_SIGNUP=true
BLOCKED_SIGNUP_EMAILS=
BLOCKED_SIGNUP_DOMAINS=

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://your-backend-domain.com/api/auth/oauth/google/callback

LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_REDIRECT_URI=https://your-backend-domain.com/api/auth/oauth/linkedin/callback

PROCESS_UPLOADS_ON_REQUEST=false
VECTOR_SEARCH_ENABLED=true
CHROMA_PERSIST_DIRECTORY=/tmp/chroma_db
```

Frontend:

```env
REACT_APP_API_URL=https://your-backend-domain.com/api
REACT_APP_ALLOW_PUBLIC_SIGNUP=true
```

## S3 Setup

Use a private bucket. Do not enable public access for uploaded documents.

Minimum IAM permissions for the application bucket/prefix:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name",
        "arn:aws:s3:::your-bucket-name/tendereval-prod/*"
      ]
    }
  ]
}
```

Versioning is optional. It is useful for recovery but not required by the app.

You cannot rename an S3 bucket. To change a bucket name, create a new bucket, update environment variables, and migrate/copy objects if needed.

## Render Deployment

1. Push the repository to GitHub.
2. Create or connect services from `render.yaml`.
3. Create PostgreSQL and Redis resources.
4. Add backend environment variables in Render.
5. Add frontend environment variables.
6. Set backend build command:

```bash
pip install -r backend/requirements.txt && pip install -r backend/requirements-ml.txt
```

7. Set backend start command:

```bash
cd backend && python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

8. Set worker start command:

```bash
cd backend && celery -A app.worker.celery_app worker --loglevel=info
```

9. Set frontend build command:

```bash
cd frontend && npm install && npm run build
```

10. Set frontend publish directory:

```text
frontend/build
```

## OAuth Production URLs

Google authorized JavaScript origin:

```text
https://your-frontend-domain.com
```

Google authorized redirect URI:

```text
https://your-backend-domain.com/api/auth/oauth/google/callback
```

LinkedIn authorized redirect URL:

```text
https://your-backend-domain.com/api/auth/oauth/linkedin/callback
```

The provider value and `.env` value must match exactly.

## Database

Production schema changes must go through Alembic:

```bash
cd backend
python -m alembic upgrade head
```

Do not use seed data in production. Seed data is only demo data for local testing.

Create production users through:

- OTP signup
- OAuth login
- Admin user management
- A controlled one-time admin creation script if needed

## ChromaDB

`chroma_db/` contains generated vector-search metadata and binary index files. Small or nearly empty `.bin` files are normal for small datasets.

For production:

- Use `/tmp/chroma_db` for ephemeral vector cache, or
- Mount a persistent disk if you want indexes to survive restarts.

The canonical uploaded files remain in S3 and core records remain in PostgreSQL.

## Production Smoke Test

After deploy:

1. Open frontend.
2. Sign up with OTP.
3. Login.
4. Upload a tender.
5. Upload multiple bidder documents for that tender.
6. Run evaluations.
7. Confirm criteria count matches the tender content after extraction.
8. Confirm each criterion has decision, confidence, source, and evidence where possible.
9. Export one evaluation PDF.
10. Export JSON.
11. Export tender comparison.
12. Email a report.
13. Assign a review item to another eligible assignee.
14. Delete a test bidder and tender.
15. Check audit logs.

## Security Checklist

- Rotate any key that was exposed in chat, screenshots, logs, or Git.
- Use HTTPS only.
- Use private S3 buckets.
- Use strong `JWT_SECRET_KEY`.
- Restrict CORS to real frontend domains.
- Use SMTP app passwords or provider tokens.
- Keep `DEBUG=false`.
- Keep `AUTO_CREATE_TABLES=false`.
- Review admin users before handover.
- Enable database backups.
- Enable platform logs/alerts.

## Rollback Plan

Before major releases:

1. Backup PostgreSQL.
2. Record current backend/frontend image or commit hash.
3. Verify migrations are backward compatible or have a rollback path.
4. Keep the previous deployment available until smoke tests pass.
