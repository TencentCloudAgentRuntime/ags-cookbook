# DSH 切换镜像：构建说明

返回 [DSH 切换参考实现](../README_zh.md)。

## 为什么必须从源码构建

基础示例直接安装已发布的 `@deepseek-ai/dsh` 包。本方案要改 DSH 框架自身的代码（保留 Agent 的销毁句柄、新输入前的检查点、`turn/start` 的持久化屏障），已发布的包里没有这些，所以必须：

1. 取固定版本的 DSH 源码（tag `dsh-v0.2.1-rc.2`，并校验提交 `687f282e8625c6b8d11ff58211a90524be2e4317`）；
2. 应用 [`0001-stateless-handoff.patch`](./0001-stateless-handoff.patch)；
3. 按锁文件安装依赖，跑测试，用官方方式构建；
4. 把编译好的工作区复制到运行阶段，再安装本目录的插件。

做法与 `deployment-cookbook` 里 all-in-one 镜像给 DSH 打补丁的方式相同。

## 构建

在 reference 根目录（不是本目录）执行：

```sh
docker build --build-arg DSH_GATE_CONCURRENCY=1 -f dockerfiles/Dockerfile -t dsh-session-handoff:local .
```

构建过程中会运行两组测试，任何一组失败，构建都会中止：

- 安装依赖之后、长时间构建之前：`session-controller` 的三个测试文件（Agent 句柄、新输入受理、控制器）；
- `build:official` 之后：`agent-loop` 的全部测试（保护 `turn/start` 的同步追加和占位屏障）。这组测试里有一部分要用 DSH 的 native 插件做文件锁，而 native 插件是 `build:official` 编译出来的，所以只能放在构建之后。

## 构建参数

| 参数 | 默认值 | 什么时候改 |
| --- | --- | --- |
| `DSH_GATE_CONCURRENCY` | 不设置（按 CPU 数并行） | Docker 虚拟机内存约 8 GB 时设为 `1`。否则并行的构建步骤会内存不足，BuildKit 报 `error reading from server: EOF` |
| `BUILD_IMAGE` | `node:24.22.2-bookworm-slim` | 内网镜像源里的同版本 Node 镜像 |
| `RUNTIME_IMAGE` | `node:24.8.0-bookworm-slim` | 同上 |
| `DSH_MODULES` | `/opt/deepseek-harness/apps/cli/node_modules/@deepseek-ai` | 一般不用改。DSH 的 `@deepseek-ai/*` 包不在这个路径时才改 |

构建阶段和运行阶段使用不同的 Node 镜像：`node:24.8.0-bookworm-slim` 自带的 Debian 密钥早于 bookworm 的归档密钥轮换，`apt-get update` 会报 `NoPubKey`，构建阶段需要 `apt` 安装 `git` / `g++` / `make` / `python3`，所以用较新的镜像；运行阶段沿用基础示例的版本。

## 常见问题

**`pnpm install` 停在 SheetJS 上，很久不动。**
DSH 的锁文件里有一个包（`xlsx`）只能从 `cdn.sheetjs.com` 下载，不在 npm 仓库里。这个地址在部分网络下很慢（实测每秒几百字节到几十 KB）。Dockerfile 已把 pnpm 的存储放进 BuildKit 缓存，并把下载超时放宽到 30 分钟，**第二次构建会复用已下载的内容**。如果仍然卡住：保持构建缓存，换一个能直连该地址的网络重试，或者在内网镜像里预置这个包。不要用空包替代，也不要关闭锁文件校验，否则构建结果不可信。

**`apt-get update` 报 `NoPubKey` / `not signed`。**
构建阶段用的 Node 镜像太旧。保持默认的 `BUILD_IMAGE`，或换成较新的 bookworm 镜像。

**构建到一半 Docker 报 `error reading from server: EOF`，或安装步骤出现 `Killed`。**
Docker 虚拟机内存不足。构建步骤设置 `DSH_GATE_CONCURRENCY=1`；运行阶段的镜像直接复制已编译的工作区，不再对几百个包做一次全局安装，就是为了避免这类内存峰值。

**镜像很大。**
运行阶段保留了完整的已编译工作区和依赖图，以避免重新解析依赖；代价是体积。按实际运行架构（`amd64` / `arm64`）构建，原生依赖与架构绑定。

## 升级 DSH 版本

补丁只针对 `dsh-v0.2.1-rc.2`，不要假设它能直接用于别的版本。升级时：

1. 取新的 tag，先执行 `git apply --check`；
2. 冲突通常出现在四个位置：`ApiSessionAgentController` 的 create/resume 与句柄保存、`SessionCommandController.prompt` 的受理路径、`SessionController` 的转发方法、`agent-loop` 的 `turn()`；
3. 如果上游已经提供了等价的"新输入前钩子"和"按会话销毁 Agent"的原生接口，直接删除补丁，改用原生接口注册服务；
4. 如果同时需要 AGS 部署补丁（`0001-support-ags-deployment-web.patch`），先应用部署补丁，再应用本补丁，并重新运行测试。
