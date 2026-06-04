# Project Summary

TenderEval is a procurement evaluation platform for tender eligibility analysis. It is designed for government-style workflows where uploaded tender documents define eligibility criteria and bidder submissions must be evaluated with traceable evidence.

## Current Workflow

1. A user, procurement officer, or admin uploads a tender document.
2. One or more bidder submissions are uploaded for that tender.
3. An evaluation run extracts tender criteria freshly.
4. The bidder documents are evaluated criterion by criterion.
5. Results show decisions, confidence, reasoning, source document, and evidence.
6. Ambiguous or low-confidence cases go to manual review.
7. Users export individual or consolidated reports.

## Roles

Only three roles are currently valid:

| Role | Purpose |
|------|---------|
| `admin` | Platform administration, users, delete actions, reviews, audit, exports |
| `procurement_officer` | Procurement operations, review queue, evaluation verification |
| `user` | Tender upload, bidder upload, evaluation, export |

This role model matches the current client-facing workflow: normal users can perform the core upload/evaluation flow, procurement officers can review, and admins can govern the system.

## Implemented Features

### Authentication

- Email/password login.
- OTP email verification for public signup.
- Google OAuth.
- LinkedIn OAuth.
- JWT-based sessions.
- Role-based access control.
- Admin user management.

### Tender and Bidder Management

- Upload tender documents.
- Upload multiple bidder submissions per tender.
- List available tenders and bidders.
- Delete tenders, bidders, and bidder documents where permissions allow.
- Store file metadata in PostgreSQL.
- Store uploaded files in S3 for client/prod deployments.

### Document Processing

- PDF text extraction.
- DOCX extraction.
- OCR path for image-based/scanned PDFs when Tesseract is installed.
- Page-aware evidence snippets.
- ChromaDB/sentence-transformers support for semantic retrieval.

### Evaluation Engine

- Fresh criteria extraction per evaluation run.
- Groq LLM extraction and matching.
- Rule-based fallback and evidence extraction.
- Deduplication of repeated criteria.
- Dynamic criteria count based on the tender document, not fixed hard-coded criteria.
- Criterion-level pass/fail/manual-review decisions.
- Overall decision and confidence.
- Method reporting: `llm+rules`, `llm`, `rules`, or `unavailable`.

### Review Workflow

- Review queue for manual attention.
- Assign to self.
- Assign to another active admin/procurement officer.
- Submit review decision and comments.
- Evaluation override support.

### Reports

- Individual evaluation PDF export.
- Individual evaluation JSON export.
- Consolidated tender comparison export.
- Email PDF report through SMTP.

### Audit

- Upload actions.
- Evaluation actions.
- Review actions.
- Export actions.
- Admin actions.
- Delete actions.

## Architecture

```text
Frontend React app
  |
  v
FastAPI backend
  |
  +-- PostgreSQL: users, tenders, bidders, criteria, evaluations, reviews, audit
  +-- Redis/Celery: background processing
  +-- S3: uploaded tender and bidder files
  +-- Groq: LLM criteria extraction and evaluation reasoning
  +-- ChromaDB: local vector-search index/cache
  +-- SMTP: OTP and emailed reports
```

## Backend Modules

```text
backend/app/api/            REST routes
backend/app/models/         SQLAlchemy models
backend/app/schemas/        Pydantic schemas
backend/app/services/       Auth, document, storage, AI, rules, review, export
backend/app/utils/          Config, dependencies, logging
backend/alembic/            Database migrations
backend/scripts/            Demo/local scripts
```

## Frontend Modules

```text
frontend/src/pages/         Login, signup, dashboard, tenders, bidders, evaluations, reviews, admin
frontend/src/components/    Navigation, protected routes, shared UI
frontend/src/services/      API client
frontend/src/store/         Auth state
```

## Database Scope

Core persisted data:

- Users and roles.
- Email verification codes.
- Tenders and tender criteria.
- Bidders and bidder documents.
- Extracted fields.
- Evaluations and criterion results.
- Review queue and review records.
- Audit logs.
- Vector embedding metadata where enabled.

Migrations are managed by Alembic. Production should run migrations explicitly and keep `AUTO_CREATE_TABLES=false`.

## Storage Scope

S3 stores actual uploaded documents in production/client environments. PostgreSQL stores metadata and S3 object keys.

Local generated folders:

- `uploads/`: local fallback files
- `logs/`: application logs
- `temp/`: temporary processing files
- `chroma_db/`: generated vector index/cache
- `frontend/build/`: frontend production build

These are generated artifacts and should not be committed.

## AI and Rules Behavior

The evaluation engine is intentionally hybrid:

- Groq is used for legal/procurement language understanding and flexible matching.
- Rule extraction catches structured criteria, statutory IDs, numeric thresholds, dates, years, project counts, and common compliance labels.
- If Groq fails due to rate limit, invalid key, outage, or unusable output, rules still run.
- The UI/API reports the method so users can see whether the LLM contributed.

This keeps the app usable during LLM failures while still benefiting from LLM reasoning when available.

## Production Readiness Checklist

Before client handover:

- Rotate any exposed secrets.
- Configure S3 private bucket.
- Configure SMTP.
- Configure Google/LinkedIn production redirect URIs.
- Configure Groq key and rate limits.
- Run Alembic migrations.
- Disable debug mode.
- Set CORS to production frontend domain only.
- Confirm OTP signup.
- Confirm tender upload.
- Confirm multiple bidder upload.
- Confirm dynamic criteria extraction.
- Confirm PDF export includes criteria/results/evidence.
- Confirm email report.
- Confirm review assignment.
- Confirm delete flows.
- Confirm audit logs.
- Confirm database backups.

## Important Limitations

- AI output can vary if the LLM is used with non-deterministic settings or if provider behavior changes.
- Scanned PDFs require OCR quality good enough for extraction.
- ChromaDB local files are cache/index files, not the source of truth.
- Seed data is not production data.
- Accurate legal/procurement evaluation still requires human review for ambiguous or high-stakes cases.

## Version Status

Current status: client-preparation build.

The core workflow is implemented, but every deployment should be validated with real tender and bidder samples from the client before production handover.
