# Stage 1: Build nix environment
FROM mirror.ccs.tencentyun.com/nixos/nix:2.26.3 AS nix-builder

RUN mkdir -p ~/.config/nix && \
    echo 'substituters = https://mirrors.tuna.tsinghua.edu.cn/nix-channels/store https://mirrors.ustc.edu.cn/nix-channels/store https://cache.nixos.org' > ~/.config/nix/nix.conf && \
    echo 'sandbox = false' >> ~/.config/nix/nix.conf && \
    echo 'experimental-features = nix-command flakes' >> ~/.config/nix/nix.conf && \
    echo 'tarball-ttl = 31536000' >> ~/.config/nix/nix.conf && \
    echo 'https://mirrors.ustc.edu.cn/nix-channels/nixpkgs-unstable nixpkgs' > ~/.nix-channels

WORKDIR /workspace

COPY flake.nix /workspace/

RUN nix build && \
    mkdir -p /nix-export/nix/store && \
    for path in $(nix-store -qR ./result); do \
        cp -a "$path" /nix-export/nix/store ; \
    done

# Stage 2: envd
FROM ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest AS envd-provider

# Stage 3: Final runtime image
FROM mirror.ccs.tencentyun.com/library/alpine:3.23

WORKDIR /nix/swerex

COPY --from=nix-builder /nix-export /
COPY --from=nix-builder /workspace/result /nix/swerex/nix-env
COPY --from=envd-provider /usr/bin/envd /nix/swerex/nix-env/bin/envd

# 设置环境变量
ENV PATH=/nix/swerex/venv/bin:/nix/swerex/nix-env/bin:$PATH \
    UV_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    SSL_CERT_FILE=/nix/swerex/nix-env/etc/ssl/certs/ca-bundle.crt

# 使用 uv 创建虚拟环境并安装 swe-rex
RUN uv venv /nix/swerex/venv --python /nix/swerex/nix-env/bin/python3.12 && \
    uv pip install -p /nix/swerex/venv swe-rex && \
    /nix/swerex/venv/bin/python -c "import swerex; print('swerex installed:', swerex.__file__)" && \
    rm -rf /tmp/* ~/.cache

# 创建启动脚本
COPY entrypoint.sh /nix/swerex/entrypoint.sh
RUN chmod +x /nix/swerex/entrypoint.sh

# 默认启动命令
ENTRYPOINT ["/nix/swerex/nix-env/bin/tini", "--"]
CMD ["/nix/swerex/entrypoint.sh", "--port", "8000"]
