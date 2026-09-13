# listenbrainz-scrobbler

[![CI](https://github.com/hakula139/listenbrainz-scrobbler/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/hakula139/listenbrainz-scrobbler/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/listenbrainz-scrobbler)](https://pypi.org/project/listenbrainz-scrobbler/)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://pypi.org/project/listenbrainz-scrobbler/)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](#setup)

A background service that submits Apple Music playback on macOS to ListenBrainz. It uses Music.app's scripting interface and a user LaunchAgent. No App Store purchase or developer signing certificate is required.

## Setup

On macOS, install [uv](https://docs.astral.sh/uv/), then install the [PyPI package](https://pypi.org/project/listenbrainz-scrobbler/) with Python 3.13:

```sh
uv tool install --python 3.13 listenbrainz-scrobbler
lb-scrobbler install --dry-run
lb-scrobbler status
```

If uv reports that its executable directory is missing from `PATH`, run `uv tool update-shell` and restart your shell. For a declaratively managed service, use [Nix / Home Manager](#nix--home-manager).

Allow the Python process to control Music when macOS asks. Terminal's Automation permission applies to a foreground probe, so the LaunchAgent may need a separate grant. The first query waits up to a minute for consent. If access is denied, enable it in System Settings → Privacy & Security → Automation, then reinstall the agent. `status` shows the observation age, current track, observed playback seconds, and any read error. Confirm the observations stay fresh and the position advances while playing.

After the dry run works, quit other scrobblers to avoid duplicate submissions. Save your [ListenBrainz token](https://listenbrainz.org/settings/) in the login Keychain:

```sh
lb-scrobbler auth
lb-scrobbler install
```

For an existing SmashTunes setup, `lb-scrobbler auth --from-smashtunes` explicitly transfers its stored ListenBrainz token into this service's Keychain entry after validating it. Neither command prints the token. Do not put tokens in command arguments, project files, or Git.

`install` starts the service immediately and at future logins. It records the installed environment's Python path, so keep the uv tool installation in place while using the service. Use `uv tool install` for this persistent environment. A temporary `uvx` environment can be removed by cache cleanup. Updating the underlying Python executable may require fresh macOS Automation or Keychain consent.

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

State and logs live in `~/Library/Application Support/listenbrainz-scrobbler/`. The service stores metadata and its SQLite queue there with user-only permissions. The submission token is held separately in login Keychain under `xyz.hakula.listenbrainz-scrobbler`. Uninstalling the agent preserves both the queue and Keychain entry.

A persistent scripting process samples playback every two seconds. It submits after observing half a track or four minutes of playback, whichever comes first, following [ListenBrainz's submission rule](https://listenbrainz.readthedocs.io/en/latest/users/api/core.html). Pauses, seeks, and observation gaps longer than ten seconds do not contribute listening time. Starting the service halfway through a song does not credit playback it did not observe.

Qualified listens and playback checkpoints are committed together. A separate worker sends the queue and retains failures with the original listen timestamp. Network and server errors use delayed retries. Invalid payloads remain blocked for inspection through `status` and manual `retry`. After replacing an expired token, restart the agent so the worker loads it. For a manual installation, run `lb-scrobbler install`. Delivery is at least once: a crash after server acceptance but before local acknowledgement can resend the same payload.

Dry-run mode uses a separate queue that is never sent. There is no historical backfill or iPhone library synchronization, and no optional playing-now submissions. The service captures playback observed on this Mac.

## Limits

Polling cannot distinguish a natural repeat from manually seeking from the very end to the very beginning. It also cannot identify different recordings with identical title, artist, and album metadata. Track-start timestamps are estimated from the observed position, so seeking before the first observation can skew that estimate. Missing metadata is skipped. These limits need to be considered when comparing the history with another scrobbler.

## Development

The source is split into playback tracking, persistence, Music observation, API submission, credentials, and service lifecycle modules. Runtime dependencies are `httpx` and macOS `keyring`. No Scroblebler source is copied into this project.

```sh
nix develop
pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
uv run mypy src/lb_scrobbler
uv run pytest -q
uv build
nix flake check
```

For checkout-based development, run `uv sync --locked` and prefix CLI commands with `uv run`, for example `uv run lb-scrobbler probe`. Installing an agent from the checkout records its `.venv` Python path, so keep that environment in place and rerun `install` after recreating or moving it.

Tests cover playback thresholds, interruptions, repeats, restart persistence, and HTTP retry behavior without contacting ListenBrainz. Validate real streaming playback and Automation access separately on macOS before enabling a new installation.

## Nix / Home Manager

`nix build` builds the macOS package with Python 3.13. The flake exports `homeManagerModules.default` so nix-darwin configurations using Home Manager can manage the service declaratively. Add this repository as a flake input, then import the module in your Home Manager configuration:

```nix
imports = [ inputs.listenbrainz-scrobbler.homeManagerModules.default ];
services.listenbrainz-scrobbler.enable = true;
```

Home Manager replaces the manual installer's LaunchAgent under the same label while preserving the queue and Keychain token. Activate Home Manager, then check `lb-scrobbler status` to confirm the agent loaded and observations are fresh. The package path changes, so macOS may request Automation or Keychain access again. Use `lb-scrobbler auth` if no token is stored yet.

The LaunchAgent starts at user login after a reboot, when Music and the login Keychain are available. Home Manager owns its lifecycle after migration, so use it for configuration changes instead of the manual `install` and `uninstall` commands. After changing the token, restart the loaded agent with `launchctl kickstart -k "gui/$(id -u)/xyz.hakula.listenbrainz-scrobbler"`. Disable the module and reactivate Home Manager to remove it. The existing Keychain entry keeps credentials outside the Nix store.

The development shell generates pre-commit configuration from the flake and installs the Git hooks. CI checks hooks and locked Python dependencies on Linux and macOS, and builds the package and a Home Manager configuration on macOS. The Home Manager check builds the activation script without activating it.

## Releases

[PyPI](https://pypi.org/project/listenbrainz-scrobbler/) distributes the package for `uv tool install`. [GitHub releases](https://github.com/hakula139/listenbrainz-scrobbler/releases) provide the same Python wheel and source distribution, plus SHA-256 checksums. The same version tag is a Nix flake reference, for example `github:hakula139/listenbrainz-scrobbler/v0.1.0`. Pin that reference when adding the Home Manager module to another flake.

To release, update the package version in `pyproject.toml` and the submission client version in `tracking.py`, refresh `uv.lock`, and commit after checks pass. Push an annotated `v<version>` tag with the release notes in its annotation. The release workflow reruns Linux and macOS CI, checks that the tag matches the package version, builds the distributions, and publishes their checksums and the tag's notes to GitHub. A separate job verifies the released checksums and publishes those same files to PyPI through Trusted Publishing. To publish an existing GitHub release, run the Release workflow manually with its tag. The PyPI publisher must match this repository, `release.yml`, and the `pypi` GitHub environment.
