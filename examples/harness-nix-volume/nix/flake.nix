{
  description = "Self-contained Claude Code runtime for an AGS image-volume mount";

  inputs.nixpkgs.url = "nixpkgs";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      runtimeEnv = import ./default.nix { inherit pkgs; };
    in
    {
      packages.${system}.default = runtimeEnv;
    };
}
