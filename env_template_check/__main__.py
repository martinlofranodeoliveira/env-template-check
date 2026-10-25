"""Command-line interface for env-template-check."""

import argparse
import json
from pathlib import Path
import sys

from . import ParseError, compare, parse


def _emit(payload: dict, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return
    if "error" in payload:
        error = payload["error"]
        location = f" on line {error['line']}" if "line" in error else ""
        print(f"Error: {error['source']}{location}: {error['message']}")
        return
    print("Conforming" if payload["ok"] else "Differences found")
    if payload["missing"]:
        print("Missing: " + ", ".join(payload["missing"]))
    if payload["extra"]:
        print("Extra: " + ", ".join(payload["extra"]))
    for source, duplicates in payload["duplicates"].items():
        for name, lines in duplicates.items():
            print(f"Duplicate in {source}: {name} (lines {', '.join(map(str, lines))})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare variable names without evaluating or displaying values."
    )
    parser.add_argument("template", help="UTF-8 template file")
    parser.add_argument("actual", help="UTF-8 actual file")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)

    parsed = []
    for source, filename in (("template", args.template), ("actual", args.actual)):
        try:
            # newline='' preserves CRLF so parse() owns line handling.
            with Path(filename).open(encoding="utf-8", newline="") as stream:
                records = parse(stream.read())
        except ParseError as exc:
            error = {"kind": "parse", "source": source, "line": exc.line,
                     "message": "Expected an ASCII name followed by '='"}
        except UnicodeError:
            error = {"kind": "encoding", "source": source,
                     "message": "Input must be UTF-8"}
        except (OSError, ValueError):
            # OS error messages may contain private paths. Do not print them.
            error = {"kind": "io", "source": source,
                     "message": "Unable to read input"}
        else:
            parsed.append(records)
            continue
        _emit({"ok": False, "error": error}, args.format)
        return 2

    report = compare(*parsed)
    _emit(report.as_dict(), args.format)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
