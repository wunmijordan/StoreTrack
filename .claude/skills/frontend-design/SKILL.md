---
name: frontend-design
description: >
  Design and implement polished StoreTrack Django template/UI work while preserving
  existing form, JavaScript, permission, responsive, branding, and workflow behavior.
  Use for templates, modals, dashboards, forms, tables, navigation, print views, and UI refactors.
version: "1.0"
updated: 2026-09-04
---

# Frontend Design — StoreTrack

Use this skill whenever the task changes HTML templates, CSS/Tailwind classes, JavaScript-driven formsets, dashboards, modals, tables, navigation, exports/print surfaces, or the visual presentation of a StoreTrack workflow.

## Primary objective

Improve usability and visual quality **without changing business semantics accidentally**. StoreTrack templates are not decorative shells: many of them carry formset prefixes, hidden management fields, pricing resolvers, channel-specific visibility, stock calculations, confirmation flows, and permission-aware actions.

## StoreTrack design language

- Preserve the existing warm/off-white StoreTrack visual system unless the user explicitly asks for a redesign.
- Use the established dominant burgundy accent (`#8f172d`) where an accent is appropriate.
- Prefer restrained hierarchy: clear headings, compact operational tables, legible status badges, and obvious primary actions.
- Keep finance/stock status colors semantically consistent:
  - green = sufficient/success/cleared;
  - amber = warning/attention;
  - red = low/error/destructive.
- Do not add decorative complexity that makes production-floor or finance tasks slower.
- Make forms usable on desktop and narrow screens; preserve horizontal table usability where dense operational data genuinely needs it.

## Before editing a template

1. Read the corresponding view and form/formset.
2. Identify every POST field, management-form field, prefix, data attribute, and JavaScript selector the template depends on.
3. Search for shared JavaScript in `templates/base.html` before adding another formset-cloning implementation.
4. Check whether the page is business-scoped or permission-sensitive.
5. If a modal is populated from JSON, inspect both the JSON producer and consumer before renaming attributes or keys.

## Dynamic formset rules

StoreTrack uses Django formsets heavily. When adding/removing rows:

- preserve the correct `<prefix>-TOTAL_FORMS` management field;
- never assume a prefix is `form`;
- replace every `__prefix__` occurrence in `name`, `id`, `for`, and relevant data attributes;
- clear database IDs and DELETE flags on clones;
- reset values to the intended domain defaults (often `0`, not blank, for numeric Order fields);
- remove stale JS "already wired" markers from clones;
- re-run product/price/channel wiring on the new row;
- surface field and non-field errors visibly after a failed POST.

For production Order rows, confirm newly-added rows retain:

- product price auto-resolution;
- ordered batches/pieces defaults;
- planned-production batches/pieces defaults;
- discount defaults;
- channel/customer context.

## Forms and numeric precision

- Match HTML `step`, Django field precision, model precision, and displayed initial values.
- Do not format a valid Decimal into a browser-invalid value.
- Quantities and money are different domains; never change currency precision merely because a stock field needs more precision.
- Use normal HTML escaping inside HTML attributes. Use `escapejs` only inside actual JavaScript strings; otherwise values such as `2-in-1 Bread` can surface as literal escape sequences.

## Operational tables

- Keep the most decision-relevant columns visible first.
- Add derived columns only when their meaning is defensible from current data.
- Label estimates/traceable pools conservatively when the ledger cannot provide true lot-level precision.
- If adding export actions, keep them adjacent to the table title/filter context and ensure exports use the same business scope and status logic as the screen.

## Modals

- A modal should still communicate useful master/configuration information when transaction history is empty.
- Separate master data (recipe, configured inputs, thresholds) from history (movements, batches) visually.
- Avoid hiding an empty-history modal entirely if the user still needs the configured recipe/input information.

## Destructive actions

- Use visually distinct destructive styling and explicit confirmation text.
- Do not make deletion look equivalent to edit/view.
- Reversal and deletion are different operations; UI language must reflect that distinction.

## Validation pass

Before finishing template work:

- check Django template control blocks are balanced;
- inspect all changed formset management fields and prefixes;
- search for referenced IDs/classes/data attributes in JS;
- test empty, one-row, and multiple-row states mentally or in-browser when available;
- verify failed POST errors are visible;
- verify mobile/narrow layout does not hide the primary action;
- ensure no tenant/permission action became visible to the wrong role.

After implementation, also apply the `simplify` and relevant domain-integrity skill.
