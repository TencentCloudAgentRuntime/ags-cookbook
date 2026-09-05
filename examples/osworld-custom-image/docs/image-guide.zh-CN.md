# OSWorld 自定义镜像使用指南

## 镜像选择与版本

OSWorld1 base 用于现有 OSWorld Benchmark，OSWorld2 base 用于对应 V2 环境。
两者提供原生 linux/amd64 OCI 用户态，由 Cube 的 microVM 内核运行，无需在
沙箱中启动 QEMU。镜像来源与 server 版本分别记录，不能将内部 `v5.5.x`
镜像版本当作上游 Benchmark 版本。

当前处于个人 CCR 制品验证阶段。正式目标仓库为
`ccr.ccs.tencentyun.com/ags-image/osworld1-base` 和 `osworld2-base`；
获得发布批准并完成推送前，不应将目标地址当作已可拉取制品。
发布 tag 不覆盖；生产构建使用明确 tag 和经过验证的 digest。

`OSWORLD_BASE_IMAGE` 暂留空，不提供个人测试仓库作为客户默认值。
正式发布后填写 `ags-image` 中对应 base 的不可变 `tag@sha256` 引用。
Quickstart 以 OSWorld1 为演示；改为 OSWorld2 时替换该变量，无需新增 Dockerfile。

Docker 构建的 `FROM` 可以使用 `tag@sha256:...`。当前个人 CCR 的 AGS
创建链路不能直接复用这一写法：个人仓库解析需要 tag，而自动快照转换器不接受
同时包含 tag 和 digest 的引用。示例接收完整固定引用，以 tag 直接创建 Tool，
在启动实例前核对 Tool 保存的 `ImageDigest`；缺失或不一致时不启动实例。
不调用独立预热接口。必须保持 tag 不可变；发布新内容应换新版本，不能覆盖旧 tag。

## 可以定制什么

通过 `FROM` 继承 base，安装软件、复制文件、增加 systemd unit。保留
`/sbin/init`、桌面 `user`、OSWorld API 和显示/VNC 服务。修改这些约定后需要
自行验证 Benchmark。平台不强制这些约定，cookbook 校验也是可选的。

base 保留应用与配置，只清理无用 VM 内核、boot、缓存和日志，不为达到某个
体积数字删除任务需要的软件。base 在清理后导入为单层 OCI；用户的 Dockerfile
自然追加增量 layer。不要通过上层 `RUN rm` 期待删除下层已经存在的大文件。

## 运行接口

| 端口 | 用途 | 启动约定 |
| --- | --- | --- |
| 5000 | OSWorld API：截图、执行、上传、下载 | 随桌面环境启动 |
| 5910 | noVNC | 随桌面环境启动 |
| 8080 | VLC HTTP | 按任务使用与验证 |
| 9222 | Chrome/CDP 对外访问 | Benchmark/provider 按需启动 |

镜像不启用自定义常驻 CDP proxy 或 AGS tunnel。保留原生 `socat`，与现有
`osworld-ags` provider 的任务级 CDP 适配配合。raw VNC 5900 是 noVNC 内部依赖。

## 自动快照

当前名称包含 `auto-snapshot` 的合资格 Tool 会触发自动快照，脚本封装该命名。
快照复用取决于镜像和有效运行配置，不能只看 Tool 名称或相同 tag。
Quickstart 等 Tool ACTIVE 后立即启动：命中已有快照就复用，未就绪时允许
冷启动。更换镜像内容或运行配置可能需要制作新的快照。
`make snapshot` 会显示快照状态；当前 API 可能将它放在
`StatusReason` 的 `SnapshotStatus=...` 中，脚本兼容该形式。

制品首次准备可能较久，创建 Tool 时由平台完成；本示例不依赖独立预热接口。
跳过独立接口并不表示跳过平台内部的镜像准备。镜像准备与应用内存快照是不同阶段。
云接口失败时应查看其 RequestId 与 Tool 状态，避免盲目重复创建。

## OSWorld2 的 Docker 存储

Docker 的数据目录需要 ext4 backing filesystem，不能直接使用 Cube 根
overlay。镜像提供先于 Docker/containerd 执行的 systemd 准备：如果目标目录
已经在 ext4 上就直接使用，否则按当前容器的根 overlay 可写层定位其 backing
device，将当前容器可写目录下的 Docker/containerd 子目录 bind mount 出来。
它不格式化设备，也不假定 `/dev/vda` 是业务盘；多容器模式下该设备可能属于
monitor sidecar。未知挂盘布局会明确失败。Docker 可由任务安装，API 用法不变。

创建后确认 `/var/lib/docker` 和 `/var/lib/containerd` 的 backing filesystem，
再验证 pull、build（包含删除基础层文件）、run、bridge/DNS、端口映射与 volume。
Docker 29 的大部分镜像数据可能在 containerd 目录，仅扩 Docker 目录不够。
挂载新的数据目录会遮蔽镜像中原有 Docker 缓存。冷启动时该方案与业务根可写层
共享容量和配额，并没有凭空增加一块独立大盘；必须核对实际可用容量。
`Storage=20Gi` 示例不能承诺满足需要 100Gi 的 heavy task。

快照恢复后须再次验证 Docker 服务与存储，不能拿冷启动成功代替恢复验证。
本节完整支持范围以随制品发布的实测报告为准。

## 凭证与清理

模型凭证在恢复/启动实例后经 `5000` API 注入私有临时文件，不通过镜像构建
或 Tool 默认环境固化。运行实例的 token 通过 AGS API 单独获取。
交互实例最多保留一小时；`make clean` 提前回收。自动测试实例在 finally 中停止。
上传凭证后不要直接将实例再次制作成可共享快照。
