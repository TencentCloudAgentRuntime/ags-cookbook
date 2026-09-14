# Network requirements

## Runner-to-AGS connections

The SDK uses separate API and sandbox data endpoints. Allowing only the bare
`E2B_DOMAIN` does not cover either path.

| Source | Destination | Port | Purpose |
|---|---|---|---|
| Existing runner | `api.<E2B_DOMAIN>` | TCP 443 | Create, list, and kill sandboxes |
| Existing runner | `49983-<sandbox-id>.<sandbox-domain>` | TCP 443 | Execute commands and transfer files |
| Existing runner | GitHub Actions endpoints | TCP 443 | Checkout, action downloads, and artifact upload |
| Existing runner | Dependency download endpoints used by uv/setup-uv | TCP 443 | Install the SDK and Python tooling |

For the default AGS region the API host is
`api.ap-guangzhou.tencentags.com`. The sandbox domain comes from the service's
creation response, falling back to `E2B_DOMAIN`; use the returned domain rather
than assuming they always match. The data hostname above is the AGS routing form
used by this example. `49983` is part of the HTTPS hostname, **not** an outbound
TCP port to open. API URL overrides or other service routing modes require their
actual destinations instead.

Ensure DNS resolution and TLS access to both endpoint types. Sandbox IDs vary
per run; scope any wildcard/proxy rule to your approved sandbox domain.
Use the official GitHub runner connectivity requirements for the GitHub endpoint
list; this table is not an exhaustive GitHub/Python package CDN allowlist.

The AGS API key stays on the runner and is not forwarded to the sandbox.

## Sandbox workload connections

The included candidate and tests use only Python's standard library and perform
no network requests. They require no sandbox egress, but this example does not
configure or enforce an egress firewall.

For another workload, identify exact package registries or test-service hosts,
then configure the sandbox's network policy separately. Do not confuse allowing
runner-to-AGS HTTPS with allowing outbound connections from workload code.
