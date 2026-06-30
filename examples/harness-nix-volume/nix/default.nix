{ pkgs ? import <nixpkgs> { } }:

let
  claudeCode = pkgs.stdenvNoCC.mkDerivation {
    pname = "claude-code-linux-x64";
    version = "2.1.196";
    src = pkgs.fetchurl {
      url = "https://registry.npmjs.org/@anthropic-ai/claude-code-linux-x64/-/claude-code-linux-x64-2.1.196.tgz";
      hash = "sha512-n8/1jNHQcYLAUL9hTfjU96r4TTQD5O7QTnqjX8MAvWWlAzvVhy7cAwWrI46V2ntyVJO9CupLMmp9tXufB0QDEg==";
    };
    sourceRoot = "package";
    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [
      pkgs.glibc
      pkgs.stdenv.cc.cc.lib
    ];
    dontConfigure = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p "$out/bin"
      cp claude "$out/bin/claude"
      chmod +x "$out/bin/claude"
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
in
pkgs.buildEnv {
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
}
