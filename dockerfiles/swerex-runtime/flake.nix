{
  description = "swe-rex runtime environment with uv";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      packages.${system} = {
        default = pkgs.buildEnv {
          name = "swe-rex-runtime";
          paths = with pkgs; [
            # Python 3.12 (仅解释器，依赖由 uv 管理)
            python312

            # uv - 现代 Python 包管理器
            uv

            # 基础工具
            bash
            coreutils
            findutils
            gawk
            gnused
            gnutar
            gzip
            git
            curl
            cacert

            # 进程管理
            tini
          ];
          ignoreCollisions = true;
        };
      };
    };
}
