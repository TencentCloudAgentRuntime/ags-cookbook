# 在 AGS 中运行 Docker-in-Docker

本示例提供一个可直接用于 AGS Custom Tool 的 DinD 镜像。Sandbox 启动完成后，`dockerd`、`docker compose` 和 `envd` 已经就绪，调用方可以立即上传文件并以 `root` 执行命令，不需要再手工挂盘或启动 daemon。

公开镜像：

- 广州：`ccr.ccs.tencentyun.com/ags-image/dind:v1.0.0`
- 香港：`hkccr.ccs.tencentyun.com/ags-image/dind:v1.0.0`
- OCI image index：`sha256:b1332e5cfaeaa335e1c3aae69ffd8a84b42dd78e014247e972d56003338595d3`
- 架构：`linux/amd64`
- 构建文件：[`image/Dockerfile`](./image/Dockerfile)

镜像基于官方 `docker:29.3.1-dind`，包含 Docker Engine、Docker CLI、BuildKit、Docker Compose 5.1.1、`bash`、`util-linux`，以及从本仓库源码构建的 [`envd` 0.5.14-oci](../../utils/envd/versions/0.5.14-oci/)。

启动脚本 [`image/entrypoint.sh`](./image/entrypoint.sh) 会自动识别 cgroup，将 AGS 注入的 `/dev/vda` 挂载到 `/mnt`，再把 Docker 和 containerd 的数据目录 bind mount 到数据盘。随后它以 `root` 启动并监管 `dockerd` 与 `envd`；只有两者都可用后 readiness probe 才会通过。

如果需要构建镜像，可以在本目录执行，并上传到个人的 CCR 或 TCR 上使用：

```bash
make build-image
```

构建结果可以推送到自己的 TCR/CCR，也可以直接使用上面的公开镜像。

## 前置条件

- 使用最新版 `agr`。
- 已配置腾讯云凭证。
- 本示例选择香港 `PUBLIC` 网络，因为需要从 GitHub、PyPI 和 Docker Hub 下载 Harbor 及示例镜像。

## 1. 创建 Tool 和 Sandbox

运行初始化检查。它会确认 `agr` 已安装且为最新版本，并在需要时从 `.env.example` 创建 `.env`：

```bash
make setup
```

继续前请检查 `.env`。如果本机的 `agr` 尚未配置腾讯云凭证，请填写 `TENCENTCLOUD_SECRET_ID` 和 `TENCENTCLOUD_SECRET_KEY`；使用临时凭证时同时填写 `TENCENTCLOUD_TOKEN`。[`tool-custom-configuration.hk.json`](./tool-custom-configuration.hk.json) 通过固定 digest 匿名拉取香港公开镜像，并申请 4 CPU、8 GiB 内存和 20 GiB 磁盘，不需要 `RoleArn`。

创建 Tool 和 Sandbox：

```bash
make create-tool
make start
```

Tool ID 和 Instance ID 会分别写入 `.tool-id` 与 `.instance-id`。`make start` 会等待 envd 数据面可用，并检查默认用户为 `root`、默认目录为 `/workspace`，以及 Docker Engine 和 Compose 是否已经就绪。

也可以直接执行命令：

```bash
agr --region ap-hongkong instance exec "$(cat .instance-id)" \
  --user root -- docker compose version
```

## 2. 使用 Harbor Oracle 运行真实的 Terminal-Bench Compose 任务

本示例使用 Harbor v0.22.0 内置的 `oracle` agent，运行 Terminal-Bench 3.0.0 的真实任务 [`intrastat-meldung`](https://github.com/harbor-framework/terminal-bench/tree/v3.0.0/tasks/intrastat-meldung)：

```bash
make harbor-oracle
```

[`run-harbor-oracle.sh`](./scripts/run-harbor-oracle.sh) 先通过 envd 上传 runner。runner 在 Sandbox 内安装 Git、Python 和 `uv`，只检出这个任务，然后执行：

```bash
harbor trial start \
  --path terminal-bench/tasks/intrastat-meldung \
  --agent oracle \
  --env docker
```

接下来由 Harbor 通过内层 Docker daemon 管理完整的任务生命周期：

1. 使用任务原始的 Dockerfile 构建镜像，并启动由 `main`、`odoo`、`compliance-hub`、`idev`、`services` 和 `dms` 组成的六服务 Compose 环境。
2. 等待各 service 健康，将任务的 `solution/` 复制到 `main`，并运行官方 Oracle。Oracle 实时调用五个 sidecar 的 API 完成任务并生成产物。
3. 按照 `task.toml` 的声明，从 `main` 和 `compliance-hub` 收集 artifacts。
4. 使用原始 `tests/Dockerfile` 构建 verifier，按照 `task.toml` 的声明在独立环境中执行验证，并要求 reward 为 `1.0`。
5. 清理 Compose 容器、网络和卷，并将结构化结果写入 `/mnt/ags-dind/harbor-oracle-intrastat-meldung-v3.0.0/trials/`。

这一个任务会实际验证 AGS DinD 镜像上的 Harbor 原生流程，包括 Compose 启动与 healthcheck、service DNS、共享卷、跨 service artifact 收集、Oracle 执行、独立 verifier 和资源清理。

成功时最后会输出：

```text
Harbor Oracle validation: PASS (.../result.json)
```

首次使用时，也可以执行 `make run`，连续完成 Tool 创建、Sandbox 启动和 Oracle 验证。

## 清理

完成后删除本示例创建的 Instance 和 Tool：

```bash
make cleanup
```
