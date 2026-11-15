import sys
from pathlib import Path

from pipeline.lake import LAKE_ROOT
from pipeline.transform import lake_connection


def run_checks(layer, lake_root=LAKE_ROOT):
    check_counts = {}
    with lake_connection(lake_root) as connection:
        sql_directory = Path(__file__).resolve().parents[1] / "sql" / "checks" / layer
        for query in sorted(sql_directory.glob("*.sql")):
            check_counts[query.stem] = connection.sql(query.read_text()).aggregate(
                "count(*)"
            ).fetchall()[0][0]
    failures = [
        f"{check}: {row_count}"
        for check, row_count in check_counts.items() if row_count > 0
    ]
    if failures:
        raise ValueError("Checks failed: " + "; ".join(failures))
    return check_counts


if __name__ == "__main__":
    for check in run_checks(sys.argv[1]):
        print(f"{check}: ok")
