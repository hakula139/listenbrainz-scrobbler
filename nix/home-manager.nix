# ==================================================================================================
# listenbrainz-scrobbler Home Manager Module
# ==================================================================================================

{
  packageFor,
}:

{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.listenbrainz-scrobbler;
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
        assertion = pkgs.stdenv.isDarwin;
        message = "ListenBrainz scrobbler requires macOS and Music.app.";
      }
    ];

    home.packages = [ cfg.package ];

    # launchd opens the log files when it starts the agent, so the state directory must exist first.
    home.activation.listenbrainzScrobbler =
      lib.hm.dag.entryBetween [ "setupLaunchAgents" ] [ "writeBoundary" ]
        ''
          run install -d -m 0700 ${lib.escapeShellArg stateDir}
        '';

    launchd.agents.listenbrainz-scrobbler = {
      enable = true;
      config = {
        Label = "xyz.hakula.listenbrainz-scrobbler";
        ProgramArguments = [
          "${cfg.package}/bin/lb-scrobbler"
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
}
