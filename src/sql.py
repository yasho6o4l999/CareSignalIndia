from pathlib import Path

from src.config import ROOT


SQL_ROOT = ROOT / "sql"


def render_sql(relative_path: str, **paths: Path | str) -> str:
    template = (SQL_ROOT / relative_path).read_text(encoding="utf-8")
    escaped_paths = {name: str(path).replace("'", "''") for name, path in paths.items()}
    return template.format_map(escaped_paths)

