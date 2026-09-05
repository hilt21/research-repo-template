"""Synthetic behavior fixtures; these are not EMB evidence."""

import hashlib
import subprocess

import pytest
from core import initialize, read_document, scaffold, validate, write_document
from operations import build_index, mark_affected, snapshot_source
from review import accept, prepare


def run(root, *args):
    return subprocess.run(args, cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def instance(tmp_path):
    initialize(tmp_path, "测试课题", "测试问题", "测试范围", "测试标准")
    run(tmp_path, "git", "init", "-b", "main")
    run(tmp_path, "git", "config", "user.name", "Test")
    run(tmp_path, "git", "config", "user.email", "test@example.invalid")
    (tmp_path / '.gitignore').write_text('.cache/\n')
    run(tmp_path, "git", "add", ".")
    run(tmp_path, "git", "commit", "-m", "test baseline")
    return tmp_path


def complete(root, kind, **research):
    path = scaffold(root, kind, f"测试 {kind}")
    doc = read_document(path)
    doc.meta['research'].update(research)
    body = '\n\n'.join(f'## {heading}\n\n测试说明。' for heading in doc.sections)
    write_document(path, doc.meta, body)
    return path


def hypothesis(root):
    trace = complete(root, 'ResearchTrace')
    path = complete(root, 'Claim', claim_state='hypothesis',
                    traces=[trace.relative_to(root).as_posix()])
    return path, trace


def errors(root):
    return [i.message for i in validate(root) if i.level == 'error']


def test_hypothesis_without_external_source_is_allowed(instance):
    hypothesis(instance)
    assert not errors(instance)
    assert any(i.level == 'warning' for i in validate(instance))


def test_supported_requires_located_support(instance):
    path, _ = hypothesis(instance)
    doc = read_document(path)
    doc.meta['research']['claim_state'] = 'supported'
    write_document(path, doc.meta, doc.body)
    assert any('支持证据' in m for m in errors(instance))


def test_duplicate_id_and_broken_link_fail(instance):
    path, _ = hypothesis(instance)
    (path.parent / 'duplicate.md').write_bytes(path.read_bytes())
    with path.open('a') as f:
        f.write('\n[missing](./missing.md)\n')
    issues = errors(instance)
    assert any('重复 ID' in m for m in issues)
    assert any('引用不存在' in m for m in issues)


def test_fenced_code_link_is_not_a_reference(instance):
    path, _ = hypothesis(instance)
    with path.open('a') as f:
        f.write('\n```md\n[x](does-not-exist.md)\n```\n')
    assert not errors(instance)


def test_instance_does_not_scan_examples(instance):
    path = instance / 'examples/bad/knowledge/bad.md'
    path.parent.mkdir(parents=True)
    path.write_text('not a document')
    assert not errors(instance)


def test_snapshot_is_content_addressed_and_drift_detected(instance, tmp_path):
    source = tmp_path / 'input.txt'
    source.write_text('first')
    record = snapshot_source(instance, source)
    assert record['sha256'] == hashlib.sha256(b'first').hexdigest()
    source.write_text('second')
    second = snapshot_source(instance, source)
    assert second['path'] != record['path']
    assert (instance / record['path']).read_text() == 'first'


def test_index_is_rebuildable_and_uses_knowledge_only(instance):
    hypothesis(instance)
    build_index(instance)
    first = (instance / 'knowledge/index.md').read_bytes()
    build_index(instance)
    assert (instance / 'knowledge/index.md').read_bytes() == first
    assert b'traces/' not in first


def test_impact_follows_explicit_claim_ids(instance):
    claim, _ = hypothesis(instance)
    ident = read_document(claim).meta['research']['id']
    artifact = complete(instance, 'Artifact', claims=[ident], review_state='current')
    assert mark_affected(instance, [ident]) == [artifact.relative_to(instance).as_posix()]
    assert read_document(artifact).meta['research']['review_state'] == 'needs_review'


def test_review_binds_content_and_rejects_post_review_change(instance):
    path, trace = hypothesis(instance)
    selected = [str(p.relative_to(instance)) for p in (path, trace)]
    ticket = prepare(instance, selected)
    with path.open('a') as f:
        f.write('\n新增未审阅内容\n')
    with pytest.raises(ValueError, match='变化'):
        accept(instance, ticket, 'must not commit', confirmed=True)
    assert run(instance, 'git', 'rev-list', '--count', 'HEAD') == '1'


def test_commit_does_not_include_unrelated_staged_files(instance):
    path, trace = hypothesis(instance)
    unrelated = instance / 'personal.txt'
    unrelated.write_text('unrelated')
    run(instance, 'git', 'add', 'personal.txt')
    ticket = prepare(instance, [str(p.relative_to(instance)) for p in (path, trace)])
    commit = accept(instance, ticket, 'accept test hypothesis', confirmed=True)
    names = run(instance, 'git', 'show', '--pretty=', '--name-only', commit)
    assert str(path.relative_to(instance)) in names
    assert 'personal.txt' not in names
    assert 'personal.txt' in run(instance, 'git', 'diff', '--cached', '--name-only')


def test_confirmation_is_required(instance):
    path, trace = hypothesis(instance)
    ticket = prepare(instance, [str(p.relative_to(instance)) for p in (path, trace)])
    with pytest.raises(ValueError, match='确认'):
        accept(instance, ticket, 'no approval', confirmed=False)


def test_candidate_reference_must_be_in_commit(instance):
    path, _ = hypothesis(instance)
    with pytest.raises(ValueError, match='校验'):
        prepare(instance, [str(path.relative_to(instance))])


def test_snapshot_path_cannot_override_candidate_tree(instance):
    path = complete(instance, 'Source', retrieved_at='2026-09-05T12:00:00Z', publisher='测试')
    doc = read_document(path)
    doc.meta['resource'] = 'https://example.invalid/source'
    doc.meta['research']['snapshot'] = {
        'path': '.cache/sources/../../knowledge/topic.md',
        'sha256': hashlib.sha256((instance / 'knowledge/topic.md').read_bytes()).hexdigest(),
    }
    write_document(path, doc.meta, doc.body)
    assert any('快照路径' in e for e in errors(instance))
    with pytest.raises(ValueError):
        prepare(instance, [str(path.relative_to(instance))])


def test_literal_filename_does_not_expand_git_pathspec(instance):
    original = complete(instance, 'Entity')
    special = original.with_name('*.md')
    original.rename(special)
    other = complete(instance, 'Entity')
    ticket = prepare(instance, [str(special.relative_to(instance))])
    commit = accept(instance, ticket, 'literal filename', confirmed=True)
    names = run(instance, 'git', 'show', '--pretty=', '--name-only', commit)
    assert '*.md' in names
    assert other.name not in names


def test_nonexistent_glob_is_not_a_file_list(instance):
    complete(instance, 'Entity')
    with pytest.raises(ValueError):
        prepare(instance, ['knowledge/entities/*.md'])


def test_invalid_yaml_key_is_reported_with_location(instance):
    (instance / 'research.yaml').write_text('? [a, b]\n: c\n')
    issues = validate(instance)
    assert issues and issues[0].path == 'research.yaml'
    assert issues[0].level == 'error'


def test_source_original_internal_path_is_checked(instance):
    path = complete(instance, 'Source', retrieved_at='2026-09-05T12:00:00Z', publisher='测试')
    doc = read_document(path)
    doc.meta['resource'] = './missing.pdf'
    write_document(path, doc.meta, doc.body)
    assert any('引用不存在' in e for e in errors(instance))


def supported(root):
    path, trace = hypothesis(root)
    source = complete(root, 'Source', publisher='Test')
    doc = read_document(source)
    doc.meta['resource'] = 'https://example.invalid/evidence'
    write_document(source, doc.meta, doc.body)
    ident = doc.meta['research']['id']
    doc = read_document(path)
    doc.meta['sources'] = [{'id': ident, 'resource': '../sources/' + source.name}]
    doc.meta['research'].update(claim_state='supported', evidence=[
        {'source_id': ident, 'locator': 'Section 2', 'role': 'supports'}])
    write_document(path, doc.meta, doc.body)
    return path, trace, source


def test_relative_source_reference_can_be_accepted(instance):
    paths = supported(instance)
    assert not errors(instance)
    ticket = prepare(instance, [str(p.relative_to(instance)) for p in paths])
    assert accept(instance, ticket, 'supported claim', confirmed=True)


def test_record_named_log_cannot_bypass_validation(instance):
    claim, _ = hypothesis(instance)
    doc = read_document(claim)
    doc.meta['research'].update(claim_state='supported', traces=[])
    write_document(claim, doc.meta, doc.body)
    target = claim.with_name('log.md')
    claim.rename(target)
    assert errors(instance)
    with pytest.raises(ValueError, match='校验'):
        prepare(instance, [str(target.relative_to(instance))])


def test_reserved_index_is_not_a_hidden_claim(instance):
    claim, _ = hypothesis(instance)
    (instance/'knowledge/index.md').write_bytes(claim.read_bytes())
    assert errors(instance)


def test_broken_index_link_is_reported(instance):
    (instance/'knowledge/index.md').write_text('---\nokf_version: "0.2"\n---\n[x](missing.md)\n')
    assert any('引用不存在' in e for e in errors(instance))


def test_stale_head_rejects_review(instance):
    paths = hypothesis(instance)
    ticket = prepare(instance, [str(p.relative_to(instance)) for p in paths])
    run(instance, 'git', 'commit', '--allow-empty', '-m', 'concurrent change')
    with pytest.raises(ValueError, match='基线'):
        accept(instance, ticket, 'stale', confirmed=True)


def test_missing_and_corrupted_source_snapshot(instance):
    _, _, path = supported(instance)
    doc = read_document(path)
    doc.meta['research']['snapshot'] = {'path': '.cache/sources/raw.txt',
        'sha256': hashlib.sha256(b'original').hexdigest()}
    write_document(path, doc.meta, doc.body)
    assert not errors(instance)
    assert any('快照缺失' in i.message for i in validate(instance))
    raw=instance/'.cache/sources/raw.txt'
    raw.parent.mkdir(parents=True)
    raw.write_text('changed')
    assert any('哈希不匹配' in e for e in errors(instance))


def test_contested_requires_both_sides(instance):
    path, _, _ = supported(instance)
    doc=read_document(path)
    doc.meta['research']['claim_state']='contested'
    write_document(path,doc.meta,doc.body)
    assert any('挑战' in e for e in errors(instance))
    doc.meta['research']['evidence'].append({**doc.meta['research']['evidence'][0],
        'role':'challenges','locator':'Section 3, counterexample'})
    write_document(path,doc.meta,doc.body)
    assert not errors(instance)


def test_malformed_research_metadata_is_located_in_candidate(instance):
    path=instance/'knowledge/bad.md'
    path.write_text('---\ntype: Claim\ntitle: Bad\nstatus: draft\nresearch: []\n---\nBody\n')
    with pytest.raises(ValueError, match='knowledge/bad.md'):
        prepare(instance,['knowledge/bad.md'])
