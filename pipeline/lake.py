from pathlib import Path


LAKE_ROOT = Path("data/lake")


def table_path(layer, table, lake_root=LAKE_ROOT):
    return Path(lake_root) / "Tables" / layer / table


def raw_directory(lake_root=LAKE_ROOT):
    return Path(lake_root) / "Files" / "raw"
