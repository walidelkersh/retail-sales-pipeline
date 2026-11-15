import sys
from contextlib import contextmanager
from pathlib import Path

import duckdb
from deltalake import write_deltalake

from pipeline.lake import LAKE_ROOT, table_path


def expose_table(connection, path):
    layer = path.parent.name
    table = path.name
    delta_path = path.as_posix().replace("'", "''")
    connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{layer}"')
    connection.execute(
        f'CREATE OR REPLACE VIEW "{layer}"."{table}" AS '
        f"SELECT * FROM delta_scan('{delta_path}')"
    )


@contextmanager
def lake_connection(lake_root):
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        for delta_log in sorted((Path(lake_root) / "Tables").glob("*/*/_delta_log")):
            expose_table(connection, delta_log.parent)
        yield connection


def run_layer(layer, lake_root=LAKE_ROOT):
    table_counts = {}
    with lake_connection(lake_root) as connection:
        sql_directory = Path(__file__).resolve().parents[1] / "sql" / layer
        for query in sorted(sql_directory.glob("*.sql")):
            # a prefix such as "00." only orders the files within a layer
            table = query.stem.split(".")[-1]
            path = table_path(layer, table, lake_root)
            write_deltalake(
                path,
                connection.sql(query.read_text()),
                mode="overwrite",
            )
            expose_table(connection, path)
            table_counts[table] = connection.execute(
                f'SELECT count(*) FROM "{layer}"."{table}"'
            ).fetchall()[0][0]
    return table_counts


if __name__ == "__main__":
    for table, row_count in run_layer(sys.argv[1]).items():
        print(f"{table}: {row_count}")
