from pathlib import Path

from pipeline.lake import write_target


def test_write_target(monkeypatch):
    monkeypatch.setenv(
        "LAKE_WRITE_URL", "abfss://workspace@onelake.dfs.fabric.microsoft.com/lakehouse",
    )
    assert write_target("bronze", "online_retail_lines", "local/lake") == (
        "abfss://workspace@onelake.dfs.fabric.microsoft.com/lakehouse"
        "/Tables/bronze/online_retail_lines"
    )
    monkeypatch.delenv("LAKE_WRITE_URL")
    assert write_target("bronze", "online_retail_lines", "local/lake") == Path(
        "local/lake/Tables/bronze/online_retail_lines"
    )
