# Paquet Apolo-emu, utilisé par flake.nix et default.nix.
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

  # La suite complète tourne au build, y compris l'intégration avec un vrai QEMU.
  nativeCheckInputs = [ qemu ];
  checkPhase = ''
    runHook preCheck
    python -m unittest discover -s tests -t .
    runHook postCheck
  '';
  pythonImportsCheck = [ "apolo_emu" ];

  meta = {
    description = "Émulateur du synthétiseur vocal Dolphin Apollo II pour QEMU";
    mainProgram = "apolo-emu";
    platforms = lib.platforms.linux;
  };
}
