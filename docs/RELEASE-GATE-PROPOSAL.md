# Release gate proposal (not wired into Actions)

This is a read-only validation contract for a future reviewed publisher job. It
does not create, upload, edit, or publish GitHub releases.

## Required order

1. The tested commit SHA, package/build SHA, and workflow `GITHUB_SHA` must be
   identical. Build every artifact from that clean checkout.
2. Run `python tools/release_gate.py --dist dist --version "$VERSION"
   --tested-commit "$TESTED_SHA" --build-commit "$BUILD_SHA"
   --workflow-commit "$GITHUB_SHA"` before any release mutation.
3. Resolve `v$VERSION` through Git refs, recursively dereferencing annotated
   tags. If the ref exists, it must resolve to the tested commit. Never infer
   tag identity from a release's `target_commitish` string.
4. Fetch an existing release snapshot and pass its JSON plus the dereferenced
   tag SHA to the gate. Interpret its plan as follows:
   - `create_draft`: create a draft at the tested commit; then upload the full
     verified asset set.
   - `resume_draft`: upload only the listed missing assets. Existing assets
     must already have the expected names and SHA-256 values.
   - `publish_draft`: all assets are present and exact; wait for the protected
     environment approval, then publish.
   - `no_op`: the version is already published, immutable, and byte-for-byte
     identical. Do not upload or edit anything.
   - `block`: stop. Do not replace assets, retarget a tag, or treat the rerun
     as successful. Resolve the draft manually or use a new version.
5. After publication, fetch the Git tag and release again. Require the tag to
   resolve to the tested commit, `immutable=true`, and the exact expected asset
   name/hash map.

The expected asset map is nine files: four platform ZIPs, `suite-update.json`,
`SHA256SUMS.txt`, `bootstrap.py`, `install.sh`, and `install.ps1`. Both the local
directory and GitHub's uploaded asset list must match exactly. The feed's four
platform entries must point at those ZIPs and use their actual SHA-256 digests.
The checksum file must enumerate every other asset once, with no extras.

## Partial release handling

Only an unpublished draft with a correct tag and a matching subset of assets is
resumable. Upload its missing files and verify the complete set again before
publication. A draft with an unexpected name or conflicting digest is blocked;
the gate never deletes or replaces an asset. A published mutable release is
blocked even when its current bytes happen to match. A published immutable
release is a successful rerun only when its tag, commit, names, and hashes all
match exactly.

## GitHub controls needed before wiring the publisher

- Protect `main`: PR-only changes, at least one independent approval, dismiss
  stale approvals or require approval of the most recent push, require the
  complete test/package/release-artifact status checks, resolve review threads,
  and disallow force pushes/deletion and bypass.
- Add a `production-release` environment to the publishing job. Require an
  independent maintainer reviewer, prevent self-review, and restrict allowed
  deployment refs to `main`.
- Enable repository release immutability **before** creating the next release.
  Existing mutable releases do not become immutable retroactively.
- Allow the publish job only from a reviewed main commit and an explicitly
  approved version. Development branch pushes stay test/build-only.

Repository settings are external to this file and must be verified by an
administrator. If any gate or immutable-release setting is unavailable, keep
publication blocked.
