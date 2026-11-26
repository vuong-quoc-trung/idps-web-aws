"""Apply the existing catalog seeds as one insert-only staging transaction."""

from pathlib import Path
import subprocess
import sys

SEEDS = (
    "006_seed_pbl4_faculties.sql",
    "008_seed_mechanical_catalog.sql",
    "009_seed_it_catalog.sql",
    "010_seed_transport_energy_catalog.sql",
    "011_seed_thermal_catalog.sql",
    "013_seed_it_classes.sql",
)
CATALOG = ("faculties", "majors", "training_programs", "classes")
DATABASE = "ws_r47_student"


def transaction(seed_dir):
    sql = [
        "SET LOCAL lock_timeout = '3s';",
        "SET LOCAL statement_timeout = '20s';",
        "SET LOCAL websentinel.catalog_insert_only = 'on';",
        "LOCK TABLE faculties, majors, training_programs, classes, code_counters "
        "IN SHARE ROW EXCLUSIVE MODE;",
    ]
    for table in CATALOG:
        sql.append(f"CREATE TEMP TABLE before_{table} ON COMMIT DROP AS "
                   f"SELECT id, to_jsonb(t) AS row FROM public.{table} AS t;")
    for name in SEEDS:
        body = (seed_dir / name).read_text()
        preamble, begin, body = body.partition("\nBEGIN;\n")
        body, commit, _ = body.partition("\nCOMMIT;")
        if not begin or not commit or any(
            line.strip() and not line.startswith("--") for line in preamble.splitlines()
        ):
            raise ValueError(f"Unexpected seed transaction boundaries: {name}")
        sql.append(body)
    checks = "\n".join(
        f"IF EXISTS (SELECT 1 FROM before_{table} AS old LEFT JOIN public.{table} AS t "
        f"USING(id) WHERE to_jsonb(t) IS DISTINCT FROM old.row) THEN "
        f"RAISE EXCEPTION 'Existing {table} rows would change'; END IF;"
        for table in CATALOG
    )
    sql.append(f"DO $$ BEGIN {checks} END $$;")
    counts = ", ".join(
        f"'{table}', json_build_object("
        f"'before', (SELECT count(*) FROM before_{table}), "
        f"'after', (SELECT count(*) FROM public.{table}))"
        for table in CATALOG
    )
    sql.append(f"SELECT json_build_object({counts});")
    return "\n".join(sql)


def apply(seed_dir, database):
    result = subprocess.run(
        ["runuser", "-u", "postgres", "--", "psql", "-XqAt", "--single-transaction",
         "-v", "ON_ERROR_STOP=1", "-d", database, "-f", "-"],
        input=transaction(seed_dir), text=True, stdout=subprocess.PIPE,
        check=True, timeout=40,
    )
    print(result.stdout.strip(), flush=True)


if __name__ == "__main__":
    import refresh

    refresh.verify_host()
    refresh.verify_database()
    if len(sys.argv) != 2:
        sys.exit("Pass the directory containing the verified catalog seeds.")
    apply(Path(sys.argv[1]), DATABASE)
