# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-13

### Added

- _(playback)_ Show the current Apple Music track on ListenBrainz before it qualifies for listening history, keep current playback updates responsive while older listens wait for retry, and clear this service's playing-now notification when playback pauses or stops ([#5](https://github.com/hakula139/listenbrainz-scrobbler/pull/5))
- _(release)_ Maintain a changelog linked from the package description ([#4](https://github.com/hakula139/listenbrainz-scrobbler/pull/4))

## [0.1.1] - 2026-09-13

### Fixed

- _(service)_ Restore timely Apple Music observation under heavy system load for manual and Home Manager installations ([#3](https://github.com/hakula139/listenbrainz-scrobbler/pull/3))
- _(service)_ Prevent false observer timeouts and enforce a deadline when playback output is incomplete ([#3](https://github.com/hakula139/listenbrainz-scrobbler/pull/3))
- _(service)_ Report macOS Automation permission errors accurately ([#3](https://github.com/hakula139/listenbrainz-scrobbler/pull/3))

### Changed

- _(readme)_ Refresh the package description with current installation, upgrade, and Home Manager instructions ([#1](https://github.com/hakula139/listenbrainz-scrobbler/pull/1), [#2](https://github.com/hakula139/listenbrainz-scrobbler/pull/2))

## [0.1.0] - 2026-09-13

### Added

- Submit qualifying Apple Music listens to ListenBrainz, including streamed tracks outside the library
- Preserve playback checkpoints and retry failed submissions through a durable queue, with credentials stored separately in login Keychain
- Run automatically at login through the command-line installer or Nix / Home Manager module
- Install with Python 3.13 from PyPI or use a versioned Nix flake, with wheels, source archives, and checksums on GitHub releases

[0.2.0]: https://github.com/hakula139/listenbrainz-scrobbler/compare/v0.1.1..v0.2.0
[0.1.1]: https://github.com/hakula139/listenbrainz-scrobbler/compare/v0.1.0..v0.1.1
[0.1.0]: https://github.com/hakula139/listenbrainz-scrobbler/releases/tag/v0.1.0
