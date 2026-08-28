# Shop Assistant - Shopping Cart Automation Demo

This example uses the AGS browser sandbox plus Playwright to search Amazon, enter a product page, add an item to cart, and inspect the cart.

## Prerequisites

- Python >= 3.12
- `uv`
- `E2B_API_KEY`
- Required `E2B_DOMAIN`
- Optional `cookie.json` if you want a logged-in flow

## Required environment variables

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
export KEEPALIVE_SECONDS="0"  # optional, avoids long post-run sleep
```

## Local commands

```bash
make setup
make run
```

## Expected result

A successful run should:

- open Amazon in the remote browser sandbox
- search for the configured product keyword
- enter a product detail page
- attempt add-to-cart
- open the cart view

Guest mode is supported when `cookie.json` is absent, so missing cookies are no longer a hard blocker.

## Common failure hints

- If Amazon returns anti-bot or login prompts, retry with fresh cookies or accept the guest-mode limitations
- If sandbox startup fails, verify `E2B_API_KEY` and `E2B_DOMAIN`

## Notes

- Console output includes VNC/debug hints for observing the browser remotely
- Avoid committing real cookies or account data
