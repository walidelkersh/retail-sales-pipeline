import re
from pathlib import Path

from deltalake import DeltaTable

from pipeline.lake import table_path


def test_source_columns_match_gold(gold_lake):
    tables = {
        "Sales": "fact_sales",
        "Date": "dim_date",
        "Product": "dim_product",
        "Customer": "dim_customer",
        "Country": "dim_country",
    }
    definitions = (
        Path(__file__).resolve().parents[1]
        / "powerbi/retail-sales.SemanticModel/definition/tables"
    )
    assert {path.stem for path in definitions.glob("*.tmdl")} == set(tables)
    for name, gold_table in tables.items():
        definition = (definitions / f"{name}.tmdl").read_text(encoding="utf-8")
        source_columns = set(re.findall(r"^\t\tsourceColumn: (\w+)$", definition, re.M))
        gold_columns = {
            field.name
            for field in DeltaTable(table_path("gold", gold_table, gold_lake)).schema().fields
        }
        assert source_columns == gold_columns, name
