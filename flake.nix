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

    git-hooks-nix = {
      url = "github:cachix/git-hooks.nix";
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
      git-hooks-nix,
      home-manager,
      ...
    }:
    let
      inherit (nixpkgs) lib;

      # git-hooks.nix has dropped x86_64-darwin, which Nixpkgs supports only through 26.05.
      systems = [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];

      eachSystem =
        f:
        let
          bySystem = lib.genAttrs systems f;
          outputs = builtins.attrNames bySystem.${builtins.head systems};
        in
        lib.genAttrs outputs (output: builtins.mapAttrs (_: attrs: attrs.${output}) bySystem);

      packageFor =
        pkgs:
        self.packages.${pkgs.stdenv.hostPlatform.system}.default
          or (pkgs.callPackage ./nix/package.nix { });

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
    // eachSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        inherit (pkgs.stdenv) isDarwin;

        package = pkgs.callPackage ./nix/package.nix { };

        python = pkgs.python313.withPackages (p: [
          p.httpx
          p.keyring
          p.mypy
        ]);

        # ------------------------------------------------------------------------------------------
        # Pre-commit Hooks
        # ------------------------------------------------------------------------------------------
        hooks = {
          actionlint.enable = true;
          check-added-large-files.enable = true;
          check-yaml.enable = true;
          deadnix.enable = true;
          editorconfig-checker.enable = true;
          end-of-file-fixer.enable = true;
          nixfmt.enable = true;
          ruff.enable = true;
          ruff-format.enable = true;
          statix.enable = true;
          taplo.enable = true;
          trim-trailing-whitespace.enable = true;

          cspell = {
            enable = true;
            args = [
              "--no-progress"
              "--no-must-find-files"
            ];
          };

          markdownlint = {
            enable = true;
            args = [ "--fix" ];
          };

          mypy = {
            enable = true;
            entry = "${python}/bin/mypy";
            pass_filenames = false;
          };

          prettier = {
            enable = true;
            files = "\\.(js|json|jsonc|ya?ml)$";
          };
        };

        preCommit = git-hooks-nix.lib.${system}.run {
          src = ./.;
          hooks = hooks // {
            pytest = {
              enable = true;
              entry = "${lib.getExe pkgs.uv} run --frozen pytest";
              args = [ "-q" ];
              types = [ "python" ];
              pass_filenames = false;
            };
          };
        };

        # The pytest hook needs the uv environment, which the check sandbox lacks.
        preCommitCheck = git-hooks-nix.lib.${system}.run {
          src = ./.;
          inherit hooks;
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

          packages = preCommit.enabledPackages ++ [
            pkgs.git-cliff
            pkgs.python313
            pkgs.uv
          ];

          # The Python hook tools would otherwise put their packages on PYTHONPATH, where they
          # shadow the uv environment's locked versions.
          dontAddPythonPath = true;

          inherit (preCommit) shellHook;
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
          pre-commit = preCommitCheck;
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
