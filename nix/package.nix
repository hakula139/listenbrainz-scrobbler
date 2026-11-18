# ==================================================================================================
# listenbrainz-scrobbler
# ==================================================================================================

{
  lib,
  python313Packages,
}:

let
  inherit (lib.importTOML ../pyproject.toml) project;
  pyPkgs = python313Packages;
in
pyPkgs.buildPythonApplication {
  pname = project.name;
  inherit (project) version;
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../pyproject.toml
      ../README.md
      ../LICENSE
      ../src
      ../tests
    ];
  };

  build-system = [ pyPkgs.hatchling ];

  dependencies = [
    pyPkgs.httpx
    pyPkgs.keyring
  ];

  nativeCheckInputs = [
    pyPkgs.pytest-cov-stub
    pyPkgs.pytestCheckHook
  ];
  pythonImportsCheck = [ "lb_scrobbler" ];

  meta = {
    inherit (project) description;
    homepage = project.urls.Repository;
    license = lib.licenses.mit;
    mainProgram = "lb-scrobbler";
    platforms = lib.platforms.darwin;
  };
}
