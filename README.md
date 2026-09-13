# listenbrainz-scrobbler

A background service that submits Apple Music playback on macOS to ListenBrainz. It uses Music.app's scripting interface and a user LaunchAgent. No App Store purchase or developer signing certificate is required.

## Setup

Install Python 3.12 or newer and [uv](https://docs.astral.sh/uv/), then run from this checkout:

```sh
uv sync --locked
uv run lb-scrobbler install --dry-run
uv run lb-scrobbler status
```

Allow the Python process to control Music when macOS asks. Terminal's Automation permission applies to a foreground probe, so the LaunchAgent may need a separate grant. The first query waits up to a minute for consent. If access is denied, enable it in System Settings → Privacy & Security → Automation, then reinstall the agent. `status` shows the observation age, current track, observed playback seconds, and any read error. Confirm the observations stay fresh and the position advances while playing.

After the dry run works, quit other scrobblers to avoid duplicate submissions. Save your [ListenBrainz token](https://listenbrainz.org/settings/) in the login Keychain:

```sh
uv run lb-scrobbler auth
uv run lb-scrobbler install
```

For an existing SmashTunes setup, `uv run lb-scrobbler auth --from-smashtunes` explicitly transfers its stored ListenBrainz token into this service's Keychain entry after validating it. Neither command prints the token. Do not put tokens in command arguments, project files, or Git.

`install` starts the service immediately and at future logins. It records the current virtual environment's Python path, so keep the checkout and `.venv` in place. Rerun `install` after moving the project or recreating the environment. Updating the underlying Python executable may require fresh macOS Automation or Keychain consent.

## Operation

```sh
uv run lb-scrobbler probe       # Read Music without submitting
uv run lb-scrobbler status      # Last observation and submission queue
uv run lb-scrobbler stop        # Stop until reinstalled or the next login
uv run lb-scrobbler uninstall   # Remove the launch agent
uv run lb-scrobbler retry       # Retry retained failures after fixing their cause
```

`uv run lb-scrobbler run --dry-run` runs in the foreground. Stop the LaunchAgent first, since only one process may own the playback tracker.

State and logs live in `~/Library/Application Support/listenbrainz-scrobbler/`. The service stores metadata and its SQLite queue there with user-only permissions. The submission token is held separately in login Keychain under `xyz.hakula.listenbrainz-scrobbler`. Uninstalling the agent preserves both the queue and Keychain entry.

A persistent scripting process samples playback every two seconds. It submits after observing half a track or four minutes of playback, whichever comes first, following [ListenBrainz's submission rule](https://listenbrainz.readthedocs.io/en/latest/users/api/core.html). Pauses, seeks, and observation gaps longer than ten seconds do not contribute listening time. Starting the service halfway through a song does not credit playback it did not observe.

Qualified listens and playback checkpoints are committed together. A separate worker sends the queue and retains failures with the original listen timestamp. Network and server errors use delayed retries. Invalid payloads remain blocked for inspection through `status` and manual `retry`. After replacing an expired token, reinstall the agent so the worker loads it. Delivery is at least once: a crash after server acceptance but before local acknowledgement can resend the same payload.

Dry-run mode uses a separate queue that is never sent. There is no historical backfill or iPhone library synchronization, and no optional playing-now submissions. The service captures playback observed on this Mac.

## Limits

Polling cannot distinguish a natural repeat from manually seeking from the very end to the very beginning. It also cannot identify different recordings with identical title, artist, and album metadata. Track-start timestamps are estimated from the observed position, so seeking before the first observation can skew that estimate. Missing metadata is skipped. These limits need to be considered when comparing the history with another scrobbler.

## Development

The source is split into playback tracking, persistence, Music observation, API submission, credentials, and service lifecycle modules. Runtime dependencies are `httpx` and macOS `keyring`. No Scroblebler source is copied into this project.

```sh
uv run pre-commit install
uv run pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

Tests cover playback thresholds, interruptions, repeats, restart persistence, and HTTP retry behavior without contacting ListenBrainz. Validate real streaming playback and Automation access separately on macOS before enabling a new installation.
