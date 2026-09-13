---
name: release
description: Prepare and publish listenbrainz-scrobbler releases to GitHub and PyPI with a versioned Nix flake and maintained changelog. Use for release requests and package-description updates that require a new version.
---

# Release

Use `git-workflow` for commits, PRs, and merge authorization. Prepare the release on a branch, then tag the approved merged commit after checks pass. Publication authorization applies to the requested release and does not authorize merging a different PR.

## Prepare

- Inspect the current version, published tags, and changes since the previous release. Include only changes intended for this release.
- Update `pyproject.toml`, `submission_client_version` in `src/lb_scrobbler/tracking.py`, and the versioned Nix example in `README.md`. Run `uv lock` and inspect the diff for unrelated dependency changes.
- Draft the new section with `nix develop -c git cliff --unreleased --tag vX.Y.Z -o /tmp/scrobbler-release-draft.md`. Curate it into `CHANGELOG.md`, resolving the draft's Review group into user-visible changes or omitting internal maintenance. Compare the result with the actual changes and preserve published entries. Move applicable Unreleased entries into the new section and advance its compare link to the new tag. Add the version's compare link to the previous tag, or a release link for the first version. Do not direct generated output at the maintained changelog.
- Keep README links usable on PyPI, including absolute GitHub URLs for repository files. PyPI stores the uploaded description with the release: changing GitHub's README or re-uploading an existing version does not refresh that description. Publish a new version when the package description must change.

Run the checks in [AGENTS.md](../../../AGENTS.md). Build candidates into an empty temporary directory with `uv build --out-dir <directory>`. Inspect wheel `METADATA` and source `PKG-INFO`: both must contain the intended version, Markdown content type, and exact current README. Confirm the wheel includes `lb_scrobbler/music.js`.

## Publish

After the release PR is approved and merged, create an annotated `v<version>` tag on the merged commit. Copy the reviewed changelog section, including its link definitions, to a temporary notes file and pass it to `git tag -a vX.Y.Z -F <notes-file>`. The release workflow takes GitHub release notes from that annotation. Push the tag when publication is authorized for this release.

The tag workflow checks Linux and macOS, builds distributions, publishes GitHub assets and `SHA256SUMS`, then uploads those same verified files to PyPI through Trusted Publishing. The PyPI publisher matches this repository, `release.yml`, and the `pypi` GitHub environment.

If GitHub publication succeeds but PyPI publication fails, diagnose the failed job. After fixing its cause, manually dispatch the Release workflow with the existing tag to upload the already released files. Do not move a published tag or replace its artifacts to include later code or documentation changes.

## Verify

Wait for both GitHub and PyPI publishing jobs to finish. Verify the GitHub release tag points at the intended commit, and compare both published distribution hashes against `SHA256SUMS` and PyPI's version-specific JSON response.

Check that the public PyPI description matches the intended README and its rendered links work. Install the published version in an isolated uv environment and run `lb-scrobbler --help`. Keep installation verification separate from activating the user's existing service.

Report the release and package URLs with the verified version. A successful build or queued workflow is not a completed publication.
