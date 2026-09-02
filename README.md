# StoreTrack

A lightweight, multi-vertical, multitenant inventory, production, and sales
system. Bakery businesses retain the original full workflow; restaurants add
food-service vocabulary and dine-in/takeaway/delivery details; other makers
use a general production profile. It remains one Django codebase and one
SQLite database, suitable for PythonAnywhere.

## What it does

- **Inventory** — raw materials (with a real purchase→package→usage unit
  chain: buy in bags, track in kg, dispense in grams/spoons/caps — see
  "Units" below) and finished goods, each with a recipe (bill of materials)
  and an optional batch size.
- **Procurement** — purchase orders; receiving one converts through the
  unit chain and updates stock + cost per unit automatically.
- **Customer Orders & Sales** — one form, one model, split by type:
  - **Walk-in** — immediate, deducts from existing shelf stock, exactly
    like a normal point-of-sale transaction.
  - **Customer order** — saved as *pending*, touches no stock yet. Link
    each order line from a Production Request, then a Production Order;
    completing that order automatically flips the sale to *fulfilled* and
    hands the ordered quantity to the customer — any surplus from batch
    rounding stays as shelf stock. A multi-item order only clears once
    *every* line's production is done.
- **Production requests** — the store asks production to make more of
  something, either as a general restock or linked to a specific pending
  customer order line (which fills in the product and quantity for you).
- **Production orders** — the approval step: completing one deducts raw
  materials by recipe (per batch, rounded up to whole batches — you can't
  make a fraction of a batch) and adds finished stock, inside a database
  transaction, with a shortage warning you can override.
- **Reports** — CSV export for stock, procurement, production, sales, plus
  a full JSON backup.
- Login required on every page (Django's built-in auth), with a
  `created_by` trail on every record.

### Units — the three-layer chain

Raw materials separate **what you buy** (purchase unit — bag, carton),
**what's in the pack** (package qty + unit — e.g. 50 kg), and **what a
recipe actually consumes** (usage unit — kg, g, spoon, cap, with a
conversion factor you set). Stock and cost are tracked internally in the
fine usage unit; the Add/Edit form lets you enter both in the purchase
unit instead (e.g. "3 bags", "₦9,000/bag") and does the conversion for you.

### Batches

A finished good can have a batch size (`units_per_batch`) — e.g. 41 loaves
per batch of Family Loaf. Recipe quantities are **per batch**, not per
unit; reorder level stays in individual units. A Production Order's
quantity is still in units (inherited from wherever it came from), but
production always rounds up to whole batches — order 50 loaves at a
41-per-batch size, and 2 batches (82) get made, with the extra 32 landing
as shelf stock.

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

Open http://127.0.0.1:8001. Existing users sign in; a new business owner uses
**Sign up** to create a workspace and its first Business Admin account.

### WiFi-only access for staff, right now

```bash
python manage.py runserver 0.0.0.0:8001
```

Then on their phone/tablet: `http://<your-computer's-local-IP>:8001`. Only
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
`storetrack.wsgi.application` → set `SECRET_KEY`, `DEBUG=False`,
`ALLOWED_HOSTS=yourusername.pythonanywhere.com`, and an absolute SQLite URL
such as `DATABASE_URL=sqlite:////home/yourusername/storetrack/db.sqlite3`.

For an upgrade with live data, stop/reload traffic around this short sequence:

```bash
cp db.sqlite3 "db.sqlite3.backup-$(date +%F-%H%M%S)"
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py check
```

Then reload the web app. Do not replace the SQLite file: the migrations add
nullable/defaulted fields in place, classify every existing business as
`bakery`, preserve all foreign keys/rows, and grant legacy tenants all current
modules.

Other options (Render, Railway, Fly.io, a VPS) all run Django fine — just
confirm the free tier gives a **persistent disk**, or plan to switch
`DATABASES` in `settings.py` to Postgres if it doesn't.

## Backup & restore

- **Reports & Backup** page → "Download backup (JSON)".
- Restore on a server: `python manage.py loaddata your-backup-file.json`

## Security checklist before going live

- [ ] `SECRET_KEY` set to a fresh random value
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` set to your real domain
- [ ] Each staff member has their own login (Business Settings → Users & Access)

## What's next

See `docs/ROADMAP.md` for production planning, location support, and future
plan/pricing work.
