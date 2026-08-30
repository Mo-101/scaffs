"""Every ``self.X(...)`` call must resolve to something that exists.

This class of bug has bitten twice in one day on the dispatch path, both
times silently until a live order hit the code:

  - ``BinanceTestnetStateProvider.positions`` was indented out of its class,
    so ``exchange.positions()`` raised AttributeError and the Step 4 gate
    reported EXCHANGE_STATE_UNAVAILABLE for 43 signals.
  - ``_record_criteria`` was defined as a nested function inside
    ``dispatch_queued_signal`` but called as ``self._record_criteria(...)``,
    so auto-execute died with "'SignalQueueManager' object has no attribute
    '_record_criteria'" the first time a symbol was rejected.

Neither was caught by the suite, because the tests that exercise dispatch
need a live Postgres and are skipped/failing in CI. A static check needs no
database and catches the whole class in every method, including branches that
only run on a rejection path.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

agent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_dir))
sys.path.insert(0, str(agent_dir / "src"))


def _assigned_instance_attrs(class_node: ast.ClassDef) -> set[str]:
    """Names bound via ``self.X = ...`` anywhere in the class body."""
    found: set[str] = set()
    for node in ast.walk(class_node):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if (
                    isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"
                ):
                    found.add(t.attr)
    return found


def _self_attribute_uses(class_node: ast.ClassDef) -> set[str]:
    return {
        node.attr
        for node in ast.walk(class_node)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    }


def _check(module, class_name: str) -> list[str]:
    tree = ast.parse(inspect.getsource(module))
    cls_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name),
        None,
    )
    assert cls_node is not None, f"{class_name} not found in {module.__name__}"

    cls = getattr(module, class_name)
    known = set(dir(cls)) | _assigned_instance_attrs(cls_node)
    return sorted(name for name in _self_attribute_uses(cls_node) if name not in known)


@pytest.mark.parametrize(
    "module_path,class_name",
    [
        ("src.trading.signal_queue", "SignalQueueManager"),
        ("src.trading.connectors.binance.binance_testnet_executor", "BinanceTestnetExecutor"),
        ("src.trading.position.position_reconciler", "PositionReconciler"),
        ("src.trading.position.position_risk_resolver", "PositionRiskResolver"),
    ],
)
def test_no_unresolvable_self_attributes(module_path, class_name):
    module = __import__(module_path, fromlist=[class_name])
    unresolved = _check(module, class_name)
    assert not unresolved, (
        f"{class_name} uses self.{{{', '.join(unresolved)}}} but no such attribute or method "
        f"exists -- a nested function called as a method, or a method indented out of its class"
    )


def test_the_check_actually_catches_the_bug():
    """Guard the guard: the detector must fail on the real defect shape."""
    source = (
        "class Thing:\n"
        "    def run(self):\n"
        "        def helper():\n"
        "            return 1\n"
        "        return self.helper()\n"
    )
    namespace: dict = {}
    exec(compile(source, "<test>", "exec"), namespace)
    tree = ast.parse(source)
    cls_node = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    cls = namespace["Thing"]
    known = set(dir(cls)) | _assigned_instance_attrs(cls_node)
    unresolved = [n for n in _self_attribute_uses(cls_node) if n not in known]
    assert unresolved == ["helper"]
