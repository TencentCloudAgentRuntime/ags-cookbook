#!/usr/bin/env python3
"""
使用 ttyd 在 Agent Sandbox 沙箱中开启 Web 终端进行调试
通过上传 ttyd 二进制文件到沙箱，启动 Web 终端服务，获取可访问的调试链接。
"""

import os
import sys
import urllib.request

from dotenv import load_dotenv

# 加载 .env 文件（优先级：环境变量 > .env 文件）
load_dotenv()

# 沙箱 ID（必填，从控制台获取已有沙箱的 ID）
SANDBOX_ID = os.getenv("SANDBOX_ID", "")

# ttyd 二进制文件路径（相对于脚本所在目录）
TTYD_BINARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ttyd.i686")

# ttyd 下载地址
TTYD_DOWNLOAD_URL = "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.i686"

# ttyd 监听端口
TTYD_PORT = 8080


def download_ttyd():
    """从 GitHub 下载 ttyd 二进制文件"""
    print(f"正在从 GitHub 下载 ttyd ...")
    print(f"下载地址: {TTYD_DOWNLOAD_URL}")
    try:
        urllib.request.urlretrieve(TTYD_DOWNLOAD_URL, TTYD_BINARY, _download_progress)
        print(f"\n下载完成: {TTYD_BINARY}")
    except Exception as e:
        print(f"\n下载失败: {e}")
        print("请手动下载并放置到当前目录:")
        print(f"  {TTYD_DOWNLOAD_URL}")
        sys.exit(1)


def _download_progress(block_num, block_size, total_size):
    """显示下载进度"""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100, downloaded * 100 / total_size)
        bar_len = 40
        filled = int(bar_len * percent / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  [{bar}] {percent:.1f}% ({downloaded // 1024}KB/{total_size // 1024}KB)", end="", flush=True)
    else:
        print(f"\r  已下载 {downloaded // 1024}KB", end="", flush=True)


def check_ttyd_binary():
    """检查 ttyd 二进制文件，不存在则自动下载"""
    if os.path.exists(TTYD_BINARY):
        print(f"ttyd 二进制文件已找到: {TTYD_BINARY}")
    else:
        print(f"未找到 ttyd 二进制文件: {TTYD_BINARY}")
        download_ttyd()


def connect_sandbox():
    """连接到已有沙箱"""
    from e2b_code_interpreter import Sandbox

    if not SANDBOX_ID:
        print("错误: 未指定沙箱 ID，请在 .env 文件中设置 SANDBOX_ID")
        sys.exit(1)

    print(f"连接到沙箱: {SANDBOX_ID}")
    sandbox = Sandbox.connect(sandbox_id=SANDBOX_ID)
    print(f"沙箱连接成功: {sandbox.sandbox_id}")
    return sandbox


def check_ttyd_in_sandbox(sandbox):
    """检查沙箱中 ttyd 文件是否已存在"""
    result = sandbox.commands.run("test -x /root/ttyd && echo EXISTS", user="root")
    return "EXISTS" in result.stdout


def check_ttyd_running(sandbox):
    """检查沙箱中 ttyd 进程是否已在运行"""
    result = sandbox.commands.run(
        "ps aux 2>/dev/null | grep '[t]tyd' | grep -v grep && echo RUNNING",
        user="root",
    )
    return "RUNNING" in result.stdout


def check_port_in_use(sandbox, port):
    """检查沙箱中指定端口是否被占用"""
    result = sandbox.commands.run(
        f"cat /proc/net/tcp 2>/dev/null | grep ':{port:04X} ' && echo IN_USE",
        user="root",
    )
    return "IN_USE" in result.stdout


def upload_ttyd(sandbox):
    """上传 ttyd 二进制文件到沙箱（如已存在则跳过）"""
    if check_ttyd_in_sandbox(sandbox):
        print("沙箱中已存在 ttyd，跳过上传")
        return

    print("上传 ttyd 到沙箱...")
    with open(TTYD_BINARY, "rb") as f:
        sandbox.files.write("/root/ttyd", f, user="root")
    sandbox.commands.run("chmod +x /root/ttyd", user="root")
    print("ttyd 上传完成")


def start_ttyd(sandbox):
    """在沙箱中启动 ttyd 服务（如已在运行则跳过）"""
    if check_ttyd_running(sandbox):
        print("ttyd 进程已在运行，跳过启动")
        return

    if check_port_in_use(sandbox, TTYD_PORT):
        print(f"错误: 端口 {TTYD_PORT} 已被其他进程占用")
        sys.exit(1)

    print(f"启动 ttyd 服务 (端口: {TTYD_PORT})...")
    sandbox.commands.run(
        f"/root/ttyd -p {TTYD_PORT} -W bash",
        user="root",
        background=True,
        timeout=0,
    )
    print("ttyd 服务已在后台启动")


def get_access_url(sandbox):
    """获取 ttyd Web 终端的访问地址"""
    host = sandbox.get_host(TTYD_PORT)
    token = sandbox._envd_access_token
    url = f"https://{host}/?access_token={token}"
    return url


def main():
    check_ttyd_binary()
    sandbox = connect_sandbox()
    upload_ttyd(sandbox)
    start_ttyd(sandbox)
    url = get_access_url(sandbox)

    print("\n" + "=" * 60)
    print("ttyd Web 终端已就绪！")
    print("=" * 60)
    print(f"\n访问链接:\n{url}\n")
    print("在浏览器中打开上述链接即可进入沙箱终端进行调试。")
    print("=" * 60)


if __name__ == "__main__":
    main()
