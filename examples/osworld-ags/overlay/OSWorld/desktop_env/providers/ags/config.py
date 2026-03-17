"""
AGS (Agent Sandbox) Provider Configuration

Environment variables (loaded from .env file):
- E2B_API_KEY: API key for Agent Sandbox (required)
- E2B_DOMAIN: Domain for Agent Sandbox (default: e2b.dev)
- AGS_TEMPLATE: Template name for the sandbox (default: osworld)
- AGS_TIMEOUT: Sandbox timeout in seconds (default: 1800 = 30 minutes)

Derived from xlang-ai/OSWorld under Apache-2.0.
Modified and redistributed by Agent Sandbox Cookbook as part of the OSWorld AGS overlay.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Configuration
E2B_API_KEY = os.environ.get("E2B_API_KEY", "")
E2B_DOMAIN = os.environ.get("E2B_DOMAIN", "e2b.dev")

# Sandbox Configuration
AGS_TEMPLATE = os.environ.get("AGS_TEMPLATE", "osworld")
AGS_TIMEOUT = int(os.environ.get("AGS_TIMEOUT", str(30 * 60)))  # 30 minutes in seconds

# Port Configuration (matching AGS sandbox defaults)
SERVER_PORT = 5000
CHROMIUM_PORT = 9222
VNC_PORT = 5910
VLC_PORT = 8080
