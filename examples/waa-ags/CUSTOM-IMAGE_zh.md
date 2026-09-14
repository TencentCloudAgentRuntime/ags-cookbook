# AGS WAA自定义镜像制作指导

[English](CUSTOM-IMAGE_en.md) | 简体中文

本文指导您从一台干净的腾讯云 Windows Server CVM 开始，使用脚本安装并验证 WAA 运行环境，制作可用于 AGS WAA 沙箱工具的自定义镜像。您也可以在完成 WAA 环境安装后，继续安装业务所需的软件、配置运行环境，再执行验证并制作镜像，使后续启动的沙箱实例直接具备所需的软件和配置。

## 1. 环境准备

- 一台干净的腾讯云 Windows Server CVM（Desktop Experience x64），推荐使用 **Windows Server 2025 英文版**；提供 IP、管理员账号和密码，建议系统盘至少 **50 GB**，安装前 C 盘至少 25 GB 可用。
- 一台能访问目标 Windows Server（WinRM 5985 端口）并下载 COS 资源的 Linux 机器，已安装 Python 3.9–3.13（含 `venv` / `ensurepip`，glibc ≥ 2.17），至少 10 GB 可用磁盘。Windows 不需要公网 IP，安全组仅放行该 Linux 机器来源。

请勿在业务机器上安装，也不要对同一台机器同时执行多个安装任务。

## 2. 安装步骤

整体安装与自动验证预计需要 **25–40 分钟**（含软件下载、安装和多次重启），具体取决于网络和机器性能，较慢环境可能更久；此时间不包含后续安装业务软件及制作云镜像。

在 Linux 上执行，先创建权限为 600 的 `.env`。将所有占位符替换为实际值；`TENCENTCLOUD_REGION`、`CVM_INSTANCE_ID` 和 `IMAGE_NAME` 在后续制作镜像时使用：

```bash
mkdir waa-builder
cd waa-builder
cat > .env <<'EOF'
WINDOWS_SERVER_IP='<WINDOWS_IP>'
WINDOWS_SERVER_USERNAME='Administrator'
WINDOWS_SERVER_PASSWORD='<WINDOWS_PASSWORD>'
# WINDOWS_DOCKER_PASSWORD='<DOCKER_PASSWORD>'
TENCENTCLOUD_SECRET_ID='<SECRET_ID>'
TENCENTCLOUD_SECRET_KEY='<SECRET_KEY>'
TENCENTCLOUD_REGION='<REGION>'
CVM_INSTANCE_ID='<INSTANCE_ID>'
IMAGE_NAME='<IMAGE_NAME>'
EOF
chmod 600 .env
curl -fSLo install.sh https://dl.tencentags.com/waa/windows-server/latest/install.sh
bash install.sh
```

`WINDOWS_DOCKER_PASSWORD` 为可选配置，用于设置 `Docker` 桌面用户的密码；未配置时默认使用 `WINDOWS_SERVER_PASSWORD`。

`latest` 提供已通过发布校验的版本入口；脚本会固定使用对应版本的资源，不受后续更新影响。

**默认不修改分辨率**，实际尺寸取决于目标系统和显示驱动。需要指定尺寸时，在安装命令中加 `--resolution 1920x1080`。

可选参数：

| 参数 | 用途 |
| --- | --- |
| `--ssl --port 5986` | 使用具备可信证书的 WinRM HTTPS |
| `--log-dir /path/new-result` | 指定尚不存在的结果目录 |
| `--validate-only` | 仅验证已有 WAA 环境，不执行安装；会启动应用、关闭窗口并重启一次 |

安装期间会多次重启 Windows，请保持 Linux 脚本运行，不要通过 RDP 登录或手动操作桌面。

**安装流程会自动完成验证，无需额外执行验证命令。** 检查项包括 WAA 接口、截图、软件版本、中文输出、Chrome CDP、LibreOffice 和 UIA，以及指定的分辨率。单独使用 `--validate-only` 时只检查、不修改分辨率。

执行成功时，终端及 `build.log` 最后会出现以下信息，脚本正常退出（退出码为 0），结果目录中的 `result.json` 为 `"status": "passed"`：

```text
build_passed evidence=<结果目录>
```

单个阶段的 `phase_passed` 不代表全部完成。上述成功标志表示 **WAA 环境安装和验证完成**，尚未生成云镜像 ID；请继续按第 6 节制作自定义镜像。

## 3. 执行结果

结果默认保存在 Linux 的 `waa-build-日期时间/`：

| 文件 | 查看内容 |
| --- | --- |
| `result.json` | `status=passed` 表示本轮验证及收尾通过 |
| `build.log` | 整体进度和失败阶段 |
| `target/validation-initial/` | 首次验证日志、截图和实际尺寸 `screen-size.json` |
| `target/validation-reboot/` | 重启后验证结果 |

## 4. 故障排查

先看终端错误和 `build.log`，再查看 `target/` 中对应阶段日志。

| 问题 | 检查方式 |
| --- | --- |
| 连接或认证失败 | 检查 IP、账号密码、WinRM 服务、安全组和防火墙 |
| Python 或 venv 缺失 | 安装符合要求的 Python 和发行版对应的 venv 包 |
| 下载或校验失败 | 检查 Linux 到 COS 的 HTTPS 连通性和磁盘空间，不要绕过校验 |
| 提示已有 Docker 用户或目录 | 完整安装要求干净系统；已有 WAA 使用 `--validate-only`，不要直接删除用户目录 |
| 分辨率不匹配 | 对照 `screen-size.json` 和 `screenshot.png`，检查显示驱动是否支持指定尺寸 |
| 安装中断或阶段失败 | 保留结果目录，先定位原因，不要直接重复完整安装；必要时重装目标系统 |

提交问题时附上终端错误及结果目录，勿附密码文件；日志和截图可能含环境或桌面信息，分享前请检查。

## 5. 安装内容

1. 从 COS 下载 WAA 组件和固定版本软件，校验文件完整性并传到 Windows。
2. 创建 Docker 桌面用户、配置自动登录，安装 WAA Server、UIA、CDP 和 VNC/noVNC。
3. 安装 Chrome 135、LibreOffice 24.8.7.2、Python、Git、7-Zip、FFmpeg、Tesseract、VLC、GIMP、VS Code、Thunderbird、Clock 及运行依赖。
4. 按需设置分辨率，执行安装后及重启后验证，回收日志并清理本轮临时任务。

请限制机器及镜像的访问权限，不要将 WAA 5000、CDP 9222、noVNC 8006 端口暴露到互联网。

## 6. 制作自定义镜像

看到 `build_passed` 后，先登录 Windows 安装业务所需的软件并完成业务配置。确认软件可以正常启动，删除不应进入镜像的业务数据和个人凭据，并关闭所有应用。**只有完成这些操作后，才执行下面的制镜命令。**

制镜脚本从当前目录 `.env` 读取 Windows 连接信息、地域、实例 ID、镜像名称和腾讯云 AK/SK。凭据只用于 Linux 侧调用腾讯云 API，不会发送到 Windows，也不会写入结果文件。
使用的 CAM 凭据需要具备目标地域 CVM 的 `DescribeInstances`、`StopInstances`、`CreateImage` 和 `DescribeImages` 权限。

执行制镜：

```bash
bash install.sh --create-image
```

脚本会确认 IP、地域和实例 ID 指向同一台 CVM，重新执行两遍 WAA 验收，重置镜像克隆所需的初始化状态，软关机后调用腾讯云 API 制作镜像，并等待镜像可用。整个过程不要登录或启动目标 CVM。

成功时终端最后输出：

```text
image_created image_id=img-xxxxxxxx evidence=<结果目录>
```

此时 `result.json` 同时包含 `"status": "passed"`、`"image_state": "NORMAL"` 和 `"image_id": "img-..."`。脚本不会删除 CVM、镜像或关联快照；镜像使用期间请保留这些资源。

## 7. 在 AGS 中使用

AGS CLI 的安装、认证和通用用法请参见 [AGS CLI README](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/README-zh.md)。安装后的命令名为 `agr`。

用第 6 节得到的自定义镜像 ID 创建 WAA 沙箱工具：

```bash
agr --region '<REGION>' tool create \
  --tool-name '<TOOL_NAME>' \
  --tool-type waa \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --computer-configuration '{"WAAConfiguration":{"ImageId":"<IMAGE_ID>"}}' \
  --wait
```

`<REGION>` 必须与镜像地域一致，`<IMAGE_ID>` 填写自定义镜像 ID。命令成功后会返回工具 ID（`sdt-...`）。使用该工具创建实例：

```bash
agr --region '<REGION>' instance create --tool-id '<TOOL_ID>' --wait
```
