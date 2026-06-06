# Brand assets

These images are staged here for submission to the official
[home-assistant/brands](https://github.com/home-assistant/brands) repository.
They are **not** used by the integration at runtime; they exist so the HACS
`brands` check can eventually pass without being ignored.

## Files

| File | Size | Purpose |
|------|------|---------|
| `custom_integrations/bacnet/icon.png` | 256×256 | Square icon |
| `custom_integrations/bacnet/icon@2x.png` | 512×512 | hDPI icon |
| `custom_integrations/bacnet/logo.png` | ≤256 tall | Horizontal logo |
| `custom_integrations/bacnet/logo@2x.png` | 2× | hDPI logo |

Regenerate them with:

```bash
.venv\Scripts\python.exe scripts/generate_brand_assets.py
```

## Submitting to home-assistant/brands

1. Fork [home-assistant/brands](https://github.com/home-assistant/brands).
2. Copy `custom_integrations/bacnet/` (from this folder) into the same path in
   the fork.
3. Open a pull request. Requirements enforced there:
   - PNG, transparent background, trimmed.
   - `icon.png` exactly 256×256, `icon@2x.png` exactly 512×512.
   - `logo*.png` may be wider but at most 256 px tall.
4. Once the PR is merged, remove `ignore: brands` from
   `.github/workflows/validate.yml`.
