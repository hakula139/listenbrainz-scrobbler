# ==================================================================================================
# listenbrainz-scrobbler
# ==================================================================================================

{
  lib,
  python313Packages,
}:

let
  inherit (lib.importTOML ../pyproject.toml) project;
in
python313Packages.buildPythonApplication {
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

  build-system = [ python313Packages.hatchling ];

  dependencies = with python313Packages; [
    httpx
    keyring
  ];

  nativeCheckInputs = [
    python313Packages.packaging
    python313Packages.pytestCheckHook
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
