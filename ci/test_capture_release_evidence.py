import importlib.util
from pathlib import Path

PATH = Path(__file__).with_name('capture_release_evidence.py')
spec = importlib.util.spec_from_file_location('capture_release_evidence', PATH)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

def test_sha256(tmp_path):
    path = tmp_path / 'backup.dump'; path.write_bytes(b'release-evidence')
    assert module.sha256(path) == 'c614426d3275f5c86e8926536ed0c24fc37d8044ea5dafc3f6be80e51657f6a7'
