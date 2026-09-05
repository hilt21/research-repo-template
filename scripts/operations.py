"""Mechanical indexes, snapshots and explicit dependency traversal."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from core import document_paths, read_document, snapshot_path, write_document


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
