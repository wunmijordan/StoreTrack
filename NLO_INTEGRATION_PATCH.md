# No Left Overs headless API compatibility patch

This INPROFIC copy contains a small additive API improvement for the No Left Overs customer website.

## Modified

- `apps/commerce/views.py` — product API now exposes `image_url` and `preorder_min_quantity` from `StorefrontProduct`.
- `apps/commerce/tests.py` — adds a regression test for those public catalogue fields.
- `docs/COMMERCE_INTEGRATION.md` — documents the headless catalogue metadata used by restaurant websites.

No model or migration change is required. The fields already exist in INPROFIC; the patch only exposes them in the versioned product JSON.
