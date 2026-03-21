# K6 压测

基于 K6 的腾讯云沙箱实例压力测试（创建-执行-删除全生命周期）。支持本地测试和分布式（Kubernetes）测试。

## 功能特性

- **多种测试脚本**：完整生命周期、数据平面、无执行、E2B API 风格
- **6 种测试场景**：渐进式、突发、压力、浸泡、冒烟、断点
- **Kubernetes 支持**：开箱即用的 K6 Operator 部署配置
- **Grafana 仪表板**：预配置的指标可视化仪表板

## 快速开始

### 本地测试

1. **安装 K6**
   ```bash
   # macOS
   brew install k6
   
   # Linux
   sudo apt-get install k6
   ```

2. **设置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 填入你的凭证
   source .env
   ```

3. **运行测试**
   ```bash
   k6 run sandbox-stress-test.js
   ```

### 分布式测试（Kubernetes）

1. **安装 K6 Operator**
   ```bash
   helm repo add grafana https://grafana.github.io/helm-charts
   helm install k6-operator grafana/k6-operator
   ```

2. **部署 InfluxDB（用于存储测试指标）**
   ```bash
   # 添加 InfluxData Helm 仓库
   helm repo add influxdata https://helm.influxdata.com/
   helm repo update
   
   # 安装 InfluxDB 2.x
   # 先设置环境变量
   export INFLUXDB_PASSWORD="your-password"
   
   helm install influxdb2 influxdata/influxdb2 \
     --set adminUser.organization=influxdata \
     --set adminUser.bucket=default \
     --set adminUser.user=admin \
     --set adminUser.password=${INFLUXDB_PASSWORD} \
     --set service.type=ClusterIP \
     -n default
   
   # 获取 InfluxDB Token（安装后自动生成）
   kubectl get secret influxdb2-auth -o jsonpath='{.data.admin-token}' | base64 -d
   ```
   
   安装完成后，将以下信息填入 `deploy/00-configmap-secret.yaml`：
   - `INFLUXDB_URL`: `http://influxdb2.default.svc.cluster.local:80`
   - `INFLUXDB_TOKEN`: 上面获取的 Token
   - `INFLUXDB_ORG`: `influxdata`
   - `INFLUXDB_BUCKET`: `default`

3. **配置密钥**
   ```bash
   # 编辑 deploy/00-configmap-secret.yaml 填入你的凭证
   kubectl apply -f deploy/00-configmap-secret.yaml
   ```

5. **创建测试脚本 ConfigMap**
   ```bash
   # 创建所有测试脚本的 ConfigMap
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

6. **运行分布式测试**
   ```bash
   # 编辑 deploy/02-ramping-test.yaml 选择要使用的脚本 ConfigMap
   # 可选: sandbox-stress-test-script / sandbox-stress-test-non-exec-script / sandbox-stress-test-e2b-api-script
   kubectl apply -f deploy/02-ramping-test.yaml
   
   # 或运行数据面压测
   kubectl apply -f deploy/03-data-plane-test.yaml
   ```

## 测试脚本

| 脚本 | 描述 | 文档 |
|------|------|------|
| `sandbox-stress-test.js` | 完整生命周期：创建 → 获取Token → 执行 → 删除 | [详情](docs/sandbox-stress-test-zh.md) |
| `sandbox-stress-test-data-plane.js` | 数据平面压测，长时间运行代码执行 | [详情](docs/sandbox-stress-test-data-plane-zh.md) |
| `sandbox-stress-test-non-exec.js` | 仅创建/删除，不执行代码 | [详情](docs/sandbox-stress-test-non-exec-zh.md) |
| `sandbox-stress-test-e2b-api.js` | E2B 兼容 API 风格，使用 X-API-Key 认证 | [详情](docs/sandbox-stress-test-e2b-api-zh.md) |

## 测试场景

| 场景 | 命令 | 用途 |
|------|------|------|
| `ramping` | `k6 run -e TEST_SCENARIO=ramping sandbox-stress-test.js` | 寻找系统容量上限 |
| `spike` | `k6 run -e TEST_SCENARIO=spike sandbox-stress-test.js` | 测试突发流量处理 |
| `stress` | `k6 run -e TEST_SCENARIO=stress sandbox-stress-test.js` | 寻找系统断点 |
| `soak` | `k6 run -e TEST_SCENARIO=soak sandbox-stress-test.js` | 检测内存泄漏 |
| `smoke` | `k6 run -e TEST_SCENARIO=smoke sandbox-stress-test.js` | 快速健全性检查 |
| `breakpoint` | `k6 run -e TEST_SCENARIO=breakpoint sandbox-stress-test.js` | 寻找最大 RPS |

## 配置说明

查看 `.env.example` 获取所有可用环境变量。

### 关键参数

| 参数 | 描述 | 默认值 |
|------|------|--------|
| `TEST_SCENARIO` | 测试场景类型 | `ramping` |
| `TARGET_VUS` | 目标虚拟用户数 | `5` |
| `API_REGION` | API 区域 | `ap-guangzhou` |
| `USE_INTERNAL` | 使用内网（仅限腾讯云机器） | `false` |

### 网络配置

- **公网**（默认）：使用 `ags.tencentcloudapi.com` 和 `tencentags.com`，任意网络可访问
- **内网**：设置 `USE_INTERNAL=true` 使用 `ags.internal.tencentcloudapi.com` 和 `internal.tencentags.com`，仅限腾讯云机器访问

## 目录结构

```
k6/
├── .env.example                        # 环境变量模板
├── .gitignore                          # Git 忽略规则
├── sandbox-stress-test.js              # 主压测脚本（云 API）
├── sandbox-stress-test-data-plane.js   # 数据平面压测
├── sandbox-stress-test-non-exec.js     # 仅创建/删除，不执行代码
├── sandbox-stress-test-e2b-api.js      # E2B 兼容 API 风格
├── docs/                               # 详细文档
│   ├── sandbox-stress-test-zh.md
│   ├── sandbox-stress-test-data-plane-zh.md
│   ├── sandbox-stress-test-non-exec-zh.md
│   └── sandbox-stress-test-e2b-api-zh.md
├── deploy/
│   ├── 00-configmap-secret.yaml        # K8s 密钥配置
│   ├── 02-ramping-test.yaml            # K6 渐进式测试部署
│   ├── 03-data-plane-test.yaml         # K6 数据平面测试部署
│   └── dependencies/
│       └── grafana.yaml                # Grafana 仪表板配置
```

## 注意事项

### 默认配额（个人用户）

默认参数值针对**个人用户**本地测试配置：

- **API 限频**：50 QPS
- **并发沙箱数**：最多 10 个实例

默认测试参数（`TARGET_VUS=5`、`SPIKE_VUS=10` 等）均在此限制范围内。

### 企业用户

如需更高并发测试，请联系 AGS 团队申请提升配额：

- 提升 API 限频（默认 50 QPS）
- 提升并发沙箱上限（默认 10 个）

配额提升后，相应调整测试参数：
```bash
k6 run -e TARGET_VUS=100 -e SPIKE_VUS=500 sandbox-stress-test.js
```

### 其他

- 长时间测试期间注意监控云成本
- 删除失败可能需要手动清理（检查日志）
- 根据 SLA 要求调整阈值
