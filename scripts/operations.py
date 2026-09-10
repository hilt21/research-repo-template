"""Mechanical indexes, snapshots and explicit dependency traversal."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import yaml
from core import (
    CONTRACT,
    confined,
    dependency_state,
    document_paths,
    read_document,
    schema_errors,
    snapshot_path,
    write_document,
)


def work_context(root: Path, target: str) -> dict:
    """Return scoped navigation and material health without reading raw content or writing."""
    path = confined(root, target)
    if Path(target).is_absolute() or '..' in Path(target).parts:
        raise ValueError('工作目标必须使用实例内相对路径')
    target = path.relative_to(root).as_posix()
    paths = document_paths(root)
    if path not in paths or path.is_symlink():
        raise ValueError('工作目标必须是实例内研究记录')
    docs, record_issues = {}, []
    for p in paths:
        try:
            confined(root, p.relative_to(root).as_posix())
            if p.is_symlink():
                raise ValueError('研究记录不能使用符号链接')
            doc = read_document(p)
            failures = schema_errors(CONTRACT['common'], doc.meta)
            if not failures:
                failures = schema_errors(CONTRACT['types'][doc.meta['type']]['schema'], doc.meta)
            if failures:
                raise ValueError('; '.join(failures))
            if 'handoff' in doc.meta['research'] and doc.meta['type'] != 'ResearchTrace':
                raise ValueError('交接入口必须位于 ResearchTrace')
            docs[p] = doc
        except (ValueError, OSError, yaml.YAMLError) as exc:
            record_issues.append({'path': p.relative_to(root).as_posix(), 'message': str(exc)})
    if path not in docs:
        raise ValueError(f'工作目标无效: {target}; {record_issues}')
    selected = docs[path]
    if selected.meta['type'] not in ('Task', 'ResearchTrace', 'Deliverable'):
        raise ValueError('工作目标必须是 Task、ResearchTrace 或 Deliverable')
    scope = selected.meta['research'].get('handoff', {}).get('target', target)
    handoffs = []
    materials = []
    related = {path}
    related.add(confined(root, scope))
    if selected.meta['type'] == 'Deliverable':
        related.update(p for p, d in docs.items()
                       if d.meta['research'].get('deliverable') == target)
    # A task inherits delivery-level decisions, but never a sibling task's capsule.
    for p in list(related):
        if p in docs and docs[p].meta['research'].get('deliverable'):
            related.add(confined(root, docs[p].meta['research']['deliverable']))
    scopes = {p.relative_to(root).as_posix() for p in related}
    for p, doc in docs.items():
        record = doc.meta['research'].get('handoff')
        if not record:
            continue
        try:
            record_target = confined(root, record['target'])
        except ValueError as exc:
            record_issues.append({'path': p.relative_to(root).as_posix(), 'message': str(exc)})
            continue
        if record_target.relative_to(root).as_posix() not in scopes:
            continue
        scoped_target = docs.get(record_target)
        if (doc.meta['type'] != 'ResearchTrace' or scoped_target is None
                or scoped_target.meta['type'] not in ('Task', 'Deliverable')
                or (doc.meta['research'].get('task')
                    and doc.meta['research']['task'] != record['target'])
                or not doc.sections.get('交接入口')):
            raise ValueError(f'交接范围或内容无效: {p.relative_to(root)}')
        related.add(p)
        source_path = confined(root, record['source'])
        source = docs.get(source_path)
        if source is None or source.meta['type'] != 'Source':
            raise ValueError(f'交接原文 Source 不存在: {record["source"]}')
        related.add(source_path)
        handoffs.append({'path': p.relative_to(root).as_posix(), **record,
                         'saved_at': doc.meta['research']['saved_at']})
    by_id = {d.meta['research']['id']: p for p, d in docs.items()}
    pending = list(related)
    while pending:
        p = pending.pop()
        if p not in docs:
            continue
        research = docs[p].meta['research']
        references = [confined(root, v) for v in research.get('traces', [])]
        references += [confined(root, v) for v in dependency_state(
            root, docs[p], docs)['fingerprints']]
        references += [confined(root, research[k]) for k in ('task', 'deliverable')
                       if research.get(k)]
        for ident in research.get('claims', []) + research.get('inspected_sources', []):
            if ident not in by_id:
                continue  # dependency_state reports missing IDs without losing the work entry.
            references.append(by_id[ident])
        for ref in references:
            if ref not in related:
                related.add(ref)
                pending.append(ref)
    reviews = {}
    for p in sorted(related):
        if p not in docs:
            continue
        doc = docs[p]
        relative = p.relative_to(root).as_posix()
        reviews[relative] = dependency_state(root, doc, docs)
        if doc.meta['type'] != 'Source':
            continue
        material = {'path': relative, 'resource': doc.meta['resource']}
        snapshot = doc.meta['research'].get('snapshot')
        if snapshot is None:
            material['availability'] = 'not_cached'
        else:
            raw = snapshot_path(root, snapshot['path'])
            material['availability'] = (
                'missing' if not raw.is_file() else
                'available' if hashlib.sha256(raw.read_bytes()).hexdigest() == snapshot['sha256']
                else 'corrupt')
        materials.append(material)
    return {'target': target, 'related': sorted(p.relative_to(root).as_posix() for p in related),
            'handoffs': handoffs, 'materials': materials,
            'freshness': reviews.pop(target), 'related_freshness': reviews,
            'record_issues': record_issues}


def snapshot_source(root: Path, source: Path) -> dict[str, str]:
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    relative = f'.cache/sources/{digest}{source.suffix.lower()}'
    target = snapshot_path(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise ValueError('缓存内容已改变，不能覆盖已有快照')
    else:
        shutil.copyfile(source, target)
    return {'path': relative, 'sha256': digest}


def build_index(root: Path) -> None:
    lines = ["---", "okf_version: '0.2'", "---", '', '# 知识索引', '']
    groups = {}
    for path in document_paths(root):
        if not path.is_relative_to(root / 'knowledge'):
            continue
        doc = read_document(path)
        title = doc.meta['title'].replace('[', '\\[').replace(']', '\\]')
        link = path.relative_to(root / 'knowledge').as_posix()
        groups.setdefault(doc.meta['type'], []).append(f'- [{title}]({link})')
    for kind, entries in sorted(groups.items()):
        lines.extend([f'## {kind}', '', *sorted(entries), ''])
    (root / 'knowledge').mkdir(exist_ok=True)
    (root / 'knowledge/index.md').write_text('\n'.join(lines) + '\n')


def mark_affected(root: Path, claims: list[str]) -> list[str]:
    changed = []
    for path in sorted((root / 'artifacts').rglob('*.md')):
        doc = read_document(path)
        if set(doc.meta['research'].get('claims', [])) & set(claims):
            doc.meta['research']['review_state'] = 'needs_review'
            write_document(path, doc.meta, doc.body)
            changed.append(path.relative_to(root).as_posix())
    return changed
