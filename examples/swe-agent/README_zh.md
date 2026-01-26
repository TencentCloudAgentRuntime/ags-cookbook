# SWE-agent 借助 AGS 集成示例

本示例展示如何在 SWE-agent 任务中集成 AgentSandbox 沙箱，实现"读取 swe instances → 远程启动代码沙箱环境 → 模型在沙箱中推演 → 生成轨迹"的完整流程。

## 功能特性
- 沙箱隔离，安全可靠，快速部署
- swe-agent自动化推理流程

## 核心概念

```
┌─────────────────┐    ┌─────────────────┐    ┌──────────────────┐
│   SWE-Agent     │────│SWE-ReX(modified)│────│   Tencent AGS    │
│                 │    │                 │    │                  │
│ • Agent Logic   │    │ • AGSRuntime    │    │ • SandboxTool    │
│ • Task Execution│    │ • AGSDeployment │    │ • SandboxInstance│
└─────────────────┘    └─────────────────┘    └──────────────────┘
```

## 快速开始

### 1. 使用修改后的 SWE-ReX
下载 SWE-agent 官方项目，并替换其中的 SWE-ReX 代码为本示例中的修改版本，以支持 AGS 沙箱集成。

```bash
git clone https://github.com/SWE-agent/SWE-agent.git
cp -r SWE-ReX ./SWE-agent/
cd SWE-agent

cat > ./fix_pyproject_dependency.patch << EOF
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -57,7 +57,7 @@ dependencies = [
     "litellm",
     "GitPython",
     "ghapi",
-    "swe-rex>=1.4.0",
+    "swe-rex @ file://$(pwd)/SWE-ReX",
     "tabulate",
     "textual>=1.0.0",
     "requests",
EOF
git apply ./fix_pyproject_dependency.patch
uv venv
uv pip install -e .
uv run sweagent b --help_option swerex.deployment.config.TencentAGSDeploymentConfig
```

### 2. 配置模型 API 参数

```bash
cat > local_model.yaml << EOF
agent:
  model:
    name: zai/glm-4.6
    api_key: xxx
    api_base: http://ip:port/v1
  tools:
    enable_bash_tool: true
EOF
```

### 3. 设置 AGS API Key
```bash
cat > .env << EOF
TENCENTCLOUD_SECRET_ID=AKIDxxxx
TENCENTCLOUD_SECRET_KEY=Skxxx
TENCENTCLOUD_ROLE_ARN=qcs::xxx
EOF
```

### 4. 配置任务参数

```bash
cat > instances.yaml << EOF
instances:
  type: swe_bench
  subset: lite
  split: test
  deployment:
    type: tencentags
    http_endpoint: ags.tencentcloudapi.com
    region: ap-chongqing
    domain: ap-chongqing.tencentags.com
    tool_id: ""
    mount_name: rex
    mount_image: tencentcloudcr.com/example/swerex-runtime:1.4.0
    mount_image_registry_type: enterprise
    mount_path: /nix
    image_subpath: /nix
    mount_readonly: false
EOF
```
这里推荐将 swe rex runtime 镜像通过挂载的方式(mount_image)加载到 AGS 沙箱中，启动更快。SWE 相关镜像最好先使用 Tencent AGS 提供的预热接口进行预热，以减少首次启动时间。

### 5. 运行

```bash
uv run sweagent run-batch \
    --config ./local_model.yaml \
    --config config/default.yaml \
    --config ./instances.yaml \
    --num_workers 1
```

运行时，会使用 SWE 实例对应镜像启动 AGS 沙箱环境，然后在沙箱中执行模型生成的命令，最后输出轨迹结果。


## 技术亮点
- 沙箱环境可高度定制
- 自动化资源管理与清理
- 快速集成至现有SWE-agent流程

## 拓展
可以查看修改后的 SWE-ReX 项目中的概念详解，阅读相关代码，了解更多调用细节。