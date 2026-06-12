# Threat Model

## Project Overview

Travel Nurse Credentials is a FastAPI application for storing professional credential documents, tracking expirations, and sharing recruiter-facing credential packets. It uses Google OAuth for login, Starlette session cookies for authenticated web sessions, SQLite for application data, and the local filesystem for uploaded documents and feedback screenshots. The current production deployment is publicly reachable at its primary domain rather than password-gated, so the attacker model includes the unrestricted public internet in addition to authenticated users, users who possess shared bearer links or feed URLs, and admins.

## Assets

- **User accounts and session state** — Google-linked accounts, session cookies, MFA state, recovery codes, and share/calendar bearer tokens. Compromise enables account takeover or unauthorized document access.
- **Uploaded credential documents** — licenses, certifications, resumes, onboarding files, and derived previews. These are the highest-sensitivity assets because they can contain PII, professional identifiers, and licensing details.
- **Recruiter/share artifacts** — share links, download tokens, packet exports, and calendar-feed URLs. These are bearer secrets that gate access to private document metadata or files.
- **Administrative data** — feedback submissions, analytics, security events, admin access logs, and export files. These flows matter because attacker-controlled content is rendered or exported for admins.
- **Application secrets and third-party credentials** — `SESSION_SECRET`, Google OAuth secrets, Stripe credentials, Turnstile secret, email/SMS provider credentials. Leakage would undermine authentication, billing, or anti-abuse controls.

## Trust Boundaries

- **Browser ↔ application server** — all client input is untrusted, including multipart uploads, JSON bodies, and form fields.
- **Application server ↔ SQLite/filesystem** — the server can read and write sensitive documents, screenshots, tokens, and admin data locally; authorization and path controls must be correct before any file/database access.
- **Public internet/unauthenticated ↔ authenticated user** — internet-reachable surfaces include `/, /login`, OAuth routes, `/healthz`, Stripe webhook, recruiter feedback, share-link routes, and calendar feeds; most sensitive features should still require a valid session or a high-entropy bearer secret.
- **Authenticated user ↔ admin** — admin dashboards and exports consume attacker-influenced data and therefore need strong server-side access control plus safe rendering/export handling.
- **Application server ↔ third parties** — Google OAuth, Stripe, Cloudflare Turnstile, and optional email/SMS providers are external trust boundaries whose responses must be validated and whose secrets must stay server-side.

## Scan Anchors

- `app/main.py` is the primary production route surface, including uploads, document analysis/scan helpers, share links, calendar feeds, billing webhook, feedback, admin views, reminders, MFA, and premium features.
- `app/security.py` contains upload validation, rate limiting, CSRF, CSP, Turnstile verification, and download-token logic.
- `app/storage.py`, `app/packet.py`, and `app/reminders.py` are the main filesystem/export paths.
- Highest-risk production areas: file uploads/previews, document analysis/scan helpers, share/bearer-token routes, reminder/test-message endpoints, admin exports, billing webhook, and MFA/session handling.
- Likely dev-only or lower-priority surfaces: admin testing utilities and explicit dev helpers; skip unless production reachability is demonstrated.

## Threat Categories

### Spoofing

The application relies on Google OAuth, session cookies, MFA, admin gating, and bearer tokens for shared resources. Protected routes must require a valid session, accounts with MFA enabled must not receive normal application access until the second factor is satisfied, admin routes must enforce admin status server-side on every request, and bearer URLs must be long, unguessable, and revocable. Webhooks and OAuth callbacks must verify the upstream service rather than trusting caller-controlled input.

### Tampering

Users can submit forms, JSON payloads, uploads, feedback, recruiter responses, and premium workflow inputs. The server must validate categories, file types, MIME/content, and privileged state changes server-side rather than trusting template or JavaScript controls. Exported packets, share downloads, and calendar feeds must only include data already authorized for the requesting subject.

### Information Disclosure

This project stores sensitive professional documents and document-derived metadata. Every document read, preview, packet export, share route, and calendar feed must be scoped to the correct owner or bearer token, and logs/error messages must avoid leaking secrets or document contents. Admin dashboards and exports must not expose more user data than intended, and uploaded files must not become a path to read arbitrary local files.

### Denial of Service

The app accepts file uploads, document analysis and malware-scan requests, preview generation, recruiter feedback, reminder/test-message requests, AI-assisted resume processing, and webhook traffic. Production routes must enforce size limits and rate limits before expensive reads or parsing so one user cannot exhaust memory, disk, CPU, or outbound API quotas. Abuse controls are especially important on endpoints that accept multipart bodies, trigger OCR/PDF parsing, or send email/SMS through third-party providers.

### Elevation of Privilege

The main privilege boundaries are user-to-user document isolation and user-to-admin separation. Routes that accept document IDs, share tokens, feedback IDs, or export requests must enforce ownership/admin checks server-side every time. Any attacker-controlled input that reaches admin browsers or spreadsheet tooling is also a privilege-boundary concern because it can turn low-privilege input into admin-side code execution or exfiltration.
