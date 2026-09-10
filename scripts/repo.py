"""Small local commands used by research skills."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from core import CONTRACT, initialize, scaffold, validate
from operations import build_index, mark_affected, snapshot_source, work_context
from review import accept, git, head, prepare


def main() -> int:
    parser = argparse.ArgumentParser(description='研究仓库的确定性操作')
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='一个研究实例的根目录')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    for key in ('title', 'question', 'scope', 'done'):
        init.add_argument('--' + key, required=True)
    new = commands.add_parser('new')
    new.add_argument('type', choices=CONTRACT['types'])
    new.add_argument('--title', required=True)
    commands.add_parser('check')
    commands.add_parser('index')
    status = commands.add_parser('status')
    status.add_argument('--target', help='需要恢复的 Task、Trace 或 Deliverable 相对路径')
    snap = commands.add_parser('snapshot')
    snap.add_argument('file', type=Path)
    impact = commands.add_parser('impact')
    impact.add_argument('claims', nargs='+')
    review = commands.add_parser('prepare')
    review.add_argument('files', nargs='+')
    commit = commands.add_parser('accept')
    commit.add_argument('ticket')
    commit.add_argument('--message', required=True)
    commit.add_argument('--confirmed', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == 'init':
            result = str(initialize(root, args.title, args.question, args.scope, args.done))
            build_index(root)
        elif args.command == 'new':
            result = {'draft': str(scaffold(root, args.type, args.title)),
                      'note': '已保存草稿；填写正文与元数据后运行 check，尚未入库。'}
        elif args.command == 'check':
            issues = validate(root)
            result = {'ok': not any(i.level == 'error' for i in issues),
                      'issues': [vars(i) for i in issues]}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['ok'] else 1
        elif args.command == 'index':
            build_index(root)
            result = '知识索引已重建（尚未提交）'
        elif args.command == 'snapshot':
            result = snapshot_source(root, args.file.resolve())
        elif args.command == 'impact':
            result = {'needs_review': mark_affected(root, args.claims)}
        elif args.command == 'status':
            result = {'accepted_base': head(root),
                      'working_changes': git(root, 'status', '--short', '--', '.').stdout.decode(),
                      'note': '工作区变化尚未入库；Trace 内容即使已提交仍为过程记录。'}
            if args.target:
                result.update(work_context(root, args.target))
        elif args.command == 'prepare':
            ticket = prepare(root, args.files)
            result = {'ticket': ticket, **json.loads((root / ticket).read_text()),
                      'note': '请展示语义摘要并取得用户确认，再执行 accept。'}
        else:
            result = {'commit': accept(root, args.ticket, args.message, confirmed=args.confirmed)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(f'操作未完成: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
