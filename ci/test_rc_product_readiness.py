import importlib.util
from pathlib import Path

PATH = Path(__file__).with_name("check_rc_product_readiness.py")
SPEC = importlib.util.spec_from_file_location("rc_readiness", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_rc_product_readiness_contracts():
    assert MODULE.main() == 0
