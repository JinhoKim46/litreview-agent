"""Forest and funnel plots for /prisma-synthesize, rendered to SVG via matplotlib.

No hand-rolled pooling math here -- these functions only draw numbers that
synthesis/pooling.py and synthesis/heterogeneity.py already computed.
"""
import os

import matplotlib

matplotlib.use("Agg")  # headless: no display server in a Claude Code sandbox / CI

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon


def _atomic_savefig(fig, out_path, **kwargs):
    """Save `fig` via a temp sibling file + os.replace, so a crash mid-render
    can never leave a partially-written SVG as the canonical artifact
    (PRODUCT_READINESS_AUDIT.md P0-1)."""
    tmp_path = f"{out_path}.tmp{os.getpid()}"
    fig.savefig(tmp_path, **kwargs)
    os.replace(tmp_path, out_path)


# Shared low/high/unclear (RoB2 domain-level) and low risk/some concerns/high
# risk (three-tier overall) judgement vocabularies both map onto one
# green/amber/red traffic-light palette -- see rob_traffic_light_plot below.
JUDGEMENT_COLORS = {
    "low": "#2ca02c",
    "low risk": "#2ca02c",
    "high": "#d62728",
    "high risk": "#d62728",
    "unclear": "#f2c744",
    "some concerns": "#f2c744",
}
JUDGEMENT_SYMBOLS = {
    "low": "+",
    "low risk": "+",
    "high": "−",
    "high risk": "−",
    "unclear": "?",
    "some concerns": "?",
}


def forest_plot(studies, pooled, out_path, null_value=0):
    """Render a forest plot to `out_path` (SVG).

    studies: list of {"label": str, "effect": float, "ci_low": float, "ci_high": float},
        one row per study, drawn top to bottom in the given order.
    pooled: {"effect": float, "ci_low": float, "ci_high": float, "label": str},
        drawn as a diamond in its own row below the studies.
    null_value: x-position of the reference line (0 for MD/SMD, 1 for OR/RR).
    """
    n = len(studies)
    fig_height = max(2.0, 0.5 * (n + 2))
    fig, ax = plt.subplots(figsize=(8, fig_height))

    # Row y=n..1 for studies (top to bottom), y=0 for the pooled diamond.
    y_positions = list(range(n, 0, -1))
    for y, study in zip(y_positions, studies):
        ax.plot([study["ci_low"], study["ci_high"]], [y, y], color="black", linewidth=1.2, zorder=2)
        ax.plot(study["effect"], y, marker="s", color="black", markersize=7, zorder=3)

    # Pooled diamond: horizontal extent = CI, apex points at the row's vertical center.
    diamond = Polygon(
        [
            (pooled["ci_low"], 0),
            (pooled["effect"], 0.35),
            (pooled["ci_high"], 0),
            (pooled["effect"], -0.35),
        ],
        closed=True,
        facecolor="black",
        edgecolor="black",
        zorder=3,
    )
    ax.add_patch(diamond)

    ax.axvline(null_value, color="gray", linestyle="--", linewidth=1, zorder=1)

    labels = [study["label"] for study in studies] + [pooled["label"]]
    ax.set_yticks(y_positions + [0])
    ax.set_yticklabels(labels)
    ax.set_ylim(-1, n + 1)
    ax.set_xlabel("Effect size (95% CI)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    _atomic_savefig(fig, out_path, format="svg")
    plt.close(fig)


def funnel_plot(studies, out_path):
    """Render a funnel plot to `out_path` (SVG): effect (x) vs. 1/SE (y).

    studies: list of {"effect": float, "se": float}.

    Callers should only call this when there are >= 10 studies contributing to
    the pooled outcome -- funnel-plot asymmetry is not a reliable publication-bias
    signal with fewer studies (this function does not enforce that gate itself).
    """
    effects = [study["effect"] for study in studies]
    precisions = [1.0 / study["se"] for study in studies]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(effects, precisions, color="black", zorder=2)
    ax.set_xlabel("Effect size")
    ax.set_ylabel("1 / SE (precision)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    _atomic_savefig(fig, out_path, format="svg")
    plt.close(fig)


def rob_traffic_light_plot(studies, domain_labels, out_path, overall_key="overall"):
    """Render a Cochrane-RoB2-style "traffic light" plot to `out_path` (SVG):
    one row per study, one column per risk-of-bias domain plus an optional
    "Overall" column, each cell a green/amber/red circle.

    studies: list of {"label": str, "domains": {domain_key: "low"|"high"|"unclear", ...},
        "overall": "low risk"|"some concerns"|"high risk"} -- "overall" is optional,
        omit `overall_key` (pass None) to skip that column entirely.
    domain_labels: ordered list of (domain_key, short_column_header) pairs, e.g.
        [("sequence_generation", "D1"), ("allocation_concealment", "D2"), ...].
        Short headers keep columns narrow; the caller is responsible for a
        legend mapping D1..Dn back to full domain names elsewhere in the
        manuscript (e.g. a table note), matching how robvis itself labels
        RoB2 columns.
    A judgement string not in JUDGEMENT_COLORS (e.g. a domain the reviewer
    hasn't assessed yet) renders as a grey "?" circle rather than raising --
    a partially-assessed study should not block plotting the rest.
    """
    columns = list(domain_labels)
    if overall_key:
        columns = columns + [(overall_key, "Overall")]

    n_studies = len(studies)
    n_cols = len(columns)
    fig, ax = plt.subplots(figsize=(1.2 * n_cols + 2, 0.5 * n_studies + 1))

    for row, study in enumerate(studies):
        y = n_studies - row - 1
        for col, (key, _header) in enumerate(columns):
            judgement = study.get(overall_key) if overall_key and key == overall_key else study.get("domains", {}).get(key)
            judgement = (judgement or "").strip().lower()
            color = JUDGEMENT_COLORS.get(judgement, "#999999")
            symbol = JUDGEMENT_SYMBOLS.get(judgement, "?")
            ax.add_patch(Circle((col, y), 0.4, facecolor=color, edgecolor="black", zorder=2))
            ax.text(col, y, symbol, ha="center", va="center", color="white", fontsize=9, fontweight="bold", zorder=3)

    ax.set_xlim(-0.6, n_cols - 0.4)
    ax.set_ylim(-0.6, n_studies - 0.4)
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels([header for _, header in columns], rotation=45, ha="right")
    ax.set_yticks(range(n_studies))
    ax.set_yticklabels([study["label"] for study in reversed(studies)])
    ax.set_aspect("equal")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    _atomic_savefig(fig, out_path, format="svg")
    plt.close(fig)


if __name__ == "__main__":
    import tempfile

    example_studies = [
        {"label": "Smith 2019", "effect": 0.5, "ci_low": 0.1, "ci_high": 0.9},
        {"label": "Jones 2020", "effect": 0.3, "ci_low": -0.1, "ci_high": 0.7},
        {"label": "Lee 2021", "effect": 0.6, "ci_low": 0.2, "ci_high": 1.0},
    ]
    example_pooled = {"effect": 0.45, "ci_low": 0.2, "ci_high": 0.7, "label": "Pooled (random-effects)"}

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "forest_plot.svg")
        forest_plot(example_studies, example_pooled, out_path)
        assert os.path.exists(out_path), "forest_plot did not create a file"
        assert os.path.getsize(out_path) > 0, "forest_plot created an empty file"
        print(f"OK: forest_plot self-check passed ({os.path.getsize(out_path)} bytes)")

        example_rob_studies = [
            {"label": "Smith 2019", "domains": {"d1": "low", "d2": "unclear", "d3": "low"}, "overall": "some concerns"},
            {"label": "Jones 2020", "domains": {"d1": "high", "d2": "low", "d3": "low"}, "overall": "high risk"},
        ]
        rob_out_path = os.path.join(tmpdir, "rob_traffic_light.svg")
        rob_traffic_light_plot(
            example_rob_studies,
            domain_labels=[("d1", "D1"), ("d2", "D2"), ("d3", "D3")],
            out_path=rob_out_path,
        )
        assert os.path.exists(rob_out_path), "rob_traffic_light_plot did not create a file"
        assert os.path.getsize(rob_out_path) > 0, "rob_traffic_light_plot created an empty file"
        print(f"OK: rob_traffic_light_plot self-check passed ({os.path.getsize(rob_out_path)} bytes)")
