# 将 QCOW2 虚拟机镜像转换为容器镜像

**如果需要自定义 OSWorld，推荐基于我们提供的 OSWorld 基础镜像构建。** 如果只是安装软件、
替换配置或添加任务数据，请使用[基础镜像使用指南](image-guide.zh-CN.md)中的
Dockerfile 方式。这条路径保留了已验证的桌面、启动和 Docker 存储适配，
也更容易定位自定义改动带来的问题。

本文介绍 Linux QCOW2 镜像提取 rootfs、适配并生成容器镜像的流程，不要求源镜像
安装 OSWorld 或桌面。文末以 OSWorld 为例说明桌面场景的适配和验证。
**导出文件系统成功、生成容器镜像成功，不代表能在 AGS 的 Cube 运行环境中
正常启动，也不代表原有业务兼容。** 自定义启动脚本、设备等待、磁盘挂载、
网络管理或第三方安全软件，都可能导致启动失败、就绪超时或桌面黑屏。
这是一套需要人工审查的迁移流程，不是适配任意 QCOW2 的一键转换器。

## 先选择迁移方式

| 需求 | 推荐方式 |
| --- | --- |
| 安装工具、依赖，添加业务数据 | 基于适合业务的容器基础镜像编写 Dockerfile；OSWorld 可使用提供的 base OCI |
| 只需要旧 VM 中的部分文件 | 提取所需文件，再 COPY 到适合业务的基础镜像 |
| 必须保留旧 VM 的完整系统和应用环境 | 按本文提取 rootfs、逐项适配并实测 |
| 依赖原内核、特定 GPU/虚拟设备或主机级服务 | 先确认依赖能否移除或替换，不能直接承诺迁移成功 |

QCOW2 是虚拟磁盘格式，OCI 镜像包含文件系统和启动配置。迁移后由 Cube 提供
运行内核和设备环境，不会执行原 QCOW2 中的 GRUB、EFI 引导或内核。
`qemu-img convert` 只能转换虚拟磁盘格式，不能完成容器化适配。

## 1. 准备工具和磁盘空间

下面以 **Linux/amd64、Ubuntu/Debian、systemd、单个 ext4 根文件系统**为例。
Windows、其他架构、加密分区、
多个系统或独立 `/usr`、`/var`、`/home` 分区不能直接照抄。

以下命令在 Linux 环境中执行，需要 Docker、qemu-img 和 libguestfs。
已安装 Docker 后，在 Ubuntu/Debian 上安装其余工具并检查是否可用：

```bash
sudo apt-get update
sudo apt-get install -y qemu-utils libguestfs-tools
docker version
libguestfs-test-tool
```

磁盘空间应覆盖源镜像、工作副本、解包后的 rootfs 和 Docker 镜像存储，不能只按
QCOW2 的文件大小估算。先正常关闭源 VM，再取得完整镜像及来源方提供的 SHA256。

本流程使用 libguestfs 读取和修改镜像文件系统，无需手动挂载源镜像，也无需启动
源虚拟机系统。`libguestfs-test-tool` 用于检查所需的运行环境是否可用；
libguestfs 会使用辅助 QEMU 环境，是否有虚拟化加速会影响处理速度。

## 2. 校验磁盘并识别根文件系统

以下命令在同一个 Bash 会话运行。替换源路径和 SHA256：

```bash
set -euo pipefail
SOURCE="$(realpath /path/to/source.qcow2)"
WORK="$(mktemp -d "$HOME/qcow2-migrate.XXXXXX")"
EXPECTED_SHA256='替换为来源方提供的64位SHA256'

printf '%s  %s\n' "$EXPECTED_SHA256" "$SOURCE" | sha256sum -c -
qemu-img info -f qcow2 --output=json "$SOURCE"
```

检查格式、虚拟磁盘容量、`backing-filename` 和外部数据文件等依赖。如果存在外部
依赖，先请来源方提供经过校验的独立镜像，不要跟随不明路径继续转换。
确认后检查 QCOW2 元数据，并创建只写入改动的工作副本：

```bash
qemu-img check -f qcow2 "$SOURCE"
qemu-img create -f qcow2 -F qcow2 -b "$SOURCE" "$WORK/working.qcow2"
virt-filesystems --format=qcow2 -a "$WORK/working.qcow2" --all --long -h
virt-inspector --format=qcow2 -a "$WORK/working.qcow2" > "$WORK/inspection.xml"
```

原文件保持不变；工作副本在导出前仍依赖它。不要对原文件运行自动修复命令。
`qemu-img check` 不等于检查了磁盘里的 ext4 文件系统；发现文件系统损坏时，应在
副本上诊断并修复，不能忽略错误直接导入。

查看 `inspection.xml` 中的操作系统、架构和挂载点。下面的 `/dev/sda3` **只是示例**，
必须换成检测到的根设备，也可能是 LVM 逻辑卷。不能选 EFI 或 boot 分区。

```bash
ROOT_DEVICE=/dev/sda3
guestfish --ro --format=qcow2 -a "$WORK/working.qcow2" \
  -m "$ROOT_DEVICE":/ cat /etc/os-release
guestfish --ro --format=qcow2 -a "$WORK/working.qcow2" \
  -m "$ROOT_DEVICE":/ cat /etc/fstab
```

如果必要目录位于其他文件系统，先设计如何合并到导出的目录树；只导出根分区会
漏掉这些文件。本文后续命令仅适用于确认后的单根文件系统。

对 ext4，还应在**未挂载**状态下做只读文件系统检查：

```bash
guestfish --ro --format=qcow2 -a "$WORK/working.qcow2" <<EOF
run
debug sh "e2fsck -fn $ROOT_DEVICE"
EOF
```

检查完整输出，不能只看命令是否成功返回。如果出现 inode、目录或校验和错误，
先保留诊断记录，再在额外的工作副本中修复并重新检查。重要文件还应与来源校验和
或已安装软件包的文件清单核对，避免把“文件系统修复成功”当成“文件内容完好”。

## 3. 审查并适配运行环境

先检查服务 unit、启动脚本和软件依赖，再修改工作副本。建议将修改记录成自己的
`adapt.sh`，方便重复构建和回退。

| 检查项 | 需要处理的内容 |
| --- | --- |
| 挂载 | 移除对原磁盘 UUID、EFI、swap、数据盘的启动依赖，不原样保留 VM 的 fstab |
| VM 服务 | 检查 cloud-init、guest agent、ACPI、模块加载等服务，只禁用确认不再需要的项目 |
| 自定义服务 | 排查 `Requires=`/`After=`、无限重试脚本、设备等待和第三方守护进程，避免阻塞启动或重启循环 |
| 网络 | 去掉对原网卡名、固定 IP 和失效 DNS 的依赖，不让自定义脚本覆盖运行时网络 |
| 业务服务 | 确认依赖、运行用户、工作目录、监听地址和端口，保留业务所需接口 |
| 设备与 systemd | 验证 `/dev/null` 等设备权限、cgroup 可见性和 PID 1，不依赖 VM 中静态保存的 `/dev` |
| 共享内存（按需） | 按业务需要配置 `/dev/shm` 容量，并在实际沙箱中核对；构建时修改临时挂载不会保留到运行时 |
| DinD（按需） | 需要运行 Docker 时，检查 Docker/containerd 数据目录、cgroup 和存储驱动 |
| 身份与缓存 | 清理机器标识、旧 SSH 主机密钥、浏览器锁、socket、日志及可重建缓存；检查各用户目录中的凭证 |

**仅当镜像包含桌面或 OSWorld 时**，再检查图形环境：无物理显卡时可配置 dummy
Xorg；核对桌面自动登录、Xauthority 和会话 D-Bus。需要远程桌面时配置相应服务，
例如 x11vnc/noVNC。OSWorld 场景建议 `/dev/shm` 至少 4 GiB，并检查 OSWorld server。
不使用这些功能的镜像无需安装或验证它们。

不要按固定名单删除用户服务，也不要不加区分地清空系统目录。先验证功能，再按需
移除不使用的 boot 文件、内核模块、固件和缓存，以免破坏软件安装脚本或特定任务。
不要将某一个环境变量或驱动替换视为能保证兼容的万能修复。

对选定的单系统工作副本执行审查后的脚本：

```bash
# adapt.sh 由你根据检查结果编写；在镜像内执行，不是在宿主机直接执行。
ADAPT_SCRIPT="$(realpath /path/to/adapt.sh)"
virt-customize --format qcow2 -a "$WORK/working.qcow2" --run "$ADAPT_SCRIPT"
```

例如，确认必要数据已放入单根文件系统、不再需要原 fstab 条目后，可将下面内容
纳入 `adapt.sh`。这只是挂载配置示例，**不是完整的桌面或 systemd 适配脚本**：

```sh
#!/bin/sh
set -eu
cp -a /etc/fstab /etc/fstab.vm-backup
printf '# Mounts are supplied by the container runtime.\n' > /etc/fstab
rm -f /swapfile
```

## 4. 导出 rootfs，生成容器镜像

完成适配并停止修改后，导出文件树。保留数字 UID/GID、扩展属性和 ACL 等信息，
不要先用普通用户解包到宿主机目录再重新打包，以免丢失权限。选项说明见
[guestfish 文档](https://libguestfs.org/guestfish.1.html#tar-out)。

```bash
guestfish --ro --format=qcow2 -a "$WORK/working.qcow2" -m "$ROOT_DEVICE":/ \
  tar-out / "$WORK/rootfs.tar" numericowner:true xattrs:true acls:true selinux:true

CUSTOM_IMAGE='ccr.ccs.tencentyun.com/YOUR_NAMESPACE/qcow2-migrated:YOUR_NEW_VERSION'
docker import --platform=linux/amd64 \
  --change 'USER root' \
  --change 'ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
  --change 'CMD ["/sbin/init"]' \
  --change 'STOPSIGNAL SIGRTMIN+3' \
  "$WORK/rootfs.tar" "$CUSTOM_IMAGE"
docker image inspect "$CUSTOM_IMAGE"
```

这里创建的是容器文件系统镜像，不是运行中 VM 的内存快照。不要把 QCOW2 或包含
分区表的 raw 磁盘直接传给 `docker import`。导入不会自动补齐应用所需的环境变量、
工作目录、端口配置或健康检查；请按实际服务配置，并核对文件 capability 等权限。
参见 [Docker import 文档](https://docs.docker.com/reference/cli/docker/image/import/)。

示例使用 systemd 的 `/sbin/init` 作为启动命令，并设置常用命令搜索路径 `PATH`。
如果只运行单个业务进程，请按实际应用调整启动命令、运行用户及停止信号。
桌面应用可按实际显示编号补充 `DISPLAY`，例如 `--change 'ENV DISPLAY=:0'`。

`EXPOSE` 不会启动服务，也不能代替 AGS 端口配置。本流程输出 OCI，不需要客户
自行制作 2 MiB 对齐的 Cube ext4。自动快照由平台完成后续 rootfs 和快照制作，
但不会替你修复镜像内部的依赖问题。

## 5. 推送到自己的仓库，在 AGS 验证

```bash
docker login ccr.ccs.tencentyun.com
docker push "$CUSTOM_IMAGE"
```

也可以使用自己的 TCR。固定版本并记录推送后的 digest，不覆盖已使用的 tag。
镜像中不要保留云密钥、模型 API Key、浏览器登录状态或客户数据。

### 通用验证流程

1. 创建自定义 Tool，将镜像地址设置为刚推送的版本，并按业务配置启动命令、
   资源、环境变量、端口和就绪探针。探针应检查自己的业务接口，不要求提供
   OSWorld 的 `/platform` 或 `/screenshot`。
2. 启动实例，检查主进程、启动日志、文件权限、必要挂载和网络访问。使用 systemd
   时检查 `systemctl --failed`，排查启动失败及重启循环。
3. 验证业务所需的接口和代表性操作；需要持久化、共享内存或嵌套 Docker 时，
   分别验证相应能力。不使用桌面的镜像无需验证 noVNC、Chrome 或截图。
4. 需要自动快照时，使用名称包含 `auto-snapshot` 的 Tool。等待快照 READY 后，
   停止旧实例并创建新实例，再执行同一套业务检查。快照未就绪时的普通启动不能
   代替恢复验证。
5. 在实际使用的目标地域验证，完成后清理测试实例和 Tool。

### OSWorld 镜像的验证示例

**以下命令和检查仅适用于提供 OSWorld server 和桌面的镜像。** 本 cookbook 的
`demo.py`、`make quickstart` 和 `smoke` 使用 OSWorld 接口，不是通用镜像验证工具。

回到 `examples/osworld-custom-image`，按 README 执行 `make setup`，在 `.env`
中填写云凭证、地域，并将 `CUSTOM_IMAGE` 设置为刚推送的地址。已有旧测试状态时，
先执行 `make clean`。**不要执行 `make copy` 或示例的 `make build`**：前者复制提供的
base，后者构建 Claude Code 示例，都不是运行刚迁移的镜像。

现有示例约定 `/sbin/init`、OSWorld API 5000、noVNC 5910 等配置。镜像不符合这些
约定时，应先适配镜像或调整运行配置，再测试：

```bash
# 先检查新镜像，不由这个测试 Tool 触发自动快照：
uv run python scripts/demo.py smoke --cold --state-dir .state/qcow2-check
uv run python scripts/demo.py clean --state-dir .state/qcow2-check
# 再打开桌面，并触发自动快照：
make quickstart
make snapshot
```

OSWorld 场景的检查项：

- `/platform` 可用不代表桌面已就绪；截图应有真实内容，不能是黑屏或占位图。
- noVNC 可交互，键鼠、剪贴板及任务所需的上传、下载、命令执行接口可用。
- PID 1 正常运行；检查 `systemctl --failed` 及相关 unit 日志，排查重启循环。
- `df -h /dev/shm` 显示至少 4 GiB，实际打开 Chrome 和任务软件操作。
- 执行代表性 OSWorld 任务；需要 DinD 时另测 Docker pull/run/build、网络和卷。
- 在目标地域分别验证常规启动和快照恢复，不能只验证构建机上的 Docker。

`--cold` 在这里仅关闭该测试 Tool 的自动制快照触发；若已有相同镜像和配置的快照，
还应核对实际启动记录，不能仅凭 Tool 名称或启动耗时认定没有复用快照。

Quickstart 会使用名称带 `auto-snapshot` 的 Tool。快照还在 BUILDING 时可以常规
启动，但这不算恢复验证。等 `make snapshot` 显示 READY 后，停止当前实例并保留
Tool，再创建新实例，重新检查桌面和任务。本示例可以这样操作：

```bash
uv run python - <<'PY'
import sys
sys.path.insert(0, 'scripts')
from dotenv import load_dotenv
from demo import Demo
load_dotenv('.env', override=False)
Demo().stop()
PY
make quickstart
```

验收结束后运行 `make clean` 清理示例的实例和 Tool。仅修改格式或通过一次健康
检查都不等于任务兼容；更换镜像或配置后，应重新验证。

## 示例：OSWorld 官方 QCOW2 的迁移实例

我们按上述流程测试了 [OSWorld 官方 Ubuntu 镜像](https://huggingface.co/datasets/xlangai/ubuntu_osworld/tree/a5d9c3eaae98eebf6e3a0beb84e7e47cf72ae133)。
本示例使用以下固定版本：

| 项目 | 本次使用的内容 |
| --- | --- |
| 数据集 revision | `a5d9c3eaae98eebf6e3a0beb84e7e47cf72ae133` |
| 下载文件 | `Ubuntu.qcow2.zip`，12,273,896,463 字节 |
| ZIP SHA256（与来源 LFS 元数据核对） | `b795b6cd4c69b252c1b4f10150a347795555032501b60fd031751ed09b896712` |
| 解压后 QCOW2 SHA256（本次实测） | `6bf667a852b3c307f61d9f09c42559351f45e0607e428b4997becf534cf4d313` |
| 原系统 | Ubuntu 22.04.3 LTS，x86_64 |
| 根文件系统 | `/dev/sda3`，ext4；不导出 EFI 分区 |

这份镜像不能只做文件导出。原镜像已有 GDM 自动登录和 OSWorld server，但没有
dummy Xorg 驱动、x11vnc、noVNC 和 websockify。本次补装这些组件，配置
1920×1080 显示和桌面访问服务；清理原 fstab 的磁盘、EFI、swap 依赖，禁用不再
需要的 VM 集成服务，并在启动阶段修正设备权限、确保 SHM 至少 4 GiB。
原有 OSWorld server 代码保持不变，只补充访问桌面所需的 Xauthority 配置。

适配脚本已放在仓库中：

- [adapt.sh](../scripts/qcow2/osworld-official/adapt.sh)：安装显示和远程桌面组件，配置
  fstab、systemd 服务、设备权限及共享内存。
- [finalize.sh](../scripts/qcow2/osworld-official/finalize.sh)：清理旧 SSH 密钥和机器标识，
  配置启动时生成 SSH 主机密钥，并记录软件版本和 OSWorld server 校验和。

这两个脚本用于上表中的官方 OSWorld 镜像，依赖 Ubuntu 22.04、UID 为 1000 的
`user` 用户、GDM 自动登录和 `/home/user/server/main.py`。脚本会修改服务配置、
删除 swap 文件、清理 SSH 密钥和日志。其他镜像请按自己的业务需求编写适配脚本。

完成第 2 步的校验并创建 `working.qcow2` 后，在 `examples/osworld-custom-image`
目录中执行以下命令，替代第 3 步的自定义 `adapt.sh`。`WORK` 沿用前文的工作目录。
脚本通过 `virt-customize` 在镜像内执行，**不要直接在宿主机上运行这两个脚本**。
第一条命令安装软件时需要访问 Ubuntu 软件源。

```bash
SCRIPT_DIR="$(realpath scripts/qcow2/osworld-official)"
virt-customize --format qcow2 -a "$WORK/working.qcow2" --no-logfile \
  --run "$SCRIPT_DIR/adapt.sh"
virt-customize --format qcow2 -a "$WORK/working.qcow2" --no-logfile \
  --run "$SCRIPT_DIR/finalize.sh"
```

完成后按第 4、5 步导出、推送，并执行 OSWorld 验证。脚本不包含 DinD 适配，
不替换原 OSWorld server，也不执行文件系统自动修复。

导出的 rootfs tar 约 15.96 GB，推送后的压缩层约 8.60 GB。这次以保留原软件环境
为主，没有为了体积批量删除桌面应用，也没有额外适配 DinD。广州普通启动实测
通过：桌面截图为 1920×1080、noVNC 握手正常、PID 1 为 systemd、SHM 为 4 GiB，
命令执行、Python 执行和文件上传/下载往返均正常。通过键盘打开终端、输入命令
写入文件，以及打开 Chrome 显示测试页面的检查也通过。

自动快照制作及恢复验证通过。等待 READY，再停止旧实例、创建新实例，恢复后的
桌面、noVNC、systemd 和 4 GiB SHM 检查通过；文件上传/下载、Python、键盘终端操作和 Chrome
窗口检查也通过。

原镜像中的 Chrome 130 会显示版本更新提示，可能遮挡任务界面。本次没有自动
升级浏览器；正式使用前应根据任务要求固定软件版本、检查弹窗和首次启动行为。

这说明该固定版本经过适配可以运行，并不代表任意 QCOW2 或全部 Benchmark
任务都已验证。需要自定义 OSWorld 时，仍推荐从提供的 base OCI 构建。

## 启动失败时先查什么

| 表现 | 优先检查 |
| --- | --- |
| systemd 长时间等待、就绪超时 | fstab、挂载 unit、原设备依赖、自定义服务的启动依赖 |
| 业务接口无法访问 | 服务进程、监听地址、端口配置及业务日志 |
| 桌面场景：截图黑屏或远程桌面不可用 | Xorg/dummy 驱动、显示配置、桌面会话、Xauthority、服务用户 |
| 桌面场景：桌面反复退出、Chrome 崩溃 | SHM 容量、设备权限、浏览器锁文件、软件日志 |
| Docker 无法启动或 build 失败 | 数据目录文件系统、cgroup、存储驱动；base 的 DinD 适配不会自动继承 |
| 镜像制作成功但 Cube 启动失败 | 原内核/驱动依赖、权限和设备假设、缺失文件、第三方启动或安全服务 |

保留失败时间、地域、Tool/Instance ID、镜像 digest 和相关服务日志，方便定位。
如果问题来自原 VM 的深度定制，建议将必要的软件和数据迁移到适合业务的容器基础镜像。
