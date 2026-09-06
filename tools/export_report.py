#!/usr/bin/env python3
"""Safe wrapper around Pandoc for /litreview-report's `--export docx|pdf` step.

Per PRODUCT_READINESS_AUDIT.md P0-1: `.claude/settings.json` used to
pre-approve `Bash(pandoc:*)` -- an unrestricted wildcard over a tool that can
load Lua filters and other options capable of executing code or reading/
writing arbitrary paths. This wrapper replaces that pre-approval: it builds
the Pandoc argument list itself from a validated topic slug and format only,
never accepts a filter/resource-path/arbitrary-flag argument, and confines
both the input and every output path to `results/<topic>/manuscript/`.

Usage:
    python3 tools/export_report.py --topic <slug> --format docx|pdf \
        [--reference-doc <path under results/<slug>/>]

Exit code 0 on a verified successful export, 1 on any failure (pandoc
missing, conversion failed, output missing/empty, unsafe path).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.path_policy import UnsafePathError, resolve_under_results, safe_topic_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="review slug")
    parser.add_argument("--format", required=True, choices=["docx", "pdf"])
    parser.add_argument(
        "--reference-doc", default=None,
        help="optional docx styling template, must live under results/<topic>/ "
             "(docx format only -- Pandoc has no equivalent flag for pdf output)",
    )
    args = parser.parse_args(argv)

    try:
        manuscript_dir = safe_topic_path(args.topic, "manuscript")
        input_path = manuscript_dir / "manuscript.md"
        output_path = manuscript_dir / f"manuscript.{args.format}"
        reference_doc_path = None
        if args.reference_doc is not None:
            if args.format != "docx":
                print("Error: --reference-doc is only supported with --format docx", file=sys.stderr)
                return 1
            reference_doc_path = resolve_under_results(args.reference_doc)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not input_path.exists():
        print(f"Error: {input_path} does not exist -- draft the manuscript first", file=sys.stderr)
        return 1

    if shutil.which("pandoc") is None:
        print(
            "Pandoc not found -- install it to enable --export docx/pdf: "
            "https://pandoc.org/installing.html",
            file=sys.stderr,
        )
        return 1

    # Fixed argument shape only: no filters, no resource-path, no passthrough
    # of any flag the caller didn't explicitly validate above.
    pandoc_cmd = ["pandoc", str(input_path), "-o", str(output_path)]
    if reference_doc_path is not None:
        pandoc_cmd.append(f"--reference-doc={reference_doc_path}")

    result = subprocess.run(pandoc_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: pandoc exited {result.returncode}: {result.stderr[:500]}", file=sys.stderr)
        return 1

    if not output_path.exists() or output_path.stat().st_size == 0:
        print(f"Error: pandoc reported success but {output_path} is missing or empty", file=sys.stderr)
        return 1

    print(f"Wrote {output_path} ({output_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
