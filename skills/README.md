# AGS Cookbook — Agent Skill

## Reference Skill example

| Skill | Path | Description |
|-------|------|-------------|
| **ags** | [`ags/SKILL.md`](./ags/SKILL.md) | Reference example for CLI-first AGS workflows with `agr`. |

This directory is a reference Agent Skill example for AGS.

Add from GitHub with the `skills` CLI:

```bash
npx skills add TencentCloudAgentRuntime/ags-cookbook --skill ags
```

Install the CLI:

```bash
# One-line install (macOS / Linux)
curl -fsSL https://github.com/TencentCloudAgentRuntime/ags-cli/releases/latest/download/install.sh | sh

# Or via go install
go install github.com/TencentCloudAgentRuntime/ags-cli/cmd/agr@latest

agr version -o json
```

The main Skill follows progressive disclosure:

- Load [`ags/SKILL.md`](./ags/SKILL.md) for day-to-day CLI work.
- Open [`ags/references/mount-templates.md`](./ags/references/mount-templates.md) only for storage JSON examples.
- Open [`ags/references/vpc-networking.md`](./ags/references/vpc-networking.md) for VPC mode, subnets, security groups, and private service access.
- Open [`ags/references/custom-images.md`](./ags/references/custom-images.md) for custom-image services, ports, probes, resources, env vars, registry access, and per-instance overrides.
- Open [`ags/references/advanced-workflows.md`](./ags/references/advanced-workflows.md) for browser/mobile/API key/raw API/image pre-cache/debug workflows.
- Open [`ags/references/troubleshooting.md`](./ags/references/troubleshooting.md) for failures, status interpretation, exit codes, and cleanup issues.
