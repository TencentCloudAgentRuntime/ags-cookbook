# go-httpbin 镜像

Deployment 示例使用以下固定版本的公共镜像：

```text
ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0
```

本目录的 Dockerfile 基于 go-httpbin release `v2.25.0` 对应的上游镜像 `ghcr.io/mccutchen/go-httpbin:2.25.0`。它不修改入口命令，只保留上游的非 root 运行方式、默认 `8080` 端口和 httpbin 行为。发布到 CCR 后统一使用带 `v` 的版本标签 `v2.25.0`。

## 构建并发布

先登录 CCR：

```bash
docker login ccr.ccs.tencentyun.com
```

在本目录执行多架构构建并直接推送：

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0 \
  --push \
  .
```

验证远端 manifest：

```bash
docker buildx imagetools inspect \
  ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0
```

升级镜像时应同时修改 Dockerfile 的上游版本、CCR 标签以及所有 Markdown 教程中的镜像引用，并重新执行四个示例的验证。
