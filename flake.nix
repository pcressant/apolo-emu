{
  description = "Apolo-emu : émulateur du synthétiseur vocal Dolphin Apollo II pour QEMU";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAll (pkgs: rec {
        apolo-emu = pkgs.callPackage ./package.nix { };
        default = apolo-emu;
      });

      apps = forAll (pkgs: {
        default = {
          type = "app";
          program = nixpkgs.lib.getExe self.packages.${pkgs.stdenv.hostPlatform.system}.default;
          meta.description = "Émulateur du synthétiseur vocal Apollo II";
        };
      });

      overlays.default = final: prev: {
        apolo-emu = final.callPackage ./package.nix { };
      };

      checks = forAll (pkgs: {
        default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      });
    };
}
