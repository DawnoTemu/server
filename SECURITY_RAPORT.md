# Security Report – DawnoTemu backend

## Scope & Method
- Repository: `server/` (Flask API, Celery workers, admin UI).
- Reviewed configs (`app.py`, `config.py`), auth/session middleware, routes/controllers, models, Celery tasks, utilities (S3/email/voice services), Docker setup, and templates. No dynamic tests or dependency scanners were run.

## Strengths
- Critical configuration validated on startup; S3 uploads default to private ACL with optional SSE and short-lived presigned URLs (`config.py`, `utils/s3_client.py`).
- Access tokens are short-lived (15m) and invalidated on profile updates via `updated_at` check; email reset/confirm endpoints avoid account enumeration (`controllers/auth_controller.py`, `utils/auth_middleware.py`).
- Production CORS is limited to `*.dawnotemu.app`; beta/admin data paths are protected by JWT or API keys.
- Background cleanup for account deletion includes S3 purging and credit refunds to avoid orphaned PII and billing drift (`models/user_model.py:148-237`).

## Findings
### High Risk
1) **Admin UI lacks CSRF and hardened cookies**  
   - Flask-Admin login and actions use a shared password with no CSRF tokens or per-request anti-replay, and rely on default Flask session cookie flags (no `Secure`/`HttpOnly`/`SameSite`) (`admin.py:475-547`, `app.py:43-55`). An authenticated admin visiting a malicious site could have privileged actions triggered; session cookies are also at risk on non-HTTPS deployments.  
   - **Fix:** Enable CSRF protection for admin forms, set `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE=strict`, force HTTPS, and prefer individual admin accounts with MFA-capable auth.

2) **Unvalidated remote image ingestion (SSRF)**  
   - `upload_story_with_image` downloads arbitrary `image_url` and uploads it to S3 without host/scheme validation or size limits (`controllers/admin_controller.py:245-304`). A malicious URL can hit internal metadata services, open file descriptors, or exhaust worker memory.  
   - **Fix:** Allowlist hosts/schemes, enforce max content length, and proxy/scan images before upload.

3) **Authentication endpoints lack brute-force throttling**  
   - Login, register, refresh, and reset flows have no rate limiting (`routes/auth_routes.py:10-170`), enabling credential stuffing and token guessing.  
   - **Fix:** Apply per-IP/user rate limits or CAPTCHA on auth endpoints using a shared backend (Redis) rather than the current in-memory limiter.

### Medium Risk
1) **Refresh tokens remain valid after credential changes**  
   - Refresh verification does not check `updated_at` or any token identifier; a stolen refresh token can continue issuing new access tokens after password/email changes or deactivation (`controllers/auth_controller.py:96-133`). Only access tokens are invalidated via `token_required`’s `iat` check (`utils/auth_middleware.py:56-68`).  
   - **Fix:** Store refresh JTIs with revocation on password resets/deactivation, rotate refresh tokens on use, and bind them to device/user agents.

2) **File upload hygiene is minimal**  
   - Voice uploads rely solely on extension checks before streaming to S3 and downstream processing (`controllers/voice_controller.py:12-55`). There are no MIME checks, size caps, or malware scanning, leaving room for oversized or disguised files to trigger DoS or exploit parsers.  
   - **Fix:** Enforce max upload size, validate MIME/headers, run AV scanning (e.g., ClamAV/Lambda), and reject files lacking expected audio characteristics.

3) **PII sent to Sentry by default**  
   - Sentry is initialized with `send_default_pii=True` for both Flask and Celery (`app.py:16-28`, `tasks/__init__.py:1-30`), so headers, IPs, and possibly Authorization tokens/PII are forwarded to a third party without scrubbing rules.  
   - **Fix:** Disable PII collection or add scrubbing for auth headers, email, and token values; confirm a DPA exists with Sentry.

4) **Static admin API keys without hardening**  
   - Bulk story/admin ingestion uses static API keys read from env and compared via plain string equality with no rate limits or audit trail (`utils/auth_middleware.py:158-189`). If leaked, keys remain valid indefinitely.  
   - **Fix:** Store hashed keys, compare with `hmac.compare_digest`, add rotation/expiry and logging, and rate-limit these endpoints.

### Low Risk / Observations
1) **Rate limiter not production-safe** – In-memory buckets (`utils/rate_limiter.py:11-35`) do not work across workers/hosts and key on raw `remote_addr`, which will be proxy IPs unless `ProxyFix`/`X-Forwarded-For` is honored.
2) **Password policy is minimal** – Only length ≥8 is enforced (`utils/validators.py:12-19`); consider complexity, breach checks, and MFA for admin accounts.
3) **Development secrets in compose** – Docker Compose ships default Postgres/MinIO credentials and enables ports (`docker-compose.yml`); safe for local use but must not be reused in staged/prod clusters.
4) **Repository ships SQLite artifact** – `instance/schema_tmp.db` is versioned locally; ensure it does not contain real data and add to gitignore if unnecessary.
5) **Dependency posture unknown** – No automated vulnerability scan observed; versions like `requests==2.31.0` are behind current releases. Run `pip-audit`/`safety` in CI.

## Recommended Next Steps
- Harden session and admin surface: enable CSRF, secure cookies, per-admin accounts, and HTTPS-only deployment; add audit logging for admin/API-key actions.
- Implement distributed rate limiting (Redis) on all auth/token issuance endpoints; consider CAPTCHA after failed attempts.
- Introduce refresh-token rotation with server-side revocation and device binding; invalidate all tokens on password reset/deactivation.
- Gate outbound fetches (`image_url`) behind allowlists and size/timeout controls; deploy AV and MIME validation for all uploads.
- Reduce data leakage: disable `send_default_pii` or configure Sentry scrubbing; avoid logging secrets; ensure `.env`/DB artifacts are excluded from commits.
- Add security checks to CI: dependency audit, secret scanning, and container image scanning; verify Docker defaults are not used outside local dev.
