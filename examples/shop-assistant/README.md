# Shop Assistant - Shopping Cart Automation Demo

Using Agent Sandbox's Browser sandbox + Playwright to search Amazon products and automatically add to cart in logged-in state, then view the cart list. Supports uploading local cookies for login-free access.

## Features

- Login-free Experience: Import local cookies to proceed with shopping flow directly
- Automation Flow: Search → Enter product page → Add to cart → View cart
- Remote Browser Control: Run Playwright via Browser sandbox
- Robust Strategy: Multiple selector fallbacks, timeout retries, loading state detection

## Business Scenario

Suitable for automation verification and demonstration in e-commerce scenarios:
- Automated verification of "Add to Cart" flow
- Key path replay with stable login state
- Support for remote observation of execution process in the cloud (VNC debugging)

## Execution Flow

1. Upload and import local cookies (cookie.json)
2. Open Amazon homepage and search for target keywords
3. Parse first product and enter detail page
4. Click add to cart and verify result
5. Open cart page to view product items

## Running Instructions

```bash
# Set environment variables
export E2B_DOMAIN='tencentags.com'
export E2B_API_KEY='your_ags_api_key'  # provided by Tencent Cloud Agent Sandbox product

# Install dependencies
pip install -r requirements.txt

# Prepare cookies (login-free)
# Export your Amazon cookies to cookie.json in current directory (refer to cookie.json.example structure)

# Run demo
python automation_cart_demo.py
```

## FAQ

- Cookie import failed
  - Confirm cookie.json exists and is in array format, containing name, value, domain, path and other fields
  - If cookies expired, please re-login and export
- E2B_API_KEY not set
  - Please set environment variable first: export E2B_API_KEY='your_ags_api_key'  # provided by Tencent Cloud Agent Sandbox product
- Want to watch execution process (VNC)
  - Console will provide instructions; debug output can be enabled in local secure environment (avoid printing token links directly in shared environments)

## Quick Start

```bash
make run
```

