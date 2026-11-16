# ==================================================================================================
# listenbrainz-scrobbler Home Manager Module
# ==================================================================================================

{
  packageFor,
}:

{
  config,
  pkgs,
  lib,
  ...
}:

let
  cfg = config.services.listenbrainz-scrobbler;
  inherit (lib.hm.dag) entryBetween;
  inherit (pkgs.stdenv.hostPlatform) isDarwin;
  stateDir = "${config.home.homeDirectory}/Library/Application Support/listenbrainz-scrobbler";
in
{
  # ------------------------------------------------------------------------------------------------
  # Module Options
  # ------------------------------------------------------------------------------------------------
  options.services.listenbrainz-scrobbler = {
    enable = lib.mkEnableOption "Apple Music scrobbling to ListenBrainz";

    package = lib.mkOption {
      type = lib.types.package;
      default = packageFor pkgs;
      defaultText = lib.literalMD "listenbrainz-scrobbler from this flake";
      description = "The ListenBrainz scrobbler package to run.";
    };
  };

  # ------------------------------------------------------------------------------------------------
  # Module Config
  # ------------------------------------------------------------------------------------------------
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = isDarwin;
        message = "ListenBrainz scrobbler requires macOS and Music.app.";
      }
    ];

    home = {
      packages = lib.optional isDarwin cfg.package;

      # launchd opens log files when starting the agent, so the state directory must exist first.
      activation = lib.optionalAttrs isDarwin {
        listenbrainzScrobbler = entryBetween [ "setupLaunchAgents" ] [ "writeBoundary" ] ''
          run install -d -m 0700 ${lib.escapeShellArg stateDir}
        '';
      };
    };

    launchd.agents = lib.optionalAttrs isDarwin {
      listenbrainz-scrobbler = {
        enable = true;
        config = {
          Label = "xyz.hakula.listenbrainz-scrobbler";
          ProgramArguments = [
            (lib.getExe cfg.package)
            "run"
          ];
          WorkingDirectory = stateDir;
          RunAtLoad = true;
          KeepAlive.SuccessfulExit = false;
          ThrottleInterval = 30;
          ExitTimeOut = 80;
          StandardOutPath = "${stateDir}/service.log";
          StandardErrorPath = "${stateDir}/service.log";
        };
      };
    };
  };
}
