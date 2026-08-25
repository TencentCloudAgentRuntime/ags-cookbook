# DeepSeek Harness all-in-one 镜像

本目录构建以下固定版本镜像：

```text
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.3
```

Dockerfile 从 DeepSeek 官方仓库 clone `dsh-v0.1.1-rc.2`，核对 commit `b150a551b8d465e31e418e1b2eaf5e79bbb7d28e`，应用仓库内保留的 [`0001-support-ags-deployment-web.patch`](./0001-support-ags-deployment-web.patch)，再执行依赖安装、patch 专项测试与官方完整构建。构建阶段使用上游 release 流程打包 `vendor` 和 `dsh` 两个 package family；最终 `linux/amd64` 阶段安装这些包，并以 Node 的 `--expose-internals` flag 启动官方 CLI，不使用额外 wrapper 脚本。

patch 只处理 Web 部署所需的三处兼容性：

1. 允许显式使用 `dsh web --host 0.0.0.0`。
2. 允许 `trustedHosts` 使用形如 `*.ap-shanghai.agents.tencentags.com` 的单层泛域名；它只匹配一个最左侧 DNS label，不是通用 glob。
3. 当反向代理请求的 HTTPS `Origin` 和改写后的 `Host` 分别命中显式 `trustedHosts` 时允许访问；这只覆盖 AGS 网关的 Deployment 外部域名与实例内部域名，不信任任意地址。

## 构建并发布

先登录 CCR：

```bash
podman login ccr.ccs.tencentyun.com
```

在本目录构建并推送 `linux/amd64` 镜像：

```bash
podman build \
  --platform linux/amd64 \
  --tag ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.3 \
  .

podman push \
  ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.3
```

验证远端 manifest：

```bash
skopeo inspect docker://ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.3
```

本示例不发布 `latest`。升级时应同时更新官方 tag、commit、patch、CCR 版本标签与教程中的镜像引用，并重新运行构建内测试和完整部署验证。
