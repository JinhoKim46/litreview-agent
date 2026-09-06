#!/usr/bin/env python3
"""Dev tool, not part of the automated suite (named _build_expected.py so
tests/ discovery, which only picks up test_*.py, never runs it): (re)generates
this fixture's expected/ directory by actually running the real
reconnaissance pipeline once against the frozen inputs in this same
directory.

Run from the repo root whenever a frozen input here changes, or a module's
output shape legitimately changes:

    python3 tests/fixtures/golden/gig-worker-wellbeing-recon/_build_expected.py

Never hand-edit a file under expected/ -- regenerate it with this script and
let tests/test_golden_reconnaissance_pipeline.py's own comparisons tell you
whether the change was expected.

Companion to tests/fixtures/golden/ponv-drug-a-review/ (M1, systematic
review) and tests/fixtures/golden/youth-digital-literacy-scoping/ (M3,
scoping review): this is M4's golden test for method.id: reconnaissance --
covering what neither of those can: relevance tagging instead of formal
screening, the unconditional non-systematic label, the forbidden-form
lint firing on reconnaissance's own two extra forms (screening_vocabulary,
eligibility_vocabulary), and same-topic promotion to a real method with
the non-independent gold-set notice.
"""
import json
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO_ROOT)

from tests.test_golden_reconnaissance_pipeline import EXPECTED_DIR, FIXTURE_DIR, SLUG
from tools import dedup, label_gate, path_policy, promote_reconnaissance, relevance_tags_gate, search_preflight


def main():
    topic_dir = path_policy.RESULTS_ROOT / SLUG
    if topic_dir.exists():
        shutil.rmtree(topic_dir)
    shutil.copytree(FIXTURE_DIR, topic_dir, ignore=shutil.ignore_patterns("expected", "_build_expected.py"))

    if os.path.exists(EXPECTED_DIR):
        shutil.rmtree(EXPECTED_DIR)
    os.makedirs(EXPECTED_DIR)

    # Stage 1: dedup (no planted duplicates in this fixture)
    dedup.dedupe_raw_files(topic_dir)
    shutil.copy(topic_dir / "records.jsonl", os.path.join(EXPECTED_DIR, "records.jsonl"))

    # Stage 2: corpus description (the deterministic tally a landscape
    # brief reports, computed from relevance_tags_table.json)
    table = relevance_tags_gate.load_relevance_tags_table(topic_dir, SLUG)
    with open(os.path.join(EXPECTED_DIR, "corpus_description.json"), "w") as f:
        json.dump({
            "n_tagged": len(table["studies"]),
            "corpus_description": relevance_tags_gate.corpus_description(table),
        }, f, indent=2)

    # Stage 3: forbidden-form lint on the actual landscape_brief.md draft --
    # must pass clean (no hard failures)
    from tools.method import list_manifests
    manifest = list_manifests()["reconnaissance"]
    brief_text = (topic_dir / "manuscript" / "landscape_brief.md").read_text()
    lint_result = label_gate.lint_text(brief_text, manifest, context="templated_output")
    with open(os.path.join(EXPECTED_DIR, "brief_lint.json"), "w") as f:
        json.dump(lint_result, f, indent=2)

    # Stage 4: label + blockers (the M4 exit criterion's unconditional label)
    label_result = label_gate.compute_label(SLUG)
    with open(os.path.join(EXPECTED_DIR, "label.json"), "w") as f:
        json.dump(label_result, f, indent=2)
    blockers = label_gate.compute_blockers(SLUG)
    with open(os.path.join(EXPECTED_DIR, "blockers.json"), "w") as f:
        json.dump(blockers, f, indent=2)

    # Stage 5: promotion to a real method
    promotion = promote_reconnaissance.promote(topic_dir, SLUG, "scoping_review", "enough prior work found to warrant a fuller map of the space")
    with open(os.path.join(EXPECTED_DIR, "promotion.json"), "w") as f:
        json.dump(promotion, f, indent=2)
    with open(os.path.join(EXPECTED_DIR, "protocol_after_promotion.json"), "w") as f:
        json.dump(json.loads((topic_dir / "protocol.json").read_text()), f, indent=2)

    # Stage 6: the promoted method's own fresh search reruns and re-finds
    # the two recon-db seeds (gw001, gw002) -- records.jsonl does not exist
    # yet post-promotion (archived to recon/), so this is a fresh dedup run
    # over new raw/ input, not the old one carried forward.
    (topic_dir / "raw").mkdir(exist_ok=True)
    fresh_raw = {
        "meta": {"source": "openalex", "query": "gig economy AND wellbeing", "retrieved": 2, "total_available": 2, "truncated": False, "fetched_at": "2026-02-01T00:00:00Z", "purpose": "protocol_driven"},
        "results": [
            {"id": "O1", "title": "Algorithmic Management and Gig Worker Mental Health: A Systematic Review", "authors": ["Alvarez R", "Tan WK"], "year": 2023, "venue": "Journal of Occupational Health Psychology", "doi": "10.3333/gw001", "abstract": "...", "url": "https://doi.org/10.3333/gw001"},
            {"id": "O2", "title": "Platform Work and Burnout: A Survey of Ride-Hailing Drivers", "authors": ["Mensah K"], "year": 2022, "venue": "Work & Stress", "doi": "10.3333/gw002", "abstract": "...", "url": "https://doi.org/10.3333/gw002"},
        ],
    }
    with open(topic_dir / "raw" / "openalex-20260201.json", "w") as f:
        json.dump(fresh_raw, f)
    dedup.dedupe_raw_files(topic_dir)

    status_before_external = search_preflight.search_status(topic_dir)
    with open(os.path.join(EXPECTED_DIR, "search_status_before_external.json"), "w") as f:
        json.dump(status_before_external, f, indent=2)

    # Stage 7: an externally-sourced known item (found by the fresh search,
    # not recon-db-provenanced) clears the non-independent gold-set notice.
    protocol = json.loads((topic_dir / "protocol.json").read_text())
    protocol["known_items"].append({"id_type": "doi", "id": "10.4444/external-item", "note": "cited by a related paper, found independently of the recon search"})
    (topic_dir / "protocol.json").write_text(json.dumps(protocol, indent=2))
    with open(topic_dir / "records.jsonl", "a") as f:
        f.write(json.dumps({"record_id": "openalex:O3", "doi": "10.4444/external-item"}) + "\n")

    status_after_external = search_preflight.search_status(topic_dir)
    with open(os.path.join(EXPECTED_DIR, "search_status_after_external.json"), "w") as f:
        json.dump(status_after_external, f, indent=2)

    shutil.rmtree(topic_dir)
    print(f"Wrote expected/ snapshot under {EXPECTED_DIR}")


if __name__ == "__main__":
    main()
