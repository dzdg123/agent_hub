"""模拟完全未安装 vector 扩展的新进程，不依赖真实模型或下载。"""

from pathlib import Path
import subprocess
import sys


def test_retrieval_import_is_lazy_and_missing_vector_dependencies_are_explained():
    source_root = Path(__file__).resolve().parents[1] / "src"
    code = r'''
import importlib.abc
import sys

sys.path.insert(0, sys.argv[1])
attempted = []
blocked = {"chromadb", "sentence_transformers", "transformers", "torch", "huggingface_hub"}

class NoVector(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            attempted.append(fullname)
            raise ModuleNotFoundError("simulated missing optional dependency", name=fullname)

sys.meta_path.insert(0, NoVector())
from research_agent.retrieval import HybridIndex, ChromaIndex
from research_agent.embeddings import SentenceTransformerEmbedder
assert attempted == [], attempted
assert HybridIndex().search("问题") == []
assert not (blocked & set(sys.modules)), blocked & set(sys.modules)
for construct in (lambda: ChromaIndex("unused-no-database"), SentenceTransformerEmbedder):
    try:
        construct()
    except RuntimeError as exc:
        assert ".[vector]" in str(exc), str(exc)
        assert isinstance(exc.__cause__, ModuleNotFoundError)
    else:
        raise AssertionError("missing vector dependency should fail explicitly")
print("IMPORT AND MISSING-DEPENDENCY CHECK PASSED")
'''
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(source_root)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CHECK PASSED" in result.stdout
