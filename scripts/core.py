"""File contracts and structural validation; no semantic judgments."""

from __future__ import annotations

import copy
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from markdown_it import MarkdownIt

BASE = Path(__file__).resolve().parent.parent
AREAS = ('knowledge', 'traces', 'tasks', 'artifacts')
MARKDOWN = MarkdownIt('commonmark')


class StrictLoader(yaml.SafeLoader):
    """Keep timestamps as strings and reject ambiguous duplicate keys."""


StrictLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for key, values in StrictLoader.yaml_implicit_resolvers.items():
    StrictLoader.yaml_implicit_resolvers[key] = [
        v for v in values if v[0] != 'tag:yaml.org,2002:timestamp'
    ]


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ValueError('YAML 映射键必须是字符串')
        if key in result:
            raise ValueError(f'重复 YAML 字段: {key}')
        result[key] = loader.construct_object(value_node)
    return result


StrictLoader.add_constructor('tag:yaml.org,2002:map', _mapping)


def load_yaml(text: str):
    return yaml.load(text, Loader=StrictLoader)


CONTRACT = load_yaml((BASE / 'schemas/objects.yaml').read_text())


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def confined(root: Path, value: str) -> Path:
    path = root / value
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'路径超出研究实例: {value}')
    return path


def snapshot_path(root: Path, value: str) -> Path:
    path = confined(root, value)
    if ('..' in Path(value).parts or Path(value).is_absolute()
            or not path.resolve().is_relative_to((root / '.cache/sources').resolve())):
        raise ValueError(f'快照路径必须位于 .cache/sources: {value}')
    return path


@dataclass
class Document:
    path: Path
    meta: dict
    body: str
    sections: dict[str, str]


@dataclass
class Issue:
    level: str
    path: str
    message: str


def sections(body: str) -> dict[str, str]:
    result = {}
    tokens = MARKDOWN.parse(body)
    lines = body.splitlines()
    for i, token in enumerate(tokens):
        if token.type != 'heading_open' or token.tag != 'h2':
            continue
        start = token.map[1]
        end = len(lines)
        for next_token in tokens[i + 1:]:
            if next_token.type == 'heading_open' and next_token.tag in ('h1', 'h2'):
                end = next_token.map[0]
                break
        result[tokens[i + 1].content] = '\n'.join(lines[start:end]).strip()
    return result


def read_document(path: Path) -> Document:
    text = path.read_text(encoding='utf-8')
    match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', text, re.S)
    if not match:
        raise ValueError('缺少 YAML frontmatter')
    meta = load_yaml(match[1])
    if not isinstance(meta, dict):
        raise ValueError('frontmatter 必须是映射')
    body = text[match.end():].strip()
    return Document(path, meta, body, sections(body))


def write_document(path: Path, meta: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    text += '---\n\n' + body.strip() + '\n'
    # Replace only after the entire text is available. Never truncate an existing record.
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def document_paths(root: Path) -> list[Path]:
    return sorted(p for area in AREAS for p in (root / area).rglob('*.md')
                  if not (p.is_relative_to(root / 'knowledge')
                          and p.name in ('index.md', 'log.md')))


def scaffold(root: Path, kind: str, title: str) -> Path:
    if kind not in CONTRACT['types']:
        raise ValueError(f'未知对象类型: {kind}')
    template = read_document(BASE / 'templates' / f'{kind}.md')
    meta = copy.deepcopy(template.meta)
    meta['title'] = title
    meta['research']['id'] = f'{kind.lower()}_{uuid.uuid4().hex[:16]}'
    for key in ('retrieved_at', 'saved_at'):
        if key in meta['research']:
            meta['research'][key] = now()
    directory = CONTRACT['types'][kind]['directory']
    filename = 'topic.md' if kind == 'Topic' else meta['research']['id'] + '.md'
    path = confined(root, f'{directory}/{filename}')
    if path.exists():
        raise ValueError(f'文件已存在: {path}')
    write_document(path, meta, template.body)
    return path


def initialize(root: Path, title: str, question: str, scope: str, done: str) -> Path:
    if (root / 'research.yaml').exists():
        config = load_yaml((root / 'research.yaml').read_text())
        if config.get('initialized'):
            raise ValueError('课题已初始化，不能覆盖')
    root.mkdir(parents=True, exist_ok=True)
    path = scaffold(root, 'Topic', title)
    doc = read_document(path)
    body = f'## 研究问题\n\n{question}\n\n## 范围\n\n{scope}\n\n## 完成标准\n\n{done}'
    write_document(path, doc.meta, body)
    for area in AREAS:
        (root / area).mkdir(exist_ok=True)
    (root / 'research.yaml').write_text(yaml.safe_dump({
        'protocol_version': '0.1', 'initialized': True,
        'topic': 'knowledge/topic.md', 'language': 'zh-CN',
    }, sort_keys=False))
    return path


def schema_errors(schema: dict, value) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f'{".".join(map(str, e.path))}: {e.message}' for e in validator.iter_errors(value)]


def resolve_link(root: Path, document: Path, target: str) -> Path | None:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    value = unquote(parsed.path)
    if not value:
        return document
    if value.startswith('/'):
        base = root / 'knowledge' if document.is_relative_to(root / 'knowledge') else root
        return confined(root, str((base / value.lstrip('/')).relative_to(root))).resolve()
    return confined(root, str((document.parent / value).relative_to(root))).resolve()


def markdown_links(body: str) -> list[str]:
    found = []
    for token in MARKDOWN.parse(body):
        for child in token.children or []:
            if child.type == 'link_open':
                found.append(child.attrGet('href'))
            elif child.type == 'image':
                found.append(child.attrGet('src'))
    return found


def validate(root: Path) -> list[Issue]:
    root = root.resolve()
    issues = []

    def add(path, message, level='error'):
        issues.append(Issue(level, str(Path(path).relative_to(root)), message))

    config_path = root / 'research.yaml'
    try:
        config = load_yaml(config_path.read_text())
        failures = schema_errors(CONTRACT['config'], config)
        for message in failures:
            add(config_path, message)
        if failures:
            return issues
    except (OSError, ValueError, yaml.YAMLError) as exc:
        add(config_path, str(exc))
        return issues

    docs = {}
    by_id = {}
    for path in sorted((root / 'knowledge').rglob('*.md')):
        if path.name not in ('index.md', 'log.md'):
            continue
        try:
            confined(root, str(path.relative_to(root)))
            if path.is_symlink():
                raise ValueError('保留文件不能使用符号链接')
            body = path.read_text(encoding='utf-8')
            if body.startswith('---\n'):
                reserved = read_document(path)
                if 'type' in reserved.meta or 'research' in reserved.meta:
                    add(path, '保留文件不能承载研究对象，请使用普通文件名')
                body = reserved.body
            for target in markdown_links(body):
                resolved = resolve_link(root, path, target)
                if resolved is not None and not resolved.exists():
                    add(path, f'引用不存在: {target}')
        except (OSError, ValueError, yaml.YAMLError) as exc:
            add(path, str(exc))
    for path in document_paths(root):
        try:
            confined(root, str(path.relative_to(root)))
            if path.is_symlink():
                raise ValueError('研究记录不能使用符号链接')
            doc = read_document(path)
            failures = schema_errors(CONTRACT['common'], doc.meta)
            for message in failures:
                add(path, message)
            if failures:
                continue
            kind = doc.meta['type']
            rules = CONTRACT['types'][kind]
            for message in schema_errors(rules['schema'], doc.meta):
                add(path, message)
            expected = root / rules['directory']
            if path.parent != expected:
                add(path, f'{kind} 必须位于 {rules["directory"]}')
            for heading in rules['sections']:
                if not doc.sections.get(heading, '').strip():
                    add(path, f'缺少非空章节: {heading}')
            ident = doc.meta['research']['id']
            if ident in by_id:
                add(path, f'重复 ID: {ident}')
            by_id[ident] = doc
            docs[path] = doc
        except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
            add(path, str(exc))

    topics = [d for d in docs.values() if d.meta['type'] == 'Topic']
    if config['initialized']:
        if len(topics) != 1 or config['topic'] != 'knowledge/topic.md':
            add(config_path, '已初始化实例必须有一个 knowledge/topic.md Topic')
        elif topics[0].path != root / 'knowledge/topic.md':
            add(config_path, 'Topic 路径不匹配')
    elif docs or config['topic'] is not None:
        add(config_path, '未初始化模板不能包含研究条目')

    used_sources = set()
    for path, doc in docs.items():
        meta, research = doc.meta, doc.meta['research']
        # Skip secondary checks on malformed per-type data, preserving primary errors.
        if schema_errors(CONTRACT['types'][meta['type']]['schema'], meta):
            continue
        targets = markdown_links(doc.body)
        if meta['type'] == 'Source':
            targets.append(meta['resource'])
        source_map = {}
        for source in meta.get('sources', []):
            if source['id'] in source_map:
                add(path, '重复来源引用 ID')
            try:
                source_map[source['id']] = resolve_link(root, path, source['resource'])
            except ValueError as exc:
                add(path, str(exc))
            targets.append(source['resource'])
        for target in targets:
            try:
                resolved = resolve_link(root, path, target)
                if resolved is not None and not resolved.exists():
                    add(path, f'引用不存在: {target}')
            except ValueError as exc:
                add(path, str(exc))
        for key, kind in (('traces', 'ResearchTrace'),):
            for relative in research.get(key, []):
                try:
                    target = confined(root, relative)
                    if target not in docs or docs[target].meta['type'] != kind:
                        add(path, f'引用不存在或类型不匹配: {relative}')
                except ValueError as exc:
                    add(path, str(exc))
        if research.get('task'):
            try:
                target = confined(root, research['task'])
                if target not in docs or docs[target].meta['type'] != 'Task':
                    add(path, 'Task 引用不存在或类型错误')
            except ValueError as exc:
                add(path, str(exc))
        for relative in research.get('proposed_changes', []):
            try:
                confined(root, relative)
            except ValueError as exc:
                add(path, str(exc))
        for ident in research.get('claims', []) + research.get('inspected_sources', []):
            kind = 'Claim' if ident in research.get('claims', []) else 'Source'
            if ident not in by_id or by_id[ident].meta['type'] != kind:
                add(path, f'{kind} 引用不存在: {ident}')
        if meta['type'] == 'Claim':
            evidence = research.get('evidence', [])
            roles = {entry['role'] for entry in evidence}
            state = research['claim_state']
            if state == 'supported' and 'supports' not in roles:
                add(path, 'supported 必须具有带定位的支持证据')
            if state == 'contested' and not {'supports', 'challenges'} <= roles:
                add(path, 'contested 必须保留支持与挑战证据')
            for entry in evidence:
                source = by_id.get(entry['source_id'])
                if source is None or source.meta['type'] != 'Source':
                    add(path, f'证据来源不存在: {entry["source_id"]}')
                elif source_map.get(entry['source_id']) != source.path:
                    add(path, f'证据与 OKF sources 未对应: {entry["source_id"]}')
                used_sources.add(entry['source_id'])
            if state in ('hypothesis', 'contested'):
                add(path, f'研究状态: {state}', 'warning')
        if meta['type'] == 'Relation':
            for key in ('from', 'to'):
                target = by_id.get(research[key])
                if target is None or target.meta['type'] != 'Entity':
                    add(path, f'Relation {key} 必须指向 Entity')
            if not meta.get('sources') and not research.get('claims'):
                add(path, 'Relation 必须关联来源或 Claim')
        if meta['type'] == 'Task' and research['task_state'] == 'blocked':
            if not doc.sections.get('阻塞原因'):
                add(path, 'blocked Task 缺少阻塞原因')
        if meta['type'] == 'Artifact' and research['review_state'] == 'needs_review':
            add(path, '输出待复核', 'warning')
        if meta['type'] == 'Source' and 'snapshot' not in research:
            add(path, '未保存本地快照，无法本地核验原文', 'warning')
        if meta['type'] == 'Source' and 'snapshot' in research:
            snapshot = research['snapshot']
            try:
                target = snapshot_path(root, snapshot['path'])
                if not target.exists():
                    add(path, '本地快照缺失，未核验原文', 'warning')
                elif hashlib.sha256(target.read_bytes()).hexdigest() != snapshot['sha256']:
                    add(path, '快照哈希不匹配')
            except (ValueError, OSError) as exc:
                add(path, str(exc))
    for path, doc in docs.items():
        if doc.meta['type'] == 'Source' and doc.meta['research']['id'] not in used_sources:
            add(path, '来源尚未被 Claim 使用', 'warning')
    return issues
