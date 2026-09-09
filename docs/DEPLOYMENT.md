# INPROFIC deployment

INPROFIC supports both deployment shapes without separate settings files:

- PythonAnywhere: SQLite or PostgreSQL, local persistent media, and its Web-tab static mappings.
- Render: Daphne/ASGI, Supabase PostgreSQL, WhiteNoise static files, and Cloudflare R2 media.

The behavior is selected entirely by environment variables. Never commit `.env`, `.env.prod`, database passwords, payment secrets, or R2 credentials.

If PythonAnywhere and Render should be interchangeable front doors to the **same live system**, give both deployments the same Supabase `DATABASE_URL`, R2 settings, and `SECRET_KEY`. If PythonAnywhere keeps SQLite/local media, it remains a separate fallback environment whose data will diverge from Render. PythonAnywhere currently requires a paid account for unrestricted access to an external PostgreSQL service such as Supabase; verify outbound R2 access there as well.

## Render + Supabase + Cloudflare R2

### 1. Supabase database

Create a Supabase project, open **Connect**, and copy the **Session pooler** connection string (port `5432`). [Supabase recommends session mode](https://supabase.com/docs/guides/database/connecting-to-postgres) for persistent backends on IPv4-only networks. Replace the password placeholder with the URL-encoded database password and keep `sslmode=require` in the URL when Supabase provides it.

Use the resulting value only for Render's `DATABASE_URL`. Do not replace the SQLite URL in PythonAnywhere unless you intentionally want PythonAnywhere to use the same Supabase database.

### 2. Cloudflare R2 media

Create an R2 bucket and an API token limited to **Object Read & Write** on that bucket. [Cloudflare's S3 guide](https://developers.cloudflare.com/r2/get-started/s3/) supplies the access-key ID, secret, and endpoint in this form:

```text
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

For public storefront images, either attach a custom public domain such as `media.example.com`, or leave `R2_CUSTOM_DOMAIN` empty and INPROFIC will generate signed R2 URLs. A custom domain must be entered without `https://` in Render. If R2 is not desired on PythonAnywhere, leave all four required R2 credential variables empty and the existing local `MEDIA_ROOT` behavior remains active.

Existing database image fields contain object names, not image bytes. When moving an existing deployment to R2, copy the contents of the current local `media/` directory into the bucket's `media/` prefix while preserving all subdirectories.

### 3. Create the Render service

Push the repository, then in Render choose **Blueprints → New Blueprint Instance** and select this repository. Render reads `render.yaml` and creates a free Python web service.

The Blueprint already supplies the build and start commands:

```text
Build: ./scripts/production.sh build
Start: ./scripts/production.sh serve
Health check: /health/
```

The start command applies migrations, runs the central scheduled-job registry, and then starts Daphne against `storetrack.asgi:application`. HTTP and WebSocket traffic therefore use the same Render service. This is intentional for the free service because Render's pre-deploy command is a paid-service feature.

Commerce notifications are durable database records. A WebSocket signal tells
connected, authorized staff browsers to fetch their tenant-scoped unread feed
immediately; automatic HTTP polling remains active only when the socket is
unavailable. Daphne sends keepalive pings and the browser reconnects with capped
exponential backoff after deploys, restarts, and network interruptions.

The free Render starter configuration runs one Daphne process and uses an
in-memory channel layer, so it requires no additional service. This is safe for
INPROFIC's starter mode because the database notification is authoritative and
polling recovers any missed transient signal. The Channels project recommends
Redis for production channel layers; configure it before adding processes or
instances.

If the web service is later scaled to multiple processes or instances, provision
a Redis-compatible service and set this environment variable on every instance:

```text
CHANNEL_REDIS_URL=rediss://<username>:<password>@<host>:<port>/0
```

When present, INPROFIC automatically switches to the Redis channel layer. Never
use the in-memory layer across multiple processes because messages cannot cross
process boundaries.

Enter the following secret values during the first Blueprint setup. For an existing Blueprint, add new `sync: false` values manually in **Service → Environment** because Render does not prompt again.

| Render variable | Where the value comes from |
| --- | --- |
| `DATABASE_URL` | Supabase Connect → Session pooler URI, including the password |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 API token result |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 API token result |
| `R2_BUCKET_NAME` | The exact R2 bucket name |
| `R2_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_CUSTOM_DOMAIN` | Optional public media domain without a scheme; leave blank for signed URLs |
| `PAYSTACK_PUBLIC_KEY` | Paystack dashboard; optional until enabled |
| `PAYSTACK_SECRET_KEY` | Paystack dashboard; secret |
| `MONNIFY_API_KEY` | Monnify dashboard; optional until enabled |
| `MONNIFY_SECRET_KEY` | Monnify dashboard; secret |
| `MONNIFY_CONTRACT_CODE` | Monnify dashboard |

`SECRET_KEY` and `CRON_SECRET` are generated by Render. Copy the generated
`CRON_SECRET` from Render into the maintenance job's bearer header. If Render
and PythonAnywhere share one database and must also share login sessions,
replace Render's generated `SECRET_KEY` with the exact same strong value used
by PythonAnywhere. `RENDER_EXTERNAL_HOSTNAME` is supplied by Render and
INPROFIC automatically trusts that hostname and its HTTPS CSRF origin.

When adding a custom application domain, manually add:

```text
ALLOWED_HOSTS=your-domain.example,www.your-domain.example
CSRF_TRUSTED_ORIGINS=https://your-domain.example,https://www.your-domain.example
```

These two variables contain hostnames/origins only; they are not secrets.

### 4. cron-job.org

[Render currently spins down](https://render.com/docs/free) a free web service after 15 minutes without inbound traffic. Create these jobs at cron-job.org:

1. **Keep awake** — `GET https://<service>.onrender.com/health/` every 10 minutes.
2. **INPROFIC maintenance** — `POST https://<service>.onrender.com/ops/run-jobs/` once daily, with the request header `Authorization: Bearer <CRON_SECRET>`.

The health endpoint performs no database query. The maintenance endpoint rejects requests when `CRON_SECRET` is missing or incorrect. [cron-job.org supports custom methods and headers](https://cron-job.org/en/faq/), and its execution history should show HTTP 200 responses. Keep in mind that an always-awake service consumes nearly all of Render's 750 free instance hours in a typical month, and free services remain unsuitable for business-critical production.

### 5. Commands in one place

All operational entry points are in `scripts/production.sh`:

```bash
./scripts/production.sh build    # dependencies, collectstatic, Django check
./scripts/production.sh jobs     # every registered scheduled job
./scripts/production.sh release  # migrate, then all scheduled jobs
./scripts/production.sh serve    # release, then Daphne/ASGI
./scripts/production.sh deploy   # build and release together
```

Future idempotent recurring commands belong in `apps/core/jobs.py`. Both `python manage.py run_scheduled_jobs` and the authenticated HTTP endpoint use that same registry.

## PythonAnywhere remains supported

Keep `.env.prod` on PythonAnywhere and retain the existing WSGI file. PythonAnywhere's normal Web tab remains HTTP-only, so the notification widget automatically falls back to polling there. Typical values are:

```text
DEBUG=False
ALLOWED_HOSTS=<username>.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://<username>.pythonanywhere.com
DATABASE_URL=sqlite:////home/<username>/inprofic/db.sqlite3
MEDIA_URL=/media/
MEDIA_ROOT=/home/<username>/inprofic/media
```

In the PythonAnywhere Web tab, keep the static mappings:

```text
/static/  -> /home/<username>/inprofic/staticfiles
/media/   -> /home/<username>/inprofic/media
```

After each code update, run:

```bash
source venv/bin/activate
./scripts/production.sh deploy
```

Then reload the PythonAnywhere web app. If you enable R2 there later, remove the `/media/` static mapping after verifying uploads and public image URLs through R2.

To use PythonAnywhere as a live failover for Render rather than as a separate copy, use the same Supabase and R2 variables there instead of the SQLite/local-media values above. This requires PythonAnywhere outbound connectivity and careful coordination of payment callback URLs; use one canonical public domain when possible.

## Moving existing SQLite data to Supabase

Changing `DATABASE_URL` starts against a different database; it does not copy the existing SQLite records. Before accepting live traffic on Render, export the current database with `dumpdata` (excluding Django content types and permissions if appropriate), run migrations against Supabase, load the reviewed fixture, and compare tenant, stock, sales, finance, and order counts. Keep the old database as a rollback backup until the new deployment is verified.
