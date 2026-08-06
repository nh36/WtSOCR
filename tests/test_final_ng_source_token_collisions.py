from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location(
    "check_final_ng_source_token_collisions",
    ROOT / "scripts/check_final_ng_source_token_collisions.py",
)
assert SPEC and SPEC.loader
module = module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_final_ng_source_token_collision_controls_pass() -> None:
    assert module.validate(ROOT) == []
