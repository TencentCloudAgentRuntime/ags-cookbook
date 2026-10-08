# AgentWay Cookbook

Scenario-oriented guides for deploying, operating, and observing AgentWay on Tencent Cloud. The detailed guides are currently written in Chinese; start with the [Chinese overview](./README_zh.md).

## What this example covers

- Run OpenClaw with a browser on Tencent Agent Runtime
- Run a public Hermes Dashboard on Tencent Agent Runtime
- Deploy and operate Hermes with the full AgentWay control plane on TKE
- Deploy `agentway-exporter`, Prometheus collection, and Grafana dashboards

## Prerequisites

- A Kubernetes cluster with `kubectl` access
- Helm 4.x for the full AgentWay installation path
- Tencent Cloud credentials and resources required by the selected guide
- Access to the container registries referenced by the manifests

## Start here

```bash
make setup
make run
```

`make setup` checks the local CLI prerequisites. `make run` prints the available guide entry points; it does not change a cluster.

Choose one path:

- [OpenClaw browser on Tencent AGS](./openclaw-browser-on-TencentAGS/README.md)
- [Hermes Dashboard on Tencent AGS](./hermes-dashboard-on-TencentAGS/README.md)
- [Hermes on TKE](./hermes-on-TKE/README.md)
- [AgentWay monitoring dashboards](./agentway-monitoring-dashboard/README.md)

The operator-only AGS path pins image `v1.0.15-d5afc116` and CRDs from commit `d5afc116883d3ffbf9041b09adda39d640e29eb1`. See the [version and capability boundaries](./openclaw-browser-on-TencentAGS/README.md#版本与能力边界) before following advanced chapters. Unsupported features are isolated as `planned-examples/*.yaml.txt`, not runnable manifests.

The OpenClaw quickstart creates three AGS Agents (2 CPU / 4Gi each). It does not preinstall Skills; a real model API key is required to validate model calls. Operator deployment also requires at least 16 CPU / 16Gi of schedulable capacity, plus system components.

Local prerequisite checks and static manifest validation do not establish end-to-end behavior on TKE/AGS.

Each guide lists the parameters to replace, commands to run, expected results, and validation steps. Review every manifest before applying it to a production cluster.
