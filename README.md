# VRIOSCU website

Official website and account platform for **VRIOSCU — Endpoint Validation & Evidence Capture**.
*Validate. Capture. Document.*

The Windows desktop application is the product: it validates endpoints, captures
evidence, collects local machine/network details and generates PDF reports.
This website is the companion platform: **Discover → Explain → Authenticate → Support → Distribute.**
It never pretends to collect machine or network information from a browser, and
it never receives validation runs, screenshots or reports.

## Stack

| Layer      | Choice | Why |
|------------|--------|-----|
| Web/API    | Python 3.11+, Flask 3, Jinja2 server-rendered pages | Few dependencies, every page works without JavaScript |
| Database   | SQLite (WAL mode) behind a repository layer | No separately managed database; swappable for PostgreSQL later |
| Export     | openpyxl (.xlsx) | Authorised Excel exports |
| App server | gunicorn on 127.0.0.1 | Behind nginx |
| Edge       | nginx + Let's Encrypt on the existing EC2 instance | HTTPS, static files, coarse rate limiting |

Runtime dependencies: `Flask`, `openpyxl`, `gunicorn` (see `requirements.txt`). Nothing else.

## Quick start (development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # defaults work for local development
flask --app wsgi init-db              # applies migrations
flask --app wsgi create-admin         # prompts for username, email, password
flask --app wsgi run --port 5000      # http://127.0.0.1:5000
```

Optional:
- Add the self-hosted fonts described in `app/static/fonts/README.md`.
- Generate the social share image: `pip install pillow && python scripts/make_og_image.py`.

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

99 tests, standard library only (no pytest needed). See `docs/TEST_REPORT.md`.

## Project layout

```
app/
  __init__.py          application factory, request lifecycle, error handling, CLI
  config.py            ALL product & environment configuration (single source of truth)
  db.py                SQLite connections, transactions, migration runner
  security.py          CSRF, rate limiting, security headers, access control
  validation.py        declarative input validation
  forms.py             field sets shared by HTML forms and the JSON API
  repositories/        the only code that contains SQL
  services/            auth/sessions, release rules, Excel export
  routes/              public, auth, account, admin, api (v1)
  templates/ static/   UI
migrations/            numbered .sql migrations
scripts/               backup_db.py, restore_db.py, maintenance.py, make_og_image.py
deploy/                nginx, systemd units, gunicorn config
docs/                  everything else
tests/                 unittest suite
```

## Documentation

| Document | Contents |
|----------|----------|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Boundaries, request flow, layers, PostgreSQL migration path |
| [API](docs/API.md) | Every endpoint, auth, errors |
| [DATABASE](docs/DATABASE.md) | Schema, migrations, data minimisation |
| [ENVIRONMENT](docs/ENVIRONMENT.md) | Every environment variable |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | EC2 step-by-step |
| [SECURITY_CHECKLIST](docs/SECURITY_CHECKLIST.md) | Controls and how each is implemented |
| [BACKUP_RESTORE](docs/BACKUP_RESTORE.md) | Backup, restore, off-host copies |
| [EXCEL_EXPORT](docs/EXCEL_EXPORT.md) | Datasets, columns, safeguards |
| [RELEASE_MANAGEMENT](docs/RELEASE_MANAGEMENT.md) | Publishing installers, update API |
| [TEST_REPORT](docs/TEST_REPORT.md) | What is tested and the latest result |
| [PRODUCTION_READINESS](docs/PRODUCTION_READINESS.md) | Go-live checklist and known gaps |

## Content rules for contributors

- Brand is **VRIOSCU**. Never "Vristu", "Vristu Screenshot Analysis" or "Artifact Validator".
- Don't invent customers, user counts, certifications, integrations, statistics or compliance claims.
- Don't describe the installer as signed, verified or certified unless `INSTALLER_SIGNED=true` is actually true.
- Never tell users to disable SmartScreen, Smart App Control, Defender or other security controls.
- Product values (version, channel, URLs, contacts) come from `app/config.py`; don't hard-code them in templates.
  GDrive - https://drive.google.com/file/d/1zW04Qogu_roVOeBISabjBJknXTVS-nBB/view?usp=sharing
  GDrive (Final_10thOct) - https://drive.google.com/file/d/1CYfUmyxPg5FlfmgQrO0FRcuXhxFcoPUp/view?usp=sharing
  
----------APPLICATION-------------------------
# VRIOSCU — Intelligent Validation & Reporting

**VRIOSCU** is an enterprise-grade Windows desktop application built for automated web endpoint validation, high-fidelity visual evidence capture, intelligent anomaly analysis, and forensic-quality PDF audit reporting. 

Designed for compliance officers, quality assurance engineers, security auditors, and digital forensics teams, VRIOSCU bridges the gap between automated testing and regulatory-grade documentation.

---

## 1. Application Overview & Purpose

Modern digital operations require transparent, tamper-evident verification of web endpoints, digital assets, online disclosures, and web services. Manual screenshot capture and ad-hoc documentation are slow, error-prone, and lack the technical rigor required for regulatory scrutiny and compliance audits.

**VRIOSCU** streamlines this entire workflow into a unified desktop environment:
- **Target Audience:** Security Auditors, QA Engineers, Regulatory & Compliance Specialists, Brand Protection Teams, and IT Operations Professionals.
- **Core Value Proposition:** Fully automated validation workflows that combine headless and live browser automation, deep network telemetry capture, computer-vision layout inspection, AI-assisted anomaly detection, and instant generation of publication-ready, multi-page PDF audit reports.
- **Privacy & Security Philosophy:** Operates strictly on a client-side execution model where operational artifacts, sensitive network captures, and generated documentation remain stored within the user's local secure environment (`%LOCALAPPDATA%\VRIOSCU`), maintaining enterprise data governance and confidentiality.

---

## 2. Key Features

- **Multi-URL Batch Processing & Queue Management:**
  - Ingest URL queues via single entry, multi-line lists, or CSV/text bulk imports.
  - Granular execution controls with real-time status indicators (Queued, Running, Completed, Warning, Failed).

- **Precision Visual Capture & Multi-Device Emulation:**
  - Automated full-page, above-the-fold, and custom viewport visual capture using Chromium automation.
  - Multi-device profile emulation (Desktop 1920x1080, Laptop 1366x768, Tablet 768x1024, Mobile 375x812).
  - Configurable page stabilization, anti-detection measures, cookie banner mitigation, and network idle wait states.

- **Forensic Network Telemetry & Diagnostic Logging:**
  - Deep inspection of HTTP/HTTPS response codes, TLS/SSL certificates, server headers, and redirect chains.
  - DNS resolution mapping, IP endpoint attribution, and performance timing breakdowns (TTFB, DOM load, total transfer time).
  - Captures complete console message histories, JavaScript runtime exceptions, and missing network resource errors.

- **AI-Powered Visual & Structural Analysis:**
  - Automated visual layout validation, typography rhythm assessment, and color contrast scoring.
  - Detection of broken layouts, overlapping elements, unrendered assets, HTTP errors, and compliance disclaimers.
  - Generates executive-ready summary assessments and severity-ranked remediation recommendations.

- **Enterprise Report Library & Historical Archive:**
  - Centralized local repository indexing all historical validation batches and generated reports.
  - Fast search, date-range filtering, tag-based categorization, and one-click report retrieval.
  - Direct folder navigation to raw image assets, JSON metadata, and final PDF deliverables.

- **Customizable Branding & Cover Page Layouts:**
  - Configurable organization metadata, auditor identity, custom branding logos, and confidential classification badges.
  - Multiple professional cover designs (Modern Corporate, Technical Audit, Minimalist, Executive Summary).

---

## 3. User Interface & Experience

The VRIOSCU desktop application features an intuitive, modern, dark-themed user interface designed for high-density information display and seamless task navigation.

### User Journey & Interface Map

#### A. First-Launch Onboarding & Operator Profile
The introductory setup screen welcomes operators on first launch, collecting local profile metadata (operator name, organization, contact, audit purpose) to ensure all subsequent generated reports carry authenticated auditor attribution.

![First-Launch Onboarding and Profile Setup](assets/screenshots/01_onboarding_profile_setup.png)

---

#### B. Main Workspace & Operational Dashboard
The central command center providing system health status, active configuration profiles, quick-launch actions, and a high-level summary of recent validation activity and report generations.

![Main Workspace Dashboard](assets/screenshots/02_main_dashboard.png)

---

#### C. Batch URL Ingestion & Configuration Hub
The primary input console where users input target URLs, configure viewport resolutions, select network capture depths, set retry policies, and define custom authentication headers.

![Batch URL Ingestion and Execution Configuration](assets/screenshots/03_batch_url_input.png)

---

#### D. Live Capture Engine & Execution Monitor
Real-time visual monitoring console displaying concurrent browser automation threads, live execution logs, progress meters, and dynamic status badges as each endpoint is inspected and captured.

![Live Capture Engine and Execution Monitor](assets/screenshots/04_live_execution_monitor.png)

---

#### E. AI Evidence Review & Quality Inspector
Interactive inspection panel enabling users to review captured visual evidence side-by-side with extracted network telemetry, console logs, and automated AI structural evaluations before final report compilation.

![AI Evidence Review and Inspection Workspace](assets/screenshots/05_ai_evidence_review.png)

---

#### F. Report Library & Historical Archive
A searchable, filterable repository of all completed validation runs, offering immediate previews of generated PDF reports, metadata inspection, and direct access to raw capture artifacts.

![Report Library and Historical Archive](assets/screenshots/06_report_library.png)

---

#### G. Application Settings & Engine Configuration
Comprehensive settings dashboard allowing operators to fine-tune browser automation parameters, PDF rendering engines, proxy settings, AI inspection thresholds, and local storage retention policies.

![Application Settings and Engine Configuration](assets/screenshots/07_application_settings.png)

---

## 4. System-Generated Reports

VRIOSCU features a built-in, automated PDF publishing engine that compiles technical telemetry, visual evidence, and AI analysis into formal, presentation-ready audit documentation.

![System Generated Audit PDF Report Layout](assets/screenshots/08_pdf_report_overview.png)

### Structure of the PDF Audit Report

1. **Executive Cover Page:**
   - Document title, classification badge (Confidential, Internal Audit, Public Verification).
   - Target URL batch overview, execution timestamp (UTC/Local), and total duration.
   - Operator credentials, organization branding logo, and audit tracking identifier.

2. **Executive Summary & Compliance Scorecard:**
   - High-level pass/warning/fail metrics across all inspected endpoints.
   - Core health indicators (Security/HTTPS, Performance, Accessibility, Visual Integrity).
   - AI-generated executive narrative summarizing critical findings.

3. **Detailed Endpoint Evidence Cards:**
   - **Visual Proof:** High-resolution, scaled full-page or viewport screenshots framed with pixel-precise dimensions and timestamp watermarks.
   - **Network & Security Matrix:** Final HTTP status, IP address, TLS protocol/cipher, page response time, and total transfer size.
   - **Diagnostic Log Trace:** Extracted JavaScript console warnings, unhandled errors, and failed network sub-requests (4xx/5xx).

4. **AI Structural & Quality Assessment:**
   - Layout integrity ratings, color contrast ratios, font scale consistency, and DOM complexity metrics.
   - Specific, itemized recommendations for visual and technical remediation.

5. **Compliance & Audit Appendix:**
   - Machine environment fingerprint (Chromium engine version, OS build, screen DPI, viewport geometry).
   - Cryptographic SHA-256 integrity hashes for each raw screenshot asset to ensure legal defensibility and tamper evidence.

---

## 5. Tech Stack Summary

- **Platform & Desktop Architecture:** Windows Desktop Application (x64) with native local process orchestration and `%LOCALAPPDATA%` sandboxed workspace management.
- **Core Runtime & Logic:** Python 3.11+ leveraging multi-threaded asynchronous workers for non-blocking I/O and parallel execution.
- **User Interface Layer:** High-performance local web rendering framework utilizing HTML5, modern Vanilla CSS (custom design system, responsive glassmorphism, fluid typography), and modular JavaScript.
- **Embedded Web Server:** High-throughput Python WSGI/Waitress HTTP server running strictly on local loopback (`127.0.0.1`) for secure internal IPC.
- **Browser Automation Engine:** Playwright / Chromium headless & headed automation subsystem optimized for high-fidelity rendering, web-font synchronization, and network event interception.
- **Document & PDF Generation:** Enterprise ReportLab PDF engine paired with Pillow (PIL) for image optimization, vector graphics rendering, and dynamic page layout pagination.
- **Computer Vision & AI Evaluation:** Deep layout analysis routines, DOM geometry inspection algorithms, and automated contrast/structure analysis modules.

---

## 6. How to Run & Use

### User Workflow Overview

```
[ Enter URLs / Batch Import ] 
             │
             ▼
[ Configure Capture & Audit Options ] 
             │
             ▼
[ Start Automated Validation Run ] 
             │
             ▼
[ Review Real-Time Progress & AI Insights ] 
             │
             ▼
[ Generate & Export Comprehensive PDF Report ]
```

### Step-by-Step Operation Guide

1. **Launch the Application:**
   - Start VRIOSCU from the Windows Start Menu, desktop shortcut, or application directory.
   - On first launch, complete the brief Operator Profile setup.

2. **Input Target Endpoints:**
   - Navigate to the **Batch Input** section on the main dashboard.
   - Paste one or more target URLs (e.g., `https://example.com/login`, `https://example.com/pricing`) or click **Import File** to load a `.txt` or `.csv` list.

3. **Select Execution Profile:**
   - Choose your desired device viewport (Desktop, Tablet, Mobile).
   - Select visual capture mode (Full Page, Above the Fold, or Custom Area).
   - Enable or disable AI Visual Analysis and Network Diagnostic Logging according to your audit scope.

4. **Execute Validation Run:**
   - Click **Run Validation**.
   - Monitor live progress in the **Execution Console** as the automation engine navigates to each URL, settles dynamic content, captures high-resolution screenshots, and logs network events.

5. **Review Evidence & Generate Report:**
   - Once the run completes, inspect individual capture cards and AI diagnostic scores in the review workspace.
   - Click **Generate PDF Report**.
   - Select your desired cover style and document classification.
   - The compiled PDF report will automatically open in your default viewer and be archived in the **Report Library** for future retrieval.

---

## 7. License & Compliance

*Copyright © 2026 VRIOSCU. All rights reserved.*

*VRIOSCU is engineered with a privacy-by-design architecture. No client validation payloads, screenshots, or generated audit reports are transmitted to external servers without explicit user consent. All operational data remains strictly within the local host environment.*
