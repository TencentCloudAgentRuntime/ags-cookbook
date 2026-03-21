# K6 Benchmark

K6-based stress testing for Tencent Cloud Sandbox instances (create-execute-delete lifecycle). Supports both local and distributed (Kubernetes) testing.

## Features

- **Multiple Test Scripts**: Full lifecycle, data-plane only, non-exec, and E2B API style
- **6 Test Scenarios**: Ramping, Spike, Stress, Soak, Smoke, Breakpoint
- **Kubernetes Support**: Ready-to-use K6 Operator deployment configs
- **Grafana Dashboard**: Pre-configured dashboard for metrics visualization

## Quick Start

### Local Testing

1. **Install K6**
   ```bash
   # macOS
   brew install k6
   
   # Linux
   sudo apt-get install k6
   ```

2. **Set Environment Variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   source .env
   ```

3. **Run Test**
   ```bash
   k6 run sandbox-stress-test.js
   ```

### Distributed Testing (Kubernetes)

1. **Install K6 Operator**
   ```bash
   helm repo add grafana https://grafana.github.io/helm-charts
   helm install k6-operator grafana/k6-operator
   ```

2. **Deploy InfluxDB (for storing test metrics)**
   ```bash
   # Add InfluxData Helm repository
   helm repo add influxdata https://helm.influxdata.com/
   helm repo update
   
   # Install InfluxDB 2.x
   # Set environment variable first
   export INFLUXDB_PASSWORD="your-password"
   
   helm install influxdb2 influxdata/influxdb2 \
     --set adminUser.organization=influxdata \
     --set adminUser.bucket=default \
     --set adminUser.user=admin \
     --set adminUser.password=${INFLUXDB_PASSWORD} \
     --set service.type=ClusterIP \
     -n default
   
   # Get InfluxDB Token (auto-generated after installation)
   kubectl get secret influxdb2-auth -o jsonpath='{.data.admin-token}' | base64 -d
   ```
   
   After installation, fill in the following in `deploy/00-configmap-secret.yaml`:
   - `INFLUXDB_URL`: `http://influxdb2.default.svc.cluster.local:80`
   - `INFLUXDB_TOKEN`: The token obtained above
   - `INFLUXDB_ORG`: `influxdata`
   - `INFLUXDB_BUCKET`: `default`

3. **Configure Secrets**
   ```bash
   # Edit deploy/00-configmap-secret.yaml with your credentials
   kubectl apply -f deploy/00-configmap-secret.yaml
   ```

4. **Create Test Script ConfigMaps**
   ```bash
   # Create ConfigMaps for all test scripts
   kubectl create configmap sandbox-stress-test-script \
     --from-file=test.js=sandbox-stress-test.js \
     -n default
   
   kubectl create configmap sandbox-stress-test-data-plane-script \
     --from-file=test.js=sandbox-stress-test-data-plane.js \
     -n default
   
   kubectl create configmap sandbox-stress-test-non-exec-script \
     --from-file=test.js=sandbox-stress-test-non-exec.js \
     -n default
   
   kubectl create configmap sandbox-stress-test-e2b-api-script \
     --from-file=test.js=sandbox-stress-test-e2b-api.js \
     -n default
   ```

5. **Run Distributed Test**
   ```bash
   # Edit deploy/02-ramping-test.yaml to select the script ConfigMap
   # Options: sandbox-stress-test-script / sandbox-stress-test-non-exec-script / sandbox-stress-test-e2b-api-script
   kubectl apply -f deploy/02-ramping-test.yaml
   
   # Or run data plane stress test
   kubectl apply -f deploy/03-data-plane-test.yaml
   ```

## Test Scripts

| Script | Description | Docs |
|--------|-------------|------|
| `sandbox-stress-test.js` | Full lifecycle: create → token → execute → delete | [Details](docs/sandbox-stress-test.md) |
| `sandbox-stress-test-data-plane.js` | Data plane stress test with long-running execution | [Details](docs/sandbox-stress-test-data-plane.md) |
| `sandbox-stress-test-non-exec.js` | Create/delete only, no code execution | [Details](docs/sandbox-stress-test-non-exec.md) |
| `sandbox-stress-test-e2b-api.js` | E2B compatible API style with X-API-Key authentication | [Details](docs/sandbox-stress-test-e2b-api.md) |

## Test Scenarios

| Scenario | Command | Use Case |
|----------|---------|----------|
| `ramping` | `k6 run -e TEST_SCENARIO=ramping sandbox-stress-test.js` | Find capacity limits |
| `spike` | `k6 run -e TEST_SCENARIO=spike sandbox-stress-test.js` | Test sudden traffic handling |
| `stress` | `k6 run -e TEST_SCENARIO=stress sandbox-stress-test.js` | Find breaking point |
| `soak` | `k6 run -e TEST_SCENARIO=soak sandbox-stress-test.js` | Detect memory leaks |
| `smoke` | `k6 run -e TEST_SCENARIO=smoke sandbox-stress-test.js` | Quick sanity check |
| `breakpoint` | `k6 run -e TEST_SCENARIO=breakpoint sandbox-stress-test.js` | Find max RPS |

## Configuration

See `.env.example` for all available environment variables.

### Key Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `TEST_SCENARIO` | Test scenario type | `ramping` |
| `TARGET_VUS` | Target virtual users | `5` |
| `API_REGION` | API region | `ap-guangzhou` |
| `USE_INTERNAL` | Use internal network (Tencent Cloud only) | `false` |

### Network Configuration

- **Public Network** (default): Uses `ags.tencentcloudapi.com` and `tencentags.com`, accessible from anywhere
- **Internal Network**: Set `USE_INTERNAL=true` to use `ags.internal.tencentcloudapi.com` and `internal.tencentags.com`, only accessible from Tencent Cloud machines

## Directory Structure

```
k6/
├── .env.example                        # Environment template
├── .gitignore                          # Git ignore rules
├── sandbox-stress-test.js              # Main stress test script (Cloud API)
├── sandbox-stress-test-data-plane.js   # Data plane stress test
├── sandbox-stress-test-non-exec.js     # Create/delete only, no execution
├── sandbox-stress-test-e2b-api.js      # E2B compatible API style
├── docs/                               # Detailed documentation
│   ├── sandbox-stress-test.md
│   ├── sandbox-stress-test-data-plane.md
│   ├── sandbox-stress-test-non-exec.md
│   └── sandbox-stress-test-e2b-api.md
├── deploy/
│   ├── 00-configmap-secret.yaml        # K8s secrets config
│   ├── 02-ramping-test.yaml            # K6 ramping test deployment
│   ├── 03-data-plane-test.yaml         # K6 data plane test deployment
│   └── dependencies/
│       └── grafana.yaml                # Grafana dashboard config
```

## Notes

### Default Quota (Personal Users)

The default values are configured for **personal users** running local tests:

- **API Rate Limit**: 50 QPS
- **Concurrent Sandboxes**: 10 instances max

Default test parameters (`TARGET_VUS=5`, `SPIKE_VUS=10`, etc.) are set within these limits.

### Enterprise Users

For higher concurrency testing, contact the AGS team to request quota increases:

- Increase API rate limit (default 50 QPS)
- Increase concurrent sandbox limit (default 10)

After quota increase, adjust test parameters accordingly:
```bash
k6 run -e TARGET_VUS=100 -e SPIKE_VUS=500 sandbox-stress-test.js
```

### Other

- Monitor cloud costs during extended test runs
- Delete failures may require manual cleanup (check logs)
- Adjust thresholds according to SLA requirements
