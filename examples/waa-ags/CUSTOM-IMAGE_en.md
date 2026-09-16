# AGS WAA Custom Image Guide

English | [简体中文](CUSTOM-IMAGE_zh.md)

This guide explains how to prepare a custom image for an AGS WAA sandbox from a clean Tencent Cloud Windows Server CVM. The installer sets up and validates the WAA runtime. After that, you may install your own applications and configuration before exporting the CVM as a reusable image.

## 1. Prerequisites

- A clean Tencent Cloud Windows Server CVM with the x64 Desktop Experience. Windows Server 2025 English is recommended. Use a system disk of at least 50 GB and make sure at least 25 GB is free before installation. You need its IP address, administrator username, and password.
- A Linux host that can reach WinRM port 5985 on the Windows CVM and download HTTPS resources. It requires Python 3.9 through 3.13 with `venv` or `ensurepip`, glibc 2.17 or later, and at least 10 GB of free disk space. The Windows CVM does not need a public IP.

Allow WinRM only from the Linux host. Do not run concurrent installers against the same Windows CVM or use a production machine as the build target.

## 2. Install and validate WAA

Installation and automatic validation normally take 25 to 40 minutes, depending on network and CVM performance. This estimate excludes your application installation and cloud image creation.

Run the following commands on the Linux host. Replace every placeholder and protect `.env` with mode 600:

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

`WINDOWS_DOCKER_PASSWORD` optionally sets the password of the `Docker` desktop user. If omitted, it defaults to `WINDOWS_SERVER_PASSWORD`.

The `latest` installer pins all resources to an immutable, verified release.

The installer does not change the display resolution by default. To request a specific resolution, add a value such as `--resolution 1920x1080` to the installation command.

Optional arguments:

| Argument | Purpose |
| --- | --- |
| `--ssl --port 5986` | Connect through WinRM HTTPS with a trusted certificate |
| `--log-dir /path/new-result` | Use a new, non-existing result directory |
| `--validate-only` | Validate an existing WAA installation without reinstalling it |

Windows restarts several times during installation. Keep the Linux command running and do not log in through RDP or interact with the desktop.

Validation is part of the installation. A successful run exits with code 0 and prints:

```text
build_passed evidence=<RESULT_DIRECTORY>
```

The `result.json` file in that directory must contain `"status": "passed"`. A single `phase_passed` line does not mean the complete workflow has succeeded.

## 3. Results

The default result directory is `waa-build-<DATE>-<TIME>/` on the Linux host:

| Path | Contents |
| --- | --- |
| `result.json` | Final machine-readable status |
| `build.log` | End-to-end progress and the failed stage, if any |
| `target/validation-initial/` | Initial validation logs, screenshot, and `screen-size.json` |
| `target/validation-reboot/` | Validation evidence collected after reboot |

## 4. Troubleshooting

Check the terminal error and `build.log` first, then inspect the corresponding directory under `target/`.

| Problem | Check |
| --- | --- |
| Connection or authentication failure | Verify the IP address, credentials, WinRM service, security group, and Windows firewall |
| Missing Python environment | Install a supported Python version and the distribution package that provides `venv` |
| Download or checksum failure | Verify HTTPS access to `dl.tencentags.com` and available Linux disk space; do not bypass checksum validation |
| Existing Docker user or profile | A full installation requires a clean OS; use `--validate-only` for an existing WAA installation |
| Resolution mismatch | Compare `screen-size.json` and `screenshot.png`, then verify display driver support |
| Interrupted or failed stage | Preserve the result directory and diagnose the failed stage before retrying; reinstall the target OS when necessary |

Do not include `.env` in support attachments. Logs and screenshots may contain environment or desktop information and should be reviewed before sharing.

## 5. What the installer does

1. Downloads pinned WAA components and application installers, verifies their checksums, and transfers them to Windows.
2. Creates the Docker desktop user, configures automatic sign-in, and installs the WAA Server, UIA, CDP, VNC, and noVNC components.
3. Installs Chrome 135, LibreOffice 24.8.7.2, Python, Git, 7-Zip, FFmpeg, Tesseract, VLC, GIMP, VS Code, Thunderbird, Clock, and required runtime dependencies.
4. Applies the requested resolution only when `--resolution` is provided, validates the installation before and after reboot, collects evidence, and removes build-time tasks.

Restrict access to the CVM and image, and never expose WAA port 5000, CDP port 9222, or noVNC port 8006 to the internet.

## 6. Create the custom image

After `build_passed`, log in to Windows and install your applications and configuration. Remove business data and personal credentials, then close all applications. Only run the image command after those steps are complete:

```bash
bash install.sh --create-image
```

The command reads CVM and Tencent Cloud credentials from `.env`. The credentials stay on the Linux host and require permission to call CVM `DescribeInstances`, `StopInstances`, `CreateImage`, and `DescribeImages` in the target region.

Before image creation, the script verifies that the IP address, region, and instance ID refer to the same CVM. It runs WAA validation twice, resets clone initialization state, gracefully stops the CVM, calls the Tencent Cloud image API, and waits until the image is ready.

A successful run prints:

```text
image_created image_id=img-xxxxxxxx evidence=<RESULT_DIRECTORY>
```

The final `result.json` must contain `"status": "passed"`, `"image_state": "NORMAL"`, and the generated `"image_id"`. The script does not delete the CVM, image, or associated snapshots.

## 7. Use the image with AGS

See the [AGS CLI README](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/README.md) for CLI installation and authentication.

Create a WAA sandbox tool with the image ID returned above:

```bash
agr --region '<REGION>' tool create \
  --tool-name '<TOOL_NAME>' \
  --tool-type waa \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --computer-configuration '{"WAAConfiguration":{"ImageId":"<IMAGE_ID>"}}' \
  --wait
```

The region must match the image region. After the command returns a tool ID, create an instance:

```bash
agr --region '<REGION>' instance create --tool-id '<TOOL_ID>' --wait
```
