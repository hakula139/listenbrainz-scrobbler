# ==================================================================================================
# listenbrainz-scrobbler Development Flake
# ==================================================================================================

{
  description = "listenbrainz-scrobbler packages and development environment";

  # ------------------------------------------------------------------------------------------------
  # Inputs
  # ------------------------------------------------------------------------------------------------
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

    devkit = {
      url = "github:hakula139/devkit/v2";
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

      packageFor = pkgs: pkgs.callPackage ./nix/package.nix { };

      # A key lets the module system deduplicate the module when it is imported twice.
      homeModuleKey = "${self}/flake.nix#homeModules.default";
    in
    # ----------------------------------------------------------------------------------------------
    # Home Manager Module
    # ----------------------------------------------------------------------------------------------
    {
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
        inherit (pkgs.stdenv) isDarwin;

        package = packageFor pkgs;

        # ------------------------------------------------------------------------------------------
        # Pre-commit Hooks
        # ------------------------------------------------------------------------------------------
        preCommit = dk.preCommit {
          src = ./.;
          hooks = {
            actionlint.enable = true;
            check-yaml.enable = true;
            cspell.enable = true;
            deadnix.enable = true;
            dprint.enable = true;
            editorconfig-checker.enable = true;
            markdownlint-cli2.enable = true;
            nixfmt.enable = true;
            prettier.enable = true;
            ruff.enable = true;
            ruff-format.enable = true;
            shellcheck.enable = true;
            shfmt.enable = true;
            sort-file-contents.enable = true;
            statix.enable = true;
            taplo.enable = true;
          };

          devHooks = {
            mypy = {
              enable = true;
              package = dk.uvTool "mypy";
              pass_filenames = false;
            };
            pytest = {
              enable = true;
              entry = "${lib.getExe pkgs.uv} run --locked pytest";
              args = [ "-q" ];
              types = [ "python" ];
              pass_filenames = false;
            };
          };
        };

        moduleCheck = home-manager.lib.homeManagerConfiguration {
          inherit pkgs;
          modules = [
            self.homeModules.default
            {
              home = {
                username = "scrobbler-test";
                homeDirectory = "/Users/scrobbler-test";
                stateVersion = "26.05";
              };

              services.listenbrainz-scrobbler.enable = true;
            }
          ];
        };
      in
      {
        # ------------------------------------------------------------------------------------------
        # Dev Shell
        # ------------------------------------------------------------------------------------------
        devShells.default = pkgs.mkShell {
          name = "listenbrainz-scrobbler-dev";

          inputsFrom = [ preCommit.shell ];

          packages = [
            pkgs.git-cliff
            pkgs.python313
            pkgs.uv
          ];

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
        checks = {
          pre-commit = preCommit.check;
        }
        // lib.optionalAttrs isDarwin {
          inherit package;
          home-manager = moduleCheck.activationPackage;
        };

        # ------------------------------------------------------------------------------------------
        # Formatter
        # ------------------------------------------------------------------------------------------
        formatter = pkgs.nixfmt-tree;
      }
    );
}
