"""Bind review to an exact Git tree; never include unrelated staged work.

The confirmation flag represents an approval obtained by the agent, not an
authentication mechanism. Users can still operate Git directly.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import yaml
from core import AREAS, confined, document_paths, read_document, snapshot_path, validate


def git(root: Path, *args: str, env=None, input=None, check=True):
    result = subprocess.run(['git', '--literal-pathspecs', '-C', str(root), *args], input=input,
                            capture_output=True, env=env)
    if check and result.returncode:
        raise ValueError(result.stderr.decode(errors='replace').strip())
    return result


def head(root: Path) -> str | None:
    result = git(root, 'rev-parse', '--verify', 'HEAD', check=False)
    return result.stdout.decode().strip() if result.returncode == 0 else None


def repository(root: Path) -> tuple[Path, str]:
    parent = Path(git(root, 'rev-parse', '--show-toplevel').stdout.decode().strip())
    relative = root.resolve().relative_to(parent.resolve()).as_posix()
    return parent, '' if relative == '.' else relative + '/'


def normalized_paths(root: Path, paths: list[str]) -> list[str]:
    if not paths:
        raise ValueError('提交范围不能为空')
    output = []
    for value in paths:
        path = confined(root, value)
        relative = path.relative_to(root).as_posix()
        if '..' in Path(value).parts or Path(value).is_absolute():
            raise ValueError('提交范围必须使用实例内相对路径')
        if relative != 'research.yaml' and Path(relative).parts[0] not in AREAS:
            raise ValueError(f'不是研究文件: {value}')
        if path.is_dir() or path.is_symlink():
            raise ValueError('请逐个指定普通文件，不能提交目录或符号链接')
        output.append(relative)
    return sorted(set(output))


def file_digests(root: Path, paths: list[str]) -> dict[str, str | None]:
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            if (root / p).exists() else None for p in paths}


def build_tree(root: Path, paths: list[str], base: str | None) -> str:
    parent, prefix = repository(root)
    with tempfile.TemporaryDirectory(prefix='research-index-') as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / 'index'))
        git(parent, 'read-tree', base or '--empty', env=env)
        git(parent, 'add', '-A', '--', *(prefix + p for p in paths), env=env)
        return git(parent, 'write-tree', env=env).stdout.decode().strip()


def validate_tree(root: Path, tree: str) -> list[dict]:
    parent, prefix = repository(root)
    with tempfile.TemporaryDirectory(prefix='research-check-') as temp:
        snapshot = Path(temp)
        scopes = [prefix + 'research.yaml', *(prefix + a for a in AREAS)]
        entries = git(parent, 'ls-tree', '-r', '-z', tree, '--', *scopes).stdout
        for entry in entries.split(b'\0'):
            if not entry:
                continue
            info, name = entry.split(b'\t', 1)
            mode, kind, oid = info.split()
            if kind != b'blob' or mode not in (b'100644', b'100755'):
                raise ValueError('研究树只能包含普通文件')
            relative = name.decode()[len(prefix):]
            target = confined(snapshot, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git(parent, 'cat-file', 'blob', oid.decode()).stdout)
        # A cache is not committed. Copy only snapshots referenced by candidate records.
        for path in document_paths(snapshot):
            try:
                doc = read_document(path)
                research = doc.meta.get('research')
                record = research.get('snapshot') if isinstance(research, dict) else None
                if isinstance(record, dict) and isinstance(record.get('path'), str):
                    source = snapshot_path(root, record['path'])
                    target = snapshot_path(snapshot, record['path'])
                    if source.is_file():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, target)
            except (ValueError, TypeError, yaml.YAMLError):
                # Invalid documents are diagnosed by the validator below.
                continue
        issues = validate(snapshot)
        failures = [i for i in issues if i.level == 'error']
        if failures:
            raise ValueError('候选提交校验失败:\n' + '\n'.join(
                f'{i.path}: {i.message}' for i in failures))
        return [vars(i) for i in issues]


def prepare(root: Path, paths: list[str]) -> str:
    paths = normalized_paths(root, paths)
    base = head(root)
    digests = file_digests(root, paths)
    tree = build_tree(root, paths, base)
    warnings = validate_tree(root, tree)
    if digests != file_digests(root, paths) or head(root) != base:
        raise ValueError('准备期间内容发生变化，请重新准备')
    receipt = {'base': base, 'tree': tree, 'paths': paths, 'digests': digests,
               'warnings': warnings}
    ticket = '.cache/reviews/' + uuid.uuid4().hex + '.json'
    target = confined(root, ticket)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return ticket


def accept(root: Path, ticket: str, message: str, *, confirmed: bool = False) -> str:
    if not confirmed:
        raise ValueError('必须先获得用户对具体变更的确认')
    receipt = json.loads(confined(root, ticket).read_text())
    paths = normalized_paths(root, receipt['paths'])
    if head(root) != receipt['base'] or file_digests(root, paths) != receipt['digests']:
        raise ValueError('已审阅内容或基线发生变化，请重新准备并审阅')
    tree = build_tree(root, paths, receipt['base'])
    if tree != receipt['tree']:
        raise ValueError('实际提交内容发生变化，请重新审阅')
    validate_tree(root, tree)
    parent, prefix = repository(root)
    args = ['commit-tree', tree]
    if receipt['base']:
        args += ['-p', receipt['base']]
    commit = git(parent, *args, '-F', '-', input=message.encode()).stdout.decode().strip()
    # Compare-and-swap prevents overwriting a concurrently advanced branch.
    git(parent, 'update-ref', 'HEAD', commit, receipt['base'] or '0' * 40)
    cleanup = git(parent, 'reset', '-q', 'HEAD', '--', *(prefix + p for p in paths), check=False)
    if cleanup.returncode:
        raise ValueError(f'已提交 {commit}，但暂存区更新失败: {cleanup.stderr.decode()}')
    return commit
