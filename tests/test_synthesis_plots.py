"""Unit tests for synthesis/plots.py.

plots.py only draws numbers it is handed -- it has no pooling math of its
own -- so the thing worth testing is that the numbers passed in actually
end up at the right place in the rendered SVG. These tests parse the SVG
geometry back into data coordinates (using the axis tick calibration
matplotlib itself renders) and check it against a real worked example:
Fig. 4 of references/papers/kjae-2018-71-2-103.pdf, a 7-study fixed-effect
risk-ratio meta-analysis of homogeneous data. Each study's RR and 95% CI
below is exactly as printed in that figure; the underlying event/total
counts (also in the figure) were cross-checked by hand against RR = (e1/n1)
/ (e2/n2) before writing this file, e.g. study 1 = (3/37)/(6/24) = 0.324 ->
0.32 [0.09, 1.17], study 3 = (17/52)/(36/36) = 0.327 -> 0.33 [0.23, 0.49].
"""
import math
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis import plots

SVG_NS = "{http://www.w3.org/2000/svg}"

# Fig. 4, kjae-2018-71-2-103.pdf: 7-study fixed-effect RR meta-analysis.
STUDIES = [
    {"label": "Study 1", "effect": 0.32, "ci_low": 0.09, "ci_high": 1.17},
    {"label": "Study 2", "effect": 0.46, "ci_low": 0.19, "ci_high": 1.08},
    {"label": "Study 3", "effect": 0.33, "ci_low": 0.23, "ci_high": 0.49},
    {"label": "Study 4", "effect": 0.69, "ci_low": 0.19, "ci_high": 2.45},
    {"label": "Study 5", "effect": 0.93, "ci_low": 0.32, "ci_high": 2.75},
    {"label": "Study 6", "effect": 0.93, "ci_low": 0.50, "ci_high": 1.73},
    {"label": "Study 7", "effect": 0.62, "ci_low": 0.15, "ci_high": 2.48},
]
POOLED = {"effect": 0.52, "ci_low": 0.40, "ci_high": 0.69, "label": "Pooled (M-H, Fixed)"}


def _parse_svg(path):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.parse(path, parser=parser).getroot()


def _find_by_id(root, element_id):
    for el in root.iter():
        if el.get("id") == element_id:
            return el
    raise AssertionError(f"no element with id={element_id!r} in SVG")


def _tick_pixel_data_pairs(axis_group, coord):
    """[(pixel, data_value), ...] for one <g id="matplotlib.axis_N"> group.

    Matplotlib's SVG backend renders each tick label as an XML comment
    (e.g. "<!-- 0.6 -->") immediately preceded by the tick mark's own
    <use x=".." y=".."> (identifiable by its thin stroke-width: 0.8, vs.
    the thicker strokes used for data marks). `coord` is "x" or "y"
    depending on which one varies along this axis.
    """
    pairs = []
    pending = None
    for el in axis_group.iter():
        if el.tag is ET.Comment:
            if pending is not None:
                text = el.text.strip().replace("−", "-")  # unicode minus
                try:
                    pairs.append((pending, float(text)))
                except ValueError:
                    pass
                pending = None
        elif el.tag == SVG_NS + "use" and "stroke-width: 0.8" in el.get("style", ""):
            pending = float(el.get(coord))
    assert len(pairs) >= 2, "could not find enough axis ticks to calibrate"
    return pairs


def _linear_fit(pairs):
    """Least-squares fit of data_value = slope*pixel + intercept."""
    n = len(pairs)
    sx = sum(p for p, _ in pairs)
    sy = sum(d for _, d in pairs)
    sxx = sum(p * p for p, _ in pairs)
    sxy = sum(p * d for p, d in pairs)
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    intercept = (sy - slope * sx) / n
    return lambda px: slope * px + intercept


def _axis_to_data_fn(root, axis_id, coord):
    return _linear_fit(_tick_pixel_data_pairs(_find_by_id(root, axis_id), coord))


def _y_axis_tick_labels(root):
    """Ordered tick-label text along the y axis (top to bottom in the SVG)."""
    axis = _find_by_id(root, "matplotlib.axis_2")
    return [el.text.strip() for el in axis.iter() if el.tag is ET.Comment]


class ForestPlotTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.out_path = os.path.join(self.tmpdir.name, "forest.svg")
        plots.forest_plot(STUDIES, POOLED, self.out_path, null_value=1)
        self.assertTrue(os.path.exists(self.out_path))
        self.assertGreater(os.path.getsize(self.out_path), 0)
        self.root = _parse_svg(self.out_path)

    def test_row_labels_top_to_bottom_match_input_order(self):
        expected = [s["label"] for s in STUDIES] + [POOLED["label"]]
        self.assertEqual(_y_axis_tick_labels(self.root), expected)

    def test_ci_lines_and_markers_match_input_numbers(self):
        px_to_data = _axis_to_data_fn(self.root, "matplotlib.axis_1", "x")

        ci_paths = [
            el.get("d")
            for el in self.root.iter()
            if el.tag == SVG_NS + "path"
            and el.get("style", "") == "fill: none; stroke: #000000; stroke-width: 1.2; stroke-linecap: square"
        ]
        self.assertEqual(len(ci_paths), len(STUDIES), "one CI line expected per study")

        markers = [
            (float(el.get("x")), float(el.get("y")))
            for el in self.root.iter()
            if el.tag == SVG_NS + "use" and el.get("style") == "stroke: #000000; stroke-linejoin: miter"
        ]
        self.assertEqual(len(markers), len(STUDIES), "one square marker expected per study")

        # Document order for both matches the top-to-bottom input order (see
        # forest_plot's own zip(y_positions, studies) loop).
        for study, d, (marker_px, _marker_y) in zip(STUDIES, ci_paths, markers):
            nums = [float(t) for t in d.replace("M", "").replace("L", "").split()]
            (x1, _y1, x2, _y2) = nums
            self.assertAlmostEqual(px_to_data(min(x1, x2)), study["ci_low"], places=2)
            self.assertAlmostEqual(px_to_data(max(x1, x2)), study["ci_high"], places=2)
            self.assertAlmostEqual(px_to_data(marker_px), study["effect"], places=2)

    def test_pooled_diamond_matches_pooled_estimate(self):
        px_to_data = _axis_to_data_fn(self.root, "matplotlib.axis_1", "x")

        diamonds = [
            el.get("d")
            for el in self.root.iter()
            if el.tag == SVG_NS + "path"
            and el.get("style") == "stroke: #000000; stroke-linejoin: miter"
            and el.get("id") is None  # excludes the reusable <defs> marker-symbol path
        ]
        self.assertEqual(len(diamonds), 1, "exactly one pooled diamond expected")
        nums = [float(t) for t in diamonds[0].replace("M", "").replace("L", "").replace("z", "").split()]
        xs = nums[0::2]
        self.assertAlmostEqual(px_to_data(min(xs)), POOLED["ci_low"], places=2)
        self.assertAlmostEqual(px_to_data(max(xs)), POOLED["ci_high"], places=2)
        # apex x (the non-extreme vertex) is the pooled point estimate
        apex_x = [x for x in xs if x not in (min(xs), max(xs))][0]
        self.assertAlmostEqual(px_to_data(apex_x), POOLED["effect"], places=2)

    def test_reference_line_drawn_at_null_value(self):
        px_to_data = _axis_to_data_fn(self.root, "matplotlib.axis_1", "x")
        ref_line = _find_by_id(self.root, "line2d_1")
        path = next(el for el in ref_line.iter() if el.tag == SVG_NS + "path")
        x = float(path.get("d").split()[1])
        self.assertAlmostEqual(px_to_data(x), 1, places=2)

    def test_single_study_default_null_value_zero(self):
        out_path = os.path.join(self.tmpdir.name, "forest_single.svg")
        one_study = [{"label": "Only study", "effect": 0.5, "ci_low": 0.1, "ci_high": 0.9}]
        one_pooled = {"effect": 0.5, "ci_low": 0.1, "ci_high": 0.9, "label": "Pooled"}
        plots.forest_plot(one_study, one_pooled, out_path)  # null_value defaults to 0
        self.assertTrue(os.path.getsize(out_path) > 0)
        root = _parse_svg(out_path)
        px_to_data = _axis_to_data_fn(root, "matplotlib.axis_1", "x")
        ref_line = _find_by_id(root, "line2d_1")
        path = next(el for el in ref_line.iter() if el.tag == SVG_NS + "path")
        x = float(path.get("d").split()[1])
        self.assertAlmostEqual(px_to_data(x), 0, places=2)


class FunnelPlotTest(unittest.TestCase):
    def setUp(self):
        # Funnel plots conventionally use the log risk ratio and its SE
        # (from the 95% CI: se = (ln(high) - ln(low)) / (2 * 1.959964)).
        self.log_studies = []
        for s in STUDIES:
            se = (math.log(s["ci_high"]) - math.log(s["ci_low"])) / (2 * 1.959964)
            self.log_studies.append({"effect": math.log(s["effect"]), "se": se})

        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.out_path = os.path.join(self.tmpdir.name, "funnel.svg")
        plots.funnel_plot(self.log_studies, self.out_path)
        self.assertTrue(os.path.exists(self.out_path))
        self.assertGreater(os.path.getsize(self.out_path), 0)
        self.root = _parse_svg(self.out_path)

    def test_scatter_points_match_effect_and_precision(self):
        x_of = _axis_to_data_fn(self.root, "matplotlib.axis_1", "x")
        y_of = _axis_to_data_fn(self.root, "matplotlib.axis_2", "y")

        collection = _find_by_id(self.root, "PathCollection_1")
        points = [
            (float(el.get("x")), float(el.get("y")))
            for el in collection.iter()
            if el.tag == SVG_NS + "use" and el.get("style") == "stroke: #000000"
        ]
        self.assertEqual(len(points), len(self.log_studies))

        # Scatter preserves input order, so points line up 1:1 with studies.
        for study, (px, py) in zip(self.log_studies, points):
            self.assertAlmostEqual(x_of(px), study["effect"], places=2)
            self.assertAlmostEqual(y_of(py), 1.0 / study["se"], places=1)


class RobTrafficLightPlotTest(unittest.TestCase):
    STUDIES = [
        {"label": "Smith 2019", "domains": {"d1": "low", "d2": "unclear"}, "overall": "some concerns"},
        {"label": "Jones 2020", "domains": {"d1": "high", "d2": "low"}, "overall": "high risk"},
    ]
    DOMAIN_LABELS = [("d1", "D1"), ("d2", "D2")]

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.out_path = os.path.join(self.tmpdir.name, "rob.svg")
        plots.rob_traffic_light_plot(self.STUDIES, self.DOMAIN_LABELS, self.out_path)
        self.assertTrue(os.path.exists(self.out_path))
        self.assertGreater(os.path.getsize(self.out_path), 0)
        self.root = _parse_svg(self.out_path)

    def _circle_fill_colors(self):
        """Fill colors of every circle patch, in document (row-major) order --
        excludes the white figure/axes background patches, which always come
        first and are never a judgement color."""
        colors = []
        for i in range(1, 100):
            patch = _find_by_id_or_none(self.root, f"patch_{i}")
            if patch is None:
                break
            path = patch.find(SVG_NS + "path")
            style = path.get("style", "") if path is not None else ""
            if "fill: #ffffff" not in style and "fill:" in style:
                colors.append(style.split("fill:")[1].split(";")[0].strip())
        return colors

    def test_column_headers_are_domain_labels_plus_overall(self):
        headers = [el.text.strip() for el in _find_by_id(self.root, "matplotlib.axis_1").iter() if el.tag is ET.Comment]
        self.assertEqual(headers, ["D1", "D2", "Overall"])

    def test_row_labels_bottom_to_top_are_reversed_input_order(self):
        rows = [el.text.strip() for el in _find_by_id(self.root, "matplotlib.axis_2").iter() if el.tag is ET.Comment]
        self.assertEqual(rows, ["Jones 2020", "Smith 2019"])  # y=0 (bottom) is the last input study

    def test_circle_colors_match_judgement_in_row_major_order(self):
        # Smith: d1=low(green), d2=unclear(amber), overall=some concerns(amber)
        # Jones: d1=high(red), d2=low(green), overall=high risk(red)
        self.assertEqual(
            self._circle_fill_colors(),
            [
                plots.JUDGEMENT_COLORS["low"],
                plots.JUDGEMENT_COLORS["unclear"],
                plots.JUDGEMENT_COLORS["some concerns"],
                plots.JUDGEMENT_COLORS["high"],
                plots.JUDGEMENT_COLORS["low"],
                plots.JUDGEMENT_COLORS["high risk"],
            ],
        )

    def test_unrecognized_judgement_renders_grey_not_raises(self):
        studies = [{"label": "Unassessed", "domains": {"d1": "not yet assessed", "d2": "low"}, "overall": "low risk"}]
        out_path = os.path.join(self.tmpdir.name, "rob_unassessed.svg")
        plots.rob_traffic_light_plot(studies, self.DOMAIN_LABELS, out_path)  # must not raise
        self.assertTrue(os.path.getsize(out_path) > 0)

    def test_overall_column_omitted_when_overall_key_is_none(self):
        out_path = os.path.join(self.tmpdir.name, "rob_no_overall.svg")
        plots.rob_traffic_light_plot(self.STUDIES, self.DOMAIN_LABELS, out_path, overall_key=None)
        root = _parse_svg(out_path)
        headers = [el.text.strip() for el in _find_by_id(root, "matplotlib.axis_1").iter() if el.tag is ET.Comment]
        self.assertEqual(headers, ["D1", "D2"])


def _find_by_id_or_none(root, element_id):
    for el in root.iter():
        if el.get("id") == element_id:
            return el
    return None


if __name__ == "__main__":
    unittest.main()
