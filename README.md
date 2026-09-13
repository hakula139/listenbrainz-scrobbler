# listenbrainz-scrobbler

[![CI](https://github.com/hakula139/listenbrainz-scrobbler/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/hakula139/listenbrainz-scrobbler/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/listenbrainz-scrobbler)](https://pypi.org/project/listenbrainz-scrobbler/)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://pypi.org/project/listenbrainz-scrobbler/)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](#setup)

Automatically submit Apple Music listens on macOS to ListenBrainz, including streamed songs outside your library.

## Setup

On macOS, install [uv](https://docs.astral.sh/uv/), then install the [PyPI package](https://pypi.org/project/listenbrainz-scrobbler/) with Python 3.13:

```sh
uv tool install --python 3.13 listenbrainz-scrobbler
lb-scrobbler install --dry-run
lb-scrobbler status
```

If uv reports that its executable directory is missing from `PATH`, run `uv tool update-shell` and restart your shell. For a declaratively managed service, use [Nix / Home Manager](#nix--home-manager).

Play a song and allow the background Python process to control Music when macOS asks. Check `status` for fresh observations and an advancing playback position. If access is denied, enable it in System Settings → Privacy & Security → Automation, then reinstall the agent. A successful foreground probe may still require a separate permission for the background service.

After the dry run works, quit other scrobblers to avoid duplicate submissions. Save your [ListenBrainz token](https://listenbrainz.org/settings/) in the login Keychain:

```sh
lb-scrobbler auth
lb-scrobbler install
```

For an existing SmashTunes setup, `lb-scrobbler auth --from-smashtunes` explicitly transfers its stored ListenBrainz token into this service's Keychain entry after validating it. Neither command prints the token. Do not put tokens in command arguments, project files, or Git.

`install` starts the service immediately and at future logins. Keep the uv tool installation in place: the service depends on its Python environment. Avoid installing the service through temporary `uvx` environments. Python upgrades may require fresh macOS Automation or Keychain consent.

To upgrade, restart the agent against the updated tool environment:

```sh
lb-scrobbler stop
uv tool upgrade listenbrainz-scrobbler
lb-scrobbler install
```

## Operation

```sh
lb-scrobbler probe       # Read Music without submitting
lb-scrobbler status      # Last observation and submission queue
lb-scrobbler stop        # Stop until reinstalled or the next login
lb-scrobbler uninstall   # Remove the launch agent
lb-scrobbler retry       # Retry retained failures after fixing their cause
```

`lb-scrobbler run --dry-run` runs in the foreground. Stop the LaunchAgent first, since only one process may own the playback tracker.

State and logs live in `~/Library/Application Support/listenbrainz-scrobbler/`. Queued listens are stored there with user-only permissions. The submission token is held separately in login Keychain under `xyz.hakula.listenbrainz-scrobbler`. Uninstalling the agent preserves both the queue and Keychain entry.

A listen is submitted after observing half a track or four minutes of playback, whichever comes first, following [ListenBrainz's submission rule](https://listenbrainz.readthedocs.io/en/latest/users/api/core.html). Pauses, seeks, and observation gaps longer than ten seconds do not contribute listening time. Starting the service halfway through a song does not credit playback it did not observe.

Failed submissions stay queued with their original timestamps. Network and server errors are retried automatically. Inspect other failures with `status`, fix their cause, then run `retry`. After changing the token, restart the agent. For a manual installation, run `lb-scrobbler install`. A crash during submission can occasionally cause a duplicate listen.

Dry runs never submit listens.

## Limits

Only playback observed on this Mac is captured. There is no history import, iPhone synchronization, or playing-now submission.

Polling cannot distinguish a natural repeat from manually seeking from the very end to the very beginning. It also cannot identify different recordings with identical title, artist, and album metadata. Track-start timestamps are estimated from the observed position, so seeking before the first observation can skew that estimate. Missing metadata is skipped.

## Nix / Home Manager

Add a versioned flake input such as `github:hakula139/listenbrainz-scrobbler/v0.1.1`, then import the module in your Home Manager configuration:

```nix
imports = [ inputs.listenbrainz-scrobbler.homeManagerModules.default ];
services.listenbrainz-scrobbler.enable = true;
```

Home Manager replaces the manual installer's LaunchAgent under the same label while preserving the queue and Keychain token. Activate Home Manager, then check `lb-scrobbler status` to confirm the agent loaded and observations are fresh. The package path changes, so macOS may request Automation or Keychain access again. Use `lb-scrobbler auth` if no token is stored yet.

The LaunchAgent starts at user login after a reboot, when Music and the login Keychain are available. Home Manager owns its lifecycle after migration, so use it for configuration changes instead of the manual `install` and `uninstall` commands. After changing the token, restart the loaded agent with `launchctl kickstart -k "gui/$(id -u)/xyz.hakula.listenbrainz-scrobbler"`. Disable the module and reactivate Home Manager to remove it. The existing Keychain entry keeps credentials outside the Nix store.

See the [changelog](https://github.com/hakula139/listenbrainz-scrobbler/blob/main/CHANGELOG.md) for release changes. [GitHub releases](https://github.com/hakula139/listenbrainz-scrobbler/releases) also provide wheels, source archives, and checksums.
