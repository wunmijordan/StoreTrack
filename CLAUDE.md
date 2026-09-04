# StoreTrack — Agent Instructions

Read this before editing the repo. It's the scaled-down sibling of the
ChurchForce foundation doc: same shape, far fewer moving parts. It is a
multi-business, multi-vertical inventory/production/sales SaaS foundation.

See also `docs/ARCHITECTURE.md` for the fuller structural writeup and
`docs/skills/SKILL.md` for the project prompt-skill index.

## 1. System shape

- Django 5.2, project package `storetrack/`
- Domain apps live under `apps/`, added to `sys.path` in `storetrack/settings.py`
  so `INSTALLED_APPS` uses plain names (`inventory`, not `apps.inventory`)
- SQLite, one shared database, membership/session tenant routing
- Server-rendered templates (no separate frontend build, no JS framework)
- No Redis, Channels, Cloudinary, or background scheduler — nothing here needs
  them yet. If a future feature does, follow the same pattern ChurchForce
  uses for that piece rather than inventing a new one.

## 2. The Business (tenant) pattern

`core.models.Business` is the tenant root. Most data belongs
to a business through `core.models.BusinessOwnedModel`, which mirrors
`ChurchOwnedModel`:

- `BusinessMiddleware` resolves the business from the authenticated user's
  active `UserBusiness` memberships and session selection, attaches
  `request.business`, and sets it in `core.context` for scoped managers.
- Global superusers may select any Business. Ordinary users can select only an
  active membership; users without one receive no tenant data.
- `BusinessOwnedModel.objects` is a scoped manager — it filters by the
  current business. This is a real filter, not decoration: verified with two
  business rows in the same table during development.
- `BusinessOwnedModel.raw_objects` is unscoped, for admin/shell/management
  commands — the same split ChurchForce makes between `objects` and
  `raw_objects`.
- Line-item / join models (`RecipeItem`, `PurchaseOrderItem`, `SaleItem`)
  are **not** business-owned directly — they're scoped implicitly through
  their parent. Don't add a `business` FK to these; it'd be redundant.

## 3. Rules for agents

- Views use `Model.objects`, never `Model.raw_objects`, except in management
  commands or admin/provisioning code that runs outside a request.
- Every view that creates a `BusinessOwnedModel` row must set
  `obj.business = request.business` before saving (see any `views.py` for
  the pattern: `form.save(commit=False)` → set `business` → `save()`).
  Forms never expose `business` as a field — it's always set server-side.
- Don't add `using=` or otherwise hand-route queries; there's one database.
- Money fields are `DecimalField`, never float — keep it that way for
  procurement costs, prices, and totals.
- Stock-mutating operations (`po_receive`, `order_complete`, `sale_form`)
  run inside `transaction.atomic()`. Keep new stock-mutating logic atomic too
  — this is what prevents two concurrent staff actions from corrupting stock
  counts.
- Production-order completion and sales both check for shortages before
  mutating stock, and require an explicit `force=1` to proceed anyway. Don't
  silently allow stock to go negative — make it an explicit, visible choice.

## 4. App boundaries

| App           | Owns                                                                                                                                                       |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `core`        | `Business`, base model classes, dashboard, reports/backup, business settings                                                                               |
| `inventory`   | `RawMaterial`, `FinishedGood`, `RecipeItem` (bill of materials)                                                                                            |
| `procurement` | `PurchaseOrder`, `PurchaseOrderItem`                                                                                                                       |
| `production`  | `Order`, `OrderItem` — customer orders (made to order, delivered directly) and physical store restocks (add to shelf stock), approved/completed as a whole |
| `sales`       | `Sale`, `SaleItem`                                                                                                                                         |

Cross-app foreign keys use the string form (`"inventory.FinishedGood"`) to
avoid import-order issues — keep doing this for any new cross-app FK.

## 5. Editing checklist

Before editing:

- Identify which app(s) the change touches. Model changes usually mean a
  migration in that app only.
- If the change adds a new top-level (non-line-item) model, inherit
  `BusinessOwnedModel` and set `business` in its create view.

After editing:

- `python manage.py check`
- `python manage.py makemigrations` and review the diff before `migrate`
- If you touched a stock-mutating view, re-run it through the actual
  workflow (procure → receive → produce → complete → sell) — a
  shell/Client-based smoke test is faster than clicking through the UI and
  catches formset-prefix and business-scoping mistakes that `check` won't.

## 6. Common mistakes to avoid

- Forgetting to set `business` on a new `BusinessOwnedModel` row (it'll
  raise an IntegrityError — that's intentional, don't work around it by
  making the field nullable).
- Assuming Django inline-formset prefixes default to `"form"` — they
  default to the FK's `related_name` (`items`, `recipe_items` here). Check
  the rendered `TOTAL_FORMS` field name if an "add row" button breaks.
- Adding a `business` FK to a line-item model — scope through the parent
  instead.
- Bypassing `transaction.atomic()` on a new stock-mutating view.

## 7. Project prompt skills

StoreTrack now includes repository-local skills under `.claude/skills/`. These
are instructions for coding/prompt agents, not runtime Django features. Load
them when the task matches their domain:

| Skill | Invoke when |
| --- | --- |
| `storetrack` | Cross-app or architecture-heavy work |
| `frontend-design` | Templates, forms, formsets, modals, dashboards and UI work |
| `excalidraw-diagram` | Architecture/process/pitch diagrams and diagrammatic documents |
| `simplify` | After every implementation |
| `tenant-safety` | Tenant/query/admin/report changes |
| `production-integrity` | Recipes, Shared Runs, stock, batches, offcuts, reversal |
| `finance-integrity` | Money movement, payments, receivables/payables, reversals |
| `migration-safety` | Any schema change or remote migration history |
| `systematic-debugging` | Tracebacks, silent forms, dynamic formsets, multi-app bugs |
| `code-reviewer` | Deep review of substantial or cross-domain changes |

Before presenting an implementation, run the `simplify` checklist and whichever
domain safety skill applies. The full index is `docs/skills/SKILL.md`. Codex uses the mirrored `.codex/skills/` library through the repository `AGENTS.md`.

## 8. Not built yet (by design)

These remain deliberately deferred:

- Host/subdomain/custom-domain tenant routing. Current routing is membership
  plus an `active_business_id` session key.
- Subscription plans and prices. `BusinessModuleAccess` is the entitlement
  boundary and currently enables every module for every business.
- A dedicated-database path for a "white-label" business.
- A runtime end-user AI/automation skill registry. The repository prompt skills
  in `.claude/skills/` are developer-agent instructions only.
