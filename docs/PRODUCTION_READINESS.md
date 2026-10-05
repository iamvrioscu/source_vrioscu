# Production readiness checklist

Work through this before pointing `vrioscu.com` at the server.

## Must do before launch

- [ ] `APP_ENV=production`, a fresh random `SECRET_KEY` (≥32 chars), `BASE_URL=https://vrioscu.com`
- [ ] `TRUSTED_PROXY_COUNT=1` (behind nginx)
- [ ] `DATABASE_PATH=/var/lib/vrioscu/vrioscu.db`; `ls -l` shows `-rw------- vrioscu vrioscu`
- [ ] `/etc/vrioscu/vrioscu.env` is `root:vrioscu 0640`; no `.env` in the repo
- [ ] **Confirm `WINDOWS_COMPATIBILITY`** matches platforms you have actually tested
- [ ] `INSTALLER_SIGNED` reflects reality (`false` for the unsigned 1.0.0 beta)
- [ ] Installer hosted at HTTPS; `DOWNLOAD_ALLOWED_HOSTS` set to that host
- [ ] Release 1.0.0 created in Admin → Releases with the **real** SHA-256 and size, then published
- [ ] Downloaded the file via the site and confirmed `Get-FileHash` matches the published value
- [ ] Real `SUPPORT_EMAIL` / `PRIVACY_EMAIL` set, or deliberately left empty (contact form is then the route)
- [ ] Privacy page reviewed by whoever is accountable for data protection; `PRIVACY_NOTICE_VERSION` set
- [ ] Self-hosted fonts added (`app/static/fonts/README.md`)
- [ ] `app/static/img/og.png` generated (`python scripts/make_og_image.py`)
- [ ] Brand assets replaced if the official VRIOSCU logo differs from the placeholder mark
       (`app/templates/partials/mark.html`, `app/static/img/favicon.svg`, `app/static/img/og.png`)
- [ ] First admin created with `flask create-admin`; strong unique password stored in a password manager
- [ ] Test suite passes on the server: `python -m unittest discover -s tests -t .`
- [ ] TLS certificate issued; `certbot renew --dry-run` succeeds
- [ ] Security group: 80/443 public, 22 restricted (or closed with SSM), 8000 closed
- [ ] `curl -sI https://vrioscu.com` shows HSTS, CSP, X-Frame-Options, nosniff, Referrer-Policy
- [ ] `/static/../instance/vrioscu.db`, `/.env`, `/vrioscu.db` all return 404
- [ ] `vrioscu-backup.timer` enabled; one manual backup taken and **test-restored**
- [ ] Off-host backup in place (EBS snapshot policy or S3)

## Functional smoke test (production, by hand)

- [ ] Every public page loads on desktop and phone: Home, Product, Features, How it works, Use cases, Public Beta,
      Download, Documentation, Privacy, Contact
- [ ] Register → lands on profile; product updates default off
- [ ] Sign out → sign in with email, then with username
- [ ] Five wrong passwords → lockout message
- [ ] Profile edit, preference toggle, password change, data export, feedback all work
- [ ] Contact form submission appears in Admin → Support requests
- [ ] As a normal user, `/admin` returns 403
- [ ] Admin: export each dataset; open in Excel; no password/hash columns
- [ ] Download button redirects to the installer; count increments in Admin → Releases
- [ ] `GET /api/v1/releases/latest?current_version=0.9.0` returns `update_available: true`
- [ ] Submit a sitemap in search-engine webmaster tools; check `robots.txt`

## Known gaps (decide before or soon after launch)

| Gap | Impact | Suggested approach |
|---|---|---|
| No password-reset email | Users who forget passwords must contact support | Add SMTP/SES; time-limited single-use hashed reset tokens |
| No email verification | Accounts can be created with addresses the person doesn't own | Same mail provider; verify before sending product updates |
| No email sending for product updates | Subscribers are exported and emailed manually | Integrate a mail provider that honours unsubscribe |
| No MFA for admin accounts | Admin security rests on one password | TOTP for admins |
| Real report screenshots not used | Site shows report structure as a blank template | Add genuine, sanitised report page images once approved; don't use mock data |
| Single instance | Instance loss means downtime until restore | Acceptable for the beta; documented restore path |

## After launch

- [ ] Weekly: review `journalctl -u vrioscu` for `ERROR`, `auth.login_locked`, `rate_limit.exceeded`
- [ ] Monthly: `pip-audit`, OS updates, test-restore a backup
- [ ] On each release: follow `RELEASE_MANAGEMENT.md`
