import importlib.util
from pathlib import Path

PATH = Path(__file__).with_name("capture_release_evidence.py")
spec = importlib.util.spec_from_file_location("capture_release_evidence", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_sha256(tmp_path):
    path = tmp_path / "backup.dump"
    path.write_bytes(b"release-evidence")
    assert (
        module.sha256(path)
        == "86d2013e196c2988bd1058ee04da96a95ff8dc094d511295329b207e74eb88b6"
    )
