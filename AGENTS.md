# AGENTS.md: listenbrainz-scrobbler

`listenbrainz-scrobbler` is a user LaunchAgent that submits Apple Music listens on macOS to ListenBrainz, installed from PyPI with uv or through the Home Manager module. `CLAUDE.md` is a symlink to this file.

## Playback and persistence

Count observed playback only. Pauses, seeks, and observation gaps must not manufacture listening time. Preserve the original listen timestamp when retrying submissions.

Commit the playback checkpoint and newly qualified listen in the same SQLite transaction. Keep dry-run storage separate from the submission queue. Changes to tracking or persistence need regression tests for the affected repeat, restart, or interruption behavior.

`music.js` runs under macOS JavaScript for Automation, which has no Node.js APIs, so keep it free of Node.js modules and of build steps such as bundling or transpiling. Preserve the persistent scripting process: starting a new process for every sample repeatedly initializes macOS input services. Keep control-flow bodies braced, including single-line returns.

Configure logging at the CLI boundary and use named loggers in other modules. Keep HTTP library logging quiet because request details can expose credentials. Log submission identifiers and sanitized failure details without tokens or raw request objects.

## Service integration

Music automation and the login Keychain require a user session, so keep the service a user LaunchAgent that starts at login. A changed Python executable may require new Automation or Keychain consent. Leave launchd's `ProcessType` at its default, since `Background` throttling can delay observer startup for minutes under load and prevent timely playback sampling.

The manual installer in `service.py` and the Home Manager module share the LaunchAgent label, state directory, and Keychain entry, which lets users migrate without losing their queue or credentials. Keep those contracts and the agent's launchd keys aligned between the two.

Only one process may own the tracker, including dry runs. Use `probe` for observation diagnostics while the service is running, since `run` holds the tracker lock.

## Verification

```sh
nix develop -c run-hooks
nix flake check --all-systems
nix develop -c uv run --locked pytest
nix develop -c uv build
```

`uv run lb-scrobbler install` records the checkout's `.venv` Python in the agent, so rerun `install` after recreating or moving that environment.

No automated check activates the service or reads Music. For a change to Music observation, check on macOS that streamed tracks outside the library are observed and that the background agent has Automation access, which a foreground `probe` does not prove. A runtime check must tell a loaded LaunchAgent apart from fresh observations and successful submissions.

## Releases

PR titles become draft changelog entries, so write them for users and mark a break of the [stability surface](RELEASING.md#stability-surface) with `!`.

Use absolute GitHub URLs for repository files in README links so they work on PyPI. Follow [RELEASING.md](RELEASING.md) for releases.
