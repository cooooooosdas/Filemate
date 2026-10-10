"""跨平台执行同一静态迁移检查器，不运行Linux部署或迁移模块。"""

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

source = Path(__file__).resolve().parents[2] / 'scripts/deploy_existing.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
functions = {'migration_contract', 'migration_signature', 'check_migration_upgrade'}
namespace = {'ast': ast, 'hashlib': hashlib, 'json': json, 'Path': Path}
# 只加载仓库受信检查器，不执行候选迁移文件的顶层代码。
exec(compile(ast.Module(body=[node for node in tree.body  # noqa: S102
                             if isinstance(node, ast.FunctionDef) and node.name in functions],
                        type_ignores=[]), str(source), 'exec'), namespace)
deploy = SimpleNamespace(**{name: namespace[name] for name in functions})


def test_actual_current_migration_contract_allows_v26_append(tmp_path) -> None:
    storage = Path(__file__).resolve().parents[2] / 'filemate/execution/storage.py'
    contract = deploy.migration_contract(storage)
    assert contract[-1][0] == 26 and contract[-1][1] == 'confirmed_data_actions'
    assert 'CREATE TABLE' in contract[-1][2]
    old = tmp_path / 'released.py'
    old.write_text('_MIGRATIONS = ' + repr(tuple(contract[:-1])), encoding='utf-8')
    deploy.check_migration_upgrade(old, storage)


def test_imported_sql_is_not_executed_and_changed_contract_is_rejected(tmp_path) -> None:
    package = tmp_path / 'filemate/execution'
    package.mkdir(parents=True)
    storage = package / 'storage.py'
    storage.write_text('from filemate.execution import extra\n_MIGRATIONS = ((1, "old", extra.SCHEMA),)', encoding='utf-8')
    module = package / 'extra.py'
    module.write_text('SCHEMA = "CREATE TABLE x(a INT)"\nraise RuntimeError("must not execute")', encoding='utf-8')
    old = tmp_path / 'old.py'
    old.write_text('_MIGRATIONS = ((1, "old", "CREATE TABLE x(a INT)"),)', encoding='utf-8')
    deploy.check_migration_upgrade(old, storage)
    module.write_text('SCHEMA = "CREATE TABLE x(a TEXT)"', encoding='utf-8')
    with pytest.raises(AssertionError, match='改写'):
        deploy.check_migration_upgrade(old, storage)
