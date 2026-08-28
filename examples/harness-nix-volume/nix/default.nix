{ pkgs ? import <nixpkgs> { } }:

let
  claudeCode = pkgs.buildNpmPackage {
    pname = "claude-code";
    version = "2.1.196";
    src = ./claude-code;
    npmDepsHash = "sha256-w+aMO1Lq/5xISg8ax4svjy4vzRN/piikAhi2cm0pSw8=";

    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [
      pkgs.glibc
      pkgs.stdenv.cc.cc.lib
    ];
    dontNpmBuild = true;
    dontStrip = true;

    postInstall = ''
      package_dir="$out/lib/node_modules/ags-claude-code-nix-runtime"
      rm -rf "$package_dir/node_modules/@anthropic-ai/claude-code-linux-x64-musl"
      mkdir -p "$out/bin"
      ln -s "$package_dir/node_modules/@anthropic-ai/claude-code/bin/claude.exe" "$out/bin/claude"
    '';
  };
in
pkgs.buildEnv {
  name = "ags-claude-code-nix-env";
  paths = [ claudeCode ];
}
