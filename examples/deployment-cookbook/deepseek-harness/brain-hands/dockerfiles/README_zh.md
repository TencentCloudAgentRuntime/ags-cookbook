# Brain 与 Hands 镜像源码

[English](./README.md) | 中文

两个镜像都从公开且固定的输入构建：

| 镜像 | 关键 pin |
| --- | --- |
| Brain | 按 digest 固定的 Node `24.8.0-bookworm-slim`、pnpm `11.19.0`、DSH package `0.1.0-rc.8`、E2B SDK `2.29.1`。 |
| Hands | 按 digest 固定的 Go `1.26.5-alpine` 与 Ubuntu `24.04`，以及 envd commit `2acf2d51bd1e2fe146914f24c44f7ee07d2213c5`（版本 `0.6.13`）。 |

Hands builder checkout 精确的 envd commit，并校验编译结果报告的版本。Brain 固定 Node 的 `linux/amd64` 子清单而不是不区分架构的 tag，使用已提交的 `pnpm-lock.yaml`，应用已提交的 E2B 禁止 redirect patch，编译 TypeScript，再删除开发依赖。

## 第三方许可证边界

精确版本的 DSH `0.1.0-rc.8` package 与 E2B SDK `2.29.1` 均声明 MIT 许可证；其许可证文件保留在 Brain 生产镜像的 `node_modules` 中。固定的 envd 源码采用 Apache-2.0；Hands 会从同一固定 commit 复制上游许可证到 `/usr/share/doc/envd/LICENSE`。腾讯云 SDK 采用 Apache-2.0，其他直接 Node runtime 依赖采用 MIT、BSD-2-Clause 或 Apache-2.0。

`pnpm licenses list --prod` 当前解析出 215 个生产依赖，许可证类别包括 MIT、Apache-2.0、BSD-2-Clause、BSD-3-Clause、ISC、0BSD、BlueOak-1.0.0 与 `(Apache-2.0 AND BSD-3-Clause)`。发布时仍须重新生成该清单和镜像 SBOM，因为传递依赖元数据与 OS package 属于最终构建产物，而不只属于本源码 manifest。

## 构建

在 `brain-hands` 目录运行：

```bash
make build
```

等价命令为：

```bash
podman build --platform linux/amd64 \
  --tag ags-cookbook/dsh-brain:local \
  --file dockerfiles/brain/Dockerfile .

podman build --platform linux/amd64 \
  --tag ags-cookbook/dsh-hands:local \
  --file dockerfiles/hands/Dockerfile dockerfiles/hands
```

npm、Alpine、Ubuntu 和 Go 下载使用腾讯云镜像；Git 源码仍从固定 commit 的公开 upstream URL 获取。

## 发布前验证

```bash
pnpm typecheck
pnpm test
pnpm test:mysql

podman image inspect ags-cookbook/dsh-brain:local
podman image inspect ags-cookbook/dsh-hands:local
pnpm licenses list --prod
```

使用 `.env.example` 中的变量启动 Brain，要求 `GET /readyz` 返回 `200`。启动 Hands 后，要求端口 `49983` 的 `GET /health` 返回 `200`；还要通过 E2B `2.29.1` 完成文件写入、读取和命令执行，不能只用 `curl` 验证。

发布前，请使用镜像仓库配套工具生成 SBOM 与漏洞报告，记录不可变镜像 digest，并对 digest 签名。仓库中的 [release manifest](../release-manifest.json) 记录源码身份与镜像预期内容；它不会假装已有发布 digest。

## 镜像边界

Brain 包含 DSH、MySQL 连接、腾讯云 API client 与 E2B client，不保存权威本地 session 目录。

Hands 包含 `envd`、`bash`、CA certificate、`curl`、`git`、`procps`、`ripgrep` 和 `util-linux`。构建时会拒绝错误的 envd 版本。Hands 明确不包含 Node.js、DSH、MySQL、SQLite 或 COS 集成。
