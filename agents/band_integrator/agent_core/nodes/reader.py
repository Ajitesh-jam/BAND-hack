"""
Folder scanner: reads Python source files from a user-supplied directory and
returns them as a dict suitable for injection into the integrator prompt.

Design decisions:
- Only `.py` files are read; non-Python assets are irrelevant for code analysis.
- Common virtual-environment and build directories are excluded so the LLM
  doesn't spend context on third-party library source code.
- Large files are truncated at MAX_FILE_CHARS with a clear marker so the LLM
  knows to expect incomplete content.
- A combined size cap (MAX_TOTAL_CHARS) prevents runaway context usage when
  the user points at a large mono-repo.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories that are never useful to read
_SKIP_DIRS = {
    "__pycache__", ".venv", "venv", "env", ".env",
    "node_modules", ".git", ".mypy_cache", ".pytest_cache",
    "dist", "build", "*.egg-info", ".tox", "site-packages",
}

MAX_FILE_CHARS = 8_000
MAX_TOTAL_CHARS = 40_000   # ~10k tokens total across all files


def read_folder(folder_path: str) -> dict[str, str]:
    """
    Recursively read all .py files under `folder_path`.

    Returns:
        dict mapping relative file path (str) → file content (str).
        Files are ordered: shorter paths first (top-level before nested).

    Raises:
        ValueError: if folder_path does not exist or is not a directory.
    """
    root = Path(folder_path).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"Folder not found: {folder_path}")
    if not root.is_dir():
        raise ValueError(f"Path is not a directory: {folder_path}")

    collected: dict[str, str] = {}
    total_chars = 0

    py_files = sorted(
        (p for p in root.rglob("*.py") if _should_include(p, root)),
        key=lambda p: (len(p.parts), str(p)),
    )

    if not py_files:
        logger.warning("No .py files found in %s", root)
        return {}

    for path in py_files:
        if total_chars >= MAX_TOTAL_CHARS:
            logger.warning(
                "Total size cap (%d chars) reached — skipping remaining files.",
                MAX_TOTAL_CHARS,
            )
            break

        rel = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Could not read %s: %s", path, exc)
            continue

        if len(text) > MAX_FILE_CHARS:
            logger.warning(
                "File %s truncated to %d chars (original: %d chars).",
                rel, MAX_FILE_CHARS, len(text),
            )
            text = text[:MAX_FILE_CHARS] + f"\n\n# ... [TRUNCATED — {len(text)} chars total] ..."

        collected[rel] = text
        total_chars += len(text)

    logger.info(
        "Read %d files from %s (%d chars total).",
        len(collected), root, total_chars,
    )
    return collected


def format_for_prompt(file_contents: dict[str, str]) -> str:
    """
    Render the file dict as a single labelled string for injection into a
    prompt.  Each file is wrapped with a clear header/footer.
    """
    parts: list[str] = []
    for filename, content in file_contents.items():
        parts.append(f"### FILE: {filename}\n{content}\n### END: {filename}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _should_include(path: Path, root: Path) -> bool:
    """Return True if `path` is not inside any skip directory."""
    for part in path.relative_to(root).parts[:-1]:   # exclude the filename itself
        if part in _SKIP_DIRS or part.endswith(".egg-info"):
            return False
    return True
