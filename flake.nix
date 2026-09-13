# ==============================================================================
# ListenBrainz Scrobbler Flake
# ==============================================================================

{
  description = "Apple Music scrobbler for ListenBrainz";

  # ----------------------------------------------------------------------------
  # Inputs
  # ----------------------------------------------------------------------------
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";
    git-hooks-nix = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  # ----------------------------------------------------------------------------
  # Outputs
  # ----------------------------------------------------------------------------
  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      git-hooks-nix,
      home-manager,
    }:
    {
      homeManagerModules.default = import ./nix/home-manager.nix { inherit self; };
    }
    // flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        inherit (pkgs) lib;
        python = pkgs.python313.withPackages (p: [
          p.httpx
          p.keyring
          p.mypy
          p.pytest
        ]);
        package = pkgs.callPackage ./nix/package.nix { };

        # ----------------------------------------------------------------------
        # Pre-commit hooks
        # ----------------------------------------------------------------------
        preCommitCheck = git-hooks-nix.lib.${system}.run {
          src = ./.;
          hooks = {
            check-added-large-files.enable = true;
            check-yaml.enable = true;
            end-of-file-fixer.enable = true;
            trim-trailing-whitespace.enable = true;
            nixfmt.enable = true;
            statix.enable = true;
            deadnix.enable = true;
            ruff.enable = true;
            ruff-format.enable = true;
            mypy = {
              enable = true;
              entry = "${python}/bin/mypy";
              args = [ "src/lb_scrobbler" ];
              pass_filenames = false;
            };
            pytest = {
              enable = true;
              entry = "${python}/bin/pytest";
              args = [
                "-q"
                "-p"
                "no:cacheprovider"
              ];
              types = [ "python" ];
              pass_filenames = false;
            };
          };
        };

        moduleCheck = home-manager.lib.homeManagerConfiguration {
          inherit pkgs;
          modules = [
            self.homeManagerModules.default
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
        # ----------------------------------------------------------------------
        # Package and checks
        # ----------------------------------------------------------------------
        packages = lib.optionalAttrs pkgs.stdenv.isDarwin { default = package; };
        checks = {
          pre-commit = preCommitCheck;
        }
        // lib.optionalAttrs pkgs.stdenv.isDarwin {
          inherit package;
          home-manager = moduleCheck.activationPackage;
        };

        # ----------------------------------------------------------------------
        # Development shell
        # ----------------------------------------------------------------------
        devShells.default = pkgs.mkShell {
          packages = preCommitCheck.enabledPackages ++ [
            python
            pkgs.uv
          ];
          inherit (preCommitCheck) shellHook;
        };
        formatter = pkgs.nixfmt;
      }
    );
}
