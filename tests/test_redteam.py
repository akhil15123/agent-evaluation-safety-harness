import json
from pathlib import Path

from agent_harness.redteam import generate_redteam

ROOT = Path(__file__).parents[1]


def test_generates_reproducible_lineage_cases(tmp_path):
    output = tmp_path / "redteam.json"
    suite = generate_redteam(ROOT / "examples/support-suite.json", output, variants=2)
    assert len(suite["cases"]) == 14
    assert all(case["metadata"]["parent_case"] for case in suite["cases"])
    assert json.loads(output.read_text()) == suite
