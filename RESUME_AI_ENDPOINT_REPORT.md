# Resume AI Endpoint Report

## Files Changed

- `app/main.py`
- `app/db.py`
- `app/services/openai_service.py`
- `tests/test_resume_ai_endpoint.py`
- `RESUME_AI_ENDPOINT_REPORT.md`

## Endpoint Created

- `POST /api/resume/enhance-ai`
- Implemented in the existing FastAPI backend so the current Credanta app can serve it without a rebuild.
- Uses `app/services/openai_service.py`, which mirrors the `server/services/openaiService.ts` resume-generation contract for the active Python runtime.

Request body:

```json
{
  "resumeText": "string",
  "targetRole": "string optional"
}
```

Success response:

```json
{
  "success": true,
  "data": {
    "professionalVersion": "string",
    "recruiterVersion": "string",
    "impactVersion": "string",
    "suggestedKeywords": [],
    "improvementNotes": []
  }
}
```

Error response:

```json
{
  "success": false,
  "message": "Unable to enhance resume right now. Please try again."
}
```

## Security Protections

- Requires an authenticated session through the existing `require_user` flow.
- Uses existing CSRF middleware through the `X-CSRF-Token` header.
- Reads `OPENAI_API_KEY` only on the backend.
- Never returns the API key, stack traces, raw OpenAI responses, or provider errors.
- Does not log full resume text.
- Rejects empty resume text.
- Rejects resume text longer than 12,000 characters.
- Rejects target roles longer than 100 characters.
- Rejects script/HTML-like payloads.
- Stores only AI usage metadata, not original resume text.

## Rate Limit

Created `resume_ai_usage`:

- `id`
- `user_id`
- `target_role`
- `model_used`
- `created_at`

The endpoint allows 3 successful AI resume enhancements per authenticated user per UTC day.

## Curl/Postman Testing

1. Sign in through the app so the browser has a valid `session` cookie.
2. Read the CSRF token from the page meta tag:

```html
<meta name="csrf-token" content="...">
```

3. Send:

```bash
curl -X POST "https://your-credanta-host/api/resume/enhance-ai" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: YOUR_CSRF_TOKEN" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{"resumeText":"Managed ICU patient care for travel assignments.","targetRole":"Travel Nurse"}'
```

## Remaining Frontend Integration Steps

- Add a frontend action that calls `/api/resume/enhance-ai`.
- Use the existing CSRF token already exposed in `base.html`.
- Render the three generated versions, keywords, and notes.
- Preserve the existing local resume enhancer until intentionally migrated.
