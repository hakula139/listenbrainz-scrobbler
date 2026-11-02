# Releasing

Pushing a tag that matches `v[0-9]+.*` starts `.github/workflows/release.yml`, which waits for a passing CI run on the tagged commit, builds the wheel and source archive, and publishes a GitHub Release with the tag's `CHANGELOG.md` section as its notes. The same verified files are then uploaded to PyPI through Trusted Publishing.

To republish a tag's notes after correcting its section, run the Release workflow on `main` with the tag in its `notes` input, which edits the release and builds nothing:

```bash
gh workflow run release.yml --ref main -f notes=vX.Y.Z
```

## Versioning

- **Before 1.0**: tag `v0.N.0` whenever a user-visible batch lands, and `v0.N.M` for a fix to shipped behavior. A change to the stability surface bumps the minor version and is listed under Breaking changes.
- **After 1.0**: a breaking change to the [stability surface](#stability-surface) bumps the major version, a user-visible addition or change bumps the minor version, and a fix bumps the patch version.
- **Prereleases**: a tag with a suffix such as `-rc.1` publishes a prerelease, and its section lists only changes since the previous tag.

### Stability surface

Within a minor version, stable releases keep these compatible:

- Subcommands, flags, and exit codes
- The flake's `homeModules.default` output and the module's options
- The LaunchAgent label, the state directory layout under `~/Library/Application Support/listenbrainz-scrobbler/`, and the Keychain service name
- The PyPI package name and the `lb-scrobbler` entry point
- The on-disk playback checkpoint and submission queue format

## Changelog

[git-cliff](https://git-cliff.org) drafts each release's `CHANGELOG.md` section from `cliff.toml`, and the release PR curates the draft into the published notes.

- Each squash-merged PR title becomes one draft entry.
- `feat`, `fix`, `perf`, and `revert` titles appear under Added, Fixed, Changed, and Removed, respectively. Titles with `!` appear under Breaking changes. Other types are skipped, including routine `chore(deps)` and `chore(flake)` bumps.
- Each `(#N)` links to its PR.
- A stable section includes every change since the previous stable release. A prerelease section includes only changes since the previous tag.
- `--prepend` adds one section while preserving the rest. Avoid `--output CHANGELOG.md`, which regenerates the whole file and drops every curated section and compare link.

### Curate the section

The draft lists PR titles, which are too short to explain each change to users. Before opening the release PR, rewrite and reorganize the draft for users, reading a PR's description wherever its title leaves the effect unclear. Follow these rules:

- For a stable section, start from the curated sections of the prereleases it rolls up and carry over every entry.
- Describe what users can now do, what no longer breaks, and what now works differently, such as a check that now fails or a value that is now rejected. Omit implementation details.
- Merge entries that describe the same user-visible change, keeping every PR link. Fold a fix to a feature that is new in the same section into that feature's entries, and describe the feature as it now works.
- Move each entry to the group that matches its effect, such as a `fix` that adds a capability moving to Added. Keep entries under Breaking changes there.
- Drop entries with no user-visible effect, such as a CI-only or test-only change titled `fix`.
- Order entries within each group by user impact, and keep their scope labels.
- Lead with the highlights when the release has any, curating them like the entries.
- Describe only what the PRs changed.

## Prepare a release

1. Branch off `main` as `chore/release-vX.Y.Z`.

2. Set `version` in `pyproject.toml`, `submission_client_version` in `src/lb_scrobbler/tracking.py` and its expectation in `tests/test_playing_now.py`, and the versioned Nix example in `README.md`. Run `uv lock` and keep only the project version change.

3. Inside the dev shell, which provides git-cliff, prepend the section. Because `cliff.toml` bounds sections at stable tags only, a prerelease adds a `--tag-pattern` that bounds its section at every tag:

   ```bash
   git cliff --unreleased --tag vX.Y.Z --prepend CHANGELOG.md                                # Stable
   git cliff --unreleased --tag vX.Y.Z --tag-pattern '^v[0-9]+\.' --prepend CHANGELOG.md     # Prerelease
   ```

   For a notable release, list the highlights as Markdown bullets in `highlights.md` and add `--with-tag-message="$(<highlights.md)"`, which renders them under `### Highlights` at the top of the section.

4. Because `--prepend` writes no compare link, add the section's link reference above the first one at the end of `CHANGELOG.md`. A stable release compares against the previous stable tag, and a prerelease against the previous tag:

   ```bash
   git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude '*-*'    # Previous stable tag
   git describe --tags --abbrev=0 --match 'v[0-9]*'                    # Previous tag
   ```

   ```markdown
   [X.Y.Z]: https://github.com/hakula139/listenbrainz-scrobbler/compare/<previous-tag>..vX.Y.Z
   ```

   When the stable lookup finds no tag, as for `v0.1.0`, link `https://github.com/hakula139/listenbrainz-scrobbler/releases/tag/vX.Y.Z` instead.

5. [Curate the section](#curate-the-section) that git-cliff prepended.

6. Run the [verification block](AGENTS.md#verification).

7. Commit, then open a PR titled `chore(release): vX.Y.Z`. Record the checks in the PR's Test plan. The diff should touch only `pyproject.toml`, `uv.lock`, `src/lb_scrobbler/tracking.py`, `tests/test_playing_now.py`, `README.md`, `CHANGELOG.md`, and possibly `.cspell/words.txt`.

8. Merge after CI passes and the review is approved. If another PR merges first, recreate the branch from `main` and repeat the steps before curation, because updating the branch leaves a section that misses the new commit.

## Tag

Pushing the tag starts the Release workflow and is hard to undo, so get approval for it separately from the release PR.

Tag the release PR's squash commit by its SHA, since a later PR may already sit on top of `main`:

```bash
git fetch origin
sha=$(gh pr view <release-pr> --json mergeCommit --jq .mergeCommit.oid)
git tag vX.Y.Z "$sha" && git push origin vX.Y.Z
```

The workflow reuses the CI run that the merge started on `main` and waits up to an hour for it to finish. It publishes nothing unless a push or dispatched CI run on that commit passed, so a tag on a commit that never ran CI on `main` needs `gh workflow run ci.yml --ref vX.Y.Z` first, and a failed run needs its failed jobs rerun. Then rerun the Release workflow's failed jobs.

## Verify publication

Watch the [Release workflow](https://github.com/hakula139/listenbrainz-scrobbler/actions/workflows/release.yml) with `gh run watch` and check:

- The release notes match the changelog section, and a prerelease tag published a prerelease.
- The release attaches the wheel, the source archive, and `SHA256SUMS`, and `sha256sum --check SHA256SUMS` passes on a download.
- PyPI's version-specific JSON response lists the same distribution hashes, and its description matches the README.
- An isolated `uv tool install --python 3.13 listenbrainz-scrobbler==X.Y.Z` runs `lb-scrobbler --help`. Keep this separate from activating the user's existing service.

If GitHub publication succeeds but the PyPI job fails, fix its cause and rerun that job, which downloads the already published release files. Do not move a published tag or replace its artifacts to include later code or documentation changes.

## Re-cut an existing tag

The PR-based flow tags only reviewed, CI-green commits, so re-cutting should be rare. If a release still needs to be redone, let any in-flight release run finish first. To rebuild the same commit, delete only the release with `gh release delete vX.Y.Z --yes` and run the Release workflow from the Actions tab against the tag. To release a different commit, delete the release and its tag, then move and push the tag:

```bash
gh release delete vX.Y.Z --cleanup-tag --yes
git tag -f vX.Y.Z <commit> && git push origin vX.Y.Z
```
