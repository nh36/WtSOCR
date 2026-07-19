import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_final_ng_batch_reconciliation",
    ROOT / "scripts/check_final_ng_batch_reconciliation.py",
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_glang_batch_reconciles_to_44_plus_2() -> None:
    assert module.validate(ROOT) == []
