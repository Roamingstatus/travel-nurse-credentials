# Terminology Change Report — Credanta

**Date:** June 11, 2026
**Task:** Replace "credential/credentials/credentialing" language with modern portfolio/document language across all user-facing templates.
**Backend impact:** None. All routes, DB tables, Python variable names, Stripe metadata, and analytics event names are unchanged.

## Summary of Changes by File

### app/templates/base.html
- Sidebar nav label: **Credentials** → **Portfolio**
- Bottom nav label: **Credentials** → **Portfolio**

### app/templates/dashboard.html
- Subtitle: "X credentials up to date" → "X documents up to date"
- Empty state: "Your credential vault is empty — add your first credential below" → "Your portfolio is empty — add your first document below"
- Expired alert: "X credential(s) expired" → "X document(s) expired"
- Expiring alert: "X credential(s) expiring soon" → "X document(s) expiring soon"
- Footer link: "Browse all credentials" → "Browse all documents"

### app/templates/documents.html
- Page title: "Credentials · Credanta" → "Professional Portfolio · Credanta"
- ARIA label: "Credential categories" → "Document categories"

### app/templates/premium.html
- Hero copy: "manage credentials, share packets" → "manage documents, share packets"
- Basic plan feature: "Upload & store credential documents" → "Upload & store professional documents"
- Premium plan feature: "Credential packet (.zip + PDF manifest)" → "Submission packet (.zip + PDF manifest)"
- Comparison table: "Credential packet (.zip + PDF)" → "Submission packet (.zip + PDF)"
- FAQ: "What happens when a credential expires?" → "What happens when a document expires?"
- FAQ: "Expired credentials are flagged" → "Expired documents are flagged"
- FAQ: "your current credential packet" → "your current submission packet"
- Included section: "Upload and store credential documents" → "Upload and store professional documents"

### app/templates/premium_checklist.html
- Subtitle: "Check your credential readiness" → "Check your submission readiness"

### app/templates/premium_reminders.html
- Subtitle: "before credentials expire" → "before documents expire"
- Upgrade prompt: "before credentials expire" → "before documents expire"
- Checkbox label: "before credentials expire" → "before documents expire"

### app/templates/premium_agency.html
- Subtitle: "which credentials are ready" → "which documents are ready"

### app/templates/premium_calendar.html
- Subtitle: "your credential expirations" → "your document expirations"

### app/templates/premium_resume.html
- Reassurance label: "facts, dates & credentials are preserved" → "facts, dates & qualifications are preserved"

### app/templates/share_view.html
- Section header: **Credentials** → **Professional Portfolio**
- Benefit card: "through credentialing faster" → "through onboarding faster"
- Workflow copy: "common credential requirements" → "common document requirements"
- Workflow copy: "credential review dashboards" → "document review dashboards"
- Workflow copy: "from the credentialing community" → "from the onboarding community"
- Success step: "future credential packets" → "future submission packets"

### app/templates/login.html
- Hero bullet: "Shareable credential packets" → "Shareable submission packets"
- Hero bullet: "Credential checklist tracking" → "Readiness checklist tracking"
- Logo alt text: "credentials secured" → "documents secured"

### app/templates/about.html
- Lead: "professional credential and document management platform" → "professional document management platform"
- Body: "manages a portfolio of credentials" → "manages a professional portfolio"
- Body: "share your credentials with third parties" → "share your documents with third parties"
- Disclaimer: "credentialing agency" → "document review service"

### app/templates/account.html
- Preferences toggle description: "before credentials expire" → "before documents expire"
- Delete modal: "all uploaded documents, and credentials" → "all uploaded documents"

### app/templates/security_overview.html
- Expiration reminders card: "credentials are approaching renewal" → "documents are approaching renewal"
- Account protection card: "verified credentials separate" → "verified permissions separate"

### app/templates/document_security.html
- Disclaimer: "credentialing agency" → "document review service"

### app/templates/admin.html
- Section header: "Top credential categories" → "Top document categories"

### app/templates/admin_recruiter_feedback.html
- Subtitle: "shared credential packets" → "shared submission packets"

### app/templates/email/reminder.html
- Email subtitle: "Credential Expiration Reminder" → "Document Expiration Reminder"
- Body copy: "your credential [title]" → "your document [title]"

### app/templates/email/expired.html
- Email subtitle: "Credential Expired Alert" → "Document Expired Alert"

### app/templates/email/test.html
- Body copy: "When a credential is approaching" → "When a document is approaching"

## What Was NOT Changed

- API routes: `/documents`, `/credentials`, `/packet`, `/share`, etc.
- Python variable names: `credentials`, `docs`, `summary`, etc.
- SQLAlchemy model names and column names
- Stripe metadata keys
- Analytics/tracking event names
- Jinja2 code comments
- The word "credentialed" as an adjective for licensed professionals (about.html)
- "Credentialing team" as an industry job-title option in recruiter feedback form
