import re
import subprocess
import sys
from pathlib import Path


def test_readme_badge_counts_every_test():
    root = Path(__file__).resolve().parents[1]
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout
    tests = int(re.search(r"^(\d+) tests? collected", collected, re.M).group(1))
    badge = re.search(r"badge/tests-(\d+)_passing", (root / "README.md").read_text(encoding="utf-8"))
    assert int(badge.group(1)) == tests
