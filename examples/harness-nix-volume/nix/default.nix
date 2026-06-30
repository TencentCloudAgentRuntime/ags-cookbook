{ pkgs ? import <nixpkgs> { } }:

let
  claudeCode = pkgs.buildNpmPackage {
    pname = "claude-code";
    version = "2.1.196";
    src = ./claude-code;
    npmDepsHash = "sha256-5J4UnkxH2uIsrG2pzJlbn32MmStl5SvImreGrr1/7nQ=";

    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [
      pkgs.glibc
      pkgs.stdenv.cc.cc.lib
    ];
    dontNpmBuild = true;
    dontStrip = true;

    postInstall = ''
      package_dir="$out/lib/node_modules/ags-harness-claude-code-runtime"
      rm -rf "$package_dir/node_modules/@anthropic-ai/claude-code-linux-x64-musl"
      mkdir -p "$out/bin"
      ln -s "$package_dir/node_modules/@anthropic-ai/claude-code/bin/claude.exe" "$out/bin/claude"
    '';
  };

  harness = pkgs.stdenvNoCC.mkDerivation {
    pname = "ags-harness-demo";
    version = "0.1.0";
    src = ./src;
    dontConfigure = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p "$out/bin" "$out/share/ags-harness-demo"
      cp harness_server.py "$out/share/ags-harness-demo/harness_server.py"

      cat > "$out/bin/harness-demo" <<EOF
#!${pkgs.bash}/bin/bash
set -euo pipefail
export PATH="${claudeCode}/bin:${pkgs.python312}/bin:${pkgs.nodejs_22}/bin:${pkgs.coreutils}/bin:${pkgs.gnugrep}/bin:${pkgs.curl}/bin:\$PATH"
exec ${pkgs.python312}/bin/python3 "$out/share/ags-harness-demo/harness_server.py" "\$@"
EOF
      chmod +x "$out/bin/harness-demo"
    '';
  };

  runtimeEnv = pkgs.buildEnv {
    name = "ags-harness-nix-env";
    paths = [
      claudeCode
      harness
      pkgs.bash
      pkgs.coreutils
      pkgs.curl
      pkgs.jq
      pkgs.nodejs_22
      pkgs.python312
    ];
  };
in
runtimeEnv
