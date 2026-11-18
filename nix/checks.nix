# ==================================================================================================
# listenbrainz-scrobbler Integration Checks
# ==================================================================================================

{
  pkgs,
  self,
  home-manager,
}:

let
  inherit (pkgs) lib;
  inherit (pkgs.stdenv.hostPlatform) isDarwin system;

  # ------------------------------------------------------------------------------------------------
  # Package Fixtures
  # ------------------------------------------------------------------------------------------------
  locked = self.packages.${system}.listenbrainz-scrobbler;

  canaryPkgs = pkgs.extend (
    _: prev: {
      python313Packages = prev.python313Packages.overrideScope (
        _: prevPy: {
          httpx = prevPy.httpx.overridePythonAttrs (_: {
            pname = "httpx-canary";
          });
        }
      );
    }
  );

  # Darwin's static Python is broken, so model the platform distinction with an evaluable scope.
  staticPlatform = canaryPkgs.stdenv.hostPlatform // {
    isStatic = true;
  };

  staticPkgs = canaryPkgs // {
    stdenv = canaryPkgs.stdenv // {
      hostPlatform = staticPlatform;
      targetPlatform = staticPlatform;
    };
  };

  # ------------------------------------------------------------------------------------------------
  # Home Manager Evaluation
  # ------------------------------------------------------------------------------------------------
  evalHome =
    {
      hmPkgs ? pkgs,
      enable,
      extraModules ? [ ],
    }:
    home-manager.lib.homeManagerConfiguration {
      pkgs = hmPkgs;
      modules = [
        self.homeModules.default
        {
          home = {
            username = "scrobbler-test";
            homeDirectory = if isDarwin then "/Users/scrobbler-test" else "/home/scrobbler-test";
            stateVersion = "26.05";
          };

          services.listenbrainz-scrobbler.enable = enable;
        }
      ]
      ++ extraModules;
    };

  # Home Manager throws on a failed assertion before exposing config.
  linuxAssertions =
    (lib.evalModules {
      modules = [
        self.homeModules.default
        {
          options.assertions = lib.mkOption {
            type = lib.types.listOf lib.types.unspecified;
            default = [ ];
          };
        }
        { _module.check = false; }
        {
          _module.args.pkgs = pkgs;
          services.listenbrainz-scrobbler.enable = true;
        }
      ];
    }).config.assertions;
in
{
  # ------------------------------------------------------------------------------------------------
  # Overlay Check
  # ------------------------------------------------------------------------------------------------
  overlay =
    let
      extendedPkgs = canaryPkgs.extend self.overlays.default;
      fallbackPkgs = self.overlays.default staticPkgs staticPkgs;
    in
    if isDarwin then
      assert (canaryPkgs.callPackage ./package.nix { }).drvPath != locked.drvPath;
      assert extendedPkgs.listenbrainz-scrobbler.drvPath == locked.drvPath;
      assert fallbackPkgs.listenbrainz-scrobbler.drvPath != locked.drvPath;
      pkgs.emptyFile
    else
      assert !(extendedPkgs ? listenbrainz-scrobbler);
      pkgs.emptyFile;

  # ------------------------------------------------------------------------------------------------
  # Home Manager Check
  # ------------------------------------------------------------------------------------------------
  home-manager =
    if isDarwin then
      let
        enabledHome = evalHome {
          hmPkgs = canaryPkgs;
          enable = true;
        };
        enabledPackage = enabledHome.config.services.listenbrainz-scrobbler.package;
      in
      assert enabledPackage.drvPath == locked.drvPath;
      enabledHome.activationPackage
    else
      let
        disabledHome = evalHome { enable = false; };
        enabledConfig =
          (evalHome {
            enable = true;
            extraModules = [ { assertions = lib.mkForce [ ]; } ];
          }).config;
        failedAssertions = builtins.filter (a: !a.assertion) linuxAssertions;
        failedMessages = map (a: a.message) failedAssertions;
        drvPaths = ps: map (p: p.drvPath) ps;
      in
      assert failedMessages == [ "ListenBrainz scrobbler requires macOS and Music.app." ];
      assert drvPaths enabledConfig.home.packages == drvPaths disabledHome.config.home.packages;
      assert !(enabledConfig.home.activation ? listenbrainzScrobbler);
      assert !(enabledConfig.launchd.agents ? listenbrainz-scrobbler);
      disabledHome.activationPackage;
}
// lib.optionalAttrs isDarwin { package = locked; }
