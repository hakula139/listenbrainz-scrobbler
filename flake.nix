# ==================================================================================================
# listenbrainz-scrobbler Development Flake
# ==================================================================================================

{
  description = "listenbrainz-scrobbler packages and development environment";

  nixConfig = {
    extra-substituters = [ "https://hakula.cachix.org" ];
    extra-trusted-public-keys = [
      "hakula.cachix.org-1:7zwB3fhMfReHdOjh6DmnaLXgqbPDBcojvN9F+osZw0k="
    ];
  };

  # ------------------------------------------------------------------------------------------------
  # Inputs
  # ------------------------------------------------------------------------------------------------
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

    devkit = {
      url = "github:hakula139/devkit/v3";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  # ------------------------------------------------------------------------------------------------
  # Outputs
  # ------------------------------------------------------------------------------------------------
  outputs =
    {
      self,
      nixpkgs,
      devkit,
      home-manager,
      ...
    }:
    let
      inherit (nixpkgs) lib;

      platformKey = p: { inherit (p) config isStatic; };

      packageFor =
        pkgs:
        let
          locked = (self.packages.${pkgs.stdenv.hostPlatform.system} or { }).listenbrainz-scrobbler or null;
        in
        if
          locked != null
          && platformKey pkgs.stdenv.buildPlatform == platformKey locked.stdenv.buildPlatform
          && platformKey pkgs.stdenv.hostPlatform == platformKey locked.stdenv.hostPlatform
          && pkgs.stdenv.hostPlatform == pkgs.stdenv.targetPlatform
        then
          locked
        else
          pkgs.callPackage ./nix/package.nix { };

      # A key lets the module system deduplicate the module when it is imported twice.
      homeModuleKey = "${self}/flake.nix#homeModules.default";
    in
    # ----------------------------------------------------------------------------------------------
    # Overlay and Home Manager Module
    # ----------------------------------------------------------------------------------------------
    {
      overlays.default =
        _: prev:
        lib.optionalAttrs prev.stdenv.hostPlatform.isDarwin {
          listenbrainz-scrobbler = packageFor prev;
        };

      homeModules.default = {
        _class = "homeManager";
        _file = homeModuleKey;
        key = homeModuleKey;
        imports = [ (import ./nix/home-manager.nix { inherit packageFor; }) ];
      };
    }
    // devkit.lib.eachSystem devkit.lib.systems (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        dk = devkit.lib.mkLib pkgs;
        inherit (pkgs.stdenv.hostPlatform) isDarwin;

        package = pkgs.callPackage ./nix/package.nix { };

        # ------------------------------------------------------------------------------------------
        # Pre-commit Hooks
        # ------------------------------------------------------------------------------------------
        preCommit = dk.preCommit {
          src = ./.;
          hooks = {
            mypy.enable = true;
            prettier.enable = true;
            ruff.enable = true;
            ruff-format.enable = true;
            shellcheck.enable = true;
            shfmt.enable = true;
            taplo.enable = true;
          };
        };

        canaryPkgs = pkgs.extend (
          _: prev: {
            python313Packages = prev.python313Packages.overrideScope (
              _: _: {
                httpx = throw "consumer python313Packages reconstruction";
              }
            );
          }
        );

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

        # Home Manager throws on a failed assertion before exposing `config`, so evaluate the module
        # without its surrounding modules to read its own entries.
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

        extendedPkgs = canaryPkgs.extend self.overlays.default;
      in
      {
        # ------------------------------------------------------------------------------------------
        # Dev Shell
        # ------------------------------------------------------------------------------------------
        devShells.default = pkgs.mkShell {
          name = "listenbrainz-scrobbler-dev";

          inputsFrom = [ preCommit ];

          packages = [ pkgs.python313 ] ++ builtins.attrValues dk.uvToolchain;
        };

        # ------------------------------------------------------------------------------------------
        # Packages
        # ------------------------------------------------------------------------------------------
        packages = lib.optionalAttrs isDarwin {
          default = package;
          listenbrainz-scrobbler = package;
        };

        # ------------------------------------------------------------------------------------------
        # Checks
        # ------------------------------------------------------------------------------------------
        checks =
          if isDarwin then
            let
              enabledHome = evalHome {
                hmPkgs = canaryPkgs;
                enable = true;
              };
            in
            assert extendedPkgs.listenbrainz-scrobbler.drvPath == package.drvPath;
            assert enabledHome.config.services.listenbrainz-scrobbler.package.drvPath == package.drvPath;
            {
              inherit package;
              home-manager = enabledHome.activationPackage;
              overlay = pkgs.emptyFile;
            }
          else
            let
              disabledHome = evalHome { enable = false; };
              enabledConfig =
                (evalHome {
                  enable = true;
                  extraModules = [ { assertions = lib.mkForce [ ]; } ];
                }).config;
              failedMessages = map (a: a.message) (builtins.filter (a: !a.assertion) linuxAssertions);
              drvPaths = ps: map (p: p.drvPath) ps;
            in
            assert !(extendedPkgs ? listenbrainz-scrobbler);
            assert failedMessages == [ "ListenBrainz scrobbler requires macOS and Music.app." ];
            assert drvPaths enabledConfig.home.packages == drvPaths disabledHome.config.home.packages;
            assert !(enabledConfig.home.activation ? listenbrainzScrobbler);
            assert !(enabledConfig.launchd.agents ? listenbrainz-scrobbler);
            {
              home-manager = disabledHome.activationPackage;
              overlay = pkgs.emptyFile;
            };

        # ------------------------------------------------------------------------------------------
        # Formatter
        # ------------------------------------------------------------------------------------------
        formatter = pkgs.nixfmt-tree;
      }
    );
}
