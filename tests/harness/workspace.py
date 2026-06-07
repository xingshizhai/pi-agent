"""Temporary workspace management for test scenarios."""
import shutil
import tempfile
from pathlib import Path


class Workspace:
    def __init__(self):
        self._dir = Path(tempfile.mkdtemp(prefix="pi-test-"))

    @property
    def dir(self) -> str:
        return str(self._dir)

    def setup(self, files: list[dict]):
        """Create workspace files. Each dict: {path, content}."""
        for f in files:
            p = self._dir / f["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f["content"], encoding="utf-8")

    def read(self, path: str) -> str:
        return (self._dir / path).read_text(encoding="utf-8")

    def exists(self, path: str) -> bool:
        return (self._dir / path).exists()

    def snapshot(self) -> dict[str, str]:
        """Return {relative_path: content} for all files in workspace."""
        result = {}
        for p in self._dir.rglob("*"):
            if p.is_file():
                key = str(p.relative_to(self._dir)).replace("\\", "/")
                result[key] = p.read_text(encoding="utf-8")
        return result

    def cleanup(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()
