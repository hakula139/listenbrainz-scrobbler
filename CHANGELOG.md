# Changelog

## [Unreleased]

## [0.1.1] - 2026-09-13

### Fixed

- Restore timely Apple Music observation under heavy system load for manual and Home Manager installations.
- Prevent false observer timeouts and enforce a deadline when playback output is incomplete.
- Report macOS Automation permission errors accurately.

### Changed

- Update the PyPI description with current installation, upgrade, and Home Manager instructions.

## [0.1.0] - 2026-09-13

### Added

- Submit qualifying Apple Music listens to ListenBrainz, including streamed tracks outside the library.
- Preserve playback checkpoints and retry failed submissions through a durable queue, with credentials stored separately in login Keychain.
- Run automatically at login through the command-line installer or Nix / Home Manager module.
- Install with Python 3.13 from PyPI or use a versioned Nix flake. GitHub releases provide wheels, source archives, and checksums.

[Unreleased]: https://github.com/hakula139/listenbrainz-scrobbler/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/hakula139/listenbrainz-scrobbler/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hakula139/listenbrainz-scrobbler/releases/tag/v0.1.0
