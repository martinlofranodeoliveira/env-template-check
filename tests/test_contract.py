import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from env_template_check import Assignment, ParseError, compare, parse


class ParserTests(unittest.TestCase):
    def test_restricted_grammar_preserves_line_numbers(self):
        text = "# sample\n \t\n  export APP_NAME =demo\r\n_URL=\r\n\tCOUNT=2\n"
        self.assertEqual(parse(text), (
            Assignment("APP_NAME", 3), Assignment("_URL", 4), Assignment("COUNT", 5)
        ))

    def test_empty_and_comment_only_inputs(self):
        for text in ("", "\n", " \t\n  # example\n"):
            with self.subTest(text=text):
                self.assertEqual(parse(text), ())

    def test_values_are_opaque_and_absent_from_records(self):
        secret = 'SYNTHETIC_SENTINEL_${HOME}_$(touch /tmp/never)_`id`_"#;=é'
        records = parse("TOKEN=" + secret)
        self.assertEqual(records, (Assignment("TOKEN", 1),))
        self.assertNotIn(secret, repr(records))
        self.assertEqual(set(vars(records[0])), {"name", "line"})

    def test_export_can_itself_be_a_variable_name(self):
        self.assertEqual(parse("export=yes"), (Assignment("export", 1),))

    def test_invalid_names_and_unsupported_syntax(self):
        invalid = (
            "1NAME=x", "NÄME=x", "名字=x", "A-B=x", "A.B=x", "A B=x",
            "NAME", "export NAME", "EXPORT NAME=x", "exportNAME x",
            "set NAME=x", "NAME: value", "\ufeffNAME=x", "\vNAME=x",
        )
        for line in invalid:
            with self.subTest(line=line):
                with self.assertRaises(ParseError) as caught:
                    parse("# header\n" + line)
                self.assertEqual(caught.exception.line, 2)
                self.assertEqual(str(caught.exception), "Invalid assignment on line 2")
                self.assertEqual(set(vars(caught.exception)), {"line"})

    def test_multiline_quoted_value_is_not_evaluated(self):
        with self.assertRaises(ParseError) as caught:
            parse('NAME="first\nsecond"\n')
        self.assertEqual(caught.exception.line, 2)

    def test_no_environment_mutation(self):
        before = dict(os.environ)
        parse("SYNTHETIC_ENV_CHECK=changed\nPATH=synthetic\n")
        self.assertEqual(dict(os.environ), before)

    def test_records_are_immutable(self):
        record = parse("NAME=value")[0]
        with self.assertRaises(AttributeError):
            record.name = "OTHER"


class ComparisonTests(unittest.TestCase):
    def test_matching_names_ignore_values_and_order(self):
        report = compare(parse("B=2\nA=1"), parse("A=different\nB="))
        self.assertTrue(report.ok)
        self.assertEqual(report.as_dict(), {
            "ok": True, "missing": [], "extra": [],
            "duplicates": {"template": {}, "actual": {}},
        })

    def test_missing_and_extra_names_are_sorted(self):
        report = compare(parse("Z=\nA=\nCOMMON="), parse("Y=\nCOMMON=\nB="))
        self.assertEqual(report.missing, ("A", "Z"))
        self.assertEqual(report.extra, ("B", "Y"))
        self.assertFalse(report.ok)

    def test_duplicates_include_all_source_lines_on_both_sides(self):
        report = compare(
            parse("Z=1\nA=1\nZ=2\nA=2\nZ=3"), parse("A=3\nZ=4\nA=5")
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.as_dict()["duplicates"], {
            "template": {"A": [2, 4], "Z": [1, 3, 5]},
            "actual": {"A": [1, 3]},
        })
        self.assertEqual(report.missing, ())
        self.assertEqual(report.extra, ())

    def test_iterators_are_supported(self):
        self.assertTrue(compare(iter(parse("A=1")), iter(parse("A=2"))).ok)

    def test_empty_inputs_conform(self):
        self.assertTrue(compare((), ()).ok)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="env-template-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.template = self.root / "template.txt"
        self.actual = self.root / "actual.txt"

    def run_cli(self, template=b"A=template\n", actual=b"A=actual\n", output="json"):
        self.template.write_bytes(template)
        self.actual.write_bytes(actual)
        return self.invoke(self.template, self.actual, "--format", output)

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "env_template_check", *map(str, args)],
            capture_output=True, text=True, check=False,
        )

    def test_conforming_exit_zero_and_stable_json(self):
        first = self.run_cli()
        second = self.run_cli()
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stderr, "")
        self.assertEqual(first.stdout, second.stdout)
        self.assertTrue(json.loads(first.stdout)["ok"])

    def test_difference_exit_one_and_complete_json(self):
        result = self.run_cli(b"Z=\nA=\nA=\n", b"B=\nB=\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {
            "ok": False, "missing": ["A", "Z"], "extra": ["B"],
            "duplicates": {"template": {"A": [2, 3]}, "actual": {"B": [1, 2]}},
        })

    def test_duplicates_alone_fail(self):
        for template, actual in ((b"A=1\nA=2", b"A=3"), (b"A=1", b"A=2\nA=3")):
            with self.subTest(template=template, actual=actual):
                self.assertEqual(self.run_cli(template, actual).returncode, 1)

    def test_parse_errors_identify_role_and_line_without_input(self):
        secret = b"SYNTHETIC_SECRET_DO_NOT_PRINT"
        for role in ("template", "actual"):
            with self.subTest(role=role):
                invalid = b"# header\nINVALID " + secret
                result = self.run_cli(
                    invalid if role == "template" else b"A=1",
                    invalid if role == "actual" else b"A=2",
                )
                self.assertEqual(result.returncode, 2)
                error = json.loads(result.stdout)["error"]
                self.assertEqual((error["kind"], error["source"], error["line"]),
                                 ("parse", role, 2))
                self.assertNotIn(secret.decode(), result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")

    def test_invalid_utf8_is_safe(self):
        result = self.run_cli(actual=b"A=\xff")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"], {
            "kind": "encoding", "source": "actual", "message": "Input must be UTF-8"
        })

    def test_missing_file_and_directory_are_io_errors_without_paths(self):
        self.template.write_text("A=synthetic", encoding="utf-8")
        for bad in (self.root / "SYNTHETIC_PRIVATE_PATH.txt", self.root):
            with self.subTest(path=bad):
                result = self.invoke(self.template, bad, "--format", "json")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["error"]["kind"], "io")
                self.assertNotIn(str(self.root), result.stdout + result.stderr)

    def test_values_are_never_printed_or_executed(self):
        marker = self.root / "must-not-exist"
        value = f'SYNTHETIC_SECRET_$(touch {marker})_${{HOME}}_`id`'
        result = self.run_cli(
            ("A=" + value + "\nMISSING=" + value).encode(),
            ("A=" + value + "\nEXTRA=" + value).encode(),
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(value, result.stdout + result.stderr)
        self.assertNotIn("SYNTHETIC_SECRET", result.stdout + result.stderr)
        self.assertFalse(marker.exists())

    def test_text_output_and_default_format(self):
        result = self.run_cli(b"A=1\nA=2\nB=3", b"A=4\nC=5", "text")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, (
            "Differences found\nMissing: B\nExtra: C\n"
            "Duplicate in template: A (lines 1, 2)\n"
        ))
        default = self.invoke(self.template, self.actual)
        self.assertEqual(default.stdout, result.stdout)

    def test_text_parse_error_is_safe(self):
        result = self.run_cli(actual=b"DO_NOT_PRINT_THIS", output="text")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, (
            "Error: actual on line 1: Expected an ASCII name followed by '='\n"
        ))
        self.assertNotIn("DO_NOT_PRINT_THIS", result.stdout + result.stderr)

    def test_crlf_inputs_and_empty_values(self):
        result = self.run_cli(b"A=\r\nB=\r\n", b"export B=other\r\nA=\r\n")
        self.assertEqual(result.returncode, 0)

    def test_argument_errors_use_exit_two(self):
        self.assertEqual(self.invoke().returncode, 2)
        self.assertEqual(self.invoke("a", "b", "--format", "yaml").returncode, 2)

    def test_help_documents_cli(self):
        result = self.invoke("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--format {json,text}", result.stdout)


if __name__ == "__main__":
    unittest.main()
