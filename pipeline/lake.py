import os
from pathlib import Path


LAKE_ROOT = Path(os.environ.get("LAKE_ROOT", "data/lake"))


def table_path(layer, table, lake_root=LAKE_ROOT):
    return Path(lake_root) / "Tables" / layer / table


def write_target(layer, table, lake_root=LAKE_ROOT):
    # The OneLake mount cannot rename files, so delta-rs has to write through the URL.
    if url := os.environ.get("LAKE_WRITE_URL"):
        return f"{url.rstrip('/')}/Tables/{layer}/{table}"
    return table_path(layer, table, lake_root)


def raw_directory(lake_root=LAKE_ROOT):
    return Path(lake_root) / "Files" / "raw"
