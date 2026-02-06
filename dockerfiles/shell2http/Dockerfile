# Stage 1: Build nix environment
FROM nixos/nix:2.26.3 AS nix-builder

RUN mkdir -p ~/.config/nix && \
    echo 'substituters = https://mirrors.tuna.tsinghua.edu.cn/nix-channels/store https://mirrors.ustc.edu.cn/nix-channels/store https://cache.nixos.org' > ~/.config/nix/nix.conf && \
    echo 'sandbox = false' >> ~/.config/nix/nix.conf && \
    echo 'experimental-features = nix-command flakes' >> ~/.config/nix/nix.conf && \
    echo 'tarball-ttl = 31536000' >> ~/.config/nix/nix.conf && \
    echo 'https://mirrors.ustc.edu.cn/nix-channels/nixpkgs-unstable nixpkgs' > ~/.nix-channels

WORKDIR /workspace

COPY flake.nix /workspace/

RUN nix build --impure && \
    mkdir -p /nix-export/nix/store && \
    for path in $(nix-store -qR ./result); do \
        cp -a "$path" /nix-export/nix/store ; \
    done

# Stage 2: Build Go binary
FROM golang:1.25-alpine3.23 AS go-builder

WORKDIR /build

COPY go.mod go.sum main.go ./

RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o shell2http main.go

# Stage 3: Final runtime image
FROM alpine:3.23

WORKDIR /nix/shell2http

COPY --from=nix-builder /nix-export /
COPY --from=nix-builder /workspace/result /nix/shell2http/nix-env
COPY --from=go-builder /build/shell2http /nix/shell2http/

# 设置环境变量
ENV PATH=/nix/shell2http/nix-env/bin:$PATH

RUN chmod +x /nix/shell2http/shell2http

WORKDIR /workspace

EXPOSE 8080

CMD ["/nix/shell2http/shell2http"]
