# API Documentation

Base URL:

```text
http://localhost:8000/api
```

Production example:

```text
https://your-backend-domain.com/api
```

All protected endpoints require:

```http
Authorization: Bearer <access_token>
```

## Roles

Valid roles:

- `admin`
- `procurement_officer`
- `user`

`user` can upload tenders and bidder submissions. Admin-only operations include user management and destructive delete operations.

## Authentication

### Request Signup OTP

`POST /auth/signup/request-otp`

```json
{
  "email": "user@example.com",
  "password": "secure_password_123",
  "full_name": "John Doe",
  "organization": "ABC Corp"
}
```

Creates a pending signup and emails an OTP. Public signup allows all email domains after OTP verification unless blocklists are configured.

### Verify Signup OTP

`POST /auth/signup/verify`

```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

Response:

```json
{
  "access_token": "jwt",
  "token_type": "bearer",
  "user_id": "uuid",
  "email": "user@example.com",
  "role": "user"
}
```

### Login

`POST /auth/login`

```json
{
  "email": "user@example.com",
  "password": "secure_password_123"
}
```

### Current User

`GET /auth/me`

### OAuth

OAuth callbacks:

- `GET /auth/oauth/google/callback`
- `GET /auth/oauth/linkedin/callback`

Provider redirect URIs must match the configured callback URLs exactly.

## Tenders

### Upload Tender

`POST /tenders/upload`

Multipart form:

- `file`: PDF or DOCX
- optional metadata fields depending on UI/API client

Response includes tender id, upload status, extraction status, and metadata.

### List Tenders

`GET /tenders?skip=0&limit=20`

### Get Tender

`GET /tenders/{tender_id}`

Returns tender metadata, extraction status, extracted text summary where available, and stored criteria.

### Delete Tender

`DELETE /tenders/{tender_id}`

Admin/procurement operation. Deletes tender-related bidder submissions, documents, evaluations, reviews, queue entries, and storage objects where supported.

## Bidders

### Create Bidder

`POST /bidders`

```json
{
  "tender_id": "uuid",
  "company_name": "ABC Corporation"
}
```

The bidder UI should not require shared bidder details for multi-document batch submissions because each file may represent a different bidder.

### Upload Bidder Document

`POST /bidders/{bidder_id}/upload-document`

Multipart form:

- `file`: PDF, DOCX, or supported image
- `document_type`: optional classification such as proposal, certificate, financial, technical

### List Bidders

`GET /bidders?tender_id=uuid&skip=0&limit=20`

### Get Bidder

`GET /bidders/{bidder_id}`

### Delete Bidder

`DELETE /bidders/{bidder_id}`

Deletes bidder documents, extracted fields, evaluations, review queue items, reviews, and storage objects where supported.

### Delete Bidder Document

`DELETE /bidders/{bidder_id}/documents/{document_id}`

## Evaluations

### Create Evaluation

`POST /evaluations`

```json
{
  "tender_id": "uuid",
  "bidder_id": "uuid"
}
```

Behavior:

1. Reads the selected tender text.
2. Extracts criteria freshly for this run.
3. Stores/replaces criteria for the tender.
4. Evaluates the selected bidder documents.
5. Saves criterion-level results, evidence, confidence, method, and final decision.

### List Evaluations

`GET /evaluations?tender_id=uuid&decision=eligible&skip=0&limit=20`

Decision filters:

- `eligible`
- `not_eligible`
- `needs_manual_review`

### Get Evaluation

`GET /evaluations/{evaluation_id}`

Important fields:

```json
{
  "overall_decision": "eligible",
  "overall_confidence": 0.88,
  "decision_summary": "Method: llm+rules; LLM criteria: 8, rule criteria: 2, LLM failed sections: 0.",
  "evaluation_method": "llm+rules",
  "criteria_results": [
    {
      "criterion": "The bidder must have valid GST registration",
      "decision": "PASS",
      "extracted_value": "29ABCDE1234F1Z5",
      "source_document": "bidder.pdf, page 2",
      "confidence": 0.9,
      "reasoning": "GSTIN found in bidder statutory details.",
      "evidence": "[PAGE 2] GSTIN: 29ABCDE1234F1Z5"
    }
  ]
}
```

Evaluation methods:

- `llm+rules`
- `llm`
- `rules`
- `unavailable`

### Override Evaluation

`POST /evaluations/{evaluation_id}/override`

```json
{
  "new_decision": "not_eligible",
  "comments": "GST certificate expired."
}
```

## Review Queue

### List Review Queue

`GET /review/queue?skip=0&limit=20`

Shows evaluations needing human attention, usually low-confidence, ambiguous, failed mandatory criteria, or manually overridden cases.

### List Assignees

`GET /review/assignees`

Returns active users who can receive review assignments, usually admins and procurement officers.

### Assign To Me

`POST /review/{queue_id}/assign-to-me`

### Assign To User

`POST /review/{queue_id}/assign`

```json
{
  "assigned_to": "user_uuid"
}
```

### Submit Review

`POST /review`

```json
{
  "evaluation_id": "uuid",
  "decision": "eligible",
  "comments": "Verified supporting documents manually.",
  "approved": true
}
```

## Admin Users

Admin endpoints support listing, creating/updating roles/status, and deleting or deactivating users depending on configured route behavior.

Typical fields:

```json
{
  "email": "officer@example.com",
  "full_name": "Officer Name",
  "role": "procurement_officer",
  "is_active": true
}
```

Only valid role values are `admin`, `procurement_officer`, and `user`.

## Audit Logs

### List Logs

`GET /audit?skip=0&limit=50`

### Tender Logs

`GET /audit/tender/{tender_id}`

Audit logs track uploads, evaluations, reviews, exports, admin changes, and deletes.

## Export

### Evaluation PDF

`GET /export/evaluation/{evaluation_id}/pdf`

Returns a binary PDF report with summary, criteria results, and evidence.

### Evaluation JSON

`GET /export/evaluation/{evaluation_id}/json`

### Tender Comparison

`GET /export/tender/{tender_id}/comparison`

Returns consolidated bidder-wise comparison for a tender.

### Email Evaluation PDF

`POST /export/evaluation/{evaluation_id}/email`

```json
{
  "recipients": ["procurement@example.com"],
  "cc": ["audit@example.com"],
  "subject": "Tender evaluation report",
  "message": "Please find the attached evaluation report."
}
```

Requires SMTP configuration.

## Common Error Responses

```json
{
  "detail": "Invalid email or password"
}
```

```json
{
  "detail": "Not authorized"
}
```

```json
{
  "detail": "Resource not found"
}
```

```json
{
  "detail": "Internal server error"
}
```

For PDF/export or AI failures, check backend logs first. The frontend only shows the HTTP status and user-facing message.
