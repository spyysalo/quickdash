# Share eval rules, weights and named sets

Choose the file to edit based on what you want to change:

- **Interpret a new eval:** add one YAML file to [evals/](evals/), containing its task matching, category, scoring metric, normalization, and language assignments. [polymath.yaml](evals/polymath.yaml) shows an eval with weighted components; [boolq.yaml](evals/boolq.yaml) is a simpler example. Adding a rule does not require every model to run it.
- **Combine component results:** add an `aggregation` rule in that eval’s file. Each component stores a `relative_weight`; PolyMath uses 1, 2, 4, and 8, divided by their sum when scoring. Named sets must select complete component groups with compatible shot settings; incompatible configurations are errors. Missing results within a valid selection warn and exclude the group; see [component aggregation](../docs/configuration.md#weighted-components-within-an-eval).
- **Try different weighting:** add a YAML profile to [weights/](weights/). It can be used with any eval set. Category weights, English shares, and the default calculation live here.
- **Require a standard comparison set:** add a YAML file to [sets/](sets/). [flagship-1.yaml](sets/flagship-1.yaml) names whole eval groups with set-wide and per-eval language exclusions; [any-available.yaml](sets/any-available.yaml) needs no required-eval list and compares shared data, with an explicit exclusion for unvalidated prompted Global PIQA.

[catalogue.yaml](catalogue.yaml) is a small manifest pointing to `evals/`. Every `.yaml` or `.yml` file directly in that directory is loaded in filename order; adding a file needs no registration elsewhere. Keep language tasks in the file for the eval they match. The loader rejects misplaced tasks, duplicate names or assignments, and incompatible component configurations before changing the dashboard. An empty `languages: []` is allowed for an eval without known language metadata; unknown-language warnings still apply to its results.

Catalogue `metric`, `metric_filter`, and `shots` are defaults. A named set can override these for a whole eval; omitted values inherit. The dashboard can explicitly relax few-shot matching with warnings. Language exclusions use the catalogue’s assignments, including both translation endpoints. Unknown names are configuration errors. See [set configuration and matching](../docs/configuration.md#strict-and-relaxed-matching).

Distinct evaluation protocols use separate catalogue entries, such as [polymath.yaml](evals/polymath.yaml) and [polymath_cot.yaml](evals/polymath_cot.yaml). The default `flagship-1` set selects the corrected CoT and code-continuation entries, without fallback to original runs. `Any available` can include both; use a named set to choose one protocol per benchmark.

Put repeated language `evidence` and `note` under `language_defaults` in the eval file; individual language entries can override either field. Ordinary entries need only a canonical `language` and `tasks`: scope is inferred from the declared language fields. Keep an explicit `scope: pooled` when a pooled result is assigned to a specific language label. See [shared language metadata](../docs/configuration.md#shared-language-metadata).

Each profile or set needs a distinct `name` within its directory. To change a selector's startup choice, edit that directory's `default.txt` to name one YAML file. The catalogue is selected at build time with `--catalogue`, or temporarily loaded in the browser.

The [configuration reference](../docs/configuration.md) describes all three formats with small examples. [examples/](examples/) contains the fictional catalogue and weights used by [examples/scores.csv](../examples/scores.csv).

Submit changes as a PR, then check the generated dashboard:

```sh
python3 -m app.build --results-dir results --sample-csv examples/sample-evals.csv --output output/shared
```

The build validates every offered combination before replacing output. In the dashboard, inspect **Warnings** for the comparison you intend to use. Named-set scores with missing requirements are explicitly incomplete; extras are excluded but remain inspectable.

The generated `output/shared/catalogue.yaml` contains the complete catalogue, including every language assignment, with no file references. Browser catalogue export produces the same portable format. Import that complete file when moving settings between dashboards; the repository manifest alone is not a browser import.

For temporary changes, use the separate load/export controls under **Eval configuration**. Files stay in the browser. Weight exports save edited weights and the active calculation; catalogue and eval-set exports are independent. None of these controls modify the repository.
