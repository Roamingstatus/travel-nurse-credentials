# Terminology Audit — Credanta

**Date:** June 11, 2026
**Scope:** All user-facing Jinja2 templates under `app/templates/`
**Constraint:** Backend code (routes, variable names, DB tables, Stripe metadata, analytics events) unchanged.

## Replacement Map Applied

| Old term | New term | Context |
|---|---|---|
| Credentials (nav label) | Portfolio | Sidebar + bottom nav |
| credential(s) in body text | document(s) | Alerts, descriptions, email copy |
| credential vault is empty | portfolio is empty | Dashboard empty state |
| X credentials up to date | X documents up to date | Dashboard subtitle |
| credential packet | submission packet | Premium, share view, recruiter feedback |
| credential expiration reminder | document expiration reminder | Email templates |
| credential expired alert | document expired alert | Email templates |
| credential expirations | document expirations | Calendar feed page |
| credential readiness | submission readiness | Checklist page subtitle |
| which credentials are ready | which documents are ready | Agency auto-fill page |
| shared credential packets | shared submission packets | Admin recruiter feedback |
| credentialing faster | onboarding faster | Share view recruiter section |
| credential review dashboards | document review dashboards | Share view copy |
| from the credentialing community | from the onboarding community | Share view copy |
| credential requirements (common) | document requirements | Share view copy |
| future credential packets | future submission packets | Share view success step |
| Credential checklist tracking | Readiness checklist tracking | Login hero bullets |
| Shareable credential packets | Shareable submission packets | Login hero bullets |
| credentials are approaching renewal | documents are approaching renewal | Security overview |
| credentialing agency | document review service | Security overview, About, Document security |
| verified credentials (admin) | verified permissions | Security overview |
| credential and document management platform | document management platform | About page |
| portfolio of credentials | professional portfolio | About page |
| share your credentials | share your documents | About page |
| Get notified before credentials expire | Get notified before documents expire | Account preferences, Reminders |
| before credentials expire (reminders) | before documents expire | Premium reminders |
| Top credential categories | Top document categories | Admin dashboard |
| Upload & store credential documents | Upload & store professional documents | Premium pricing |
| Credential packet (.zip + PDF) | Submission packet (.zip + PDF) | Premium pricing table |
| What happens when a credential expires | What happens when a document expires | Premium FAQ |
| Expired credentials are flagged | Expired documents are flagged | Premium FAQ |
| your current credential packet | your current submission packet | Premium FAQ |
| Your facts, dates & credentials | Your facts, dates & qualifications | Resume enhancer |
| When a credential is approaching | When a document is approaching | Test email |
| Credentials · Credanta (page title) | Professional Portfolio · Credanta | Documents page title |
| Browse all credentials | Browse all documents | Dashboard footer |
| modal: all documents, and credentials | all uploaded documents | Account delete modal |

## Intentionally Preserved

| Term | Location | Reason |
|---|---|---|
| `{# matches credentials page #}` | dashboard.html line 9 | Jinja2 code comment, not user-facing |
| "credentialed fields" | about.html | Industry adjective for licensed professionals; not app concept |
| "Credentialing team" | share_view.html feedback form | Real industry job-title used by hospitals/agencies |

## Files Modified

- `app/templates/base.html`
- `app/templates/dashboard.html`
- `app/templates/documents.html`
- `app/templates/premium.html`
- `app/templates/premium_checklist.html`
- `app/templates/premium_reminders.html`
- `app/templates/premium_agency.html`
- `app/templates/premium_calendar.html`
- `app/templates/premium_resume.html`
- `app/templates/share_view.html`
- `app/templates/login.html`
- `app/templates/about.html`
- `app/templates/account.html`
- `app/templates/security_overview.html`
- `app/templates/document_security.html`
- `app/templates/admin.html`
- `app/templates/admin_recruiter_feedback.html`
- `app/templates/email/reminder.html`
- `app/templates/email/expired.html`
- `app/templates/email/test.html`
