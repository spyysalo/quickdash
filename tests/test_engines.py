"""Identical behavioral cases exercise native Python and the actual browser engine."""

import csv
import io
import json
import math
import random
import re
import subprocess
import unittest
import warnings
from copy import deepcopy
from pathlib import Path
from quickdash import analyze, compare, load_config, QuickdashWarning, DiagnosticError
from quickdash.io import parse_csv, parse_yaml
from quickdash.config import assemble_catalogue

ROOT = Path(__file__).resolve().parent.parent


def fixture():
    catalogue = dict(
        version=1,
        name="Fixture",
        evals=[
            dict(
                name="E",
                category="C",
                match={"regex": "e_.+"},
                metric="acc",
                metric_filter="none",
                score={"scale": 1},
                normalize={"min": 0.25, "max": 1},
            )
        ],
        languages=[
            dict(tasks=["e_en"], scope="single", language="eng_Latn"),
            dict(tasks=["e_fr"], scope="single", language="fra_Latn"),
        ],
    )
    return dict(
        catalogue=catalogue,
        profile=dict(version=1, name="Weights", weights={"C": 1}),
        suite=dict(version=1, name="Available", mode="available"),
    )


def row(task="e_en", value=".625", **kwargs):
    return {
        **dict(
            checkpoint="A",
            task=task,
            metric="acc",
            filter="none",
            n_shot="0",
            harness="fixture",
            backend="cpu",
            value=value,
        ),
        **kwargs,
    }


def paired(rows):
    return rows + [{**r, "checkpoint": "B", "value": ".4"} for r in rows]


def native(c):
    try:
        cfg = (
            load_config(
                catalogue=parse_yaml(c["yaml"]["catalogue"]),
                weights=parse_yaml(c["yaml"]["profile"]),
                eval_set=parse_yaml(c["yaml"]["suite"]),
            )
            if "yaml" in c
            else c["config"]
        )
        if "eval_definitions" in c:
            cfg = deepcopy(cfg)
            cfg["catalogue"] = assemble_catalogue(
                cfg["catalogue"], c["eval_definitions"]
            )
        rows = parse_csv(c["csv"]) if "csv" in c else c["rows"]
        value = (
            compare(
                rows,
                cfg,
                a=c.get("a", "A"),
                b=c.get("b", "B"),
                diagnostics="collect",
                matching=c.get("matching", "strict"),
            )
            if c.get("operation") == "compare"
            else analyze(
                rows, cfg, diagnostics="collect", matching=c.get("matching", "strict")
            )
        )
        return {"value": value}
    except ValueError as error:
        return {"error": True, "message": str(error)}


def semantics(value):
    # Human-facing wording is deliberately not a cross-language API contract.
    if isinstance(value, dict):
        return {
            k: semantics(v) for k, v in value.items() if k not in ("detail", "variants")
        }
    if isinstance(value, list):
        return [semantics(v) for v in value]
    return value


class Engines(unittest.TestCase):
    def close(self, a, b, path="result"):
        if isinstance(a, dict):
            self.assertEqual(a.keys(), b.keys(), path)
            for k in a:
                self.close(a[k], b[k], path + "." + k)
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b), path)
            for i, (x, y) in enumerate(zip(a, b)):
                self.close(x, y, f"{path}[{i}]")
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            self.assertIsInstance(b, (int, float), path)
            self.assertTrue(
                math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9), f"{path}: {a} != {b}"
            )
        else:
            self.assertEqual(a, b, path)

    def both(self, cases):
        js = json.loads(
            subprocess.check_output(
                ["node", "tests/engine_adapter.cjs"],
                input=json.dumps(cases),
                text=True,
                cwd=ROOT,
            )
        )
        self.assertEqual(len(js), len(cases), "Every case must produce a JS result")
        results = []
        for i, (case, other) in enumerate(zip(cases, js)):
            py = native(case)
            with self.subTest(case=i):
                self.assertEqual("error" in py, "error" in other, (py, other, case))
                if "error" not in py:
                    self.close(semantics(py["value"]), semantics(other["value"]))
            results.append((py, other))
        return results

    def test_documented_eval_sets_resolve_in_both_engines(self):
        section = (ROOT / "docs/configuration.md").read_text().split("## Strict and relaxed matching")[0]
        examples = [parse_yaml(block) for block in re.findall(r"```yaml\n(.*?)```", section, re.S)]
        self.assertTrue(examples, "The eval-set guide must contain executable examples")
        base = load_config(catalogue=ROOT / "configs/catalogue.yaml",
                           weights=ROOT / "configs/weights/oellm.yaml")
        rows = parse_csv((ROOT / "examples/sample-evals.csv").read_text())
        cases = [dict(config={**base, "suite": suite}, rows=rows) for suite in examples]
        for results in self.both(cases):
            for result in results:
                self.assertNotIn("error", result)

    def test_per_eval_catalogue_assembly(self):
        original = fixture()
        metadata = {"version": 1, "name": "Fixture", "notes": ["Shared catalogue"]}
        definition = {
            **original["catalogue"]["evals"][0],
            "languages": original["catalogue"]["languages"],
        }
        c = {**original, "catalogue": metadata}
        good = dict(
            config=c,
            eval_definitions=[definition],
            rows=paired([row(), row("e_fr")]),
            operation="compare",
        )
        reference_case = {k: v for k, v in good.items() if k != "eval_definitions"}
        reference_case["config"] = {
            **original,
            "catalogue": {**original["catalogue"], "notes": metadata["notes"]},
        }
        reference = native(reference_case)
        for result in self.both([good])[0]:
            self.assertNotIn("error", result)
            self.close(semantics(result), semantics(reference))
            self.assertEqual(result["value"]["a"]["score"], 50)
        invalid = []
        for definitions in ([], None, [None], [definition, definition]):
            invalid.append({**good, "eval_definitions": definitions})
        for mutate in (
            lambda e: e.pop("languages"),
            lambda e: e.update(languages={}),
            lambda e: e.update(unexpected=True),
            lambda e: e["languages"][0].update(tasks=["foreign_task"]),
            lambda e: e["languages"][0].update(language="de"),
            lambda e: e["languages"].append(deepcopy(e["languages"][0])),
        ):
            e = deepcopy(definition)
            mutate(e)
            invalid.append({**good, "eval_definitions": [e]})
        # Overlap across files is rejected for explicitly assigned tasks.
        overlap = deepcopy(definition)
        overlap.update(name="Other", languages=[])
        invalid.append({**good, "eval_definitions": [definition, overlap]})
        for outputs in self.both(invalid):
            for result in outputs:
                self.assertIn("error", result)
        # Adding entries changes the result according to their data, not file count.
        for size in (1, 3, 7):
            definitions = []
            rows = []
            for i in range(size):
                e = deepcopy(definition)
                e.update(
                    name=f"Eval {i}",
                    match={"name": f"task{i}"},
                    languages=[
                        dict(tasks=[f"task{i}"], scope="single", language="eng_Latn")
                    ],
                )
                definitions.append(e)
                rows.append(row(f"task{i}", ".625"))
            for result in self.both(
                [dict(config=c, eval_definitions=definitions, rows=rows)]
            )[0]:
                self.assertNotIn("error", result)
                self.assertEqual(result["value"]["models"][0]["score"], 50)

    def test_language_metadata_defaults_and_local_overrides(self):
        original = fixture()
        metadata = {"version": 1, "name": "Fixture"}
        definition = {
            **original["catalogue"]["evals"][0],
            "language_defaults": {
                "evidence": "https://example.org/shared",
                "note": "Shared explanation",
            },
            "languages": deepcopy(original["catalogue"]["languages"]),
        }
        definition["languages"][1]["note"] = "French-specific explanation"
        reference = deepcopy(original)
        reference["catalogue"]["languages"][0].update(definition["language_defaults"])
        reference["catalogue"]["languages"][1].update(
            evidence="https://example.org/shared", note="French-specific explanation"
        )
        case = dict(
            config={**original, "catalogue": metadata},
            eval_definitions=[definition],
            rows=paired([row(), row("e_fr")]),
            operation="compare",
        )
        before = deepcopy(case)
        expected = native(
            dict(config=reference, rows=case["rows"], operation="compare")
        )
        for result in self.both([case])[0]:
            self.assertNotIn("error", result)
            self.close(semantics(result), semantics(expected))
        self.assertEqual(case, before)
        compiled = assemble_catalogue(metadata, [definition])
        self.assertEqual(compiled, reference["catalogue"])
        # An explicit empty string clears an inherited value; omitted fields inherit independently.
        definition["languages"][1].update(evidence="", note="")
        reference["catalogue"]["languages"][1].update(evidence="", note="")
        expected = native(
            dict(config=reference, rows=case["rows"], operation="compare")
        )
        for result in self.both([case])[0]:
            self.assertNotIn("error", result)
            self.close(semantics(result), semantics(expected))
        invalid = []
        for defaults in (
            None,
            [],
            "note",
            {"note": False},
            {"evidence": None},
            {"evidence": "file:///tmp/source"},
            {"scope": "single"},
            {"language": "eng_Latn"},
        ):
            bad = deepcopy(case)
            bad["eval_definitions"][0]["language_defaults"] = defaults
            invalid.append(bad)
            # Bad defaults remain invalid even when all local fields override them or there are no groups.
            empty = deepcopy(bad)
            empty["eval_definitions"][0]["languages"] = []
            invalid.append(empty)
        for outputs in self.both(invalid):
            for result in outputs:
                self.assertIn("error", result)

    def test_language_scope_inference_and_explicit_overrides(self):
        c = fixture()
        metadata = {"version": 1, "name": "Fixture"}
        assignments = [
            dict(language="eng_Latn"),
            dict(language="fra_Latn"),
            dict(source_language="eng_Latn", target_language="fra_Latn"),
            dict(language="mul"),
            dict(language="srp_Latn", scope="pooled"),
            dict(language="srp_Latn", scope="single"),
        ]
        cases = []
        for fields, scope in zip(
            assignments,
            ["single", "single", "translation", "pooled", "pooled", "single"],
        ):
            group = dict(tasks=["e_en"], **fields)
            definition = {**c["catalogue"]["evals"][0], "languages": [group]}
            expected = {**group, "scope": scope}
            self.assertEqual(
                assemble_catalogue(metadata, [definition])["languages"], [expected]
            )
            reference = deepcopy(c)
            reference["catalogue"]["languages"] = [expected]
            case = dict(
                config={**c, "catalogue": metadata},
                eval_definitions=[definition],
                rows=[row()],
            )
            cases.append(case)
            for result in self.both([case])[0]:
                self.assertNotIn("error", result)
                self.close(
                    semantics(result),
                    semantics(native(dict(config=reference, rows=[row()]))),
                )
        bad_fields = [
            {},
            dict(language="mul", scope="single"),
            dict(source_language="eng_Latn"),
            dict(target_language="fra_Latn"),
            dict(
                language="eng_Latn",
                source_language="eng_Latn",
                target_language="fra_Latn",
            ),
            dict(language="eng_Latn", scope="translation"),
            dict(
                source_language="eng_Latn", target_language="fra_Latn", scope="single"
            ),
            dict(language="eng_Latn", scope=None),
            dict(language="eng_Latn", scope="guess"),
        ]
        invalid = []
        for fields in bad_fields:
            definition = {
                **c["catalogue"]["evals"][0],
                "languages": [dict(tasks=["e_en"], **fields)],
            }
            invalid.append(
                dict(
                    config={**c, "catalogue": metadata},
                    eval_definitions=[definition],
                    rows=[row()],
                )
            )
        for outputs in self.both(invalid):
            for result in outputs:
                self.assertIn("error", result)

    def test_clipping_defaults_to_true(self):
        cases = []
        for clip in (None, True, False):
            c = fixture()
            if clip is not None:
                c["catalogue"]["evals"][0]["normalize"]["clip"] = clip
            cases.append(dict(config=c, rows=[row(value=".1")]))
        for outputs, score in zip(self.both(cases), (0, 0, -20)):
            for result in outputs:
                self.assertNotIn("error", result)
                self.assertAlmostEqual(result["value"]["models"][0]["score"], score)

    def test_strict_fewshot_warnings_are_grouped_without_duplicate_coverage_warnings(
        self,
    ):
        c = fixture()
        c["catalogue"]["evals"][0]["shots"] = 5
        rr = [row(t, n_shot="0") for t in ["e_en", "e_fr"]]
        cases = []
        for mode in ["available", "fixed"]:
            cfg = deepcopy(c)
            if mode == "fixed":
                cfg["suite"] = dict(
                    version=1, name="Required", mode=mode, evals=[dict(name="E")]
                )
            cases.append(dict(config=cfg, rows=rr))
        for i, results in enumerate(self.both(cases)):
            for result in results:
                report = result["value"]
                self.assertEqual(
                    [d["code"] for d in report["diagnostics"]], ["strict_shot_setting"]
                )
                d = report["diagnostics"][0]
                self.assertEqual(
                    (
                        d["eval"],
                        d["model"],
                        d["expected_shots"],
                        d["actual_shots"],
                        d["effect"],
                    ),
                    ("E", "A", 5, 0, "excluded"),
                )
                self.assertEqual(d["tasks"], ["e_en", "e_fr"])
                self.assertEqual(len(d["measurement_ids"]), 2)
                self.assertIsNone(report["models"][0]["score"])
                self.assertTrue(
                    all(
                        not m["included"] and m["effective_weight"] == 0
                        for m in report["models"][0]["measurements"]
                    )
                )
                if i == 1:
                    self.assertEqual(len(report["coverage"][0]["missing"]), 2)
        # Each actual setting has its own group; another protocol doesn't inflate the task count.
        many = rr + [row("e_en", n_shot="0", backend="other"), row("e_fr", n_shot="3")]
        for result in self.both([dict(config=c, rows=many)])[0]:
            ds = result["value"]["diagnostics"]
            self.assertEqual([d["actual_shots"] for d in ds], [0, 3])
            self.assertEqual([len(d["tasks"]) for d in ds], [2, 1])
        # Exact selected data makes alternative shots harmless for that task.
        for result in self.both([dict(config=c, rows=rr + [row(n_shot="5")])])[0]:
            ds = result["value"]["diagnostics"]
            self.assertEqual(len(ds), 1)
            self.assertEqual(ds[0]["tasks"], ["e_fr"])
            self.assertEqual(result["value"]["models"][0]["score"], 50)
        # Preserve genuinely absent requirements and other causes (wrong metric/filter).
        cfg = deepcopy(c)
        cfg["catalogue"]["languages"][0]["tasks"] += [
            "e_missing",
            "e_wrong_metric",
            "e_wrong_filter",
        ]
        cfg["suite"] = dict(
            version=1, name="Required", mode="fixed", evals=[dict(name="E", shots=10)]
        )
        mixed = rr + [
            row("e_wrong_metric", metric="other"),
            row("e_wrong_filter", filter="other"),
        ]
        for result in self.both([dict(config=cfg, rows=mixed)])[0]:
            ds = result["value"]["diagnostics"]
            shot = next(d for d in ds if d["code"] == "strict_shot_setting")
            self.assertEqual(shot["expected_shots"], 10)
            self.assertEqual(shot["tasks"], ["e_en", "e_fr"])
            missing = next(d for d in ds if d["code"] == "missing_suite_data")
            self.assertEqual(
                missing["tasks"], ["e_missing", "e_wrong_filter", "e_wrong_metric"]
            )
            self.assertIn("missing_scoring_field", {d["code"] for d in ds})
            self.assertIn("missing_scoring_setting", {d["code"] for d in ds})
        # Excluded languages never enter the mismatch count.
        cfg["suite"]["evals"][0]["exclude_languages"] = ["fra_Latn"]
        for result in self.both([dict(config=cfg, rows=rr)])[0]:
            ds = result["value"]["diagnostics"]
            shot = next(d for d in ds if d["code"] == "strict_shot_setting")
            self.assertEqual(shot["tasks"], ["e_en"])
            self.assertIn("not_used", {d["code"] for d in ds})
        # Counts are grouped independently for each model.
        for result in self.both([dict(config=c, rows=paired(rr))])[0]:
            ds = result["value"]["diagnostics"]
            self.assertEqual(
                [d["code"] for d in ds], ["strict_shot_setting", "strict_shot_setting"]
            )
            self.assertEqual([d["model"] for d in ds], ["A", "B"])
            self.assertEqual(
                [d["tasks"] for d in ds], [["e_en", "e_fr"], ["e_en", "e_fr"]]
            )
        # Relaxed mode retains its own warning.
        for result in self.both([dict(config=c, rows=paired(rr), matching="relaxed")])[
            0
        ]:
            ds = result["value"]["diagnostics"]
            self.assertEqual(
                [d["code"] for d in ds],
                ["relaxed_shot_setting", "relaxed_shot_setting"],
            )

    def test_relaxed_fewshot_selection_and_warnings(self):
        c = fixture()
        c["catalogue"]["evals"][0]["shots"] = 5
        rr = [row(n_shot="5"), row(checkpoint="B", n_shot="0", value=".4")]
        case = dict(config=c, rows=rr, operation="compare", matching="relaxed")
        for result in self.both([case])[0]:
            self.assertNotIn("error", result)
            r = result["value"]
            self.assertAlmostEqual(r["delta"], 30)
            self.assertTrue(r["inconsistent"])
            self.assertEqual(r["b"]["measurements"][0]["n_shot"], "0")
            self.assertEqual(
                r["deltas"][0]["measurement_b"], r["b"]["measurements"][0]["id"]
            )
            warnings = [
                d for d in r["diagnostics"] if d["code"] == "relaxed_shot_setting"
            ]
            self.assertEqual(
                [
                    (d["model"], d["expected_shots"], d["actual_shots"])
                    for d in warnings
                ],
                [("B", 5, 0)],
            )
        for result in self.both([{**case, "matching": "strict"}])[0]:
            self.assertIsNone(result["value"]["delta"])
            self.assertFalse(result["value"]["inconsistent"])
        # Exact settings win, irrespective of score; an unused alternative's value is not validated.
        more = rr + [
            row(checkpoint="B", n_shot="5", value=".55"),
            row(checkpoint="B", n_shot="1", value="NaN"),
        ]
        for result in self.both([{**case, "rows": more}])[0]:
            self.assertNotIn("error", result)
            r = result["value"]
            self.assertAlmostEqual(r["delta"], 10)
            self.assertFalse(r["inconsistent"])
            self.assertEqual(
                [m["n_shot"] for m in r["b"]["measurements"] if m["included"]], ["5"]
            )
        for result in self.both(
            [{**case, "rows": rr + [row(checkpoint="B", n_shot="3", value=".7")]}]
        )[0]:
            self.assertEqual(
                [
                    m["n_shot"]
                    for m in result["value"]["b"]["measurements"]
                    if m["included"]
                ],
                ["3"],
            )
        tie = [rr[0], row(checkpoint="B", n_shot="3"), row(checkpoint="B", n_shot="7")]
        for result in self.both([{**case, "rows": tie}])[0]:
            self.assertIsNone(result["value"]["delta"])
            self.assertIn(
                "ambiguous_shot_setting",
                {d["code"] for d in result["value"]["diagnostics"]},
            )
        for field, value in [
            ("filter", "other"),
            ("metric", "other"),
            ("harness", "other"),
            ("backend", "other"),
        ]:
            bad = deepcopy(rr)
            bad[1][field] = value
            for result in self.both([{**case, "rows": bad}])[0]:
                self.assertIsNone(result["value"]["delta"])
                self.assertNotIn(
                    "relaxed_shot_setting",
                    {d["code"] for d in result["value"]["diagnostics"]},
                )
        for result in self.both([{**case, "matching": "best_score"}])[0]:
            self.assertIn("error", result)
        for result in self.both([{**case, "operation": "analyze"}])[0]:
            self.assertEqual(len(result["value"]["models"]), 2)
            self.assertTrue(result["value"]["inconsistent"])
        # An eval without an expected shot setting retains strict A/B matching.
        unpinned = fixture()
        for result in self.both([{**case, "config": unpinned}])[0]:
            self.assertIsNone(result["value"]["delta"])
        # Required task coverage comes from the set; expected shots come from the catalogue.
        fixed = deepcopy(c)
        fixed["suite"] = dict(
            version=1,
            name="Required",
            mode="fixed",
            evals=[dict(name="E", variants=[dict(task="e_en")])],
        )
        for result in self.both([{**case, "config": fixed}])[0]:
            self.assertTrue(result["value"]["coverage"]["complete"])
            self.assertEqual(result["value"]["coverage"]["sharedRequired"], 1)
        for result in self.both([{**case, "a": "B", "b": "A"}])[0]:
            self.assertAlmostEqual(result["value"]["delta"], -30)

    def test_relaxed_matching_preserves_component_protocols_and_validation(self):
        c = fixture()
        e = c["catalogue"]["evals"][0]
        e["shots"] = 5
        e["aggregation"] = {
            "components": [
                dict(name=n, match={"name": "e_" + n}, relative_weight=i + 1)
                for i, n in enumerate(["low", "high"])
            ]
        }
        c["catalogue"]["languages"] = [
            dict(tasks=["e_low", "e_high"], language="eng_Latn", scope="single")
        ]
        rr = [
            row("e_" + n, n_shot=shots, checkpoint=model)
            for model, shots in [("A", "5"), ("B", "0")]
            for n in ["low", "high"]
        ]
        case = dict(config=c, rows=rr, operation="compare", matching="relaxed")
        for result in self.both([case])[0]:
            self.assertNotIn("error", result)
            self.assertEqual(result["value"]["delta"], 0)
            self.assertTrue(result["value"]["inconsistent"])
            self.check_tree(result["value"]["b"]["tree"])
        split = deepcopy(rr)
        split[-1]["n_shot"] = "5"
        for rows in [split, rr[:-1]]:
            for result in self.both([{**case, "rows": rows}])[0]:
                self.assertNotIn("error", result)
                self.assertIsNone(result["value"]["delta"])
                self.assertFalse(result["value"]["inconsistent"])
                self.assertIn(
                    "incomplete_components",
                    {d["code"] for d in result["value"]["diagnostics"]},
                )
        bad = deepcopy(rr)
        bad[-1]["value"] = "NaN"
        for rows in [bad, rr + [dict(rr[-1])]]:
            for result in self.both([{**case, "rows": rows}])[0]:
                self.assertIn("error", result)

    def test_eval_set_defaults_overrides_and_language_exclusions(self):
        c = fixture()
        c["catalogue"]["evals"][0]["shots"] = 5
        c["catalogue"]["languages"].append(
            dict(tasks=["e_ka"], scope="single", language="kat_Geor")
        )
        c["suite"] = dict(
            version=1,
            name="Required",
            mode="fixed",
            exclude_languages=["kat_Geor"],
            evals=[dict(name="E", shots=0, metric="acc_norm", metric_filter="")],
        )
        rr = paired(
            [row(t, metric="acc_norm", filter="") for t in ["e_en", "e_fr", "e_ka"]]
        )
        before = deepcopy(c)
        for result in self.both([dict(config=c, rows=rr, operation="compare")])[0]:
            self.assertNotIn("error", result)
            r = result["value"]
            self.assertEqual(r["coverage"]["required"], 2)
            self.assertTrue(r["coverage"]["complete"])
            self.assertEqual(r["a"]["score"], 50)
            self.assertEqual(
                {m["task"] for m in r["a"]["measurements"] if m["included"]},
                {"e_en", "e_fr"},
            )
            self.assertEqual({d["code"] for d in r["diagnostics"]}, {"not_used"})
        self.assertEqual(c, before, "Resolution must not mutate inputs")
        c["suite"]["evals"][0]["exclude_languages"] = ["eng_Latn"]
        cases = [dict(config=deepcopy(c), rows=rr, operation="compare")]
        # Missing excluded data is not a missing requirement.
        cases.append(
            dict(
                config=deepcopy(c),
                rows=[r for r in rr if r["task"] == "e_fr"],
                operation="compare",
            )
        )
        # Relaxation applies after the effective override, preserving actual identities.
        changed = [{**r, "n_shot": "3"} if r["checkpoint"] == "B" else r for r in rr]
        cases.append(
            dict(
                config=deepcopy(c),
                rows=changed,
                operation="compare",
                matching="relaxed",
            )
        )
        for i, results in enumerate(self.both(cases)):
            for result in results:
                r = result["value"]
                self.assertTrue(r["coverage"]["complete"])
                self.assertEqual(r["coverage"]["required"], 1)
                self.assertEqual(
                    [m["task"] for m in r["a"]["measurements"] if m["included"]],
                    ["e_fr"],
                )
                if i == 2:
                    d = next(
                        d
                        for d in r["diagnostics"]
                        if d["code"] == "relaxed_shot_setting"
                    )
                    self.assertEqual((d["expected_shots"], d["actual_shots"]), (0, 3))
        # Removing an included language must warn even though another language exists.
        c["suite"]["evals"][0].pop("exclude_languages")
        for result in self.both(
            [
                dict(
                    config=c,
                    rows=paired([row(metric="acc_norm", filter="")]),
                    operation="compare",
                )
            ]
        )[0]:
            self.assertFalse(result["value"]["coverage"]["complete"])
            self.assertIn(
                "missing_suite_data",
                {d["code"] for d in result["value"]["diagnostics"]},
            )
        # Metric mismatches are never relaxed.
        for result in self.both(
            [
                dict(
                    config=c,
                    rows=paired([row()]),
                    operation="compare",
                    matching="relaxed",
                )
            ]
        )[0]:
            self.assertIsNone(result["value"]["a"]["score"])
            self.assertIn(
                "missing_scoring_field",
                {d["code"] for d in result["value"]["diagnostics"]},
            )

    def test_required_inventory_unicode_order(self):
        c = fixture()
        tasks = ["e_😀", "e_\ue000", "e_fr"]
        c["catalogue"]["languages"] = [
            dict(tasks=tasks, scope="single", language="fra_Latn")
        ]
        c["suite"] = dict(
            version=1, name="Required", mode="fixed", evals=[dict(name="E")]
        )
        for result in self.both([dict(config=c, rows=[row("e_fr")])])[0]:
            self.assertEqual(
                [v["task"] for v in result["value"]["coverage"][0]["missing"]],
                sorted(tasks[:2]),
            )

    def test_eval_set_reference_errors(self):
        base = fixture()
        base["suite"] = dict(
            version=1, name="Required", mode="fixed", evals=[dict(name="E")]
        )
        bad = []
        for patch in [
            dict(name="Typo"),
            dict(exclude_languages=["deu_Latn"]),
            dict(shots=-1),
            dict(shots=True),
            dict(metric=""),
            dict(metric_filter=None),
            dict(filter="none"),
            dict(variants=[dict(task="e_typo")]),
        ]:
            c = deepcopy(base)
            c["suite"]["evals"][0].update(patch)
            bad.append(c)
        c = deepcopy(base)
        c["suite"]["exclude_languages"] = ["kat_Geor"]
        bad.append(c)
        c = deepcopy(base)
        c["suite"]["exclude_languages"] = ["eng_Latn", "eng_Latn"]
        bad.append(c)
        c = fixture()
        c["suite"]["exclude"] = ["Typo"]
        bad.append(c)
        for outputs in self.both([dict(config=c, rows=paired([row()])) for c in bad]):
            for result in outputs:
                self.assertIn("error", result)

    def test_eval_set_translation_exclusions_and_empty_selection(self):
        c = fixture()
        c["catalogue"]["languages"] = [
            dict(
                tasks=["e_to_ka"],
                scope="translation",
                source_language="eng_Latn",
                target_language="kat_Geor",
            ),
            dict(
                tasks=["e_from_ka"],
                scope="translation",
                source_language="kat_Geor",
                target_language="eng_Latn",
            ),
            dict(tasks=["e_fr"], scope="single", language="fra_Latn"),
        ]
        rr = paired([row(t) for t in ["e_to_ka", "e_from_ka", "e_fr"]])
        cases = []
        for mode in ["fixed", "available"]:
            s = dict(
                version=1, name="Excluded", mode=mode, exclude_languages=["kat_Geor"]
            )
            if mode == "fixed":
                s["evals"] = [dict(name="E")]
            c["suite"] = s
            cases.append(dict(config=deepcopy(c), rows=rr, operation="compare"))
            c["suite"]["exclude_languages"].append("fra_Latn")
            cases.append(dict(config=deepcopy(c), rows=rr, operation="compare"))
        for i, results in enumerate(self.both(cases)):
            for result in results:
                r = result["value"]
                self.assertEqual(
                    [m["task"] for m in r["a"]["measurements"] if m["included"]],
                    [] if i % 2 else ["e_fr"],
                )
                self.assertNotIn(
                    "missing_suite_data", {d["code"] for d in r["diagnostics"]}
                )
                if i % 2:
                    self.assertIsNone(r["a"]["score"])

    def test_eval_set_inheritance_and_component_language_exclusions(self):
        c = fixture()
        e = c["catalogue"]["evals"][0]
        e["shots"] = 5
        e["aggregation"] = {
            "components": [
                dict(name=n, match={"regex": "e_.+_" + n}, relative_weight=i + 1)
                for i, n in enumerate(["low", "high"])
            ]
        }
        c["catalogue"]["languages"] = [
            dict(
                tasks=["e_" + lang + "_low", "e_" + lang + "_high"],
                language=code,
                scope="single",
            )
            for lang, code in [("en", "eng_Latn"), ("fr", "fra_Latn")]
        ]
        c["suite"] = dict(
            version=1,
            name="Required",
            mode="fixed",
            evals=[dict(name="E", exclude_languages=["fra_Latn"])],
        )
        rr = paired(
            [
                row("e_" + lang + "_" + part, n_shot="5", value=value)
                for lang in ["en", "fr"]
                for part, value in [("low", ".25"), ("high", "1")]
            ]
        )
        for result in self.both([dict(config=c, rows=rr, operation="compare")])[0]:
            r = result["value"]
            self.assertEqual(r["coverage"]["required"], 2)
            self.assertTrue(r["coverage"]["complete"])
            self.assertAlmostEqual(r["a"]["score"], 200 / 3)
            self.assertEqual({d["code"] for d in r["diagnostics"]}, {"not_used"})
        # Explicit membership may not slice a required component group.
        c["suite"]["evals"][0]["variants"] = [dict(task="e_en_low")]
        for result in self.both([dict(config=c, rows=rr)])[0]:
            self.assertIn("error", result)

    def test_flagship_exclusions_are_set_policy(self):
        config = load_config(
            catalogue=ROOT / "configs/catalogue.yaml",
            weights=ROOT / "configs/weights/oellm.yaml",
            eval_set=ROOT / "configs/sets/flagship-1.yaml",
        )
        rows = parse_csv((ROOT / "examples/sample-evals.csv").read_text())
        report = analyze(rows, config, matching="relaxed", diagnostics="collect")
        records = report.models[0]["measurements"]
        georgian = [
            r
            for r in records
            if "kat_Geor"
            in [
                r["language"].get(k)
                for k in ("language", "source_language", "target_language")
            ]
        ]
        self.assertTrue(georgian)
        self.assertTrue(all(not r["included"] for r in georgian))
        self.assertTrue(
            all(not r["included"] for r in records if r["task"] == "xcsqa_eng_Latn")
        )
        config["suite"] = dict(version=1, name="Available", mode="available")
        free = analyze(rows, config, matching="relaxed", diagnostics="collect")
        included = {r["task"] for r in free.models[0]["measurements"] if r["included"]}
        excluded_tasks = ({r["task"] for r in georgian} | {"xcsqa_eng_Latn"}) & included
        self.assertTrue(excluded_tasks)
        self.assertIn("xcsqa_eng_Latn", excluded_tasks)
        warned = {
            t for d in report.diagnostics if d["code"] == "not_used" for t in d["tasks"]
        }
        self.assertTrue(excluded_tasks <= warned)
        self.assertFalse(
            excluded_tasks.intersection(
                t
                for d in report.diagnostics
                if d["code"] == "missing_suite_data"
                for t in d["tasks"]
            )
        )

    def test_flagship_selects_corrected_protocols_without_legacy_fallback(self):
        replacements = {
            "AIME24": "aime24_cot", "AIME25": "aime25_cot", "AMC23": "amc23_cot",
            "GPQADiamond": "gpqa_diamond_cot", "HumanEval": "humaneval_cont",
            "JEEBench": "jeebench_cot", "LiveCodeBench": "livecodebench_cont",
            "MATH500": "math500_cot", "mbpp": "mbpp_cont", "polymath": "polymath_cot",
        }
        config = load_config(catalogue=ROOT / "configs/catalogue.yaml",
                             weights=ROOT / "configs/weights/oellm.yaml",
                             eval_set=ROOT / "configs/sets/flagship-1.yaml")
        required = {e["name"]: e for e in config["suite"]["evals"]}
        self.assertTrue(set(replacements.values()) <= required.keys())
        self.assertFalse(set(replacements) & required.keys())
        definitions = {e["name"]: e for e in config["catalogue"]["evals"]}
        for old_name, new_name in replacements.items():
            with self.subTest(eval=new_name):
                old = definitions[old_name]
                # Scores are invented. Only the protocol selection contract uses shipped rules.
                if old_name == "polymath":
                    old_tasks = [t for g in config["catalogue"]["languages"] for t in g["tasks"]
                                 if re.fullmatch(r"polymath_.+_(low|medium|high|top)", t)]
                    new_tasks = [t + "_cot" for t in old_tasks]
                else:
                    old_tasks, new_tasks = [old["match"]["name"]], [new_name]
                shots = "3" if new_name == "mbpp_cont" else "0"
                legacy = [row(t, "1", metric=old["metric"], filter=old["metric_filter"],
                              n_shot=str(old["shots"])) for t in old_tasks]
                corrected = [row(t, ".6", metric="pass@1", filter="all", n_shot=shots) for t in new_tasks]
                alternatives = [row(t, "1", metric=metric, filter=filter_, n_shot=shots)
                                for t in new_tasks for metric, filter_ in
                                [("pass@4", "all"), ("think_closed", "all"), ("pass@1", "none")]]
                subset = {**config, "suite": {**config["suite"], "evals": [required[new_name]]}}
                complete = dict(config=subset, rows=legacy + corrected + alternatives)
                missing = dict(config=subset, rows=legacy + alternatives)
                for outputs in self.both([complete, {**complete, "matching": "relaxed"}]):
                    for output in outputs:
                        self.assertNotIn("error", output)
                        report = output["value"]
                        measurements = report["models"][0]["measurements"]
                        included = [m for m in measurements if m["included"]]
                        self.assertEqual({m["task"] for m in included}, set(new_tasks))
                        self.assertEqual(len(included), len(new_tasks))
                        self.assertEqual({(m["metric"], m["filter"], m["n_shot"]) for m in included},
                                         {("pass@1", "all", shots)})
                        self.assertTrue(all(not m["included"] for m in measurements if m["task"] in old_tasks))
                        self.assertNotIn("missing_suite_data", {d["code"] for d in report["diagnostics"]})
                        self.assertAlmostEqual(sum(m["effective_weight"] for m in included), 1)
                for outputs in self.both([missing, {**missing, "matching": "relaxed"}]):
                    for output in outputs:
                        self.assertNotIn("error", output)
                        report = output["value"]
                        self.assertIsNone(report["models"][0]["score"])
                        self.assertFalse(any(m["included"] for m in report["models"][0]["measurements"]))
                        self.assertIn("missing_suite_data", {d["code"] for d in report["diagnostics"]})
                if old_name == "polymath":
                    incomplete = {**complete, "rows": legacy + [r for r in corrected if not r["task"].endswith("_top_cot")]}
                    for output in self.both([incomplete])[0]:
                        self.assertNotIn("error", output)
                        self.assertIsNone(output["value"]["models"][0]["score"])
                        self.assertIn("incomplete_components", {d["code"] for d in output["value"]["diagnostics"]})

    def test_published_sample_across_all_shipped_configs(self):
        # Discover files so adding a profile or set automatically extends parity coverage.
        rows = parse_csv((ROOT / "examples/sample-evals.csv").read_text())
        a = rows[0]["checkpoint"]
        b = "Parity comparison"
        copy = [{**r, "checkpoint": b} for r in rows]
        profiles = sorted(
            p
            for p in (ROOT / "configs/weights").iterdir()
            if p.suffix in {".yaml", ".yml"}
        )
        suites = sorted(
            p
            for p in (ROOT / "configs/sets").iterdir()
            if p.suffix in {".yaml", ".yml"}
        )
        self.assertTrue(profiles)
        self.assertTrue(suites)
        for weights in profiles:
            for suite in suites:
                config = load_config(
                    catalogue=ROOT / "configs/catalogue.yaml",
                    weights=weights,
                    eval_set=suite,
                )
                for mode in ("standard", "english_eval", "english_category"):
                    config["profile"]["aggregate"] = mode
                    with self.subTest(
                        weights=weights.name, suite=suite.name, mode=mode
                    ):
                        cases = [
                            dict(config=config, rows=rows),
                            dict(
                                config=config,
                                rows=rows + copy,
                                operation="compare",
                                a=a,
                                b=b,
                            ),
                            dict(
                                config=config,
                                rows=rows + [r for i, r in enumerate(copy) if i % 7],
                                operation="compare",
                                a=a,
                                b=b,
                            ),
                        ]
                        cases = [
                            {**case, "matching": matching}
                            for matching in ("strict", "relaxed")
                            for case in cases
                        ]
                        for outputs in self.both(cases):
                            for result in outputs:
                                self.assertNotIn("error", result)
                                report = result["value"]
                                models = report.get(
                                    "models", [report.get("a"), report.get("b")]
                                )
                                for model in models:
                                    self.assertIsNotNone(model["score"])
                                    self.check_tree(model["tree"])
                        # Matching data has identical aggregate scores and contributions.
                        self.assertEqual(native(cases[1])["value"]["delta"], 0)

    def test_hand_calculated_modes_and_tree(self):
        c = fixture()
        c["catalogue"]["evals"].append(
            dict(
                name="F",
                category="C",
                match={"name": "f_en"},
                metric="acc",
                metric_filter="none",
                score={"scale": 1},
            )
        )
        c["catalogue"]["languages"][0]["tasks"].append("f_en")
        c["profile"]["english_weights"] = {"C": 0.5}
        rr = [row(value="1"), row("e_fr", ".25"), row("f_en", ".6")]
        cases = []
        for mode in ("standard", "english_eval", "english_category"):
            cc = deepcopy(c)
            cc["profile"]["aggregate"] = mode
            cases.append(dict(config=cc, rows=rr))
        for outputs, expected in zip(self.both(cases), (55, 55, 40)):
            for result in outputs:
                self.assertAlmostEqual(result["value"]["models"][0]["score"], expected)
                self.check_tree(result["value"]["models"][0]["tree"])
        # Unequal language counts distinguish per-eval balancing from ordinary averaging.
        c["catalogue"]["languages"].append(
            dict(tasks=["e_de"], scope="single", language="deu_Latn")
        )
        rr.append(row("e_de", ".25"))
        cases = []
        for mode in ("standard", "english_eval", "english_category"):
            cc = deepcopy(c)
            cc["profile"]["aggregate"] = mode
            cases.append(dict(config=cc, rows=rr))
        for outputs, expected in zip(self.both(cases), (140 / 3, 55, 40)):
            for result in outputs:
                self.assertAlmostEqual(result["value"]["models"][0]["score"], expected)

    def check_tree(self, node):
        if node["children"]:
            self.assertAlmostEqual(
                sum(c["contribution"] for c in node["children"]), node["contribution"]
            )
            if node["effective_weight"]:
                self.assertAlmostEqual(sum(c["weight"] for c in node["children"]), 1)
                self.assertAlmostEqual(
                    sum(c["weight"] * (c["score"] or 0) for c in node["children"]),
                    node["score"],
                )
            for child in node["children"]:
                self.check_tree(child)

    def test_warning_and_exclusion_contract(self):
        cases = []
        expected = []

        def add(config, rows, codes, operation="compare"):
            cases.append(dict(config=config, rows=rows, operation=operation))
            expected.append(set(codes))

        c = fixture()
        c["catalogue"]["evals"][0]["warning"] = "Caveat"
        add(c, paired([row()]), ["config_caveat"])
        c = fixture()
        c["suite"]["exclude"] = ["E"]
        add(c, paired([row()]), ["not_used"])
        c = fixture()
        c["suite"] = dict(
            version=1,
            name="Required",
            mode="fixed",
            evals=[dict(name="E", variants=[dict(task="e_en"), dict(task="e_fr")])],
        )
        add(c, paired([row()]), ["missing_suite_data"])
        c = fixture()
        rr = paired([row()])
        rr[0]["metric"] = "acc_norm"
        add(
            c, rr, ["missing_scoring_field", "no_selected_score", "comparison_coverage"]
        )
        c = fixture()
        rr = paired([row()])
        rr[0]["filter"] = "other"
        add(
            c,
            rr,
            ["missing_scoring_setting", "no_selected_score", "comparison_coverage"],
        )
        add(fixture(), paired([row()]) + [row("e_fr")], ["comparison_coverage"])
        add(fixture(), paired([row(), row("unknown")]), ["no_config"])
        add(fixture(), paired([row("e_unknown")]), ["unknown_language"])
        add(fixture(), paired([row(n_samples="many")]), ["invalid_sample_count"])
        rr = paired([row(n_samples="100")])
        rr[1]["n_samples"] = "90"
        add(fixture(), rr, ["sample_count_mismatch"])
        add(
            fixture(),
            paired([row(), row("e_fr", n_shot="5")]),
            ["inconsistent_scoring_settings"],
        )
        for outputs, codes in zip(self.both(cases), expected):
            for result in outputs:
                self.assertNotIn("error", result)
                report = result["value"]
                self.assertEqual({d["code"] for d in report["diagnostics"]}, codes)
                self.assertEqual(
                    {r["task"] for r in report["a"]["measurements"] if r["included"]},
                    {r["task"] for r in report["b"]["measurements"] if r["included"]},
                )

    def test_dynamic_components(self):
        cases = []
        expected = []
        for n in (1, 2, 3, 4, 7):
            c = fixture()
            e = c["catalogue"]["evals"][0]
            e.pop("normalize")
            e["aggregation"] = {
                "components": [
                    dict(
                        name=str(i), match={"regex": f"e_.+_{i}"}, relative_weight=i + 1
                    )
                    for i in range(n)
                ]
            }
            c["catalogue"]["languages"] = [
                dict(
                    tasks=[f"e_en_{i}" for i in range(n)],
                    scope="single",
                    language="eng_Latn",
                )
            ]
            rows = [row(f"e_en_{i}", str((i + 1) / (n + 1))) for i in range(n)]
            cases.append(dict(config=c, rows=paired(rows)))
            expected.append(
                100
                * sum((i + 1) ** 2 / (n + 1) for i in range(n))
                / sum(range(1, n + 1))
            )
        for outputs, score in zip(self.both(cases), expected):
            for result in outputs:
                self.assertAlmostEqual(result["value"]["models"][0]["score"], score)
                self.check_tree(result["value"]["models"][0]["tree"])
        c = cases[-1]["config"]
        rr = cases[-1]["rows"][:-1]
        for result in self.both([dict(config=c, rows=rr, operation="compare")])[0]:
            self.assertIsNone(result["value"]["a"]["score"])
            self.assertIn(
                "incomplete_components",
                {d["code"] for d in result["value"]["diagnostics"]},
            )
        c = deepcopy(c)
        c["suite"] = dict(
            version=1,
            name="Incomplete",
            mode="fixed",
            evals=[dict(name="E", variants=[dict(task="e_en_0")])],
        )
        for result in self.both([dict(config=c, rows=rr)])[0]:
            self.assertIn("error", result)

    def test_input_and_config_edge_cases(self):
        cases = []
        mutations = [
            lambda c: c["catalogue"].update(name="  "),
            lambda c: c["catalogue"]["evals"][0].update(category=" "),
            lambda c: c["profile"].update(weights={"C": 0}),
            lambda c: c["catalogue"]["evals"][0].update(match={"regex": "(?=e)e.*"}),
            lambda c: c["catalogue"]["evals"][0].update(shots=True),
        ]
        for mutate in mutations:
            c = fixture()
            mutate(c)
            cases.append(dict(config=c, rows=[row()]))
        for field in (
            "checkpoint",
            "task",
            "metric",
            "filter",
            "n_shot",
            "harness",
            "backend",
            "value",
        ):
            r = row()
            del r[field]
            cases.append(dict(config=fixture(), rows=[r]))
        for value in ("NaN", "Infinity", "", "0x1", None, True, -0.1, 1.1):
            cases.append(dict(config=fixture(), rows=[row(value=value)]))
        for name in (
            "SYNTHETIC demo — perturbed",
            "SYNTHETIC demo — higher scores",
            "SYNTHETIC demo — future option",
        ):
            cases.append(dict(config=fixture(), rows=[row(checkpoint=name)]))
        cases.append(dict(config=fixture(), rows=[row(), row()]))
        for outputs in self.both(cases):
            for result in outputs:
                self.assertIn("error", result)
        c = fixture()
        c["catalogue"]["evals"][0]["match"] = {"regex": r"e_\d+"}
        for result in self.both([dict(config=c, rows=[row("e_١")])])[0]:
            self.assertFalse(
                result["value"]["models"][0]["measurements"][0]["selected"]
            )

    def test_yaml_csv_and_diagnostics_delivery(self):
        c = fixture()
        stream = io.StringIO()
        w = csv.DictWriter(stream, fieldnames=row())
        w.writeheader()
        w.writerow(row())
        case = dict(
            yaml={k: json.dumps(v) for k, v in c.items()},
            csv="\ufeff" + stream.getvalue(),
        )
        for result in self.both([case])[0]:
            self.assertEqual(result["value"]["models"][0]["score"], 50)
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            r = analyze([row("unknown")], c)
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0].message, QuickdashWarning)
        self.assertEqual(seen[0].message.diagnostic, r.diagnostics[0])
        with self.assertRaises(DiagnosticError):
            analyze([row("unknown")], c, diagnostics="error")
        with warnings.catch_warnings(record=True) as seen:
            analyze([row("unknown")], c, diagnostics="collect")
        self.assertFalse(seen)

    def test_randomized_sizes_and_order(self):
        rng = random.Random(91403)
        cases = []
        for _ in range(60):
            c = fixture()
            c["catalogue"]["evals"] = []
            c["catalogue"]["languages"] = []
            c["profile"]["weights"] = {}
            rows = []
            nc = rng.randint(1, 5)
            for cat in range(nc):
                category = f"C{cat}"
                c["profile"]["weights"][category] = 1 / nc
                for ev in range(rng.randint(1, 6)):
                    name = f"e{cat}_{ev}"
                    c["catalogue"]["evals"].append(
                        dict(
                            name=name,
                            category=category,
                            match={"regex": name + "_.+"},
                            metric="acc",
                            metric_filter="none",
                            score={"scale": 1},
                        )
                    )
                    for lang in ("eng_Latn", "fra_Latn", "deu_Latn")[
                        : rng.randint(1, 3)
                    ]:
                        task = name + "_" + lang
                        c["catalogue"]["languages"].append(
                            dict(tasks=[task], scope="single", language=lang)
                        )
                        rows.append(row(task, str(rng.random())))
            c["profile"]["aggregate"] = rng.choice(
                ["standard", "english_eval", "english_category"]
            )
            c["profile"]["english_weights"] = {
                k: rng.choice([0, 0.3, 0.5, 1]) for k in c["profile"]["weights"]
            }
            rng.shuffle(rows)
            rng.shuffle(c["catalogue"]["evals"])
            cases.append(dict(config=c, rows=paired(rows), operation="compare"))
        for outputs in self.both(cases):
            for result in outputs:
                report = result["value"]
                self.check_tree(report["a"]["tree"])
                self.assertAlmostEqual(
                    sum(r["contribution_delta"] for r in report["deltas"]),
                    report["delta"],
                )

    def test_translation_pooling_and_unknown_language_balance(self):
        c = fixture()
        c["catalogue"]["evals"][0].pop("normalize")
        c["profile"].update(aggregate="english_eval", english_weights={"C": 0.5})
        c["catalogue"]["languages"] = [
            dict(
                tasks=["e_to_en"],
                scope="translation",
                source_language="fra_Latn",
                target_language="eng_Latn",
            ),
            dict(
                tasks=["e_from_en"],
                scope="translation",
                source_language="eng_Latn",
                target_language="fra_Latn",
            ),
            dict(tasks=["e_pool"], scope="pooled", language="mul"),
        ]
        rr = [
            row("e_to_en", "1"),
            row("e_from_en", "0"),
            row("e_pool", ".5"),
            row("e_unknown", "0"),
        ]
        for result in self.both([dict(config=c, rows=rr)])[0]:
            report = result["value"]
            self.assertAlmostEqual(report["models"][0]["score"], 25)
            self.assertEqual(
                {d["code"] for d in report["diagnostics"]}, {"unknown_language"}
            )
            tree = report["models"][0]["tree"]
            self.check_tree(tree)
            self.assertEqual(
                tree["children"][0]["children"][0]["children"][0]["kind"],
                "language_group",
            )
            self.assertEqual(len(report["models"][0]["measurements"]), 4)

    def test_empty_zero_weight_missing_category_and_self_comparison(self):
        cases = [dict(config=fixture(), rows=[])]
        c = fixture()
        c["profile"]["weights"] = {"Other": 1}
        cases.append(dict(config=c, rows=paired([row()]), operation="compare"))
        c = fixture()
        c["profile"]["weights"] = {"C": 0.3, "Other": 0.7}
        cases.append(dict(config=c, rows=[row()]))
        cases.append(
            dict(config=fixture(), rows=[row()], operation="compare", a="A", b="A")
        )
        results = self.both(cases)
        for result in results[0]:
            self.assertEqual(result["value"]["models"], [])
        for result in results[1]:
            self.assertIsNone(result["value"]["delta"])
            self.assertIn(
                "no_category_weight",
                {d["code"] for d in result["value"]["diagnostics"]},
            )
        for result in results[2]:
            self.assertEqual(result["value"]["models"][0]["score"], 50)
        for result in results[3]:
            self.assertEqual(result["value"]["delta"], 0)

    def test_shots_protocols_and_named_requirements(self):
        c = fixture()
        c["suite"] = dict(
            version=1,
            name="Named",
            mode="fixed",
            evals=[
                dict(
                    name="E",
                    variants=[dict(task="e_en", n_shot=0), dict(task="e_fr", n_shot=5)],
                )
            ],
        )
        rr = paired([row(), row("e_fr", n_shot="5")])
        rr[-1]["backend"] = "different"
        for result in self.both([dict(config=c, rows=rr, operation="compare")])[0]:
            report = result["value"]
            self.assertFalse(report["coverage"]["complete"])
            self.assertEqual(report["coverage"]["sharedRequired"], 1)
            self.assertEqual(report["a"]["score"], 50)
            self.assertEqual(
                {r["task"] for r in report["a"]["measurements"] if r["included"]},
                {"e_en"},
            )
        c["catalogue"]["evals"][0]["shots"] = 0
        for result in self.both([dict(config=c, rows=rr)])[0]:
            self.assertIn("error", result)

    def test_component_protocol_compatibility_and_scaling(self):
        c = fixture()
        e = c["catalogue"]["evals"][0]
        e["aggregation"] = {
            "components": [
                dict(name="low", match={"regex": "e_.+_low"}, relative_weight=1),
                dict(name="top", match={"regex": "e_.+_top"}, relative_weight=8),
            ]
        }
        c["catalogue"]["languages"] = [
            dict(tasks=["e_en_low", "e_en_top"], scope="single", language="eng_Latn")
        ]
        rr = paired([row("e_en_low", "1"), row("e_en_top", ".25")])
        cases = [dict(config=c, rows=rr, operation="compare")]
        for field in ("n_shot", "harness", "backend"):
            mutated = deepcopy(rr)
            mutated[1][field] = "5" if field == "n_shot" else "different"
            cases.append(dict(config=c, rows=mutated, operation="compare"))
        scaled = deepcopy(c)
        for component in scaled["catalogue"]["evals"][0]["aggregation"]["components"]:
            component["relative_weight"] *= 11
        cases.append(dict(config=scaled, rows=rr, operation="compare"))
        results = self.both(cases)
        for result in results[0] + results[-1]:
            self.assertAlmostEqual(result["value"]["a"]["score"], 100 / 9)
        for outputs in results[1:-1]:
            for result in outputs:
                self.assertIsNone(result["value"]["delta"])
                self.assertIn(
                    "incomplete_components",
                    {d["code"] for d in result["value"]["diagnostics"]},
                )

    def test_csv_and_yaml_failures_in_both_engines(self):
        cases = []
        for source in (
            "",
            "a,b\n",
            "a,a\n1,2",
            "a,b\n1",
            "a,b\n1,2,3",
            'a,b\n"unclosed',
            'a,b\na"b,1',
            'a,b\n"a"b,1',
            "a,b\n,",
        ):
            cases.append(dict(config=fixture(), csv=source))
        base = {k: json.dumps(v) for k, v in fixture().items()}
        for source in (
            "version: 1\nversion: 1",
            "!!python/object:evil {}",
            "[unclosed",
            "---\n{}\n---\n{}",
            "version: 1\nname: &x [*x]\nevals: []\nlanguages: []",
        ):
            cases.append(dict(yaml={**base, "catalogue": source}, rows=[row()]))
        for outputs in self.both(cases):
            for result in outputs:
                self.assertIn("error", result)
        # These YAML words must remain strings; aliases and folded notes are supported.
        source = """version: 1
name: yes
evals:
  - name: on
    category: C
    match: {name: e_en}
    metric: acc
    metric_filter: none
    score: {scale: 1}
languages: []
notes:
  - &note >-
    Folded text
    across lines.
  - *note
"""
        for result in self.both(
            [dict(yaml={**base, "catalogue": source}, rows=[row()])]
        )[0]:
            self.assertEqual(result["value"]["models"][0]["score"], 62.5)

    def test_portable_regex_character_semantics(self):
        cases = []
        expected = []
        for pattern, task, selected in [
            (r"e_\d+", "e_123", True),
            (r"e_\d+", "e_١", False),
            (r"e_\w+", "e_é", False),
            (r"e_\s+", "e_\u00a0", True),
            ("e_.+", "e_\r", False),
            ("e_.", "e_😀", True),
            ("e_[a-z]+", "e_en\n", False),
        ]:
            c = fixture()
            c["catalogue"]["evals"][0]["match"] = {"regex": pattern}
            cases.append(dict(config=c, rows=[row(task)]))
            expected.append(selected)
        for outputs, selected in zip(self.both(cases), expected):
            for result in outputs:
                self.assertEqual(
                    result["value"]["models"][0]["measurements"][0]["selected"],
                    selected,
                )
        for field, value in [("n_shot", "0\n"), ("n_shot", 2**53), ("n_shot", 1.0)]:
            case = dict(config=fixture(), rows=[row(**{field: value})])
            for result in self.both([case])[0]:
                self.assertEqual("error" in result, value != 1.0)

    def test_python_runtime_never_calls_node_and_cli_streams(self):
        import os
        import sys
        import tempfile
        from unittest.mock import patch

        with patch(
            "subprocess.run", side_effect=AssertionError("No subprocess allowed")
        ):
            c = load_config(
                catalogue=fixture()["catalogue"], weights=fixture()["profile"]
            )
            self.assertEqual(
                analyze([row()], c, diagnostics="collect").models[0]["score"], 50
            )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for key, value in fixture().items():
                (folder / (key + ".yaml")).write_text(json.dumps(value))
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=row())
            writer.writeheader()
            writer.writerow(row("unknown"))
            (folder / "scores.csv").write_text(stream.getvalue())
            command = [
                sys.executable,
                "-m",
                "quickdash",
                str(folder / "scores.csv"),
                "--catalogue",
                str(folder / "catalogue.yaml"),
                "--weights",
                str(folder / "profile.yaml"),
                "--format",
                "json",
            ]
            env = {**os.environ, "PATH": tmp}
            result = subprocess.run(
                command, capture_output=True, text=True, env=env, cwd=ROOT
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("warning [no_config]", result.stderr)
            self.assertIsNone(json.loads(result.stdout)["models"][0]["score"])
            strict = subprocess.run(
                command + ["--strict"],
                capture_output=True,
                text=True,
                env=env,
                cwd=ROOT,
            )
            self.assertEqual(strict.returncode, 1)
            self.assertEqual(strict.stdout, "")
            self.assertIn("no_config", strict.stderr)

    def test_diagnostic_context_and_suppression(self):
        c = fixture()
        c["catalogue"]["evals"][0]["warning"] = "Review this eval"
        rr = paired([row()])
        rr[0]["metric"] = "alternate"
        for output in self.both([dict(config=c, rows=rr, operation="compare")])[0]:
            report = output["value"]
            self.assertNotIn(
                "config_caveat", {d["code"] for d in report["diagnostics"]}
            )
            d = next(
                d for d in report["diagnostics"] if d["code"] == "missing_scoring_field"
            )
            self.assertEqual(
                (d["model"], d["eval"], d["tasks"], d["effect"]),
                ("A", "E", ["e_en"], "excluded"),
            )
            self.assertEqual(
                d["measurement_ids"], [report["a"]["measurements"][0]["id"]]
            )
            self.assertIsNone(report["delta"])
        c["suite"] = dict(
            version=1,
            name="Other set",
            mode="fixed",
            evals=[dict(name="E", variants=[dict(task="e_fr")])],
        )
        for output in self.both([dict(config=c, rows=rr, operation="compare")])[0]:
            self.assertEqual(
                {d["code"] for d in output["value"]["diagnostics"]},
                {"not_used", "missing_suite_data"},
            )
        # An unused catalogue rule neither requires data nor advertises its caveat.
        c = fixture()
        c["catalogue"]["evals"].append(
            dict(
                name="Unused",
                category="Other",
                match={"name": "unused"},
                metric="acc",
                metric_filter="none",
                score={"scale": 1},
                warning="Unused caveat",
            )
        )
        for output in self.both(
            [dict(config=c, rows=paired([row()]), operation="compare")]
        )[0]:
            self.assertFalse(output["value"]["diagnostics"])

    def test_swaps_and_permutations_preserve_allocation(self):
        c = fixture()
        rr = paired([row(), row("e_fr", ".4")])
        cases = [
            dict(config=c, rows=rr, operation="compare"),
            dict(config=c, rows=list(reversed(rr)), operation="compare"),
            dict(config=c, rows=rr, operation="compare", a="B", b="A"),
        ]
        results = self.both(cases)
        for engine in (0, 1):
            reports = [r[engine]["value"] for r in results]
            self.assertAlmostEqual(reports[0]["delta"], reports[1]["delta"])
            self.assertAlmostEqual(reports[0]["delta"], -reports[2]["delta"])
            self.close(reports[0]["a"]["tree"], reports[1]["a"]["tree"])
            self.assertEqual(
                {
                    r["id"]: r["effective_weight"]
                    for r in reports[0]["a"]["measurements"]
                },
                {
                    r["id"]: r["effective_weight"]
                    for r in reports[1]["a"]["measurements"]
                },
            )

    def test_yaml_scalar_contract(self):
        base = {k: json.dumps(v) for k, v in fixture().items()}
        cases = []
        for token in (
            "0",
            "0.0",
            "0_0",
            "0_",
            "+.0",
            "0x0",
            "0b0",
            "0o0",
            ".nan",
            ".inf",
            "!!float 0",
            "!!bool yes",
        ):
            catalogue = """version: 1
name: Scalar test
evals:
  - name: E
    category: C
    match: {name: e_en}
    metric: acc
    metric_filter: none
    score: {scale: 1}
    normalize: {min: TOKEN, max: 1}
languages: []
""".replace("TOKEN", token)
            cases.append(dict(yaml={**base, "catalogue": catalogue}, rows=[row()]))
        self.both(cases)

    def test_regex_rejection_and_literal_escapes(self):
        cases = []
        for pattern in (
            r"e_[\s]",
            r"e_\_",
            r"e_\-",
            r"e_[]",
            r"e_[^]",
            r"e_}",
            r"e_{x}",
            r"e_(",
            r"(e)_\1",
            r"(?i)e_en",
            r"e_.++",
        ):
            c = fixture()
            c["catalogue"]["evals"][0]["match"] = {"regex": pattern}
            cases.append(dict(config=c, rows=[row()]))
        for outputs in self.both(cases):
            for result in outputs:
                self.assertIn("error", result)
        for pattern, task in [
            (r"e_\++", "e_++"),
            (r"e_[a-z]{2,3}", "e_en"),
            (r"e_\(\?", "e_(?"),
            (r"e_[\d]+", "e_12"),
        ]:
            c = fixture()
            c["catalogue"]["evals"][0]["match"] = {"regex": pattern}
            for result in self.both([dict(config=c, rows=[row(task)])])[0]:
                self.assertTrue(
                    result["value"]["models"][0]["measurements"][0]["selected"]
                )

    def test_csv_file_preserves_quoted_line_endings(self):
        import tempfile
        from quickdash import read_results

        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=row())
        writer.writeheader()
        writer.writerow(row(harness="first\r\nsecond"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scores.csv"
            path.write_bytes(stream.getvalue().encode())
            rows = read_results(path)
            self.assertEqual(rows[0]["harness"], "first\r\nsecond")
            self.both([dict(config=fixture(), csv=stream.getvalue())])

    def test_category_names_do_not_inherit_object_properties(self):
        cases = []
        for category in ("constructor", "toString", "__proto__", "hasOwnProperty"):
            c = fixture()
            c["catalogue"]["evals"][0]["category"] = category
            c["profile"].update(
                weights={category: 1}, english_weights={}, aggregate="english_eval"
            )
            cases.append(dict(config=c, rows=paired([row()]), operation="compare"))
        for outputs in self.both(cases):
            for result in outputs:
                self.assertEqual(result["value"]["a"]["score"], 50)

    def test_non_ascii_names_and_numeric_category_order(self):
        c = fixture()
        c["catalogue"]["evals"][0]["category"] = "2"
        c["profile"]["weights"] = {"2": 0.5, "1": 0.5}
        c["catalogue"]["evals"].append(
            dict(
                name="Other",
                category="1",
                match={"name": "other"},
                metric="acc",
                metric_filter="none",
                score={"scale": 1},
            )
        )
        rr = [
            row(checkpoint="😀"),
            row(checkpoint="\ue000"),
            row("other", checkpoint="😀"),
        ]
        self.both([dict(config=c, rows=rr)])
