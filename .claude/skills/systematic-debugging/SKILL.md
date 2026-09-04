---
name: systematic-debugging
description: >
  Debug StoreTrack errors by tracing model -> form/formset -> view -> template
  -> stock/finance side effects. Use for traceback-driven bugs, silent form
  failures, dynamic-row JavaScript problems, migration mismatches, or bugs
  spanning several apps.
version: "1.0"
updated: 2026-09-04
---

# Systematic Debugging (StoreTrack)

## Method

1. **Reproduce from the traceback or workflow**, not from assumptions.
2. **Find the first StoreTrack frame** in a Python traceback; library frames are
   usually consequences.
3. **Check schema vs model** for `OperationalError: no such column`.
4. **For forms that appear to do nothing**, inspect:
   - `form.errors` and every formset's errors;
   - management form prefix / `TOTAL_FORMS`;
   - HTML5 validation (`step`, required numeric blanks);
   - cloned JS event-binding markers;
   - whether the POST branch re-renders hidden errors.
5. **For wrong stock**, trace the exact movement service and balance mutation,
   then compare it with `OrderMaterialUsage` / cost snapshots.
6. **For tenant bugs**, verify the queryset was reached through scoped
   `.objects` under the expected `request.business`.
7. **For reversal bugs**, trace downstream sales/payments/reconciliations before
   changing the reversal guard.

## Silent-form checklist

Dynamic StoreTrack formsets have previously failed because cloned rows inherited
an "already wired" marker or because numeric fields were cloned blank. Always
verify newly added rows receive:

- correct indexes/names/ids;
- default numeric values where expected;
- fresh event handlers;
- product price auto-resolution;
- visible server-side row errors.

Fix the root cause and then run the `simplify` skill.
