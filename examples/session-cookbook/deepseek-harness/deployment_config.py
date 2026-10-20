"""Print a custom Tool config; output contains credentials and must be protected."""
import json
import os

REQUIRED = ["AGR_REGION", "AGR_DOMAIN", "SESSION_SPACE_ID", "SESSION_USER_ID",
            "TENCENTCLOUD_SECRET_ID", "TENCENTCLOUD_SECRET_KEY",
            "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"]
# Passed through when set; empty values fall back to each client's own default.
OPTIONAL = ["SESSION_API_ENDPOINT", "TENCENTCLOUD_SESSION_TOKEN"]

def main():
    values = {key: os.environ[key] for key in REQUIRED}
    if any(not value or "replace-me" in value for value in values.values()):
        raise ValueError("Replace all required environment placeholders first")
    values.update({key: os.environ.get(key, "") for key in OPTIONAL})
    print(json.dumps({
        "Image": os.environ["DSH_SESSION_IMAGE"], "ImageRegistryType": "personal",
        "Command": ["/opt/dsh/entrypoint.sh"], "Args": [],
        "Env": [{"Name": k, "Value": v} for k, v in values.items()],
        "Ports": [{"Name": "web", "Port": 3080, "Protocol": "TCP"}],
        "Resources": {"CPU": "2", "Memory": "4Gi"},
        "Probe": {"HttpGet": {"Path": "/", "Port": 3080, "Scheme": "HTTP"},
                  "ReadyTimeoutMs": 30000, "ProbeTimeoutMs": 3000, "ProbePeriodMs": 3000,
                  "SuccessThreshold": 1, "FailureThreshold": 10},
    }))

if __name__ == "__main__":
    main()
