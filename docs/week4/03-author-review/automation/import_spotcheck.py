"""Validate completed spot-check CSV and write NEW, sample-only agreement evidence."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EDITABLE = {"reviewer_decision", "reviewer_notes", "reviewer_alias",
            "reviewed_at", "independence_attestation"}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
            raise ValueError("Duplicate CSV header.")
        return list(reader)


def validate_and_compare(template, completed, predictions):
    expected = {r["judgment_id"]: r for r in template}
    if len(expected) != len(template):
        raise ValueError("Invalid blank template: duplicate ID.")
    ids = [r.get("judgment_id") for r in completed]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError("Require exactly the original 15 unique rows; retain blank rows for partial review.")
    reviewed, pending = [], []
    for row in completed:
        jid = row["judgment_id"]
        reference = expected[jid]
        if set(row) != set(reference):
            raise ValueError(f"Changed columns for {jid}.")
        if any(row[k] != v for k, v in reference.items() if k not in EDITABLE):
            raise ValueError(f"Immutable evidence changed for {jid}.")
        value = row["reviewer_decision"].strip()
        if not value:
            pending.append(jid)
            continue
        if value not in ("0", "1"):
            raise ValueError(f"Decision must be 0/1 or blank: {jid}.")
        for name in ("reviewer_notes", "reviewer_alias", "reviewed_at", "independence_attestation"):
            if not row[name].strip():
                raise ValueError(f"Missing {name}: {jid}.")
        datetime.fromisoformat(row["reviewed_at"].strip().replace("Z", "+00:00"))
        automated = predictions[jid]["predicted"]
        if automated not in ("PASS", "FAIL"):
            raise ValueError("Invalid automated prediction.")
        human = "PASS" if value == "1" else "FAIL"
        reviewed.append({
            "judgment_id": jid, "criterion": reference["evaluation_metric"],
            "human": human, "automated_provisional": automated,
            "agrees": human == automated,
            "reviewer_notes": row["reviewer_notes"],
            "reviewer_alias": row["reviewer_alias"],
            "reviewed_at": row["reviewed_at"],
            "independence_attestation": row["independence_attestation"],
        })
    agreements = sum(r["agrees"] for r in reviewed)
    by_metric = {}
    for metric in sorted({r["evaluation_metric"] for r in template}):
        own = [r for r in reviewed if r["criterion"] == metric]
        by_metric[metric] = {
            "reviewed": len(own),
            "sample_total": sum(r["evaluation_metric"] == metric for r in template),
            "agreements": sum(r["agrees"] for r in own),
            "agreement_fraction": sum(r["agrees"] for r in own) / len(own) if own else None,
        }
    return {
        "status": "COMPLETE sample review" if not pending else "PARTIAL sample review",
        "sample_total": len(template), "reviewed": len(reviewed),
        "agreements": agreements,
        "agreement_fraction_reviewed_only": agreements / len(reviewed) if reviewed else None,
        "by_metric": by_metric, "disagreements": [r for r in reviewed if not r["agrees"]],
        "reviewed_decisions": reviewed, "pending_judgment_ids": pending,
        "human_label_counts": dict(Counter(r["human"] for r in reviewed)),
        "interpretation": "Purposive sample agreement with provisional automated predictions only; not independent full-dataset approval, historical-delta validation, or live-model accuracy. Do not extrapolate.",
        "automated_fail_stratum": "No automated FAIL predictions were available; FAIL-recognition agreement is not estimable.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to((ROOT / ".local/evaluations").resolve()):
        raise ValueError("Output must be a NEW directory under .local/evaluations.")
    if destination.exists():
        raise ValueError("Refusing existing output directory; never overwrite evidence.")
    template_path = HERE / "spotcheck-15-blind.csv"
    template_sha = hashlib.sha256(template_path.read_bytes()).hexdigest()
    manifest = json.loads((HERE / "sample-manifest.json").read_text())
    if template_sha != manifest["csv_sha256"]:
        raise ValueError("Blank sample template checksum mismatch.")
    if hashlib.sha256((HERE / "automated-predictions.json").read_bytes()).hexdigest() != manifest["automated_predictions_sha256"]:
        raise ValueError("Automated predictions changed since sample selection.")
    predictions = {r["judgment_id"]: r for r in json.loads((HERE / "automated-predictions.json").read_text())}
    report = validate_and_compare(read_csv(template_path), read_csv(args.completed), predictions)
    report["completed_csv_sha256"] = hashlib.sha256(args.completed.read_bytes()).hexdigest()
    report["template_sha256"] = template_sha
    report["prediction_file_sha256"] = hashlib.sha256((HERE / "automated-predictions.json").read_bytes()).hexdigest()
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "sample-agreement.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (destination / "completed-review.csv").write_bytes(args.completed.read_bytes())
    lines = [
        "# Human-versus-automated sample agreement",
        f"Status: {report['status']}",
        f"Reviewed: {report['reviewed']}/{report['sample_total']}",
        f"Agreements among reviewed: {report['agreements']}/{report['reviewed']}",
        f"Agreement fraction: {report['agreement_fraction_reviewed_only']}",
        report["interpretation"], report["automated_fail_stratum"],
        "## Disagreements",
    ]
    lines += [f"- {r['judgment_id']}: human {r['human']}; automated {r['automated_provisional']}. {r['reviewer_notes']}"
              for r in report["disagreements"]]
    if not report["disagreements"]:
        lines.append("None among the completed judgments; pending rows are not agreements.")
    (destination / "sample-agreement.md").write_text("\n\n".join(lines) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "reviewed", "sample_total", "agreements", "agreement_fraction_reviewed_only")}, indent=2))


if __name__ == "__main__":
    main()
