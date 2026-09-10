# Network requirements inventory

Use this inventory to turn Phase 0 observations into the minimum managed Runner
Profile policy. Do not allow an entire domain category when the workload needs only
one endpoint.

## Control path used by this example

| Source | Destination | Port | Purpose | Required by fixture |
|---|---|---:|---|---|
| Existing GitHub Actions runner | `${E2B_DOMAIN}` | TCP 443 | Create, execute in, transfer files to/from, and kill the AGS sandbox | Yes |
| Existing GitHub Actions runner | GitHub Actions endpoints | TCP 443 | Checkout, action download, and workflow artifact upload | Yes; provided by GitHub-hosted runners |

The AGS API key stays on the existing runner and is used by the SDK control path.
It is not forwarded into the sandbox.

## Sandbox workload path

The included `ci_task.py` fixture performs no network requests. Its sandbox egress
requirement is therefore **none**.

For a real workload, record every observed dependency below before changing the
network policy:

| Destination/domain | Port | Consumer command | Reason | Credential forwarded? | Decision |
|---|---:|---|---|---|---|
| _example: package registry_ | 443 | _example: package install_ | Dependency download | No | Pending |

Typical categories to investigate—not blanket-allow—include source hosts, action or
release asset hosts, language package registries, container registries, artifact
stores, test services, and telemetry endpoints.

## Collection procedure

1. Run the representative workload with default-deny sandbox egress.
2. Record each failed destination and the exact command that needs it.
3. Approve only destinations required for the accepted workload set.
4. Re-run successful, failed, and cancelled jobs.
5. Store the finalized list with the versioned Runner Profile rather than in a
   workflow-controlled input.
