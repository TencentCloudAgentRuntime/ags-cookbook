# SWE 官方组件的 AGS 支持

> 本文件夹为第三方开源项目 SWE-ReX 的修改，原始项目地址：https://github.com/SWE-agent/SWE-ReX 。遵循其 LICENSE.txt 规定，版权归原作者所有。

## 基础介绍

我们在 SWE-ReX 1.4.0 版本基础上实现了 AGS Runtime 和 AGS Deployment，允许用户将 SWE 任务部署到腾讯云 AGS 上运行。

SWE-ReX AGS 支持采用分层架构设计：

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SWE-Agent     │────│   SWE-ReX       │────│   Tencent AGS   │
│                 │    │                 │    │                 │
│ • Agent Logic   │    │ • AGSRuntime    │    │ • SandboxTool   │
│ • Task Execution│    │ • AGSDeployment │    │ • SandboxInstance│
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 核心组件

#### 1. TencentAGSDeployment
- **位置**: `src/swerex/deployment/ags.py`
- **功能**: 管理 AGS 沙箱实例的完整生命周期
- **核心特性**:
  - 支持创建和管理 SandboxTool
  - 自动启动和停止 SandboxInstance
  - 实现 Token 自动刷新机制
  - 支持存储挂载配置

#### 2. AGSRuntime
- **位置**: `src/swerex/runtime/ags.py`
- **功能**: 与 AGS 沙箱实例通信的运行时
- **核心特性**:
  - 使用 X-Access-Token 进行 AGS 网关认证
  - 支持自动 Token 刷新
  - 与标准 RemoteRuntime 兼容

#### 3. TencentAGSDeploymentConfig
- **位置**: `src/swerex/deployment/config.py`
- **功能**: AGS 部署配置管理
- **配置项**:
  - 腾讯云认证信息 (SecretId/SecretKey)
  - 镜像注册表类型 (enterprise/personal)
  - RoleArn 支持 (从环境变量获取)
  - 存储挂载配置

#### 4. AGSRuntimeConfig
- **位置**: `src/swerex/runtime/config.py`
- **功能**: AGS 运行时配置管理
- **配置项**:
  - AGS Token 认证
  - SWE-ReX 服务器认证
  - 连接超时设置

## AGS 配置参考

### TencentAGSDeploymentConfig 配置项

可以通过 --instances.deployment.<配置项>=<值> 来配置 AGS 部署组件，具体配置项如下：

| 配置项 | 环境变量 | 说明 | 默认值 |
|--------|----------|------|--------|
| `secret_id` | `TENCENTCLOUD_SECRET_ID` | 腾讯云 SecretId（访问密钥ID） | 空字符串 |
| `secret_key` | `TENCENTCLOUD_SECRET_KEY` | 腾讯云 SecretKey（访问密钥） | 空字符串 |
| `role_arn` | `TENCENTCLOUD_ROLE_ARN` | 角色ARN，用于访问容器镜像仓库 | 空字符串 |
| `http_endpoint` | - | 腾讯云HTTP端点 | `ags.tencentcloudapi.com` |
| `skip_ssl_verify` | - | 跳过SSL证书验证（用于内部/预发布端点） | `false` |
| `region` | - | AGS服务区域 | `ap-chongqing` |
| `domain` | - | 沙箱端点域名 | `ap-chongqing.tencentags.com` |
| `tool_id` | - | 现有SandboxTool ID（为空时创建新工具） | 空字符串 |
| `image` | - | 沙箱容器镜像，对应数据集中镜像 | `python:3.11` |
| `image_registry_type` | - | 镜像注册表类型（enterprise/personal等） | `enterprise` |
| `timeout` | - | 沙箱实例超时时间（如：5m、300s、1h） | `1h` |
| `port` | - | 沙箱端点端口 | `8000` |
| `startup_timeout` | - | 运行时启动等待时间 | `180.0` |
| `runtime_timeout` | - | 运行时请求超时时间 | `60.0` |
| `cpu` | - | CPU资源限制 | `1` |
| `memory` | - | 内存资源限制 | `1Gi` |
| `mount_name` | - | 挂载名称 | 空字符串 |
| `mount_image` | - | 额外挂载的镜像，通常是 swerex server 镜像 | 空字符串 |
| `mount_image_registry_type` | - | 挂载镜像的注册表类型 | `enterprise` |
| `mount_path` | - | 存储挂载路径 | `/nix` |
| `image_subpath` | - | 镜像挂载内的子路径 | `/nix` |
| `mount_readonly` | - | 挂载是否为只读 | `false` |


### 环境变量配置说明

- **认证信息优先级**：环境变量优先级高于配置文件中的设置
- **自动获取机制**：如果配置文件中未设置`secret_id`、`secret_key`或`role_arn`，系统会自动从对应的环境变量中获取

### 挂载镜像说明
由于目前 ags 启动时间有限制，如果不挂载 swerex server 镜像，可能会导致首次运行时需要下载依赖包而超时失败。建议配置 `mount_image` 为 swerex server 镜像，并设置合理的挂载路径。
