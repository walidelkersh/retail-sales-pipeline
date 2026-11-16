import json
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


def test_report_fields_exist_in_model():
    powerbi = Path(__file__).resolve().parents[1] / "powerbi"
    # Power BI Desktop quotes a name only when it has a space in it.
    members = {
        path.stem: {
            quoted or bare
            for quoted, bare in re.findall(
                r"^\t(?:column|measure) (?:'([^']+)'|(\w+))",
                path.read_text(encoding="utf-8"),
                re.M,
            )
        }
        for path in (powerbi / "retail-sales.SemanticModel/definition/tables").glob("*.tmdl")
    }

    def check_fields(node, sources):
        if isinstance(node, dict):
            sources = sources | {
                source["Name"]: source["Entity"]
                for source in node.get("From", [])
                if "Entity" in source
            }
            if "Property" in node:
                source = node["Expression"]["SourceRef"]
                entity = source.get("Entity", sources.get(source.get("Source")))
                assert node["Property"] in members.get(entity, set()), (entity, node)
            for value in node.values():
                check_fields(value, sources)
        elif isinstance(node, list):
            for value in node:
                check_fields(value, sources)

    visuals = list((powerbi / "retail-sales.Report").rglob("visual.json"))
    assert visuals
    for path in visuals:
        check_fields(json.loads(path.read_text(encoding="utf-8")), {})
