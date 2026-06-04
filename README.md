# TenderEval

TenderEval is a government procurement evaluation platform. It lets users upload tender documents, upload one or more bidder submissions for a tender, extract eligibility criteria, evaluate each bidder against those criteria, send ambiguous cases for human review, and export the results.

The current workflow is intentionally simple:

1. Upload a tender document.
2. Upload bidder submissions for that tender.
3. Run evaluation.
4. Review extracted criteria, bidder-wise decisions, confidence, reasoning, and supporting evidence.
5. Send low-confidence or disputed results to the review queue.
6. Export PDF, JSON, or consolidated tender comparison reports.

## Current Capabilities

- Tender upload for PDF/DOCX documents.
- Multiple bidder submissions per tender.
- OCR support for scanned/image-based PDFs when Tesseract is available.
- Fresh criteria extraction for every evaluation run.
- Hybrid evaluation using Groq LLM output plus deterministic rule-based extraction.
- Criterion-level evidence, source document references, confidence, and decision output.
- Review queue with assignment to self or another active admin/procurement officer.
- PDF, JSON, consolidated comparison, and email report export.
- S3-first file storage for client/prod deployments.
- OTP email verification for public signup.
- Google and LinkedIn OAuth login.
- Audit logs for upload, evaluation, review, export, admin, and delete actions.
- Admin user management.

## Roles

Only these roles should exist in the current project:

| Role | Main permissions |
|------|------------------|
| `admin` | Full access, user management, delete tenders/bidders/documents, review assignment, audit logs, exports |
| `procurement_officer` | Tender/bidder workflow, evaluations, review queue, assignment/review, exports, audit visibility |
| `user` | Upload tenders, upload bidder submissions, run/view evaluations, export reports |

Seeded/demo users are only for local testing. Production users should be created through OTP signup, OAuth, or by an admin.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL |
| Queue/cache | Redis, Celery |
| Frontend | React, TypeScript, TailwindCSS |
| AI | Groq OpenAI-compatible API |
| Rules | Deterministic tender/bidder extraction services |
| Vector search | ChromaDB, sentence-transformers |
| OCR | Tesseract |
| Storage | S3 in production, local storage for development fallback |
| Deployment | Docker Compose locally, Render/VPS supported |

## Project Structure

```text
tender-evaluation-platform/
  backend/
    alembic/                 Database migrations
    app/
      api/                   FastAPI route modules
      models/                SQLAlchemy models
      schemas/               Pydantic schemas
      services/              Auth, storage, document, AI, rules, export
      utils/                 Config, dependencies, logging
      main.py                FastAPI app
    scripts/                 Seed/demo helpers
    requirements.txt
    requirements-ml.txt
  frontend/
    public/
    src/
      components/
      pages/
      services/
      store/
    package.json
  postgres/
  scripts/
  docker-compose.yml
  docker-compose.prod.yml
  Dockerfile
  Dockerfile.frontend
  render.yaml
  nginx.conf
  .env.example
```

Generated folders such as `uploads/`, `logs/`, `temp/`, `chroma_db/`, `postgres_data/`, `frontend/build/`, and `node_modules/` are runtime/build artifacts and should not be committed.

## Local Run With Docker

1. Create `.env` from `.env.example`.
2. Fill required local values:
   - `JWT_SECRET_KEY`
   - `GROQ_API_KEY`
   - `GROQ_MODEL`
   - SMTP settings for OTP/email reports
   - S3 settings if using `STORAGE_BACKEND=s3`
   - OAuth client IDs/secrets if using Google or LinkedIn
3. Start services:

```bash
docker compose up -d --build postgres redis backend worker frontend
```

4. Apply migrations if they did not run during startup:

```bash
docker compose exec backend python -m alembic upgrade head
```

5. Optional local demo data:

```bash
docker compose exec backend python -m scripts.seed_data
```

Open:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

## Local Run Without Docker

Use a virtual environment for local backend development:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-ml.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm start
```

## Evaluation Behavior

Each evaluation run extracts criteria freshly from the selected tender document. The system stores/replaces the criteria for that run, then evaluates the bidder documents against the extracted criteria.

Evaluation methods shown in the result:

| Method | Meaning |
|--------|---------|
| `llm+rules` | Groq returned criteria and rules also contributed/deduplicated criteria or evidence |
| `llm` | Groq result was used without rule fallback additions |
| `rules` | Groq was unavailable, rate-limited, invalid, or returned no usable criteria, so deterministic extraction was used |
| `unavailable` | No usable criteria/evidence could be produced |

The decision summary may include:

```text
Method: llm+rules; LLM criteria: 8, rule criteria: 3, LLM failed sections: 0.
```

If you see `Method: rules`, check the backend logs and Groq dashboard for invalid API key, exhausted quota, rate limits, or model errors.

## S3 Storage

For production/client use, keep:

```env
STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
S3_BUCKET_NAME=your-private-bucket
S3_PREFIX=tendereval
```

Keep the bucket private. The app stores file keys/metadata in PostgreSQL and the actual uploaded documents in S3.

## Environment Files

Do not commit:

- `.env`
- `.env.production`
- Any file containing real API keys, SMTP passwords, AWS keys, OAuth secrets, or JWT secrets

Commit:

- `.env.example` with safe placeholders only

If a secret was pasted into chat, logs, screenshots, or Git history, rotate it before deployment.

## Documentation

- `SETUP_GUIDE.md`: detailed local setup
- `DEPLOYMENT.md`: production deployment checklist
- `API_DOCUMENTATION.md`: API endpoint reference
- `QUICK_REFERENCE.md`: daily commands and troubleshooting
- `PROJECT_SUMMARY.md`: architecture and feature summary
