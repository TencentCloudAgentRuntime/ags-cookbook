# Agent Cluster Pod Startup Benchmark

Measure Pod startup latency, success rate, and stability on one Agent Cluster compute node. The default tests create 16 Pods serially and in parallel. The `production` profile adds init containers, multiple containers, volumes, and HTTP/TCP probes.

Follow the [Chinese testing guide](./performance-test-sop.md) for cluster checks, configuration, warmup, execution, results, and cleanup.

## Prerequisites

- Bash, `kubectl`, `jq`, and `yq` v4 on the operator machine.
- Cluster administrator access through `KUBECONFIG`.
- A Ready Cube target node with at least 16 allocatable CPUs and capacity for 16 workload Pods.
- A separate generator node with at least 16,100 millicores and approximately 5 GiB of available memory.

## Setup and execution

From the repository root:

```bash
cd benchmarks/agent-cluster
export SCALE_LOAD_DIR="$PWD/performance-test-tools"
(
  cd "$SCALE_LOAD_DIR"
  bash -n run.sh cleanup.sh sop-functions.sh
  sha256sum -c SHA256SUMS
)
```

Set `KUBECONFIG`, `TARGET_NODE`, `GENERATOR_NODE`, `LOAD_IMAGE`, and `TEST_PODS` as described in the guide, then load the helpers:

```bash
source "$SCALE_LOAD_DIR/sop-functions.sh"
run_warmup_test
run_serial_test "$TEST_PODS"
run_parallel_test "$TEST_PODS"
```

Each test prints its summary and cleans up its run resources after success. Artifacts are saved under `$RESULT_ROOT/<run-id>`; the default root is `$PWD/_output/customer-cube-cri-performance`. Failed runs preserve their resources for diagnosis. Follow the guide to inspect failures and clean up run resources and shared resources.

The generator is delivered as a pinned container image. This directory contains the complete scripts and manifests needed to run the tests; no CubeContainer source checkout or generator build is required. Use a test cluster or isolated nodes.
