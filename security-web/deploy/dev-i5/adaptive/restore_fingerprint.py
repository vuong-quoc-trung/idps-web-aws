"""Read one PostgreSQL custom archive inside the guest. Print only TOC labels and hashes."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


# Exact varchar(n) enum checks in the shipped migrations. Preserve constraint names,
# columns, values/order, typmods, collations and every other byte of the DDL.
ENUM_COLUMNS = {
    "family_members": {"relationship"},
    "student_addresses": {"address_type"},
    "students": {"gender", "profile_status", "status"},
    "training_programs": {"degree_type"},
    "users": {"role"},
    "firewall_actions": {"action", "status"},
}
LITERAL = rb"'[A-Z][A-Z0-9_]*'::character varying"
ENUM_LINE = re.compile(
    rb"(?P<head>    CONSTRAINT [a-z_][a-z_0-9]* CHECK \(\(\((?P<col>[a-z_]+)\)::text = ANY \()"
    rb"\(ARRAY\[(?P<items>" + LITERAL + rb"(?:, " + LITERAL + rb")*)\]\)::text\[\]"
    rb"(?P<tail>\)\)\),?)(?=\n)"
)


def enum_table(label):
    parts = label.split()
    if len(parts) == 4 and parts[:2] == ["TABLE", "public"] and parts[2] in ENUM_COLUMNS:
        return parts[2]
    return None


def normalize_enum_checks(body, table):
    if table is None:
        return body
    opening = b"CREATE TABLE public." + table.encode() + b" (\n"
    if body.count(opening) != 1:
        return body
    begin = body.index(opening) + len(opening)
    end = body.find(b"\n);\n", begin)
    if end < 0:
        return body
    definition = body[begin:end+1]
    # Avoid interpreting text inside multiline strings, comments or quoted identifiers as DDL.
    if re.search(rb"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", definition) or any(x in definition for x in ( b'"', b"/*", b"--", b"\\")) or any(
        line.count(b"'") % 2 for line in definition.splitlines()
    ):
        return body
    def rewrite(match):
        if match["col"].decode() not in ENUM_COLUMNS[table]:
            return match[0]
        items = [b"("+v+b")::text" for v in match["items"].split(b", ")]
        return match["head"] + b"ARRAY[" + b", ".join(items) + b"]" + match["tail"]
    definition = re.sub(rb"^" + ENUM_LINE.pattern, rewrite, definition, flags=re.M)
    return body[:begin] + definition + body[end+1:]


def canonical_object(sql, table_data, table=None, diagnostics=None):
    # Only edit pg_restore's own prologue and epilogue. Never normalize SQL bodies.
    start = b"--\n-- PostgreSQL database dump\n--\n\n"
    end = b"--\n-- PostgreSQL database dump complete\n--\n"
    if not sql.startswith(start):
        raise ValueError("unexpected pg_restore header")
    body = sql[len(start):]
    key = re.match(rb"\\restrict ([A-Za-z0-9]+)\n\n", body)
    if key:
        body = body[key.end():]
        suffix = b"\\unrestrict " + key[1] + b"\n"
        if not body.rstrip(b"\n").endswith(b"\n" + suffix.rstrip(b"\n")):
            raise ValueError("missing pg_restore terminator")
        body = body.rstrip(b"\n")[:-len(suffix.rstrip(b"\n"))]
    if not body.rstrip(b"\n").endswith(end.rstrip(b"\n")):
        raise ValueError("incomplete pg_restore output")
    versions = re.match(rb"-- Dumped from database version [^\n]+\n-- Dumped by pg_dump version [^\n]+\n", body)
    metadata = versions[0] if versions else b""
    body = body[len(metadata):]
    original = digest(body)
    if table and diagnostics is not None:
        # Only object DDL from the six selected TABLE entries, never COPY rows.
        # Hash string contents so even a sensitive default is not printed.
        safe = re.sub(rb"'(?:[^']|'')*'", lambda m: b"'#"+digest(m[0])[:16].encode()+b"'",
                      body)
        diagnostics.extend(safe.decode("utf-8").splitlines())
    body = normalize_enum_checks(body, table)
    count = None
    row_digest = None
    if table_data:
        copy = re.search(rb"^COPY [^\n]+ FROM stdin;\n", body, re.M)
        if not copy:
            raise ValueError("unsupported TABLE DATA representation")
        terminator = re.compile(rb"^\\\.\n", re.M).search(body, copy.end())
        if not terminator:
            raise ValueError("incomplete COPY")
        payload = body[copy.end():terminator.start()]
        rows = payload.split(b"\n")
        if rows.pop() != b"":
            raise ValueError("unterminated COPY row")
        count = len(rows)
        # Fixed-width digests preserve row boundaries, duplicates, NULL and column order.
        row_hashes = sorted(hashlib.sha256(row).digest() for row in rows)
        row_digest = digest(b"".join(row_hashes))
        body = body[:copy.end()] + b"".join(row_hashes) + body[terminator.start():]
    return [digest(body), original, count, digest(metadata), row_digest]


def fingerprint(archive, reader=None):
    toc = reader(archive) if reader else subprocess.check_output(["pg_restore", "--list", archive])
    objects = []
    for line in toc.splitlines():
        if not line or line.startswith(b";"):
            continue
        entry = re.fullmatch(rb"(\d+);\s+\d+\s+\d+\s+(.+)", line)
        if not entry:
            raise ValueError("unrecognized archive TOC entry")
        label = entry[2].decode("utf-8")
        # Isolate entries using pg_restore itself, so SQL comments inside a function,
        # or user data resembling a dump header, cannot introduce object boundaries.
        if reader:
            sql = reader(archive, line)
        else:
            with tempfile.NamedTemporaryFile() as selected:
                selected.write(line+b"\n")
                selected.flush()
                sql = subprocess.check_output(["pg_restore", "-L", selected.name, "-f", "-", archive])
        table = enum_table(label)
        diagnostic = []
        record = [label, *canonical_object(sql, label.startswith("TABLE DATA "), table, diagnostic)]
        if table:
            record.append(diagnostic)
        objects.append(record)
    if not objects:
        raise ValueError("empty archive TOC")
    return objects


def main():
    mode, path = sys.argv[1:]
    if mode == "archive":
        result = fingerprint(path)
    elif mode == "database":
        # Temporary 0700 guest directory; pg_dump only sees its stdout, never the path.
        with tempfile.TemporaryDirectory() as work:
            archive = Path(work)/"read-only.dump"
            with archive.open("xb") as out:
                subprocess.run(["runuser", "-u", "postgres", "--", "env",
                                "PGOPTIONS=-c default_transaction_read_only=on", "pg_dump",
                                "-Fc", "--lock-wait-timeout=5s", "-d", path], stdout=out, check=True)
            result = fingerprint(archive)
    else:
        raise ValueError("unknown fingerprint source")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
