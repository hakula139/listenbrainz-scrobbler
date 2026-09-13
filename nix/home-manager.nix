{ self }:
{
  config,
  pkgs,
  lib,
  ...
}:
let
  cfg = config.services.listenbrainz-scrobbler;
  stateDir = "${config.home.homeDirectory}/Library/Application Support/listenbrainz-scrobbler";
in
{
  options.services.listenbrainz-scrobbler = {
    enable = lib.mkEnableOption "Apple Music scrobbling to ListenBrainz";
    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      description = "The ListenBrainz scrobbler package to run.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = pkgs.stdenv.isDarwin;
        message = "ListenBrainz scrobbler requires macOS and Music.app.";
      }
    ];
    home.packages = [ cfg.package ];
    home.activation.listenbrainzScrobbler = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
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
        RunAtLoad = true;
        KeepAlive.SuccessfulExit = false;
        ThrottleInterval = 30;
        ExitTimeOut = 80;
        ProcessType = "Background";
        StandardOutPath = "${stateDir}/service.log";
        StandardErrorPath = "${stateDir}/service.log";
      };
    };
  };
}
