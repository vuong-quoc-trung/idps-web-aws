"""Read-only verifier regression; fixtures never connect to PostgreSQL."""
from pathlib import Path
import subprocess
import json
from restore_fingerprint import ENUM_COLUMNS, canonical_object, normalize_enum_checks
import unittest
from unittest.mock import patch

import preflight_guest as checker


class RestoreTests(unittest.TestCase):
    def verify(self, *outputs):
        with patch.object(checker, "guest", side_effect=outputs) as guest:
            checker.verify_restore(Path("/backup"), "r123")
        return guest

    manifest = "".join("1"*64+"  "+name+".dump\n" for name in checker.DATABASES)

    def sample(self, rows=(b"1",b"2",b"1"), key=b"abc", version=b"17", ddl=b"integer"):
        def sql(body):
            return (b"--\n-- PostgreSQL database dump\n--\n\n\\restrict "+key+b"\n\n"
                    b"-- Dumped from database version "+version+b"\n-- Dumped by pg_dump version 17\n"
                    +body+b"\n--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict "+key+b"\n")
        return [["TABLE public t postgres", *canonical_object(sql(b"CREATE TABLE t (i "+ddl+b");"),False)],
                ["TABLE DATA public t postgres", *canonical_object(sql(b"COPY t (i) FROM stdin;\n"
                 +b"\n".join(rows)+b"\n\\.\n"),True)]]

    def test_equal_contents_both_targets(self):
        before = json.dumps(self.sample())
        after = json.dumps(self.sample((b"2",b"1",b"1"),key=b"new",version=b"18")[::-1])
        guest = self.verify(self.manifest, "", before, after, before, after)
        for call, name in zip([guest.call_args_list[3],guest.call_args_list[5]],checker.DATABASES):
            self.assertEqual(call.args[-2:], ("database",name+"_r123"))

    def test_missing_dump_in_manifest(self):
        with self.assertRaisesRegex(ValueError, "SHA256SUMS thiếu"):
            self.verify(self.manifest.splitlines()[0])

    def test_corrupt_backup(self):
        with self.assertRaisesRegex(ValueError, "sai SHA256SUMS"):
            self.verify(self.manifest, subprocess.CalledProcessError(1,"sha256sum"))

    def test_both_db_differences_reported(self):
        before = json.dumps(self.sample())
        student = json.dumps(self.sample((b"1",b"2",b"2")))
        security = json.dumps(self.sample(ddl=b"bigint"))
        with self.assertRaises(ValueError) as result:
            self.verify(self.manifest, "", before, student, before, security)
        self.assertIn("websentinel_student_r123", str(result.exception))
        self.assertIn("row values/multiplicity", str(result.exception))
        self.assertIn("websentinel_security_r123", str(result.exception))
        self.assertIn("SQL definition/state", str(result.exception))

    def test_dump_failure_not_equal_empty_stream(self):
        before = json.dumps(self.sample())
        with self.assertRaisesRegex(ValueError,"unable to fingerprint"):
            self.verify(self.manifest, "", before, subprocess.CalledProcessError(1,"pg_dump"), before, before)

    def test_pg17_varchar_enum_deparse(self):
        for table, columns in ENUM_COLUMNS.items():
            for column in columns:
                items = [b"'ADMIN'::character varying", b"'STAFF'::character varying"]
                array_cast = b"(ARRAY["+b", ".join(items)+b"])::text[]"
                item_cast = b"ARRAY["+b", ".join(b"("+v+b")::text" for v in items)+b"]"
                original = (f"CREATE TABLE public.{table} (\n    {column} character varying(20),\n"
                            f"    CONSTRAINT test_check CHECK ((({column})::text = ANY (").encode()
                original += array_cast + b"))),\n    CONSTRAINT format_check CHECK (code ~ '^[A-Z]$')\n);\n"
                restored = original.replace(array_cast,item_cast)
                with self.subTest(table=table, column=column):
                    self.assertEqual(normalize_enum_checks(original,table), restored)
                    for old,new in [(b"STAFF",b"OTHER"), (b"test_check",b"new_check"),
                                    (b"ANY",b"ALL"), (b"varying(20)",b"varying(21)"),
                                    (b"^[A-Z]$",b"^[A-Z0-9]$")]:
                        self.assertNotEqual(normalize_enum_checks(original,table),
                                            normalize_enum_checks(restored.replace(old,new),table))
                    self.assertEqual(normalize_enum_checks(original,None),original)

    def test_missing_object(self):
        self.assertTrue(checker.compare_objects(self.sample(), self.sample()[:1]))

    def test_incomplete_copy(self):
        with self.assertRaises(ValueError):
            canonical_object(b"unexpected output", True)


if __name__ == "__main__":
    unittest.main()
