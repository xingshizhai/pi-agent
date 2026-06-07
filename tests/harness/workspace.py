import tempfile, shutil
from pathlib import Path

class Workspace:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="pi-test-")

    def setup(self, files: list[dict]):
        """Create files in the workspace. Each dict: {path, content}."""
        for f in files:
            p = Path(self.dir) / f["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f["content"], encoding="utf-8")

    def read(self, path: str) -> str:
        return (Path(self.dir) / path).read_text(encoding="utf-8")

    def exists(self, path: str) -> bool:
        return (Path(self.dir) / path).exists()

    def snapshot(self) -> dict[str, str]:
        """Return {relative_path: content} for all files."""
        result = {}
        for p in Path(self.dir).rglob("*"):
            if p.is_file():
                result[str(p.relative_to(self.dir))] = p.read_text(encoding="utf-8")
        return result

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def __enter__(self): return self
    def __exit__(self, *_): self.cleanup()
