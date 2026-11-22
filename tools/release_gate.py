"""Read-only release-candidate checks and safe rerun planning.

This module deliberately does not publish or edit GitHub releases. A workflow
should use it after testing/building and before publishing a draft release.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ttools.distribution import extract_zip, valid_source_commit, verify_bundle

PLATFORM_ARCHIVES = {
    'ttools-linux-x86_64.zip': 'linux-x86_64',
    'ttools-windows-x86_64.zip': 'windows-x86_64',
    'ttools-macos-x86_64.zip': 'macos-x86_64',
    'ttools-macos-arm64.zip': 'macos-arm64',
}
SUPPORT_ASSETS = {'bootstrap.py', 'install.sh', 'install.ps1'}
METADATA_ASSETS = {'suite-update.json', 'SHA256SUMS.txt'}
EXPECTED_ASSETS = set(PLATFORM_ARCHIVES) | SUPPORT_ASSETS | METADATA_ASSETS
VERSION_RE = re.compile(r'\d+\.\d+\.\d+(?:-(?:alpha|beta|rc|preview)\.\d+)?\Z')
SHA256_RE = re.compile(r'[0-9a-f]{64}\Z')


class ReleaseGateError(ValueError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_commit_binding(tested_commit, build_commit, workflow_commit):
    """Require test, build and publishing jobs to name the same full SHA."""
    values=(tested_commit, build_commit, workflow_commit)
    if not all(valid_source_commit(value) for value in values):
        raise ReleaseGateError('All candidate commits must be full lowercase Git SHAs')
    if len(set(values)) != 1:
        raise ReleaseGateError('Tested commit, bundle commit and workflow commit differ')
    return values[0]


def dereference_tag(ref_object, fetch_tag_object):
    """Resolve lightweight or annotated Git tag objects to a commit SHA."""
    current=ref_object
    seen=set()
    for _ in range(10):
        if not isinstance(current,dict):
            raise ReleaseGateError('Malformed Git tag object')
        sha=current.get('sha')
        kind=current.get('type')
        if not valid_source_commit(sha) or sha in seen:
            raise ReleaseGateError('Malformed or cyclic Git tag chain')
        seen.add(sha)
        if kind=='commit':return sha
        if kind!='tag':raise ReleaseGateError(f'Tag resolves to unsupported Git object type: {kind}')
        tagged=fetch_tag_object(sha)
        current=tagged.get('object') if isinstance(tagged,dict) else None
    raise ReleaseGateError('Git tag nesting exceeds the supported limit')


def _expected_hashes_from_sums(path):
    values={}
    for line_number,line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(),1):
        match=re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9._-]+)',line)
        if not match:
            raise ReleaseGateError(f'Invalid SHA256SUMS.txt line {line_number}')
        digest,name=match.groups()
        if name in values:raise ReleaseGateError(f'Duplicate checksum entry: {name}')
        values[name]=digest
    return values


def validate_candidate_assets(directory, version, tested_commit, build_commit, workflow_commit):
    """Validate complete local artifacts, inventories, hashes and source SHA."""
    source_commit=validate_commit_binding(tested_commit,build_commit,workflow_commit)
    if not isinstance(version,str) or not VERSION_RE.fullmatch(version):
        raise ReleaseGateError('Invalid release version')
    directory=Path(directory)
    entries=list(directory.iterdir())
    if any(not path.is_file() or path.is_symlink() for path in entries):
        raise ReleaseGateError('Release directory contains a non-file asset')
    actual={path.name for path in entries}
    if actual!=EXPECTED_ASSETS:
        raise ReleaseGateError(f'Release assets differ: missing={sorted(EXPECTED_ASSETS-actual)}, extra={sorted(actual-EXPECTED_ASSETS)}')
    hashes={path.name:sha256(path) for path in entries}
    sums=_expected_hashes_from_sums(directory/'SHA256SUMS.txt')
    if set(sums)!=EXPECTED_ASSETS-{'SHA256SUMS.txt'}:
        raise ReleaseGateError('SHA256SUMS.txt does not list every non-checksum release asset exactly once')
    for name,digest in sums.items():
        if hashes[name]!=digest:raise ReleaseGateError(f'Checksum file mismatch: {name}')

    feed=json.loads((directory/'suite-update.json').read_text(encoding='utf-8'))
    if feed.get('schema_version')!=2 or feed.get('app_id')!='ttools':
        raise ReleaseGateError('suite-update.json must use suite manifest schema 2')
    if feed.get('version')!=version or feed.get('source_commit')!=source_commit:
        raise ReleaseGateError('Update feed version/source commit mismatch')
    artifacts=feed.get('artifacts')
    if not isinstance(artifacts,list) or len(artifacts)!=len(PLATFORM_ARCHIVES):
        raise ReleaseGateError('Update feed must contain exactly one artifact per supported platform')
    artifact_by_platform={}
    for artifact in artifacts:
        if not isinstance(artifact,dict):raise ReleaseGateError('Malformed update artifact entry')
        platform=artifact.get('platform')
        if platform in artifact_by_platform:raise ReleaseGateError(f'Duplicate update platform: {platform}')
        artifact_by_platform[platform]=artifact
    expected_platforms=set(PLATFORM_ARCHIVES.values())
    if set(artifact_by_platform)!=expected_platforms:
        raise ReleaseGateError('Update feed platform set is incomplete or unexpected')

    with tempfile.TemporaryDirectory(prefix='ttools-release-gate-') as temporary:
        for name,platform in PLATFORM_ARCHIVES.items():
            artifact=artifact_by_platform[platform]
            archive_hash=hashes[name]
            expected_url=f'https://github.com/user9x21imi/ttools/releases/download/v{version}/{name}'
            if artifact.get('url')!=expected_url or artifact.get('sha256')!=archive_hash:
                raise ReleaseGateError(f'Update feed URL/hash mismatch for {platform}')
            if not isinstance(artifact.get('complete_suite_supported'),bool):
                raise ReleaseGateError(f'Missing support status for {platform}')
            extraction=Path(temporary)/platform
            extract_zip(directory/name,extraction)
            bundle=extraction/'ttools'
            manifest=verify_bundle(bundle)
            if manifest.get('version')!=version or manifest.get('source_commit')!=source_commit:
                raise ReleaseGateError(f'Bundle version/source commit mismatch for {platform}')
            if manifest.get('platform')!=platform:
                raise ReleaseGateError(f'Bundle platform mismatch for {platform}')
    return hashes


@dataclass(frozen=True)
class ReleaseSnapshot:
    tag: str
    tag_commit: str | None
    draft: bool
    immutable: bool
    assets: dict[str, str]


def snapshot_from_api(release, tag_commit):
    """Convert release API JSON plus a dereferenced tag SHA into a strict snapshot."""
    if not isinstance(release,dict):raise ReleaseGateError('Malformed release API response')
    if not isinstance(release.get('draft'),bool) or not isinstance(release.get('immutable'),bool):
        raise ReleaseGateError('Release API response is missing draft/immutable status')
    assets={}
    for asset in release.get('assets',[]):
        if not isinstance(asset,dict):raise ReleaseGateError('Malformed release asset entry')
        name=asset.get('name')
        digest=asset.get('digest')
        match=re.fullmatch(r'sha256:([0-9a-f]{64})',digest or '')
        if not isinstance(name,str) or not match or name in assets:
            raise ReleaseGateError('Release API asset has a missing digest or duplicate name')
        assets[name]=match.group(1)
    return ReleaseSnapshot(
        tag=release.get('tag_name',''),tag_commit=tag_commit,
        draft=release.get('draft') is True,immutable=release.get('immutable') is True,
        assets=assets)


@dataclass(frozen=True)
class RerunPlan:
    action: str
    missing_assets: tuple[str, ...] = ()
    reason: str = ''


def plan_rerun(tag, tested_commit, expected_assets, snapshot=None, tag_commit=None,
               tag_lookup_complete=False):
    """Plan a safe create/resume/no-op; never overwrite conflicting assets."""
    if not VERSION_RE.fullmatch(tag.removeprefix('v')):
        return RerunPlan('block',reason='Tag does not contain a supported version')
    if not valid_source_commit(tested_commit):
        return RerunPlan('block',reason='Tested commit is not a full lowercase SHA')
    if not tag_lookup_complete:
        return RerunPlan('block',reason='GitHub tag existence/target has not been verified')
    expected=dict(expected_assets)
    if set(expected)!=EXPECTED_ASSETS or any(not SHA256_RE.fullmatch(v) for v in expected.values()):
        return RerunPlan('block',reason='Expected asset set or SHA-256 values are invalid')
    if snapshot is not None:
        if tag_commit is not None and snapshot.tag_commit!=tag_commit:
            return RerunPlan('block',reason='Release snapshot and Git tag resolve to different commits')
        tag_commit=tag_commit or snapshot.tag_commit
    if tag_commit is not None and tag_commit!=tested_commit:
        return RerunPlan('block',reason='Existing tag does not point to the tested commit')
    if snapshot is None:
        return RerunPlan('create_draft',tuple(sorted(expected)))
    if snapshot.tag!=tag:return RerunPlan('block',reason='Existing release tag differs from candidate tag')
    if tag_commit is None:
        return RerunPlan('block',reason='Existing release tag target was not verified')
    if tag_commit!=tested_commit:
        return RerunPlan('block',reason='Existing tag does not point to the tested commit')
    actual=snapshot.assets
    extras=set(actual)-set(expected)
    if extras:return RerunPlan('block',reason='Existing release has unexpected assets: '+', '.join(sorted(extras)))
    mismatches=[name for name,digest in actual.items() if expected.get(name)!=digest]
    if mismatches:return RerunPlan('block',reason='Existing assets differ from candidate: '+', '.join(sorted(mismatches)))
    missing=tuple(sorted(set(expected)-set(actual)))
    if snapshot.draft:
        if snapshot.immutable:return RerunPlan('block',reason='Draft release unexpectedly reports immutable')
        if missing:return RerunPlan('resume_draft',missing,'Upload only the missing verified assets')
        return RerunPlan('publish_draft',reason='All expected draft assets match')
    if not snapshot.immutable:
        return RerunPlan('block',reason='Published release is mutable; immutable-release policy is required')
    if missing:return RerunPlan('block',reason='Published immutable release is incomplete')
    return RerunPlan('no_op',reason='Published immutable release matches tag, commit, names and hashes')


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Validate TTools release assets and plan an idempotent rerun')
    parser.add_argument('--dist',type=Path,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--tested-commit',required=True)
    parser.add_argument('--build-commit',required=True)
    parser.add_argument('--workflow-commit',required=True)
    parser.add_argument('--tag-commit',help='Dereferenced GitHub tag SHA; omit only when no tag exists')
    parser.add_argument('--tag-ref-checked',action='store_true',help='Assert the GitHub tag ref lookup completed')
    parser.add_argument('--release-json',type=Path,help='GitHub release API JSON; omit if no release exists')
    args=parser.parse_args(argv)
    try:
        hashes=validate_candidate_assets(args.dist,args.version,args.tested_commit,
                                         args.build_commit,args.workflow_commit)
        snapshot=None
        if args.release_json:
            if not args.tag_commit:raise ReleaseGateError('--tag-commit is required for an existing release')
            snapshot=snapshot_from_api(json.loads(args.release_json.read_text(encoding='utf-8')),
                                       args.tag_commit)
        plan=plan_rerun('v'+args.version,args.tested_commit,hashes,snapshot,args.tag_commit,
                        tag_lookup_complete=args.tag_ref_checked)
        print(json.dumps({'action':plan.action,'missing_assets':plan.missing_assets,
                          'reason':plan.reason,'assets':hashes},indent=2))
        return 2 if plan.action=='block' else 0
    except (OSError,ValueError,zipfile.BadZipFile) as error:
        print(json.dumps({'action':'block','reason':str(error)}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
