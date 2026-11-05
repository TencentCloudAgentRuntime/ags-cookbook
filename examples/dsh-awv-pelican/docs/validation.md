# Validation scope

## Historical source validation

The original AGC example was tested on 2026-09-22 with Chart `0.2.1` and Harness `0.1.5-rc.2`, followed by an independent reproduction using another Namespace and PVC. The Web exposure configuration was later updated in Chart `0.2.2`.

| Scenario | Original run | Independent reproduction |
| --- | ---: | ---: |
| Generate, review and publish | 136 s | 218 s |
| Inject a mobile-layout defect, review, fix, review and publish | 169 s | 207 s |

Those runs checked the shared PVC across Code, Review and display Pods on different nodes, publication gates, real browser operations, HTTP 200 and unchanged page hashes after display Pod recreation. They exercised the Harness **Headless** entry, not browser clicks in Harness Web. These are historical observations, not validation of the migrated package. No live addresses, cluster identifiers or credentials are included here.

## Migration checks (2026-11-05)

| Check | Method | Result |
| --- | --- | --- |
| Example entry points and dependencies | Repository contract checker and root `make example-setup EXAMPLE=dsh-awv-pelican` with frozen lockfiles | Passed |
| TypeScript, shell and configuration | `make check`, including Harness YAML parsing and Helm lint/render | Passed |
| Provider behavior | `make test` | 3/3 passed |
| Formatting and credentials | Repository pre-commit hooks, including Gitleaks | Passed |
| Container packaging | Build linux/amd64 Controller and Worker targets from the migrated Dockerfile | Passed |
| Harness Web startup and login | Run the Controller as UID 10001, with network disabled and a dummy model key; open its token-bearing login URL | HTTP 200 and HTML returned |
| Worker browser | Run Playwright MCP and launch real Chrome as UID 10001, render local HTML and take a screenshot with network disabled | Passed |
| Cluster task flow and cross-node persistence | Dedicated AWV installation and two-round E2E | Not run: the available test kubeconfig failed authentication |
| Native macOS execution | Run local setup/scripts on macOS | Not run |

The local checks do not exercise model calls, Kubernetes resource creation or AWV mounts. The migrated package still requires a fresh cluster E2E before claiming those paths have passed.

## Validate your installation

1. Run `make check` and `make test`. Neither runs a real Agent task.
2. Run `make run`, `make verify` and `make access`. Submit `examples/prompts/create-pelican.md` in Harness Web. Confirm Code, Review and Publish tool cards and open the returned site URL.
3. Run `make e2e` in a dedicated demo Namespace/PVC. It submits two prompts through Harness Headless, injects a deterministic mobile-layout defect, checks repair and re-review, then recreates the display Pod and compares page hashes.
4. For cross-node validation, set `CODE_NODE`, `REVIEW_NODE` and `SITE_NODE` to three different Ready amd64 nodes before deployment. Without these settings, success does not prove cross-node recovery.

`make e2e` overwrites the demonstration page. Never point it at a workspace holding business data. Raw logs and artifacts are written to `OUTPUT_DIR` (default `.local/`), which is excluded from Git. Record actual environment, image digests and outcomes after running; static checks and historical runs do not substitute for current cluster validation.
