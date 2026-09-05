import json
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
out = Path(tempfile.mkdtemp(prefix="clearledger-adversarial-"))
report = {
    "dataset_id": "COMPLETELY_WRONG_DATASET",
    "run_id": "empty",
    "duration_seconds": 0.000001,
    "total_source_records": 1000000000,
    "cases": [],
}
(out / "empty_prediction.json").write_text(json.dumps(report))
p = subprocess.run(
    [
        str(root / ".venv/bin/python"),
        "-m",
        "evaluator.cli",
        "--predictions",
        str(out / "empty_prediction.json"),
        "--ground-truth",
        str(root / "evaluator_private/ground_truth_demo.json"),
        "--output",
        str(out / "empty_eval.json"),
        "--output-md",
        str(out / "empty_eval.md"),
    ],
    cwd=root,
    capture_output=True,
    text=True,
)
print("CLI exit code:", p.returncode)
print(p.stdout)
print(p.stderr)

print("Temporary output:", out)
