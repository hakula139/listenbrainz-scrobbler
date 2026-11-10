# Releasing

Pushing a version tag runs the [Release workflow](.github/workflows/release.yml). It waits for CI on the tagged commit, publishes the tag's `CHANGELOG.md` section as a GitHub Release with the wheel, source archive, and `SHA256SUMS`, then uploads the same files to PyPI through Trusted Publishing. The [release skill](https://github.com/hakula139/plugins/blob/main/plugins/hakula-workflow/skills/release/SKILL.md) covers the shared procedure.

## Versioning

- **Before 1.0**: tag `v0.N.0` whenever a user-visible batch lands, and `v0.N.M` for a fix to shipped behavior. A change to the stability surface bumps the minor version and is listed under Breaking changes.
- **After 1.0**: a breaking change to the [stability surface](#stability-surface) bumps the major version, a user-visible addition or change bumps the minor version, and a fix bumps the patch version.
- **Prereleases**: a tag with a `-` suffix publishes a prerelease. PyPI treats its version as a prerelease too, so `uv tool install` skips it unless pinned.

### Stability surface

Within a minor version, stable releases keep these compatible:

- Subcommands, flags, and exit codes
- The flake's `homeModules.default` output and the module's options
- The LaunchAgent label, the state directory layout under `~/Library/Application Support/listenbrainz-scrobbler/`, and the Keychain service name
- The PyPI package name and the `lb-scrobbler` entry point
- The on-disk playback checkpoint and submission queue format

## Preparation

Set `version` in `pyproject.toml` to the tag without its `v` and run `uv lock`. For a stable release, also update the versioned flake input in `README.md`. Then run the [verification commands](AGENTS.md#verification).

## Verify publication

Check that PyPI's project description renders the README, then run the published version in a temporary environment, which leaves the installed tool and agent untouched:

```sh
uvx --refresh --python 3.13 --from listenbrainz-scrobbler==X.Y.Z lb-scrobbler --help
```

## Recovery

If the GitHub Release publishes but the PyPI job fails, fix the cause and rerun that job, which downloads the published release files. Rebuild a version only when its PyPI job uploaded nothing, since PyPI refuses reused filenames and the builds are not byte-reproducible. Once PyPI has the version, release a new patch version.

To republish a corrected changelog section without rebuilding the artifacts, run the Release workflow from `main` with the tag:

```sh
gh workflow run release.yml -f notes=vX.Y.Z
```
