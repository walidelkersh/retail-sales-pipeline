import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def get_id(path):
    return subprocess.run(
        ["fab", "get", path, "-q", "id"],
        check=True, capture_output=True, text=True,
    ).stdout.strip().strip("\"'")


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
            platform = {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "Notebook", "displayName": name},
                "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
            }
            (folder / ".platform").write_text(
                json.dumps(platform, indent=1) + "\n", encoding="utf-8",
            )
            subprocess.run(
                ["fab", "import", f"{workspace}/{name}.Notebook", "-i", str(folder), "--format", ".ipynb", "-f"],
                check=True,
            )


if __name__ == "__main__":
    main()
