# StoreTrack

A lightweight inventory, production, and sales system for a bakery/
restaurant-type business — Django backend and server-rendered frontend in
one codebase, structured as `apps/`-per-domain (borrowed from a larger
multitenant Django project; see `docs/ARCHITECTURE.md` and `CLAUDE.md` for
what was borrowed and what was deliberately left out).

## What it does

- **Inventory** — raw materials and finished goods, each product with a
  recipe (bill of materials).
- **Procurement** — purchase orders; receiving one adds stock and updates
  cost per unit automatically.
- **Production requests** — the store asks production to make more of
  something.
- **Production orders** — internal or customer; completing one deducts raw
  materials by recipe and adds finished stock inside a database
  transaction, with a shortage warning you can override.
- **Sales** — deducts finished-goods stock on save, same shortage warning.
- **Reports** — CSV export for stock, procurement, production, sales, plus
  a full JSON backup.
- Login required on every page (Django's built-in auth).

## Quick start — run it today, locally

Requirements: Python 3.10+

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000 and log in.

### WiFi-only access for staff, right now

```bash
python manage.py runserver 0.0.0.0:8000
```

Then on their phone/tablet: `http://<your-computer's-local-IP>:8000`. Only
works while your machine is on and everyone's on the same network — see
"Deploying" below for anywhere-access.

## VSCode + WSL setup (Windows)

To get a real bash terminal inside VSCode on Windows:

1. Open PowerShell **as Administrator** and run:
   ```
   wsl --install
   ```
   This installs WSL2 and Ubuntu by default. Restart when prompted, then
   finish the Ubuntu setup (it'll ask you to create a Linux username/password
   — separate from your Windows login).
2. Install the **WSL** extension in VSCode (search "WSL" in the Extensions
   panel — it's published by Microsoft).
3. Open a WSL terminal (Ubuntu) and clone/place this project somewhere
   inside the Linux filesystem, e.g. `~/projects/storetrack` — not
   `/mnt/c/...` — WSL is noticeably faster and more reliable when the
   project lives inside the Linux filesystem rather than a Windows-mounted
   path.
4. From that WSL terminal: `code .` — this opens VSCode connected to WSL
   (you'll see "WSL: Ubuntu" in the bottom-left corner). VSCode's integrated
   terminal is now a real bash shell in Linux, so the Quick Start commands
   above work exactly as written.
5. Inside that WSL-connected VSCode window, install the Python extension if
   prompted, and point it at `venv/bin/python` once you've created the
   virtualenv (Cmd/Ctrl+Shift+P → "Python: Select Interpreter").

## Git & GitHub

From inside the project folder (in your WSL bash terminal):

```bash
git init
git add .
git commit -m "Initial commit: StoreTrack, apps/-per-domain structure"
```

Then on GitHub: create a new **empty** repository named `StoreTrack` (don't
initialize it with a README/license — you already have one, and that avoids
a merge conflict on first push). Then:

```bash
git remote add origin https://github.com/<your-username>/StoreTrack.git
git branch -M main
git push -u origin main
```

`.gitignore` already excludes `venv/`, `db.sqlite3`, and `__pycache__/`, so
your database and virtualenv won't get committed.

## Deploying for real remote access

Plain Django, so it runs on most hosts that support Python.

**PythonAnywhere (free tier)** — persistent storage (your SQLite file
survives restarts, unlike several free hosts that wipe the filesystem on
redeploy), reachable at `yourusername.pythonanywhere.com`. Free tier has no
custom domain (needs their $10/month plan).

Steps: sign up → open a Bash console → clone this repo (or upload it) →
create a virtualenv and `pip install -r requirements.txt` → in the **Web**
tab, add a manually-configured web app pointing its WSGI file at
`storetrack.wsgi.application` → set env vars `DJANGO_SECRET_KEY`,
`DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS=yourusername.pythonanywhere.com`
→ `python manage.py migrate` and `createsuperuser` from the console →
reload the web app.

Other options (Render, Railway, Fly.io, a VPS) all run Django fine — just
confirm the free tier gives a **persistent disk**, or plan to switch
`DATABASES` in `settings.py` to Postgres if it doesn't.

## Backup & restore

- **Reports & Backup** page → "Download backup (JSON)".
- Restore on a server: `python manage.py loaddata your-backup-file.json`

## Security checklist before going live

- [ ] `DJANGO_SECRET_KEY` set to a fresh random value
- [ ] `DJANGO_DEBUG=False`
- [ ] `DJANGO_ALLOWED_HOSTS` set to your real domain
- [ ] Each staff member has their own login (Django admin → Users → Add user)

## What's next

See `CLAUDE.md` §7 for what was deliberately left out for now (real
multi-location routing, permission tiers, Postgres) and how to add it later
without a rewrite.
