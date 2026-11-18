# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-11-18

### Added

- _(nix)_ Use the flake's `overlays.default` to add `pkgs.listenbrainz-scrobbler` to a macOS package set ([#22](https://github.com/hakula139/listenbrainz-scrobbler/pull/22))

### Changed

- _(playback)_ Announce the first track after startup with a single ListenBrainz request. Clear the previous playing-now entry before announcing a repeat of the same title and artist ([#23](https://github.com/hakula139/listenbrainz-scrobbler/pull/23))

### Fixed

- _(playback)_ Handle missing Apple Music stream metadata and retry playing-now updates after HTTP 408 timeouts ([#23](https://github.com/hakula139/listenbrainz-scrobbler/pull/23))
- _(cli)_ Report `status.json` by name when `lb-scrobbler status` encounters corrupt data or cannot read the file ([#23](https://github.com/hakula139/listenbrainz-scrobbler/pull/23))
- _(nix)_ Build from the caller's package set for static or cross builds on macOS. Home Manager and the overlay reuse the flake's locked package on matching platforms, even with local Python package overrides ([#22](https://github.com/hakula139/listenbrainz-scrobbler/pull/22))
- _(nix)_ Report the macOS requirement when the Home Manager service is enabled on Linux ([#22](https://github.com/hakula139/listenbrainz-scrobbler/pull/22))

### Security

- _(deps)_ Remove the `emSign ECC Root CA - G3` certificate from the trust bundles used by the locked Python and Nix environments ([#17](https://github.com/hakula139/listenbrainz-scrobbler/pull/17))

[0.4.0]: https://github.com/hakula139/listenbrainz-scrobbler/compare/v0.3.0...v0.4.0

## [0.3.0] - 2026-11-02

### Breaking changes

- _(flake)_ Export the Home Manager module as `homeModules.default` and drop the `homeManagerModules` output, so change the import to `inputs.listenbrainz-scrobbler.homeModules.default` ([#7](https://github.com/hakula139/listenbrainz-scrobbler/pull/7))
- _(service)_ Make `install` and `uninstall` refuse to manage an agent that Home Manager installed, and make `install` refuse to run from the Nix package, whose agent could not start. Use the Home Manager module for Nix installations, then remove a manual installation with `uv tool uninstall listenbrainz-scrobbler` ([#11](https://github.com/hakula139/listenbrainz-scrobbler/pull/11))

### Changed

- _(flake)_ Stop exporting packages and dev shells for Intel Macs. The Home Manager module still builds the package there from the user's nixpkgs ([#12](https://github.com/hakula139/listenbrainz-scrobbler/pull/12))
- _(package)_ Include the MIT license in the wheel, source archive, and package metadata ([#12](https://github.com/hakula139/listenbrainz-scrobbler/pull/12))

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

[0.3.0]: https://github.com/hakula139/listenbrainz-scrobbler/compare/v0.2.0..v0.3.0
[0.2.0]: https://github.com/hakula139/listenbrainz-scrobbler/compare/v0.1.1..v0.2.0
[0.1.1]: https://github.com/hakula139/listenbrainz-scrobbler/compare/v0.1.0..v0.1.1
[0.1.0]: https://github.com/hakula139/listenbrainz-scrobbler/releases/tag/v0.1.0
