"""Exercise initialization and invalid candidate reporting through the CLI."""
import json
import sys

from repo import main


def test_cli_initialization_and_invalid_draft(tmp_path, monkeypatch, capsys):
    def cli(*args):
        monkeypatch.setattr(sys, 'argv', ['repo.py', '--root', str(tmp_path), *args])
        result = main()
        output = capsys.readouterr()
        return result, output
    result, _ = cli('init', '--title', 'Topic', '--question', 'Question',
                    '--scope', 'Scope', '--done', 'Done')
    assert result == 0
    result, output = cli('check')
    assert result == 0 and json.loads(output.out)['ok']
    result, output = cli('new', 'Claim', '--title', 'Draft')
    assert result == 0 and 'draft' in json.loads(output.out)
    result, output = cli('check')
    assert result == 1 and not json.loads(output.out)['ok']
    result, _ = cli('index')
    assert result == 0
    result, output = cli('init', '--title', 'Other', '--question', 'Question',
                        '--scope', 'Scope', '--done', 'Done')
    assert result == 1 and '已初始化' in output.err
