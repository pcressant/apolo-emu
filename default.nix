# Intégration Nix facultative : nix-build, puis ./result/bin/apolo-emu
{ pkgs ? import <nixpkgs> { } }:

pkgs.python3Packages.buildPythonApplication {
  pname = "apolo-emu";
  version = "0.1.0";
  pyproject = true;
  src = pkgs.lib.cleanSource ./.;
  build-system = [ pkgs.python3Packages.setuptools ];
  nativeCheckInputs = [ pkgs.qemu ];
  checkPhase = ''
    runHook preCheck
    python -m unittest discover -s tests -t .
    runHook postCheck
  '';
  meta.mainProgram = "apolo-emu";
}
