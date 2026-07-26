ARG NIX_BUILDER_IMAGE=nixos/nix:2.26.3
FROM ${NIX_BUILDER_IMAGE} AS builder

WORKDIR /src
RUN mkdir -p /etc/nix \
    && printf 'experimental-features = nix-command flakes\naccept-flake-config = true\nsandbox = false\nfilter-syscalls = false\n' > /etc/nix/nix.conf

COPY nix/ /src/nix/
RUN nix-build /src/nix/default.nix --out-link /tmp/claude-code-result \
    && result_path="$(readlink -f /tmp/claude-code-result)" \
    && mkdir -p /nix-export/nix/store /nix-export/nix/claude-code \
    && cp -a $(nix-store -qR /tmp/claude-code-result) /nix-export/nix/store/ \
    && ln -s "$result_path" /nix-export/nix/claude-code/nix-env

FROM scratch
COPY --from=builder /nix-export/ /
