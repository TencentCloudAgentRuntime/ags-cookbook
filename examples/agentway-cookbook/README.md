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

Each guide lists the parameters to replace, commands to run, expected results, and validation steps. Review every manifest before applying it to a production cluster.
