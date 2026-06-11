import json
import os
import tempfile
from pathlib import Path


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    path = Path(path)
    ensure_parent(path)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        finally:
            raise


def atomic_write_text(path: Path | str, data: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, data.encode(encoding))


def atomic_write_json(path: Path | str, data: object) -> None:
    atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
