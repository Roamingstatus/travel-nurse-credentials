# OpenAI Service Report

## Files Created

- `server/services/openaiService.ts`
- `server/services/openaiService.test.ts`
- `OPENAI_SERVICE_REPORT.md`

## Environment Variables

- `OPENAI_API_KEY` is required on the server to call OpenAI.
- `OPENAI_MODEL` is optional and can override the default model.

The API key must never be exposed to frontend code, browser responses, logs, or client-side bundles.

## Exported Service Methods

- `generateResumeVersions(data, model?)`
  - Produces `professionalVersion`, `recruiterVersion`, `impactVersion`, `suggestedKeywords`, and `improvementNotes`.
  - Uses healthcare recruiting-focused instructions.
  - Instructs the model not to invent experience, certifications, licenses, or employers.
  - Preserves factual content and improves wording only.

- `generateChecklistSuggestions(data, model?)`
  - Placeholder for future Smart Checklist AI suggestions.

- `generateLayoutSuggestions(data, model?)`
  - Placeholder for future AI Layout Suggestions.

- `canUseAI(userId?)`
  - Placeholder hook for future rate limits and entitlements.

- `trackAIUsage(userId?)`
  - Placeholder hook for future AI usage accounting.

## Model Configuration

- The model is centralized in `DEFAULT_MODEL`.
- Current default: `gpt-5.4-mini`.
- Each generation method accepts an optional `model` argument for future overrides.

## Future Integration Points

- Resume Enhancer can call `generateResumeVersions()` after the existing flow is intentionally migrated.
- Smart Checklist can call `generateChecklistSuggestions()` after prompts and output schema are defined.
- AI Layout Suggestions can call `generateLayoutSuggestions()` after layout data contracts are defined.
- Recruiter tools and Career Assistant features can share the same client initialization, logging, validation, and error handling patterns.

## Security Considerations

- `OPENAI_API_KEY` is read only from `process.env` on the server.
- The service throws a clean startup error when the key is missing in production.
- The service returns friendly validation and availability errors without stack traces.
- Logs include timestamp, operation, model, and success/failure metadata.
- Logs do not include API keys, resume text, raw OpenAI responses, stack traces, or provider error payloads.
- Input size and output token limits are enforced to help control cost.
- Empty and oversized resumes are rejected before calling OpenAI.

