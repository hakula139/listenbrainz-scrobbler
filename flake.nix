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
    }:
    let
      inherit (nixpkgs) lib;

      platformKey = p: { inherit (p) config isStatic; };

      packageFor =
        pkgs:
        let
          locked = self.packages.${pkgs.stdenv.hostPlatform.system}.listenbrainz-scrobbler or null;
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
        checks = import ./nix/checks.nix { inherit pkgs self home-manager; };

        # ------------------------------------------------------------------------------------------
        # Formatter
        # ------------------------------------------------------------------------------------------
        formatter = pkgs.nixfmt-tree;
      }
    );
}
