# 08. 用 Console API 自动化创建 Hermes

## 本章场景

你希望把 Console 页面操作变成脚本，用于批量创建、CI 验证或环境初始化。

Console API 和页面操作是等价的：API 写入的内容最终也会反映到 AgentWay CRD 中。

---

## 前置章节

请先完成：

- [02. 通过 Console 创建 Hermes Dashboard](./02-create-hermes-dashboard-with-console.md)

---

## 通过 Console 操作

本章不新增新的页面操作。它复用前面章节的页面流程：

1. 文件预设
2. 运行时
3. 模板
4. 发布版本
5. 创建实例

建议先通过 Console 手工跑通一次，再把请求转换成脚本。

---

## 通过 Console API 操作

登录获取 token：

```bash
TOKEN=$(curl -s -X POST http://<console>/api/login \
  -H 'Content-Type: application/json' \
	  -d '{"username":"admin","password":"<password>"}' | jq -r .token)
```

准备脚本变量：

```bash
MODEL_NAME='glm5'
PROVIDER_NAME='openrouter'
PROVIDER_BASE_URL='https://openrouter.ai/api/v1'
PROVIDER_DEFAULT_MODEL='z-ai/glm-5'
PROVIDER_API_KEY='<Provider API Key>'
HERMES_IMAGE='ccr.ccs.tencentyun.com/agentway/hermes:v2026.06.30-r1'
```

生产脚本不要把真实 `PROVIDER_API_KEY` 打到日志里，也不要提交到仓库。

配置模型网关：

```bash
curl -s -X PUT http://<console>/api/model-config \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  --data @- <<JSON
{
  "models": [
    {
      "modelName": "${MODEL_NAME}",
      "providerName": "${PROVIDER_NAME}",
      "baseUrl": "${PROVIDER_BASE_URL}",
      "apiType": "openai-completions",
      "defaultModel": "${PROVIDER_DEFAULT_MODEL}",
      "apiKey": "${PROVIDER_API_KEY}"
    }
  ]
}
JSON
```

设置出口白名单模式，并添加 Hermes 需要访问的模型 Provider：

```bash
curl -s -X PUT http://<console>/api/admin/settings/egress-mode \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"whitelist"}'

curl -s -X POST http://<console>/api/egress-rules \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{
    "ruleType": "l7",
    "target": "openrouter.ai",
    "port": 443,
    "protocol": "https",
    "enabled": true,
    "description": "Hermes model provider"
  }'
```

创建文件预设：

```bash
FILE_PRESET_ID=$(curl -s -X POST http://<console>/api/addon/file-presets \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  --data @- <<'JSON' | jq -r .id
{
  "displayName": "Hermes Dashboard Config",
  "description": "Hermes Dashboard config.yaml and .env",
  "items": [
    {
      "filePath": "/opt/data/config.yaml",
      "writeMode": "overwrite",
      "orderIndex": 0,
      "content": "model:\n  provider: \"custom\"\n  default: \"glm5\"\n  base_url: \"http://agent-way-model-gateway.agent-infra.svc.cluster.local:4000/v1\"\n  api_key: \"$MODEL_API_KEY\"\n\ndashboard:\n  basic_auth:\n    username: \"admin\"\n    password: \"$AGENT_ACCESS_TOKEN\"\n    secret: \"$AGENT_ACCESS_TOKEN\"\n"
    },
    {
      "filePath": "/opt/data/.env",
      "writeMode": "overwrite",
      "orderIndex": 1,
      "content": "API_SERVER_ENABLED=true\nAPI_SERVER_HOST=0.0.0.0\nAPI_SERVER_KEY=$AGENT_ACCESS_TOKEN\nGATEWAY_ALLOW_ALL_USERS=true\n"
    }
  ]
}
JSON
)
```

创建运行时：

```bash
RUNTIME_ID=$(curl -s -X POST http://<console>/api/runtimes \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  --data @- <<JSON | jq -r .id
{
  "displayName": "Hermes Dashboard on TKE",
  "description": "Hermes Dashboard image using AgentWay model gateway",
  "containerImage": "${HERMES_IMAGE}",
  "command": "/usr/local/bin/hermes-ags-entrypoint.sh",
  "shell": "bash",
  "accessPort": 9119,
  "accessPath": "login",
  "healthCheckPath": "login",
  "resourceCpu": 2,
  "resourceMemoryGi": 4,
  "runtimeCapabilitiesAdd": ["SETUID", "SETGID"],
  "envVars": [
    {"key": "HERMES_DASHBOARD", "value": "true"},
    {"key": "HERMES_DASHBOARD_HOST", "value": "0.0.0.0"},
    {"key": "HERMES_DASHBOARD_PORT", "value": "9119"}
  ]
}
JSON
)
```

创建模板并发布：

```bash
TEMPLATE_ID=$(curl -s -X POST http://<console>/api/templates \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  --data @- <<JSON | jq -r .id
{
  "displayName": "Hermes Dashboard on AgentWay TKE",
  "description": "Hermes Dashboard through AgentWay Kubernetes provider",
  "visibility": "all",
  "runtimeId": ${RUNTIME_ID},
  "filePresetIds": [${FILE_PRESET_ID}]
}
JSON
)

curl -s -X POST http://<console>/api/templates/${TEMPLATE_ID}/publish \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"changelog":"Create Hermes Dashboard template"}'
```

如果模板已经存在，也可以直接查询可用模板，找到 Hermes 模板的 `id`：

```bash
TEMPLATE_ID=$(curl -s http://<console>/api/templates \
  -H "Authorization: Bearer ${TOKEN}" \
  | jq -r '.templates[] | select(.displayName=="Hermes Dashboard on AgentWay TKE") | .id')
```

创建实例：

```bash
curl -s -X POST http://<console>/api/instances \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "hermes-dashboard-tke",
    "templateId": '"${TEMPLATE_ID}"'
  }'
```

查询实例：

```bash
curl -s http://<console>/api/instances \
  -H "Authorization: Bearer ${TOKEN}" | jq '.instances[] | select(.name=="hermes-dashboard-tke")'
```

重启实例：

```bash
curl -X POST http://<console>/api/instances/<agent-id>/restart \
  -H "Authorization: Bearer ${TOKEN}"
```

---

## 通过 Kubernetes API 对照

API 创建实例后，可以直接查看底层 `Agent`：

```bash
kubectl get agent <agent-id> -n <agent-id> -o yaml
```

你应该能看到：

- `spec.profile` 中包含镜像、端口、命令和环境变量
- `spec.fileInjects` 中包含 `/opt/data/config.yaml` 和 `/opt/data/.env`
- `metadata.labels` 中记录模板版本和 owner
- `status.phase` 最终进入 `Running`

---

## 预期效果

- 脚本可以创建 Hermes 实例
- Console 页面可以看到同一个实例
- Kubernetes 中可以看到对应 `Agent` CR

---

## 如何验证

```bash
curl -s http://<console>/api/instances -H "Authorization: Bearer ${TOKEN}" | jq .
kubectl get agent -A
```

---

## 下一章

完成后，继续：

- [09. 观测 Hermes 实例和平台资产](./09-observe-hermes-assets.md)
