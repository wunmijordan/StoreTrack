---
name: migration-safety
description: >
  Plan and review StoreTrack Django migrations against the current migration
  graph and live SQLite deployment. Use before adding, renaming, removing or
  changing model fields, especially after the user reports remote migrations.
version: "1.0"
updated: 2026-09-04
---

# Migration Safety (StoreTrack)

## Rules

1. Inspect the actual latest migration files in the supplied/current zip before
   choosing a migration number.
2. Never reuse a migration number already created remotely.
3. Depend on the real current leaf for that app.
4. Preserve user-provided migration files exactly unless the requested task is
   specifically to repair them.
5. Prefer additive/backward-compatible migrations when historical rows exist.
6. If replacing a field/model concept, decide whether old data needs a data
   migration before removing schema.
7. Avoid faking migrations unless the database state is independently verified.
8. For SQLite, remember table rewrites can occur for schema changes; keep
   migrations narrow.

## Model/schema consistency check

Before packaging, compare Django model declarations to the migration state.
A model field with no matching migration can cause runtime errors such as
`no such column`; an old migration that adds a removed field can create the
opposite mismatch.

## Deployment guidance

When code and migration graph are consistent, normal deployment is:

```bash
python manage.py migrate
```

Do not tell the user that deleting rows resets database sequences unless an
explicit sequence reset is implemented.
