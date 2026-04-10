from __future__ import annotations

from pathlib import Path


class FileService:
    def __init__(self, root: Path) -> None:
        self.root = root

    def list_files(self) -> list[dict[str, object]]:
        if not self.root.exists():
            return []

        items: list[dict[str, object]] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(self.root).as_posix()
            items.append(
                {
                    "name": path.name,
                    "relative_path": relative_path,
                    "size_bytes": path.stat().st_size,
                }
            )
        return items

    def resolve_file(self, relative_path: str) -> Path | None:
        if not relative_path.strip():
            return None

        candidate = (self.root / relative_path).resolve()
        root_resolved = self.root.resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate
