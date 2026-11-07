# Releasing

Pushing a tag that matches `v[0-9]+.*` starts `.github/workflows/release.yml`, which waits for a passing CI run on the tagged commit, builds the wheel and source archive, and publishes a GitHub Release with the tag's `CHANGELOG.md` section as its notes. The same verified files are then uploaded to PyPI through Trusted Publishing.

## Versioning

- **Before 1.0**: tag `v0.N.0` whenever a user-visible batch lands, and `v0.N.M` for a fix to shipped behavior. A change to the stability surface bumps the minor version and is listed under Breaking changes.
- **After 1.0**: a breaking change to the [stability surface](#stability-surface) bumps the major version, a user-visible addition or change bumps the minor version, and a fix bumps the patch version.
- **Prereleases**: a tag with a suffix such as `-rc.1` publishes a prerelease, and its section lists only changes since the previous tag. PyPI treats the matching version as a prerelease, so `uv tool install` skips it unless pinned.

### Stability surface

Within a minor version, stable releases keep these compatible:

- Subcommands, flags, and exit codes
- The flake's `homeModules.default` output and the module's options
- The LaunchAgent label, the state directory layout under `~/Library/Application Support/listenbrainz-scrobbler/`, and the Keychain service name
- The PyPI package name and the `lb-scrobbler` entry point
- The on-disk playback checkpoint and submission queue format

## Preparation

Follow the [shared release procedure](https://github.com/hakula139/devkit/blob/main/docs/releasing.md) for changelog curation, the release PR, approval, tagging its exact squash commit, and CI recovery. This repository uses `cliff.toml` and `CHANGELOG.md` as the notes source.

Set `version` in `pyproject.toml` to the tag without its `v`, then run `uv lock` and keep the project version change. For a stable release, also update the versioned Nix example in `README.md`. Run the [verification block](AGENTS.md#verification). The release diff normally touches `pyproject.toml`, `uv.lock`, `README.md`, `CHANGELOG.md`, and possibly `.cspell/words.txt`.

The changelog uses compare reference links. Stable sections compare against the previous stable tag, and prereleases against the previous tag. The Release workflow's `notes` input republishes a corrected changelog section without rebuilding artifacts.

## Verify publication

Watch the [Release workflow](https://github.com/hakula139/listenbrainz-scrobbler/actions/workflows/release.yml) with `gh run watch` and check:

- The release notes match the changelog section, and a prerelease tag published a prerelease.
- The release attaches the wheel, the source archive, and `SHA256SUMS`, and `sha256sum --check SHA256SUMS` passes on a download.
- PyPI's version-specific JSON response lists the same distribution hashes, and its description matches the README.
- An isolated `uvx --refresh --python 3.13 --from listenbrainz-scrobbler==X.Y.Z lb-scrobbler --help` succeeds. It runs in a temporary environment, so the user's installed tool and agent stay untouched.

If GitHub publication succeeds but the PyPI job fails, fix its cause and rerun that job, which downloads the already published release files.

## Recovery restrictions

Follow the shared release procedure for recovery. Rebuilding the same version is allowed only when its PyPI job uploaded nothing, since PyPI refuses reused filenames and the builds are not byte-reproducible. Once PyPI has the version, release a new patch version. Any source change also requires a new version through the release PR process.
