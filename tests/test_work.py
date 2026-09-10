"""Public workflow checks using synthetic research, never domain evidence."""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from core import initialize, read_document, write_document
from repo import main
from review import accept, prepare
from test_research import complete, run


@pytest.fixture
def workspace(tmp_path):
    initialize(tmp_path, '合成课题', '问题', '范围', '标准')
    run(tmp_path, 'git', 'init', '-b', 'main')
    run(tmp_path, 'git', 'config', 'user.name', 'Test')
    run(tmp_path, 'git', 'config', 'user.email', 'test@example.invalid')
    (tmp_path / '.gitignore').write_text('.cache/\n')
    run(tmp_path, 'git', 'add', '.')
    run(tmp_path, 'git', 'commit', '-m', 'synthetic baseline')
    return tmp_path


@pytest.fixture
def cli(workspace, monkeypatch, capsys):
    def invoke(*args):
        monkeypatch.setattr(sys, 'argv', ['repo.py', '--root', str(workspace), *args])
        code = main()
        output = capsys.readouterr()
        return code, json.loads(output.out) if output.out else output.err
    return invoke


def relative(root, path):
    return path.relative_to(root).as_posix()


def handoff(root, task):
    source = complete(root, 'Source', publisher='合成用户', snapshot={
        'path': '.cache/sources/chat.txt', 'sha256': hashlib.sha256(b'raw').hexdigest()})
    doc = read_document(source)
    doc.meta['resource'] = 'https://example.invalid/chat'
    write_document(source, doc.meta, doc.body)
    trace = complete(root, 'ResearchTrace', task=relative(root, task), handoff={
        'target': relative(root, task), 'source': relative(root, source),
        'locator': '用户第 3 轮', 'base': run(root, 'git', 'rev-parse', 'HEAD')})
    doc = read_document(trace)
    write_document(trace, doc.meta, doc.body + '\n\n## 交接入口\n\n保留风险解释，不讨论成本。')
    return trace, source


def test_resume_task_reports_missing_raw_without_writing(workspace, cli):
    task = complete(workspace, 'Task')
    trace, source = handoff(workspace, task)
    before = {relative(workspace, p): p.read_bytes() for p in workspace.rglob('*')
              if p.is_file() and '.git' not in p.parts}
    code, result = cli('status', '--target', relative(workspace, task))
    assert code == 0
    assert result['target'] == relative(workspace, task)
    assert [c['path'] for c in result['handoffs']] == [relative(workspace, trace)]
    assert result['materials'] == [{'path': relative(workspace, source),
                                    'resource': 'https://example.invalid/chat',
                                    'availability': 'missing'}]
    assert result['accepted_base']
    assert result['working_changes']
    assert before == {relative(workspace, p): p.read_bytes() for p in workspace.rglob('*')
                      if p.is_file() and '.git' not in p.parts}


def test_two_deliverables_share_claims_but_keep_outputs_and_review_scope(workspace, cli):
    trace = complete(workspace, 'ResearchTrace')
    claim = complete(workspace, 'Claim', traces=[relative(workspace, trace)])
    claim_id = read_document(claim).meta['research']['id']
    talk = complete(workspace, 'Deliverable', claims=[claim_id])
    report = complete(workspace, 'Deliverable', claims=[claim_id])
    talk_task = complete(workspace, 'Task', deliverable=relative(workspace, talk))
    talk_output = complete(workspace, 'Artifact', deliverable=relative(workspace, talk),
                           claims=[claim_id])
    report_output = complete(workspace, 'Artifact', deliverable=relative(workspace, report),
                             claims=[claim_id])
    code, result = cli('check')
    assert code == 0, result
    code, result = cli('status', '--target', relative(workspace, talk))
    assert code == 0
    assert {relative(workspace, p) for p in (talk_task, talk_output, claim)} <= set(
        result['related'])
    assert relative(workspace, report_output) not in result['related']
    with pytest.raises(ValueError, match='校验'):
        prepare(workspace, [relative(workspace, talk_output)])
    selected = [relative(workspace, p) for p in (trace, claim, talk, talk_task, talk_output)]
    ticket = prepare(workspace, selected)
    commit = accept(workspace, ticket, 'synthetic deliverable', confirmed=True)
    names = run(workspace, 'git', 'show', '--pretty=', '--name-only', commit).splitlines()
    assert set(names) == set(selected)
    assert relative(workspace, report) not in names


@pytest.mark.parametrize('bad_target', ['../outside.md', '/tmp/outside.md'])
def test_resume_rejects_outside_target(workspace, cli, bad_target):
    code, result = cli('status', '--target', bad_target)
    assert code == 1
    assert '路径' in result


def test_handoff_rejects_wrong_scope_and_type_in_check_and_status(workspace, cli):
    task = complete(workspace, 'Task')
    trace, _ = handoff(workspace, task)
    doc = read_document(trace)
    doc.meta['research']['handoff']['target'] = 'knowledge/topic.md'
    write_document(trace, doc.meta, doc.body)
    code, result = cli('check')
    assert code == 1
    assert any('类型错误' in issue['message'] for issue in result['issues'])
    code, result = cli('status', '--target', relative(workspace, trace))
    assert code == 1
    assert '交接' in result


def test_multiple_capsules_are_scoped_and_material_health_is_explicit(workspace, cli):
    task = complete(workspace, 'Task')
    trace, source = handoff(workspace, task)
    other_task = complete(workspace, 'Task')
    other_trace, _ = handoff(workspace, other_task)
    _, result = cli('status', '--target', relative(workspace, task))
    assert relative(workspace, other_trace) not in result['related']
    raw = workspace / '.cache/sources/chat.txt'
    raw.parent.mkdir(parents=True)
    for content, expected in [('raw', 'available'), ('changed', 'corrupt')]:
        raw.write_text(content)
        _, result = cli('status', '--target', relative(workspace, task))
        assert result['materials'][0]['availability'] == expected
    doc = read_document(source)
    del doc.meta['research']['snapshot']
    write_document(source, doc.meta, doc.body)
    _, result = cli('status', '--target', relative(workspace, trace))
    assert result['materials'][0]['availability'] == 'not_cached'


def test_freshness_tracks_only_real_dependencies_without_resetting_basis(workspace, cli):
    trace = complete(workspace, 'ResearchTrace')
    claim = complete(workspace, 'Claim', traces=[relative(workspace, trace)])
    talk = complete(workspace, 'Deliverable',
                    claims=[read_document(claim).meta['research']['id']])
    _, first = cli('status', '--target', relative(workspace, talk))
    assert first['freshness']['state'] == 'unrecorded'
    doc = read_document(talk)
    doc.meta['research']['basis'] = first['freshness']['fingerprints']
    write_document(talk, doc.meta, doc.body)
    run(workspace, 'git', 'commit', '--allow-empty', '-m', 'unrelated revision')
    unrelated = complete(workspace, 'Entity')
    _, current = cli('status', '--target', relative(workspace, talk))
    assert current['freshness']['state'] == 'current'
    assert relative(workspace, unrelated) not in current['freshness']['fingerprints']
    basis = talk.read_bytes()
    with claim.open('a') as stream:
        stream.write('\n新增适用条件\n')
    _, stale = cli('status', '--target', relative(workspace, talk))
    assert stale['freshness']['state'] == 'needs_review'
    assert stale['freshness']['changes'] == [relative(workspace, claim)]
    assert talk.read_bytes() == basis
    code, check = cli('check')
    assert code == 0
    assert any('依赖变化' in i['message'] for i in check['issues'])
    claim.unlink()
    _, missing = cli('status', '--target', relative(workspace, talk))
    assert missing['freshness']['state'] == 'needs_review'
    assert relative(workspace, claim) in missing['freshness']['changes']
    code, _ = cli('check')
    assert code == 1


def test_external_source_labels_remain_valid_and_malformed_dependencies_are_reported(
        workspace, cli):
    event = complete(workspace, 'Event', occurred_at='2026-09-10')
    doc = read_document(event)
    doc.meta['sources'] = [{'id': 'external_label', 'resource': 'https://example.invalid/event'}]
    write_document(event, doc.meta, doc.body)
    code, result = cli('check')
    assert code == 0, result
    trace = complete(workspace, 'ResearchTrace')
    claim = complete(workspace, 'Claim', traces=[relative(workspace, trace)], evidence='invalid')
    complete(workspace, 'Deliverable', claims=[read_document(claim).meta['research']['id']])
    code, result = cli('check')
    assert code == 1
    assert any('evidence' in item['message'] for item in result['issues'])


def test_resume_normalizes_target_and_keeps_unrelated_drafts_nonblocking(workspace, cli):
    task = complete(workspace, 'Task')
    bad = workspace / 'knowledge/sources/unfinished.md'
    bad.parent.mkdir(parents=True)
    bad.write_text('unfinished unrelated braindump')
    code, result = cli('status', '--target', './' + relative(workspace, task))
    assert code == 0, result
    assert result['target'] == relative(workspace, task)
    assert any(i['path'] == relative(workspace, bad) for i in result['record_issues'])


def test_task_resume_includes_delivery_capsule_but_not_sibling_task_capsule(workspace, cli):
    talk = complete(workspace, 'Deliverable')
    task = complete(workspace, 'Task', deliverable=relative(workspace, talk))
    sibling = complete(workspace, 'Task', deliverable=relative(workspace, talk))
    delivery_trace, _ = handoff(workspace, talk)
    doc = read_document(delivery_trace)
    del doc.meta['research']['task']
    write_document(delivery_trace, doc.meta, doc.body)
    sibling_trace, _ = handoff(workspace, sibling)
    code, result = cli('status', '--target', relative(workspace, task))
    assert code == 0, result
    assert relative(workspace, delivery_trace) in {h['path'] for h in result['handoffs']}
    assert relative(workspace, sibling_trace) not in {h['path'] for h in result['handoffs']}


def test_semantic_acceptance_packet_passes_structure_without_accepting_its_claims(workspace, cli):
    shutil.copytree(Path(__file__).parent / 'fixtures/work', workspace, dirs_exist_ok=True)
    code, result = cli('check')
    assert code == 0, result
    _, result = cli('status', '--target', 'tasks/talk.md')
    assert [h['path'] for h in result['handoffs']] == ['traces/current.md']
    assert result['materials'][0]['availability'] == 'not_cached'
    assert 'deliverables/report.md' not in result['related']
    assert read_document(workspace / 'knowledge/claims/saving.md').meta[
        'research']['claim_state'] == 'hypothesis'
    assert read_document(workspace / 'deliverables/talk.md').meta[
        'research']['deliverable_state'] == 'active'


def test_capsule_staleness_follows_target_and_sources_not_git_head(workspace, cli):
    task = complete(workspace, 'Task')
    trace, source = handoff(workspace, task)
    _, result = cli('status', '--target', relative(workspace, trace))
    doc = read_document(trace)
    doc.meta['research']['basis'] = result['freshness']['fingerprints']
    write_document(trace, doc.meta, doc.body)
    run(workspace, 'git', 'commit', '--allow-empty', '-m', 'irrelevant')
    _, result = cli('status', '--target', relative(workspace, trace))
    assert result['freshness']['state'] == 'current'
    with task.open('a') as stream:
        stream.write('\n当前目标已经改变\n')
    with source.open('a') as stream:
        stream.write('\n补充取得的会话范围\n')
    _, result = cli('status', '--target', relative(workspace, trace))
    assert result['freshness']['changes'] == sorted(
        [relative(workspace, task), relative(workspace, source)])


def test_resume_does_not_read_symlinked_unrelated_record(workspace, cli):
    task = complete(workspace, 'Task')
    outside = workspace.parent / 'outside.md'
    outside.write_text('private content must not appear')
    link = workspace / 'tasks/link.md'
    link.symlink_to(outside)
    code, result = cli('status', '--target', relative(workspace, task))
    assert code == 0
    assert result['record_issues']
    assert 'private content' not in json.dumps(result)


def test_completed_deliverable_does_not_accept_claim_and_review_still_binds_bytes(workspace, cli):
    trace = complete(workspace, 'ResearchTrace')
    claim = complete(workspace, 'Claim', traces=[relative(workspace, trace)])
    talk = complete(workspace, 'Deliverable', deliverable_state='done',
                    claims=[read_document(claim).meta['research']['id']])
    code, result = cli('check')
    assert code == 0, result
    assert read_document(claim).meta['research']['claim_state'] == 'hypothesis'
    selected = [relative(workspace, p) for p in (trace, claim, talk)]
    ticket = prepare(workspace, selected)
    with talk.open('a') as stream:
        stream.write('\n变更目标\n')
    with pytest.raises(ValueError, match='变化'):
        accept(workspace, ticket, 'changed deliverable', confirmed=True)
