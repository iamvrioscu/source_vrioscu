# VRIOSCU website and administration — 12 October 2026

## Product and repository audit

VRIOSCU is a Windows endpoint-validation and evidence-capture workflow:
**Validate → Capture → Analyze → Document**. A URL is the input; technical
observations, screenshots, interpretation and a professional report are the output.
The supplied UI shows run/deployment configuration, URL lists, CSV import,
capture settings, URL validation, presets and report generation. Monitors are
marked Coming Soon. No monitoring or security-scanner claims were added.

This checkout contains the companion Flask 3/Jinja website, SQLite repositories,
server-side sessions, account preferences, desktop-facing APIs, support/feedback,
release management, audit logging and Excel exports. The desktop validation and
AI engine source is outside this repository. The website neither validates live
endpoints nor uploads or processes desktop reports. Existing deployment and
authorization architecture remains intact; no frontend framework was introduced.

The starting website already had a dark redesign, a 13-page historical report
and workflow tabs. Its AI copy was outdated for the new report, its workflow was
static, and an independent environment flag suppressed published releases.
The new-task baseline was **103 tests: 102 passed, one Windows-specific POSIX
permission check skipped**. Public desktop/mobile baseline screenshots were
captured in an isolated browser before the new redesign.

## Public experience

- The first screen defines the product, explains fragmented validation work,
  demonstrates actual recorded metrics and previews the report output.
- The launch form follows the hero immediately, controlled by persistent settings.
- Six connected scroll scenes progress from URL through validation, capture,
  AI interpretation, documentation and client handover. A sticky evidence pane
  and scene links follow normal scrolling; mobile and no-JS layouts show the
  relevant real report images in each scene. Reduced motion removes transitions.
- The report showcase prominently pairs evidence with AI interpretation, includes
  a genuine unavailable-analysis example and offers zoom, keyboard panning,
  Escape-to-close and focus restoration. Full image links work without JavaScript.
- Shared theme tokens provide dark and light navigation, forms, previews, charts,
  modals and admin screens. An early self-hosted script applies system preference
  or a saved local preference before CSS paints. Manrope is self-hosted with its
  SIL OFL license; no external font or analytics requests are made.

## Report and image provenance

Primary source:
`VRIOSCU_Validation_Report_Client-Website-Verification-RUN_20261012_154441.pdf`.
All 23 pages were text-extracted and rendered for review. The website publishes
unmodified 900/1800-pixel WebP renders of pages **1, 3, 4, 10, 11 and 19**:
cover, summary, endpoint evidence, HTTP 403 review evidence, AI insights and
AI-unavailable state. The page-4 screenshot is extracted separately. The full
PDF and its internal-environment page are not distributed. Report images total
approximately 1.7 MB. `scripts/prepare_report_assets.py` reproduces the assets.

The report records 10 endpoints, eight passes and two review results. The hero
uses page-4 Google measurements: DNS 46 ms, TLS 1.3, HTTP 200, one redirect hop,
render 5.78 s. The scroll story uses the ChatGPT page-10/11 evidence: DNS 1 ms,
HTTP 403, render 2.82 s and the captured title “Just a moment...”. These are dated
historical observations, not present endpoint status.

The report labels its interpretation engine **VRIOSCU Hybrid Diagnostic Engine**,
with **High (Deterministic Analysis)** confidence. This verifies recorded output,
not a live model integration or vulnerability-detection capability. Page 19
explicitly says AI analysis was unavailable while deterministic evidence remained.
The site keeps observed evidence, interpretation, human review and report delivery
distinct. No inference or simulated live processing was added.

The official embedded logo was extracted with its transparency mask. Existing
brand colors and proportions are retained in navigation, favicon and social image.

The built-in imagegen tool created the consultant illustration, saved as
`app/static/img/consultant-report.webp` and `consultant-report-small.webp`.
It is explicitly captioned as AI-generated illustration, not an actual customer.
The actual page-11 report render was its supporting layout reference.

Final generation prompt:

> Create one high-quality photorealistic editorial photograph for the VRIOSCU software website. Landscape 1536 x 1024. A thoughtful, quietly satisfied technical consultant reviewing a professional endpoint validation report on a laptop with a colleague in a calm contemporary office, natural window light, understated neutral clothing and decor. The laptop screen is clearly visible at a plausible angle, showing a white portrait report with a dark navy header, cyan and violet accents, the exact heading 'AI VALIDATION INSIGHTS', and four neatly arranged sections 'Assessment', 'Key Observations', 'Potential Issues', 'Recommended Action'. The report resembles the VRIOSCU PDF reference: white paper, blue abstract footer, technical evidence, HTTP 403 review finding; no fabricated customer logos or testimonial text. Use the provided actual report page as the visual design reference for the screen. Composition feels candid and credible, screen and people both in focus, no holograms, no decorative floating graphics, no stock-photo handshake, no exaggerated celebration. This is an illustrative scenario, not a real customer. Reference image role: supporting report layout reference only.

## Releases

Published database releases are the sole authority. The configured public channel
is preferred; if it has no eligible release, the latest eligible Public Beta or
Stable release is selected by release date, then ID, matching existing sorting.
INTERNAL, DEV and drafts remain private. Destination validation applies again
when selecting public metadata and redirecting, including a changed host allowlist.
No environment URL fallback or separate publication gate can expose or hide a release.
The obsolete `PUBLIC_DOWNLOADS_ENABLED` flag has no effect.

Home, footer, product, documentation, release information and download pages
reflect the database state on every request. Public HTML and release APIs use
`Cache-Control: no-store`; static asset stamps invalidate older cached UI files.
Publishing, redirecting, unpublishing, deleting, channel fallback and changed
destination policy are tested. External installer bytes are not fetched in QA.

## Database and administrative changes

Migration `0004_launch_and_analytics.sql` is additive. It adds six tables:
`launch_settings`, `launch_subscribers`, `analytics_visitors`, `analytics_visits`,
`analytics_views`, `analytics_maintenance`, with appropriate constraints/indexes.
It does not drop or replace any existing table. Normal application startup or
`flask --app wsgi init-db` applies pending migrations.

**Admin → Launch Interest & Subscribers** manages visibility independently from
registration acceptance, plus heading, description, button and success copy.
Disabling registrations rejects direct POSTs inside the write transaction;
hiding the form alone does not disable its endpoint. Data survives both settings
changes and restarts. Names, normalized email, consent/notice version, registration
and update timestamps, status and nullable confirmation timestamp are persisted.
Duplicate submissions preserve existing identity and consent. Email ownership
is explicitly unverified. The existing project has no mail transport, so no
confirmation or launch emails are claimed or sent.

Search, pagination, sort, status filtering, counts, unsubscribe and deletion are
admin-only. Excel export uses existing authorization, CSRF, rate limiting, audit
and formula-neutralization safeguards. Account update preferences stay separate.

**Admin → Visitor analytics** shows active visitors, selected-period page views,
uniques and visits, visits today/7/30 days, an accessible traffic chart with daily
table, popular pages and the latest 50 events with first/last activity, referrer
host and browser/device categories. No raw IP, account ID, query string, full
referrer URL or full user agent is stored.

Analytics is off until explicit opt-in. DNT, GPC and authenticated users are
excluded. Random signed identifiers last up to 30 days; the consent-choice
cookie lasts 180 days. Withdrawal deletes the current browser's analytics rows.
Event IDs deduplicate retries; heartbeats cannot add page views or create visits.
A visit ends after 30 idle minutes. Active means activity in the past five minutes;
visible pages refresh activity once per minute. Reporting periods are IST calendar
days including today. Indexed queries are limited to 1/7/30/90 days, 15 popular
pages and 50 recent events. Daily cleanup on analytics activity/dashboard access
removes data older than 90 days. A quiet site is cleaned on the next such request.

All database writers retain UTC. A shared timezone-aware formatter converts
timestamps to **Asia/Kolkata**, e.g. `12 Oct 2026, 03:40:25 PM IST`. Historical
naive timestamps use the schema's documented UTC convention. Date-only release
dates remain calendar dates. Admin exports also display IST; personal data
portability exports retain their existing explicit UTC representation.

## Verification and local use

Run the full backend suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

Run the isolated browser workflow checker (requires requirements-dev and Chromium):

```powershell
.\.venv\Scripts\python.exe scripts/check_experience.py
```

It creates a disposable database and localhost server, uses an isolated Chromium
profile and blocks non-local network requests. It checks all public and admin
pages in both themes, mobile/tablet/desktop widths, scroll-linked panes, keyboard
tabs, report magnification, reduced motion, consent, launch form/settings and the
release lifecycle. It never changes the running website's data. Screenshot and
machine-readable results are written under ignored `tmp/redesign-v2/`.

`scripts/check_ui.py --base-url http://127.0.0.1:5097` checks an independently
running local website, including its public link/anchor inventory. Do not use
port 5001 if it belongs to the Windows desktop application's internal server.

Verification results: **121 backend tests: 120 passed, one Windows-specific
POSIX permission test skipped**. A subsequent focused run of 67 relevant tests
also passed (one same skip). **196 public/admin viewport-theme checks and 30
account checks passed**, including actual browser submissions and release changes,
with no JavaScript errors or failed responses. Desktop/mobile screenshots of both
themes, AI report pages, story scenes and the new admin tools were visually reviewed.
The separate public checker passed 65 page/viewport checks and 46 internal links
and anchors. All six tested primary/navigation button hover states met a 4.5:1
text contrast ratio in both themes; system theme and saved preference were checked.
Python compilation, JavaScript syntax and `git diff --check` passed.

For an existing deployment, update any explicit `PRIVACY_NOTICE_VERSION`
override to `2026-10-12` for the revised analytics and launch-interest notice.

Email delivery and independent verification of the desktop AI integration remain
outside the implemented website scope. Changes have not been deployed or published.

## Targeted follow-up: consent, releases and report cards

The automatic analytics popup, its footer trigger, popup JavaScript and styles
were removed. The footer now links directly to the existing Privacy page's
analytics settings. That page provides normal CSRF-protected opt-in and withdrawal
forms, works without JavaScript and shows the current choice. Existing choices,
records, DNT/GPC exclusions and withdrawal deletion remain unchanged. Browsers
without an allow choice send no analytics requests.

The release form and public download interface no longer display or request
SHA-256. Related copy buttons, PowerShell instructions and obsolete styles/scripts
were removed; installation guidance no longer refers to a missing checksum.
Migration `0005_optional_release_checksum.sql` relaxes the checksum constraint
using an atomic SQLite table copy. It preserves release IDs, original hashes,
timestamps, creator links, uniqueness constraints and download counts; foreign
keys remain enabled. No placeholder hash is generated. Optional API-provided
integrity metadata remains validated and available through the existing API/export.
Ordinary edits preserve recorded hashes; changing installer identity without
supplying a replacement checksum clears the old value. A new release without a
checksum stores NULL. A consistent local backup was made before this migration.

The homepage now uses `partials/report_rail.html`: five expanding cards backed by
actual report pages 3, 4, 11 and 10, plus the screenshot extracted from page 4.
The AI card has a violet/cyan accent. Desktop cards animate explicit widths over
620 ms; the caption uses a fixed expanded width and a 120 ms delayed reveal.
Hover, keyboard focus, arrow/Home/End keys and touch select a card. Phones use
a vertical expanding stack for readable report artwork and usable tap targets.
There is no autoplay or next/previous carousel. Explore opens the shared accessible
report viewer with zoom, keyboard panning, Escape and focus restoration. Without
JavaScript all five report links remain visible. Reduced motion removes delays.

The existing `/reports` gallery retains its real pages and shares the extracted
`partials/report_lightbox.html`; other product sections keep their existing layout.
No dependencies were added. Relevant backend checks passed: 38 tests, including
the release lifecycle without a hash, retained API metadata, consent controls,
and a migration from a populated pre-change database. The complete suite passed
124 tests: 123 passed, one platform-specific permission check skipped.

`python scripts/check_experience.py --targeted` passed **36 public/admin
viewport/theme checks and 12 five-card rail checks**. It exercised no consent
on load/refresh/navigation, opt-in/withdrawal through the Privacy page, release
publishing/redirect/unpublishing/deletion without a hash, every report card,
hover, keyboard, touch, reduced motion, zoom/focus return and no-JS links.
No console errors or failed responses occurred. Desktop and phone rail captures
in both themes and the phone report viewer were visually inspected. An observed
mouse-hover conflict during phone expansion was fixed by limiting hover to
desktop layouts and preserving keyboard focus until real pointer movement.
Native Privacy form redirects now have explicit navigation waits in the checker.
The local migration was applied after backup and existing release rows, download
counts and foreign-key integrity were checked again. Python compilation,
JavaScript syntax and `git diff --check` passed.
