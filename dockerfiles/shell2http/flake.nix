{
  description = "shell2http runtime environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
    in {
      packages.${system} = {
        # 运行时环境
        default = pkgs.buildEnv {
          name = "shell2http-runtime";
          paths = with pkgs; [
            # 基础 shell
            bash
            
            # 常用工具
            coreutils
            findutils
            gnused
            gawk
            gnugrep
            gnutar
            gzip
            
            # 网络工具
            curl
            wget
            
            # 文本处理
            jq
            
            # 进程管理
            procps
            
            # 其他常用工具
            which
            file
            tree
            
            # Node.js
            nodejs_22
            
            # Git
            git
            
            # claude-code
            claude-code
            
            # 压力测试工具
            stress-ng
          ];
          ignoreCollisions = true;
        };
      };

      # 开发环境
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = with pkgs; [
          go
          gopls
          gotools
        ];
      };
    };
}
