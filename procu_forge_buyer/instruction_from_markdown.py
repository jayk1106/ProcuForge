"""Load agent system instructions from one or more Markdown files."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

BUYER_PACKAGE_ROOT = Path(__file__).resolve().parent


def negotiator_markdown_paths() -> tuple[Path, Path, Path]:
    """Default Markdown sources for negotiator_agent (order matters)."""
    root = BUYER_PACKAGE_ROOT
    return (
        root / "doc" / "a2a_guidelines.md",
        root / "doc" / "a2a_enums.md",
        root / "subagents" / "negotiator" / "skill.md",
    )


def build_instruction_from_markdown_files(
    paths: Sequence[Path | str],
    *,
    separator: str = "\n\n---\n\n",
    encoding: str = "utf-8",
    section_headers: bool = True,
) -> str:
    """Read Markdown files in order and concatenate into one instruction string.

    Args:
        paths: Files to read, in order.
        separator: Joins sections between files.
        encoding: Text encoding for reads.
        section_headers: If True, prefix each file body with ``# <filename>``.

    Returns:
        Combined Markdown suitable for an agent ``instruction``.

    Raises:
        FileNotFoundError: If any path does not exist.
        OSError: If a file cannot be read.
    """
    parts: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"instruction markdown not found: {path}")
        text = path.read_text(encoding=encoding).strip()
        if section_headers:
            parts.append(f"# {path.name}\n\n{text}")
        else:
            parts.append(text)
    return separator.join(parts)


def negotiator_instruction_from_default_markdown(
    *,
    separator: str = "\n\n---\n\n",
    encoding: str = "utf-8",
    section_headers: bool = True,
) -> str:
    """Build negotiator instruction from package default Markdown paths."""
    return build_instruction_from_markdown_files(
        negotiator_markdown_paths(),
        separator=separator,
        encoding=encoding,
        section_headers=section_headers,
    )


__all__ = [
    "BUYER_PACKAGE_ROOT",
    "build_instruction_from_markdown_files",
    "negotiator_instruction_from_default_markdown",
    "negotiator_markdown_paths",
]
