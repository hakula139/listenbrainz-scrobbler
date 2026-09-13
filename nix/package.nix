{
  pkgs,
  lib,
}:
let
  inherit (builtins.fromTOML (builtins.readFile ../pyproject.toml)) project;
in
pkgs.python313Packages.buildPythonApplication {
  pname = project.name;
  inherit (project) version;
  pyproject = true;
  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../pyproject.toml
      ../src
      ../tests
      ../README.md
    ];
  };
  build-system = [ pkgs.python313Packages.hatchling ];
  dependencies = with pkgs.python313Packages; [
    httpx
    keyring
  ];
  nativeCheckInputs = [ pkgs.python313Packages.pytestCheckHook ];
  pythonImportsCheck = [ "lb_scrobbler" ];
  meta = {
    inherit (project) description;
    mainProgram = "lb-scrobbler";
    platforms = lib.platforms.darwin;
  };
}
