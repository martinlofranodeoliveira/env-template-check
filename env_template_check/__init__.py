"""Compare variable names without evaluating or returning their values."""

from dataclasses import dataclass
import re
from typing import Iterable

__all__ = ["Assignment", "ParseError", "Report", "parse", "compare"]

_ASSIGNMENT = re.compile(r"(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=.*\Z")


@dataclass(frozen=True)
class Assignment:
    """An assignment's name and one-based source line; values are discarded."""

    name: str
    line: int


class ParseError(ValueError):
    """A malformed assignment; no source text is retained in the exception."""

    def __init__(self, line: int):
        self.line = line
        super().__init__(f"Invalid assignment on line {line}")


@dataclass(frozen=True)
class Report:
    """Sorted differences and duplicate occurrences from both inputs."""

    missing: tuple[str, ...]
    extra: tuple[str, ...]
    template_duplicates: tuple[tuple[str, tuple[int, ...]], ...]
    actual_duplicates: tuple[tuple[str, tuple[int, ...]], ...]

    @property
    def ok(self) -> bool:
        return not (
            self.missing or self.extra
            or self.template_duplicates or self.actual_duplicates
        )

    def as_dict(self) -> dict:
        """Return a JSON-ready report containing only names and line numbers."""
        return {
            "ok": self.ok,
            "missing": list(self.missing),
            "extra": list(self.extra),
            "duplicates": {
                "template": {name: list(lines) for name, lines in self.template_duplicates},
                "actual": {name: list(lines) for name, lines in self.actual_duplicates},
            },
        }


def parse(text: str) -> tuple[Assignment, ...]:
    """Parse restricted assignment syntax into immutable name/line records.

    Spaces/tabs may precede assignments and surround the name before '='.
    Optional 'export' must be followed by spaces/tabs. Values are opaque;
    comments are recognized only when '#' is the first non-space/tab character.
    No values, interpolation results, or source snippets are returned.
    """
    records = []
    for number, raw_line in enumerate(text.split("\n"), start=1):
        # Remove the CR in CRLF, but do not normalize other source characters.
        line = raw_line.removesuffix("\r").lstrip(" \t")
        if not line or line.startswith("#"):
            continue
        match = _ASSIGNMENT.fullmatch(line)
        if match is None:
            raise ParseError(number)
        records.append(Assignment(match.group(1), number))
    return tuple(records)


def _index(records: Iterable[Assignment]) -> dict[str, list[int]]:
    occurrences: dict[str, list[int]] = {}
    for record in records:
        occurrences.setdefault(record.name, []).append(record.line)
    return occurrences


def _duplicates(index: dict[str, list[int]]) -> tuple[tuple[str, tuple[int, ...]], ...]:
    return tuple(
        (name, tuple(sorted(index[name])))
        for name in sorted(index) if len(index[name]) > 1
    )


def compare(template: Iterable[Assignment], actual: Iterable[Assignment]) -> Report:
    """Compare parsed records; duplicate names on either side fail conformity."""
    expected = _index(template)
    present = _index(actual)
    return Report(
        missing=tuple(sorted(expected.keys() - present.keys())),
        extra=tuple(sorted(present.keys() - expected.keys())),
        template_duplicates=_duplicates(expected),
        actual_duplicates=_duplicates(present),
    )
