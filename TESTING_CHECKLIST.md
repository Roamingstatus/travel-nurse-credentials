# Credanta — Manual Testing Checklist

Use this checklist for UI, browser, accessibility, and mobile validation that
automated tests cannot cover. Run before any significant release.

---

## 1. Browser & Responsive Layout

Test each page at three viewport widths:
- **375 px** — mobile (iPhone SE)
- **768 px** — tablet (iPad)
- **1440 px** — desktop

| Page | 375 px | 768 px | 1440 px | Notes |
|---|---|---|---|---|
| `/login` | ☐ | ☐ | ☐ | Google button centered, hero text visible |
| `/dashboard` | ☐ | ☐ | ☐ | Status cards stack cleanly |
| `/documents` | ☐ | ☐ | ☐ | Document cards don't overflow |
| `/documents/upload` | ☐ | ☐ | ☐ | Form fields full-width on mobile |
| `/premium` | ☐ | ☐ | ☐ | Pricing cards readable |
| `/premium/reminders/settings` | ☐ | ☐ | ☐ | Toggle switches usable |
| `/premium/calendar` | ☐ | ☐ | ☐ | URL copy button works |
| `/account` | ☐ | ☐ | ☐ | Sections stack correctly |
| `/s/{token}` (share view) | ☐ | ☐ | ☐ | Works on mobile for recruiters |
| `/admin/recruiter-feedback` | ☐ | ☐ | ☐ | Tables scroll horizontally |

---

## 2. Document Interactions

### Upload
- [ ] PDF uploads and appears in list
- [ ] JPEG/PNG uploads correctly
- [ ] DOCX uploads correctly
- [ ] EXE is rejected with clear error message
- [ ] JS file is rejected
- [ ] File over 25 MB shows size error
- [ ] Empty file shows error
- [ ] Duplicate file (same content) shows duplicate warning

### Preview
- [ ] PDF opens inline in browser
- [ ] Image files display correctly
- [ ] DOCX triggers download (not inline)
- [ ] File missing from disk shows graceful 404

### Cards
- [ ] Expired document card has red status border
- [ ] Expiring soon card has amber/yellow border
- [ ] Valid card has green border
- [ ] Hover preview appears on desktop
- [ ] Tap works correctly on mobile (no hover dependency)

---

## 3. Document Status & Expiration

- [ ] Document expiring in 7 days shows "expiring soon" label
- [ ] Document expired yesterday shows "expired" label
- [ ] Document with no expiry date shows "valid" / no status border
- [ ] NIH Stroke Scale doc with issue date auto-calculates 1-year expiry (2 years default)
- [ ] Dashboard summary counts match the document list

---

## 4. Share Links

- [ ] Premium+ user can create a share link
- [ ] Generated link opens at `/s/{token}`
- [ ] Only selected/linked documents appear on the share page
- [ ] Revoked link returns 404
- [ ] Expired link returns 404
- [ ] Public share page loads without logging in

### Recruiter Feedback Modal
- [ ] "Suggest Common Requirements" button opens modal
- [ ] All 4 steps navigate correctly (Role → Documents → Timing → Agency)
- [ ] Back navigation works
- [ ] Submission shows success step
- [ ] If Turnstile is configured, widget appears before submit
- [ ] Modal closes on overlay click
- [ ] Modal closes with Escape key

---

## 5. Premium Gating

- [ ] Free user: `/packet` redirects to upgrade page (not 500)
- [ ] Free user: `/premium/reminders/settings` shows 403 or upgrade prompt
- [ ] Free user: `/share` shows upgrade prompt
- [ ] Premium user: packet download works
- [ ] Premium user: email reminders can be enabled
- [ ] Premium user: SMS toggle is shown but marked "Premium+" only
- [ ] Premium+ user: share link creation works
- [ ] Premium+ user: calendar feed URL is shown

---

## 6. Reminders

- [ ] Premium user can enable email reminders
- [ ] Reminder email address can be set independently of login email
- [ ] Saving settings shows confirmation flash
- [ ] Dev trigger button (if visible) sends test email without crashing
- [ ] Dev trigger shows clear error if Resend key is not set

---

## 7. Accessibility

### Keyboard Navigation
- [ ] Tab order through login page is logical
- [ ] Dashboard is navigable by keyboard
- [ ] Upload form is usable with keyboard only
- [ ] Modal (feedback) can be opened and closed with keyboard
- [ ] Escape key closes the feedback modal

### Labels & Contrast
- [ ] All form inputs have visible labels (not just placeholders)
- [ ] All icon-only buttons have `aria-label` attributes
- [ ] Status colors (expired/expiring/valid) also have text labels — not color alone
- [ ] Text contrast meets WCAG AA (4.5:1 minimum) in both light and dark mode

### Screen Reader (spot check)
- [ ] Page headings use proper `<h1>`, `<h2>` hierarchy
- [ ] Document cards have meaningful `alt` or `aria-label` text
- [ ] Flash messages are announced (live region or focus management)

---

## 8. Error & Edge States

- [ ] Missing `GOOGLE_CLIENT_ID` shows friendly "not configured" message on `/login`
- [ ] Missing `RESEND_API_KEY` — reminder settings loads without crashing
- [ ] Missing `TWILIO_*` keys — SMS toggle shows "coming soon" gracefully
- [ ] Stripe not configured — upgrade page loads without crashing
- [ ] Packet with zero documents — redirects to dashboard with flash message
- [ ] Share page for deleted/missing documents — page still loads, missing docs skipped

---

## 9. Dark Mode

- [ ] Toggle switches between light and dark themes
- [ ] Preference persists across page navigation
- [ ] No elements become unreadable in dark mode
- [ ] Status colors (red/amber/green) remain distinct in dark mode

---

## 10. MFA

- [ ] TOTP setup page renders QR code
- [ ] Incorrect code shows error, does not lock out immediately
- [ ] Recovery codes are displayed exactly once at setup
- [ ] MFA-protected action (delete document) prompts for verification when MFA is enabled

---

## Sign-Off

| Tester | Date | Environment | Version/Commit |
|---|---|---|---|
| | | | |
