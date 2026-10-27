# Apolo-emu package, used by flake.nix and default.nix.
{
  lib,
  python3Packages,
  qemu,
}:

python3Packages.buildPythonApplication {
  pname = "apolo-emu";
  version = "0.1.0";
  pyproject = true;
  src = lib.cleanSource ./.;
  build-system = [ python3Packages.setuptools ];

  # The full suite runs during the build, including real QEMU integration.
  nativeCheckInputs = [ qemu ];
  checkPhase = ''
    runHook preCheck
    python -m unittest discover -s tests -t .
    runHook postCheck
  '';
  pythonImportsCheck = [ "apolo_emu" ];

  meta = {
    description = "Dolphin Apollo II speech synthesizer emulator for QEMU";
    license = lib.licenses.mit;
    mainProgram = "apolo-emu";
    platforms = lib.platforms.linux;
  };
}
