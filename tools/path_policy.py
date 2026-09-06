"""Shared path-safety policy for every writer/reader that takes a
caller-supplied path: connector `--out`/`--query-file`, synthesis `--topic`,
and the manuscript-export wrapper.

Per PRODUCT_READINESS_AUDIT.md P0-1: a pre-approved connector or synthesis
Bash permission lets any turn (a crafted instruction, a compromised upstream
record, or an agent mistake) pass an arbitrary `--out`/`--out-dir` path,
which `open(path, "w")` honors with zero validation -- an arbitrary-file-write
primitive. Every path this repo writes to (or reads a query plan from) must
resolve inside `results/`, the one directory tree this repo's own state lives
under -- never outside it, and never through a symlink planted inside
`results/` that points somewhere else.

Stdlib only, no repo-internal imports (so both `connectors/_shared.py` and
`synthesis/run_synthesis.py` can depend on this without a circular import
between those two otherwise-unrelated packages).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = (ROOT / "results").resolve()

# Same slug shape /litreview-init already derives topic directories with
# (lowercase, hyphen-separated, no leading/trailing/double hyphen) -- kept
# here as the one place that shape is enforced for anything that resolves a
# filesystem path from it.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG_LEN = 60


class UnsafePathError(ValueError):
    """A caller-supplied slug or path failed this repo's containment policy."""


def validate_topic_slug(slug: str) -> str:
    """Raise UnsafePathError unless `slug` is a bare, traversal-free topic name."""
    if not isinstance(slug, str) or not slug or len(slug) > MAX_SLUG_LEN or not _SLUG_RE.match(slug):
        raise UnsafePathError(
            f"invalid topic slug {slug!r}: must be 1-{MAX_SLUG_LEN} lowercase "
            "letters/digits/hyphens, no leading/trailing/double hyphen, and "
            "no path separators"
        )
    return slug


def resolve_under_results(path_str: str) -> Path:
    """Resolve `path_str` and require the result stay inside `results/`.

    Resolves symlinks (`Path.resolve()` always does, even for a path that
    does not exist yet) so a symlink planted inside `results/` pointing
    outside it is caught the same way a literal `../` or an absolute path
    outside `results/` is. Works for both existing and not-yet-created
    paths -- callers may pass a path for a file/directory about to be created.
    """
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(RESULTS_ROOT)
    except ValueError as exc:
        raise UnsafePathError(
            f"path {path_str!r} resolves to {resolved}, which is outside "
            f"{RESULTS_ROOT} -- refusing to read/write there"
        ) from exc
    return resolved


def safe_topic_path(slug: str, *parts: str) -> Path:
    """Validate `slug` and resolve `results/<slug>/<parts...>` under `results/`."""
    validate_topic_slug(slug)
    return resolve_under_results(os.path.join("results", slug, *parts))


def demo() -> None:
    assert validate_topic_slug("streptococcus-suis-infection") == "streptococcus-suis-infection"
    for bad in ("", "Has-Upper", "has_underscore", "-leading-hyphen", "trailing-hyphen-",
                "double--hyphen", "a/b", "a" * (MAX_SLUG_LEN + 1)):
        try:
            validate_topic_slug(bad)
            raise AssertionError(f"expected UnsafePathError for slug {bad!r}")
        except UnsafePathError:
            pass

    ok = resolve_under_results("results/some-topic/raw/pubmed-20260905.json")
    assert ok == RESULTS_ROOT / "some-topic" / "raw" / "pubmed-20260905.json"

    for bad_path in ("../etc/passwd", "/etc/passwd", "results/some-topic/../../../etc/passwd",
                      str(ROOT / "connectors" / "_shared.py")):
        try:
            resolve_under_results(bad_path)
            raise AssertionError(f"expected UnsafePathError for path {bad_path!r}")
        except UnsafePathError:
            pass

    print("OK: path_policy self-check passed")


if __name__ == "__main__":
    demo()
