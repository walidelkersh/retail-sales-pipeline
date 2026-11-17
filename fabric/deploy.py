import json
import os
from pathlib import Path
import re
from shutil import copyfile, copytree
import subprocess
import sys
from tempfile import TemporaryDirectory


def get_id(path):
    return subprocess.run(
        ["fab", "get", path, "-q", "id"],
        check=True, capture_output=True, text=True,
    ).stdout.strip().strip("\"'")


def import_item(workspace, name, item_type, folder, format=None):
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": item_type, "displayName": name},
        "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
    }
    (folder / ".platform").write_text(json.dumps(platform, indent=1) + "\n", encoding="utf-8")
    command = ["fab", "import", f"{workspace}/{name}.{item_type}", "-i", str(folder)]
    if format:
        command.extend(["--format", format])
    subprocess.run([*command, "-f"], check=True)


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: uv run python fabric/deploy.py "<workspace path>" "<lakehouse name>"')
    workspace, lakehouse_name = sys.argv[1:]
    root = Path(__file__).resolve().parents[1]
    lakehouse_path = f"{workspace}/{lakehouse_name}.Lakehouse"
    code_path = f"{lakehouse_path}/Files/code"
    subprocess.run(["fab", "mkdir", code_path], check=False)
    files = [root / "pyproject.toml", root / "uv.lock"]
    # shortcut: deleted repo files stay in Files/code, remove them manually until deployment needs syncing.
    for folder in ("pipeline", "sql", "reference"):
        for directory, children, filenames in os.walk(root / folder):
            children[:] = sorted(child for child in children if child != "__pycache__")
            relative = Path(directory).relative_to(root).as_posix()
            subprocess.run(["fab", "mkdir", f"{code_path}/{relative}"], check=False)
            files.extend(Path(directory) / name for name in sorted(filenames))
    for file in files:
        relative = file.relative_to(root).as_posix()
        subprocess.run(["fab", "cp", str(file), f"{code_path}/{relative}", "-f"], check=True)

    workspace_id = get_id(workspace)
    lakehouse_id = get_id(lakehouse_path)
    with TemporaryDirectory() as staging:
        for layer in ("bronze", "silver", "gold"):
            name = f"retail_{layer}"
            notebook = json.loads((root / "fabric" / "notebooks" / f"{layer}.ipynb").read_text(encoding="utf-8"))
            notebook["metadata"]["dependencies"] = {
                "lakehouse": {
                    "default_lakehouse": lakehouse_id,
                    "default_lakehouse_name": lakehouse_name,
                    "default_lakehouse_workspace_id": workspace_id,
                }
            }
            folder = Path(staging) / f"{name}.Notebook"
            folder.mkdir()
            (folder / "notebook-content.ipynb").write_text(
                json.dumps(notebook, indent=1) + "\n", encoding="utf-8",
            )
            import_item(workspace, name, "Notebook", folder, ".ipynb")

        # These IDs are tenant-specific, so resolve them only when deploying.
        pipeline = json.loads((root / "fabric" / "pipeline-content.json").read_text(encoding="utf-8"))
        for activity in pipeline["properties"]["activities"]:
            activity["typeProperties"]["notebookId"] = get_id(f"{workspace}/retail_{activity['name']}.Notebook")
            activity["typeProperties"]["workspaceId"] = workspace_id
        folder = Path(staging) / "retail_pipeline.DataPipeline"
        folder.mkdir()
        (folder / "pipeline-content.json").write_text(
            json.dumps(pipeline, indent=2) + "\n", encoding="utf-8",
        )
        import_item(workspace, "retail_pipeline", "DataPipeline", folder)

        source = root / "powerbi" / "retail-sales.SemanticModel"
        folder = Path(staging) / "retail_sales.SemanticModel"
        copytree(source / "definition", folder / "definition")
        copyfile(source / "definition.pbism", folder / "definition.pbism")
        expressions_path = folder / "definition" / "expressions.tmdl"
        expressions = expressions_path.read_bytes()
        # The service cannot read a local folder, so use OneLake in the staged model.
        expressions, count = re.subn(
            rb'(expression LakeRoot =\s*")(?:""|[^"\r\n])*(")',
            lambda match: match[1] + f"https://onelake.dfs.fabric.microsoft.com/{workspace_id}/{lakehouse_id}".encode("utf-8") + match[2],
            expressions,
        )
        if count != 1:
            raise ValueError(f"Expected exactly one LakeRoot parameter value; found {count}.")
        gold_source = rb'Folder.Contents(LakeRoot & "\Tables\gold")'
        count = expressions.count(gold_source)
        if count != 1:
            raise ValueError(f"Expected exactly one local GoldFolder source; found {count}.")
        expressions_path.write_bytes(expressions.replace(
            gold_source,
            b'AzureStorage.DataLake(LakeRoot & "/Tables/gold", [HierarchicalNavigation = true])',
        ))
        import_item(workspace, "retail_sales", "SemanticModel", folder)

        semantic_model_id = get_id(f"{workspace}/retail_sales.SemanticModel")
        source = root / "powerbi" / "retail-sales.Report"
        folder = Path(staging) / "retail_sales.Report"
        copytree(source / "definition", folder / "definition")
        copytree(source / "StaticResources", folder / "StaticResources")
        report = {
            "version": "4.0",
            "datasetReference": {
                "byConnection": {
                    "connectionString": None,
                    "pbiServiceModelId": None,
                    "pbiModelVirtualServerName": "sobe_wowvirtualserver",
                    "pbiModelDatabaseName": semantic_model_id,
                    "name": "EntityDataSource",
                    "connectionType": "pbiServiceXmlaStyleLive",
                }
            },
        }
        (folder / "definition.pbir").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8",
        )
        import_item(workspace, "retail_sales", "Report", folder)

    print("The first refresh needs a sign-in on the semantic model's data source credentials in the Power BI service.")


if __name__ == "__main__":
    main()
