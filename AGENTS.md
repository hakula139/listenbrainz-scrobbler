# AGENTS.md: listenbrainz-scrobbler

Project-specific guidance for coding assistants. `CLAUDE.md` is a symlink to this file. Follow the user's global instructions for Git workflow, secret handling, and communication.

## Playback and persistence

Count observed playback only. Pauses, seeks, and observation gaps must not manufacture listening time. Preserve the original listen timestamp when retrying submissions.

Commit the playback checkpoint and newly qualified listen in the same SQLite transaction. Keep dry-run storage separate from the submission queue. Changes to tracking or persistence need regression tests for the affected repeat, restart, or interruption behavior.

`music.js` runs through macOS JavaScript for Automation, so Node.js APIs and tooling that rewrites the runtime are unsuitable. Preserve the persistent scripting process: starting a new process for every sample repeatedly initializes macOS input services. Keep control-flow bodies braced, including single-line returns.

Configure logging at the CLI boundary and use named loggers in other modules. Keep HTTP library logging quiet because request details can expose credentials. Log submission identifiers and sanitized failure details without tokens or raw request objects.

## Service integration

Music automation and the login Keychain require a user session. Keep the service a user LaunchAgent that starts at login. A foreground probe does not prove that the background process has Automation permission, and a changed Python executable may require new consent. Leave launchd ProcessType at its default: Background throttling can delay observer startup for minutes under load and prevent timely playback sampling.

The manual installer and Home Manager module share the LaunchAgent label, state directory, and Keychain entry so users can migrate without losing their queue or credentials. Keep those contracts aligned. In the Home Manager activation graph, create the state directory before `setupLaunchAgents`, since launchd must open the log files when starting the service.

Only one process may own the tracker, including dry runs. Use `probe` for observation diagnostics while the service is running. Runtime checks must distinguish a loaded LaunchAgent from fresh observations and successful submission.

## Verification

Enter `nix develop` to generate the pre-commit configuration and install its hooks. Change hook definitions in `flake.nix`. Keep the development shell's Python separate from the Python environment used by Nix hooks, so `uv run` does not resolve test dependencies from the hook environment.

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src/lb_scrobbler
uv run pytest -q
pre-commit run --all-files
uv build
nix flake check
```

For checkout-based development, prefix CLI commands with `uv run`, for example `uv run lb-scrobbler probe`. Installing an agent from the checkout records its `.venv` Python path, so keep that environment in place and rerun `install` after recreating or moving it.

CI runs hooks and locked Python checks on Linux and macOS. Tests cover playback thresholds, interruptions, repeats, restart persistence, and HTTP retries without contacting ListenBrainz. Use focused checks while iterating. `nix flake check` builds the package and Home Manager activation script on macOS but does not activate the service or test Music access. For changes to Music observation, validate streamed playback outside the library and background Automation access separately on macOS. See [README.md](README.md) for setup and operation.

## Releases

Use the [release skill](.agents/skills/release/SKILL.md) to prepare the changelog and version changes, publish a release, and verify GitHub and PyPI artifacts.
