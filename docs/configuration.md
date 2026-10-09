# Configuration reference

Quickdash separates four inputs: model results, a weighting profile, an optional named eval set, and the global eval catalogue. You can compare new result files with existing interpretation rules without writing a new list of required evals.

| Input | Purpose | Default |
| --- | --- | --- |
| CSV results | Raw measurements for models A and B | Shared files in `results/`, or browser imports |
| Weighting profile | Category weights, English shares, default calculation | `configs/weights/oellm.yaml` |
| Eval set | Optional expected evals and variants | `configs/sets/flagship-1.yaml` on dashboard startup |
| Global catalogue | Match tasks to evals, categories, metrics, normalization and languages | `configs/catalogue.yaml` → `configs/evals/` |

## Choose weights and expected coverage

Two profiles are supplied. **Original** is selected on startup; **Code & math emphasis** shifts weight toward those two categories.

| Category | Original | Code & math emphasis |
| --- | ---: | ---: |
| Code | 0.15 | 0.20 |
| Math | 0.15 | 0.20 |
| Reasoning | 0.15 | 0.10 |
| Knowledge | 0.15 | 0.125 |
| Commonsense | 0.15 | 0.125 |
| Reading | 0.15 | 0.15 |
| Translation | 0.1/3 | 0.1/3 |
| Language | 0.1/3 | 0.1/3 |
| Instruction following | 0.1/3 | 0.1/3 |

Both profiles default to the standard calculation and store an English share of 0.5 per category, which applies only when an English-balance calculation is selected.

**flagship-1** is the startup eval set. The **Weighting profile** and **Eval set** selectors operate independently. Switching a profile resets category weights, English shares, and the calculation to that profile's values, leaving the eval set unchanged. Switching eval sets preserves your current weights and calculation. Export edits before switching profiles if you want to keep them.

**Any available** uses recognized selected measurements shared by A and B. Measurements present on only one side generate comparison warnings and are excluded from both scores. Catalogue entries absent from both models do not generate warnings. The supplied freeform set explicitly excludes prompted Global PIQA pending validation; present data for it generates a **Not used** warning.

**flagship-1** requires the catalogue's known tasks for each listed eval, excluding Georgian throughout the set because of a vocabulary error and English specifically for X-CSQA. Original and translated tasks stay under their existing eval group (for example `arc_challenge`). A missing required result generates a warning even if other languages for that eval are present. The score is labelled **INCOMPLETE** and uses the shared subset with redistributed weights. Excluded tasks are not requirements; present excluded data produces **Not used** warnings and remains inspectable.

The set uses the corrected CoT reasoning and code-continuation protocols from the `flag-evals-471` exports. Each has its own catalogue entry, so the original and corrected runs retain distinct task identities:

| Original eval | Selected corrected eval |
| --- | --- |
| AIME24, AIME25, AMC23 | `aime24_cot`, `aime25_cot`, `amc23_cot` |
| GPQADiamond, JEEBench, MATH500 | `gpqa_diamond_cot`, `jeebench_cot`, `math500_cot` |
| HumanEval, LiveCodeBench, mbpp | `humaneval_cont`, `livecodebench_cont`, `mbpp_cont` |
| polymath | `polymath_cot` (all four difficulty levels in each of six languages) |

These entries select `pass@1` with filter `all`, at 0 shots except `mbpp_cont` at 3 shots. Alternate metrics such as `pass@4` and `think_closed` remain raw inspection fields. Category assignments, normalization floors, and PolyMath difficulty weights are retained. The inherited JEEBench floor of 0.1055 is a shared scoring convention, not a newly measured baseline for CoT prompting.

`flagship-1` excludes the original entries, avoiding duplicate contributions from the same benchmark. Missing corrected results leave coverage incomplete, even when an original run is present; relaxed matching does not substitute a different task or metric. Original entries remain available for custom sets and inspection. **Any available** can include both original and corrected entries as separate evals, so its score answers a different comparison question.

A named set can be concise:

```yaml
version: 1
name: Example required set
mode: fixed
exclude_languages: [kat_Geor]
evals:
  - name: arc_challenge
    shots: 10
  - name: sib200
    metric: acc
    metric_filter: none
  - name: xcsqa
    exclude_languages: [eng_Latn]
```

This example requires a catalogue containing those evals and language assignments. `mode: fixed` means a declared set of required evals; `mode: available` means whatever recognized results are shared by the models. This choice is independent of strict/relaxed matching.

For each named eval, omitted `metric`, `metric_filter`, and `shots` inherit from the catalogue. Set overrides apply to the **whole eval group**, including its translated tasks. They do not alter the global catalogue. Score scale and normalization remain the catalogue's interpretation of that eval; an alternative metric must be compatible with that interpretation. There are no variant-specific setting overrides. **Eval configuration** displays the effective settings and identifies fields overridden by the active set. Changing sets reinterprets loaded results and regenerates synthetic comparisons while preserving weight edits.

Known tasks come from the catalogue's explicit task-language assignments and literal `match.name`, limited by the eval's `match` and optional `select` rules. Required coverage is independent of the CSVs: absence from both models still warns. Updating the catalogue can therefore expand a named set's requirements. An eval using only a regex and no known concrete tasks cannot be required until its task inventory is supplied. A recognized task outside the known inventory is excluded from a fixed set, with a warning. Freeform mode can still use it and report missing language metadata.

`exclude_languages` applies across the entire set or just one eval. Set-wide and local exclusions combine. They use explicit canonical language assignments, not substrings of task names. For translation, either endpoint excludes the pair. Pooled results use their declared language label; exclusions cannot split pooled scores. Excluding a whole component language group is valid; partial component selections are configuration errors. If every task is excluded, the score is unavailable rather than zero.

Unknown eval names and language exclusions with no matching catalogue assignment are configuration errors. A local language exclusion must exist within that eval's eligible catalogue tasks; a set-wide exclusion must exist somewhere in the catalogue's eligible tasks. Duplicate/invalid language codes and misspelled fields also fail. A known selected task missing from the CSV is instead a recoverable warning. Failed imports preserve the active dashboard.

Available-mode sets can exclude entire evals or languages without creating required coverage:

```yaml
version: 1
name: Any available
mode: available
exclude: [global_piqa_prompted]
```

`exclude` is allowed only in available mode and contains unique, exact catalogue eval names. All names must exist even if no corresponding model results are loaded. Fixed sets exclude unlisted evals automatically. Exclusions warn when eligible task data is present, including rows with only the wrong metric. Alternate metric rows or summary children of a selected eval do not warn merely because another field or summary was selected.

For an explicitly pinned task inventory, a fixed entry may still use `variants: [{task: example_en}]`, optionally with a hard `n_shot` requirement. Each task must be known and selected by its catalogue rule. These are membership constraints, not setting overrides; a pinned `n_shot` must agree with the effective eval settings and is not loosened by relaxed matching. Ordinary named sets need no `variants` list.

## Strict and relaxed matching

Strict shot-mismatch warnings group tasks by eval, model, and expected/actual shot-count pair, with a count and expandable task list. They replace duplicate missing-setting/coverage warnings for those same tasks; missing requirements still count toward incomplete coverage.

The dashboard starts with **Strict matching**. Expected settings are resolved in this order: catalogue defaults, then optional whole-eval set overrides. Strict matching requires the configured metric, metric filter, and (when specified) shot count. Shared comparisons also require the same harness and backend.

**Relaxed — allow few-shot differences** may select a different shot count for each concrete task. It prefers the expected count; otherwise it uses the uniquely closest available count, independently for each model and task with the same metric/filter/harness/backend. Equally close alternatives are ambiguous and excluded with a warning. Scores never influence that choice. Without a configured shot expectation, shot counts still have to match across models.

Relaxed matching never substitutes a different metric or metric filter, or pairs different harnesses/backends. Component groups must still contain every component at one consistent actual shot count. If per-task selection leaves a mixed-shot or incomplete component group, the group is excluded; the engine does not search for a different combination to rescue it.

When a differing shot count actually contributes, the page prominently reports **INCONSISTENT EVALUATION SETTINGS**. Warnings give the eval, model, tasks, expected count, and actual count. Real measurement identities retain their actual settings. Enabling relaxed mode alone does not label a comparison inconsistent if no mismatched measurements contribute. The shipped working expectations are 25 shots for ARC Challenge, 10 for PIQA, and 5 for MGSM; their 0-shot translated/global variants need relaxed matching unless the set overrides the expectation.

A weighting profile works with either mode:

```yaml
version: 1
name: Reasoning weights
weights: {Reasoning: 1}
aggregate: standard
english_weights: {Reasoning: 0.5}
```

Weights must be nonnegative and sum to 1. Empty categories have their weight redistributed. A catalogue category omitted from the profile receives zero weight and produces a warning when shared measurements use it. The editor exposes that zero so it can be assigned weight. Weight profiles never list evals. All three YAML types accept optional `notes` (a list of strings), require `version: 1` and a nonempty `name`, and reject unknown fields.

## Build defaults and browser imports

The builder embeds YAML profiles directly in `configs/weights/` and sets directly in `configs/sets/`. Each directory's `default.txt` contains one YAML filename selected on startup. Missing or invalid defaults stop the build before replacing output. Names must be unique within each selector.

- `--catalogue PATH` chooses a complete catalogue YAML or a manifest pointing to per-eval files. Relative `evals_dir` paths resolve against the manifest’s directory, independent of the working directory.
- `--weights PATH` chooses a profile; used alone, it embeds only that profile. `--weights-dir DIR` offers the profiles in another directory and uses its `default.txt` unless an explicit profile is supplied.
- `--eval-set PATH` and `--sets-dir DIR` work the same way for eval sets.
- `--results-dir DIR` embeds CSVs directly in that directory. A checkpoint label may occur in only one file; one file can contain multiple models. An optional `default.yaml` in that directory selects the initial comparison using `a` and `b` checkpoint labels. Both must exist in the embedded data; invalid defaults stop the build before replacing output. Other models remain selectable. See [choosing the startup models](../results/README.md).
- `--sample-csv FILE`, used with `--results-dir`, supplies a fallback only if that directory has no CSVs. Invalid shared files stop the build; they never trigger the fallback. Pages uses `examples/sample-evals.csv` for this option.

Every offered set is validated against the catalogue and every profile before writing output. Raw results are interpreted using the catalogue with the active set’s overrides; changing sets can change both membership and scoring-field selection. An empty results directory starts without models unless `--sample-csv` supplies a fallback. Omitting both input options starts without models.

Under **Eval configuration**, load or export the catalogue, weights, and eval set separately. Uploaded choices are temporary; reload restores published defaults. Catalogue and eval-set imports reinterpret all loaded real models and regenerate synthetic comparisons. Invalid imports preserve the previous models and settings. When replacing a catalogue, first load a compatible set. A neutral set with `mode: available` and no exclusions works with any catalogue; the project's supplied Any available set references prompted Global PIQA and requires that catalogue entry. `configs/examples/eval-set.yaml` is a neutral set for the fictional example. **Clear models** retains settings.

`analysis.json` records the catalogue, selected profile and set, available `profiles` and `suites`, and source filenames/hashes. It also contains the resolved internal `scheme` used for arithmetic; that combined object is not a YAML input format. Generated `catalogue.yaml` contains the assembled, portable catalogue, with no `evals_dir` reference. `weights.yaml` and `eval-set.yaml` record the other configuration inputs. Browser export also saves the complete catalogue in one file; browser import accepts complete catalogues, not filesystem manifests.

## Share a view

The browser address updates as you use the dashboard. Copy that address to reopen
or share the current view. A short link such as `#view=languages` opens a tab with
the page's defaults. Generated links also record A/B checkpoint labels, the eval
set and weighting profile filenames, strict/relaxed matching, calculation mode,
edited category weights and English shares, filters, search, sorting, the category
being explored, and expanded eval/language details. Switching tabs adds a browser
history entry; edits within a tab update its entry. Back and Forward restore them.

Links use the CSVs and configs embedded in the page being opened; they do not pin
a historical dataset or config version. They contain settings and labels, not CSV
contents or uploaded YAML. A view using temporary uploads is marked as requiring
those files; its link cannot reproduce the comparison by itself. Share the files
separately. A local `file:` address also needs the same HTML file at that path;
use the hosted page for links to other people, or share a standalone HTML build.

Malformed links and unavailable model/config references show a notice without
changing the current comparison. On first load, the page's defaults remain visible
with that notice. The invalid anchor is retained so it can be inspected; choosing
a new view or changing a control resumes address updates. Display settings in a
link do not alter the scoring rules or suppress data warnings.

## Edit one eval

The repository keeps each eval’s interpretation and language mappings in one file.
For example, this `evals/example.yaml` selects `acc_norm` with the `none` metric filter for two language variants
of a four-choice eval:

```yaml
name: Example eval
category: Reasoning
match: {regex: 'example_(en|fr)'}
metric: acc_norm
metric_filter: none
shots: 0
score: {scale: 1}
normalize:
  min: 0.25  # Four choices: uniform guessing gets 1/4 correct.
  max: 1
  basis: uniform_choice
  note: Four-choice chance correction is enabled for this example.
languages:
  - language: eng_Latn
    tasks: [example_en]
  - language: fra_Latn
    tasks: [example_fr]
```

A `catalogue.yaml` beside the `evals/` directory gathers those files:

```yaml
version: 1
name: Example scoring
evals_dir: evals
```

`evals_dir` is a directory path. The loader reads its direct `.yaml` and `.yml`
files in filename order; subdirectories and other extensions are ignored. Each
file is one eval definition with its own `languages` list. There is no per-file
`version` field: the manifest specifies the format version. Add a new eval by
adding a file; no separate list needs updating. Metadata `notes` may be supplied
on the manifest as a list of strings.

Every explicit language task must match the eval in its file. Duplicate eval
names, duplicate task-language assignments, known tasks matching multiple evals,
and incompatible component configurations are errors. Missing or empty eval
directories and malformed files stop loading. Errors identify the source file
when a single file is invalid. All validation finishes before the builder replaces
output or a browser import takes effect.

## Shared language metadata

Put repeated language evidence and notes in `language_defaults` within the eval
file. A language entry inherits each omitted field and can override either field
independently:

```yaml
language_defaults:
  evidence: https://huggingface.co/datasets/Qwen/PolyMath
  note: Language assignments follow the benchmark configuration.
languages:
  - language: deu_Latn
    tasks: [polymath_de_low, polymath_de_medium, polymath_de_high, polymath_de_top]
  - language: eng_Latn
    tasks: [polymath_en_low, polymath_en_medium, polymath_en_high, polymath_en_top]
    note: A language-specific explanation can replace the shared note.
```

`language_defaults` accepts only `evidence` and `note`. Both must be strings;
nonempty evidence must be an HTTP(S) URL. An explicit empty string clears an
inherited field; `null` is invalid. Invalid defaults are rejected even if every
language overrides them. The assembled catalogue and single-file exports contain
the resolved metadata, so they remain self-contained.

In per-eval files, `scope` is optional: `language` implies `single`, `language: mul`
implies `pooled`, and source/target fields imply `translation`. Both translation
languages are required. Use an explicit `scope: pooled` when a score pools languages
but is grouped under one specific language code. Explicit overrides must agree
with the fields: translation cannot also have `language`, and single/pooled cannot
have source/target fields. Assembly records an explicit scope for every entry.
This uses the declared fields; it does not infer language identity from task names.

## Complete small example

For a portable single file, the format remains `version`, `name`, `evals`, and
`languages`, with optional `notes`. The loader collects each per-eval definition
under `evals` and its language groups under `languages`. This assembled format is
what the browser and scoring engines use. It contains no directory references.
See the complete [fictional catalogue](../configs/examples/catalogue.yaml), or
build a dashboard and use its generated `catalogue.yaml`. Both formats work with
`--catalogue` and Python’s `load_config`; only the complete format can be imported
into a standalone browser page. A manifest cannot also contain `evals` or
`languages`.

For an input row with `value=0.625`, the raw score is 62.5 and the normalized score is 50. Raw comparisons show the former; the composite uses the latter. A row using `acc` is retained in the configuration audit but excluded because this config selects `acc_norm`. The UI shows the original source value for every metric, including excluded metrics; the scaled and normalized columns apply to selected scores. Eval summaries label the selected metric and shot counts actually used, then list other available metrics and settings. Expanded selection rules explain blank extraction-filter fields and unrestricted shot counts separately from the data currently selected. A shot is one example in the prompt; 0-shot means no examples. Tasks eligible under `select` that lack the configured metric/filter/shot combination are highlighted and listed in Warnings for each affected model, even when other tasks in the eval have selected scores.

## Eval fields

| Field | Meaning |
|---|---|
| `language_defaults` | Optional per-eval defaults for language `evidence` and `note`; individual language entries override them. Expanded during assembly. |
| `languages` | In a per-eval file, the explicit language groups for that eval. Required; use `[]` when unknown. In a complete catalogue, these groups live in the top-level `languages` list. |
| `name` | Unique display name of the eval, grouping its variants. |
| `category` | Category label used by weighting profiles and breakdowns. |
| `match` | Exactly one of `{name: exact task name}` or `{regex: 'full-match pattern'}`. Unmatched tasks are excluded and listed in Warnings; overlapping matches are an error. |
| `metric` | Exact CSV scoring field, such as `acc`, `acc_norm`, or `python_pass@1`. |
| `metric_filter` | Exact value of the CSV `filter` column, including `""` if empty. |
| `shots` | Optional nonnegative integer selecting the CSV `n_shot`. Omit to include all shot settings. |
| `select` | Optional name/regex rule restricting which matched tasks contribute. Useful for selecting summaries while retaining child-task audits. |
| `score.scale` | Raw metric's upper scale: 1 for fractional accuracy; 100 for percentage or chrF scores. Selected values must be finite and within 0..scale. |
| `warning` | Optional nonempty text describing an unresolved scoring assumption. Appears once in Warnings when present in the selected comparison and in this eval’s configuration details; it does not change scores. |
| `aggregation` | Optional component rules with positive relative weights; see [weighted components](#weighted-components-within-an-eval). |
| `normalize` | Optional object with `min`, `max`, and optional `clip`, `basis`, `note`, and `sources`. Thresholds are fractions after division by `score.scale`. |

`metric_filter` selects the evaluator’s response-processing label recorded beside a metric; Quickdash does not execute that processing. `metric_filter: ''` matches a blank CSV field, while `metric_filter: none` matches the literal text `none`. These are distinct values, and neither means “any filter.”

Use the shared Python/JavaScript regex subset: literal text, character classes, alternatives, capturing/noncapturing groups, and ordinary quantifiers. Patterns match the entire task name. Flags, lookarounds, named groups, backreferences and possessive quantifiers are rejected. `\d` and `\w` use ASCII character classes; `\s` uses ECMAScript whitespace and must not appear inside a character class. Dot excludes line terminators and matches one Unicode code point. Language extraction does not use these patterns. Exact-name rules are available when regexes are unnecessary.

The [Python API](python-api.md) consumes these same configurations and returns score trees, audits, coverage, and structured diagnostics. All configuration counts are derived from the supplied inputs.

The Original weighting profile gives Code, Math, Reasoning, Knowledge, Commonsense, and Reading a weight of 0.15 each; Translation, Language, and Instruction following each receive 0.1/3. Category weights must be nonnegative and sum to 1. Names, metrics, and task strings are case-sensitive. Unknown config fields are rejected to catch typos. `version` must be 1; `name` labels the active config. Optional top-level `notes` is a list of strings.

## Normalization and contributions

For metric value `v`, scale `s`, and normalization bounds `lo`, `hi`:

```text
raw_fraction = v / s
raw_score = 100 × raw_fraction
normalized_score = 100 × clamp((raw_fraction − lo) / (hi − lo), 0, 1)
```

`0 ≤ lo < hi ≤ 1` is required. Omitting normalization gives `lo=0`, `hi=1`. `clip` defaults to true; setting it false allows normalized scores below 0 or above 100. All metrics are treated as higher-is-better.

For evals without component rules, under the original aggregate, one variant's weighted contribution is its normalized score multiplied by the effective category weight, divided by the number of available evals in that category and by the number of shared selected variants for that eval. Filtering does not change those denominators. Weighted A−B contributions sum to the composite difference over shared coverage. The English-balance modes redistribute contributions as described in [Choosing an aggregate](#choosing-an-aggregate).

## Weighted components within an eval

Use `aggregation` when several task results form one eval score and the exporter does not supply the intended summary. It belongs in the global catalogue. Category weights and English shares remain in the weighting profile; expected task coverage remains in the eval set.

For PolyMath, add this block to its eval entry (an excerpt, not a complete catalogue):

```yaml
aggregation:
  components:
    - name: low
      match: {regex: 'polymath_.+_low'}
      relative_weight: 1
    - name: medium
      match: {regex: 'polymath_.+_medium'}
      relative_weight: 2
    - name: high
      match: {regex: 'polymath_.+_high'}
      relative_weight: 4
    - name: top
      match: {regex: 'polymath_.+_top'}
      relative_weight: 8
  note: Difficulty-weighted accuracy; each level is required.
  sources:
    - https://qwen-polymath.github.io/#benchmark-score
```

Each component requires a unique nonempty `name`, a full-task `match` (exact `name` or `regex`, as for eval matching), and a positive finite numeric `relative_weight`. The weight sum must be finite. The list must be nonempty. Optional `note` is text and `sources` is a list of HTTP(S) URLs. Unknown fields are rejected. Multiplying all component weights by the same positive constant leaves the result unchanged.

Both supplied PolyMath rules use the authors' [Difficulty-Weighted Accuracy](https://qwen-polymath.github.io/#benchmark-score) formula: `(low + 2×medium + 4×high + 8×top)/15`. The original `polymath` entry selects `exact_match` with filter `none`; the [oellm-eval template](https://github.com/OpenEuroLLM/oellm-eval/blob/8a4b2412a8e8f7f0d95e3845e2164c792add6a79/oellm/resources/custom_lm_eval_tasks/polymath/_default_template_yaml) emits a mean accuracy for each difficulty split. The default set selects `polymath_cot`, whose task and component matches end in `_cot`, with metric `pass@1` and filter `all`. Both take unweighted per-level inputs and require all four levels within a language. Original-protocol rows cannot fill missing CoT levels.

Calculation order:

1. Select the configured metric/filter/shot results and normalize each score.
2. Within each model, eval, explicit language assignment, and protocol, require exactly one result for every component. Protocol means metric, filter, shot count, harness, and backend. Translation uses the full source/target pair; known pooled languages use their explicit pooled assignment. Unknown languages cannot form component groups.
3. Calculate `sum(relative_weight × normalized score) / sum(relative_weights)` for each complete group.
4. Average complete groups equally within the eval, or within its English/other side when balancing is enabled. Apply the selected eval/category aggregation and category weights afterward. Evals without component rules retain their ordinary variant means.

For example, fictional component scores of 60, 30, 15, and 0 produce `(60 + 60 + 60 + 0)/15 = 12`. Their contributions to that language/protocol score are 4, 4, 4, and 0 points. Each component's contribution to the full composite also includes its group's share within the eval, any English balance, the eval's share of its category, and the category weight. These full contributions drive the weighted delta bars and sum to the score difference.

**Incompatible aggregation configurations are errors.** Components inherit the parent eval's metric, filter, score scale, normalization, and any fixed shot setting; they cannot override these fields. Catalogue validation checks declared task/language assignments against the component rules and eval selection. Each represented language must have every component available in the configuration, and each task must match exactly one component. An exact component task must be eligible under its parent eval. Entire languages can be omitted; alternate task aliases are permitted in the catalogue.

A named set that lists component tasks must select exactly one task for each component at every chosen language/shot setting. For example, selecting low/medium/high at 0-shot and top at 5-shot is a configuration error, as is omitting top entirely. Omitting shots for every component is allowed; mixing unrestricted and fixed shots is rejected unless the parent eval pins the same shot count. Multiple complete shot settings are allowed. A whole-eval requirement expands to all eligible known tasks, after language exclusions. Any available has no required task inventory. Missing task-language assignments or duplicate component selections in a named set are errors.

These checks run before applying a browser config or replacing build output. Rejected imports preserve active models, settings, and scores. Regex compatibility is checked against declared task names, plus newly observed selected tasks during CSV classification; the validator does not attempt to prove arbitrary regex relationships. An observed selected task matching zero or multiple component rules is also an error.

**Missing result data still warns and excludes groups, never renormalizing over the remaining levels.** A valid selection with missing metrics/components, multiple exported task results for a component, unknown languages in newly encountered results, or incomplete scoring protocols produces warnings. Check completeness per model and again after taking the exact A/B measurement intersection; a missing component on either side excludes the entire corresponding group from both calculations. Distinct protocols cannot supply each other's missing components. Named-set completion counts reflect these exclusions. Freeform mode does not require entirely absent languages, but it does require every component for each represented group. Raw data remains in Eval configuration, including excluded results and the reason they are unused.

In **Categories** and **Languages**, a collapsed component eval/group shows the calculated normalized score. Its leaves show individual raw scores, relative weights, effective weight percentages, and contributions to the language/protocol group. Ordinary evals still show raw averages; mixed category summaries average the displayed eval scores and are descriptive, not the full composite. These breakdowns do not apply the chosen English balance; use Weighted score for that calculation. Inspection filters that hide required components leave the affected calculated summary unavailable (`—`), rather than inventing a partial benchmark score. Leaf contributions retain the full group's weights.

**Delta comparisons** keeps raw differences as raw differences, including simple raw averages on grouped rows. Its weighted contribution differences include component weights. **Eval configuration** exposes the component matching rules, weights, formula, and sources; catalogue YAML import/export preserves them. Group contributions are explicitly separate from contributions to the overall composite.

The builder and browser share the aggregation implementation. Build summaries apply completeness per model; the browser additionally enforces shared A/B coverage. `analysis.json` model summaries record component warnings alongside scores. Row audits retain metric eligibility even when component coverage excludes a result from the final calculation.

## Initial chance baselines

The supplied config applies the following baselines. Per-eval `normalize.sources` links to the benchmark definitions or evaluator code; `normalize.note` explains the choice. The UI shows a single score formula using `random_score`, defines that eval’s random score below it, and puts rationale/source links in an expandable section. `random_score` corresponds to `normalize.min`; zero means no chance correction is applied, not measured zero performance from a random model. The formula substitutes the source scale directly and omits division by 1.

| Baseline | Evals |
|---|---|
| 1/2 | COPA, PIQA, WSC273, WinoGrande, XCOPA, BoolQ, MultiBlimp |
| 1/3 | Social IQa |
| 1/4 | GPQA Diamond, INCLUDE, MMLU, Global MMLU, OpenBookQA, HellaSwag, Belebele |
| 1/5 | LSAT AR, CommonsenseQA, X-CSQA |
| 1/7 | SIB-200: seven topic labels |
| 1/11 | Language ID: 11 candidate names per question, despite 1,000 languages in the corpus |
| 0 | AIME24 and AIME25: no chance correction |
| 0.1055 | JEEBench: shared 10.55% baseline; the paper reports approximately 10.5% |
| ≈1/4 | ARC Challenge: initial approximation, including translated variants |
| 1/4 | ARC Easy: conventional approximation despite a few questions with different option counts |

The choice-based baselines model uniform *valid* guesses; JEEBench uses the paper's mixed-format guessing policy described below. These are not measured random-language-model or majority-class baselines. AIME24 and AIME25 use a zero floor without a uniform-integer guessing correction. ARC Easy uses 0.25 for consistency; the full published split has mean random accuracy approximately 0.2501613. Sources describe task definitions, but the CSV does not pin the exact run's dataset revision.

ARC Challenge uses an approximate 25% baseline. In its published test split, 1,165 of 1,172 questions have four options, four have three, and three have five, giving an exact mean of about 25.0156%. The approximation is also applied to translated variants, whose individual choice counts have not all been audited. JEEBench uses a 10.55% overall random baseline to match the shared scoring policy; [Table 2 of its paper](https://aclanthology.org/2023.emnlp-main.468.pdf#page=5) reports approximately 10.5%. This combines single-choice guessing and random option subsets with partial credit, assigning zero expected score to integer and numeric answers. It assumes the full 515-question benchmark with those scoring rules.

AMC23 is open-ended in the selected evaluator: the original contest's answer options are removed. Code generation, translation chrF, overlap F1, and other open-ended exact-match tasks do not receive an invented chance baseline.

`normalize.basis` may be `uniform_choice`, `uniform_integer`, `not_applicable`, or `unresolved`. It documents the rationale; `min`, `max`, and `clip` control the actual calculation. Optional `sources` is a list of HTTP(S) URLs, and `note` is free text. Set `min: 0` and `max: 1` to disable correction. An optional eval-level `warning` string appears in the Warnings tab once for all models and in the eval configuration details. Remove it when the concern is resolved; it does not change selection or arithmetic. The supplied config uses it for unvalidated prompted Global PIQA scoring and the Croatian/Serbian language-grouping approximation. Exported YAML preserves config values and notes; YAML comments are not retained.

`acc_norm` in lm-eval refers to choosing answers using length-normalized likelihoods; it does **not** remove chance accuracy. Chance correction here is applied to each selected variant's aggregate score before averaging evals. Clipping after aggregation is not equivalent to clipping individual items, and a mixture of corrected and uncorrected metrics is still a provisional composite.

## Explicit language assignments

Each group lists exact CSV task names. Several names may share one assignment:

```yaml
tasks: [example_english, example_en, example_eng_Latn]
scope: single
language: eng_Latn
evidence: https://example.org/benchmark-definition
note: The benchmark definition identifies all three subsets as English.

```

The URL above is illustrative; the supplied config contains actual benchmark source links. `evidence` and `note` are optional. Evidence links must use HTTP or HTTPS. Duplicate task assignments are rejected. Unlisted task names remain Unknown, even if they look like language codes.

Use `scope: pooled` for scores combining languages that cannot be separated, for example `language: mul`. The supplied MultiBLiMP `multiblimp_hbs` assignment instead uses `scope: single` and `language: srp_Latn` as an explicit grouping approximation: Serbian has more speakers than Croatian. Its eval-level `warning` and language-assignment `note` record that the score pools both languages; no data separation or Serbian-only measurement is implied. Identifiers otherwise follow `xxx_Ssss` form, such as `fra_Latn` or `srp_Cyrl`. Normalized identifiers are written directly; short aliases and spelled-out names are not interpreted at runtime. Language identifiers follow the [upstream OELLM catalogue](https://github.com/OpenEuroLLM/training-data-catalogue/blob/b4823c623c8de4c98de2de5beb24c1f1781b8123/languages). That inventory lists language names and codes, not eval-to-language assignments. Builds and browser imports use the explicit assignments in the YAML; they do not fetch the catalogue or infer languages from task names.

Translation requires both endpoints and no single `language` field:

```yaml
tasks: ['flores200:eng_Latn-spa_Latn']
scope: translation
source_language: eng_Latn
target_language: spa_Latn

```

This result appears in:

- Category first: `Translation → FLORES200 → eng_Latn → From eng_Latn → eng_Latn → spa_Latn`.
- Language first: `eng_Latn → Translation → FLORES200 → From eng_Latn → eng_Latn → spa_Latn`.
- Corresponding `spa_Latn → To spa_Latn` branches.

The Languages page supports ascending/descending sorting by language label, variant count, Raw A, Raw B, and A − B. Sorting reorders siblings at every level, including translation directions and pairs, while retaining each node’s descendants and aggregates. Expanded sections and scroll position are preserved when sorting; filters and model changes retain the selected sort.

The final `eng_Latn → spa_Latn` is a single pair label. Each pair expands into its exact task/protocol rows. Repeated endpoint branches never duplicate a measurement in a parent aggregate or in the weighted score. The `Language role` filter selects ordinary evals, translation into, or translation from the chosen language.

## Scoring choices and consistency warnings

The supplied config prefers `acc_norm` over `acc` when both exist for the selected protocol. The metric remains explicit in `metric`; missing fields never silently fall back to another metric. SIB-200 explicitly uses `acc`. A YAML comment explains that `acc_norm` is not reliable/useful in this export: 34 of its 36 values are exactly 0.25. This selection does not generate a config warning. Length-normalized option scoring and chance normalization are separate operations.

For each selected real model, the dashboard compares the sets of selected settings per task within each eval: `n_shot`, `metric`, `filter`, `harness`, and `backend`. Different sets generate one warning naming the settings, with expandable lists of affected tasks and their explicit language assignments (source → target for translation). Identical sets across tasks are consistent even if each task has multiple settings. Excluded alternate metrics, summary children, and protocols do not trigger this check. The current data has mismatches for MGSM (0/5 shots), ARC Challenge (0/10), and PIQA (0/10). These warnings do not exclude scores; use the YAML selection rules to choose comparable protocols after reviewing coverage. Fields absent from the CSV, such as prompt templates or dataset revisions, cannot be compared.

Translation metric preference is **chrF++ > chrF > BLEU**. The catalogue records an explicit selection based on the available, identified fields: FLORES200 uses `chrf++` with filter `rescored`; OpenSubtitles uses `chrf` with filter `none`. FLORES200's export has separate `chrf` and `chrf++` rows, but does not record a rescoring signature. Do not infer the variant from a generic “chrF” label alone.

The referenced [OpenSubtitles task](https://github.com/OpenEuroLLM/oellm-eval/blob/8a4b2412a8e8f7f0d95e3845e2164c792add6a79/oellm/resources/custom_lm_eval_tasks/opensubtitles_multi40/_opensubtitles_multi40_common.yaml) selects the harness's `chrf` aggregation. The [harness implementation](https://github.com/EleutherAI/lm-evaluation-harness/blob/d6de81643928d653435c431bae19945d41d32520/lm_eval/api/metrics.py) uses SacreBLEU defaults: character order 6, word order 0, beta 2. That is plain chrF; chrF++ adds word n-grams through word order 2. Update the catalogue if a better identified metric becomes available. A model missing the configured metric warns and is excluded; the browser does not silently compare different metrics or substitute BLEU.

Both translation evals retain native 0–100 points (`score.scale: 100`, `normalize: {min: 0, max: 1}`), without chance correction. This accepted policy is documented in their notes rather than flagged as an unresolved caveat. A shared numerical range does not imply equal difficulty across metrics or language pairs.

Completion-based PIQA retains `acc_norm` and a 0.5 baseline. **Global PIQA (prompted)** has a separate interpretation rule for `exact_match` / `strict_match`, a provisional zero floor, and a warning that normalization and metric selection have not been validated. It is excluded by the supplied Any available set and omitted from flagship-1. Its data generates a **Not used** notice while excluded. Including it in a custom set surfaces its scoring caveat; configuration inspection always shows the attached warning.

With these defaults, MultiBlimp's Croatian/Serbian pooling is the only configured caveat for included evals. Runtime warnings for coverage, inconsistent settings, missing fields, and unused data still apply.

MMLU and Global MMLU have separate eval configs and aggregates. MMLU selects only `mmlu`; Global MMLU selects `global_mmlu_full_[a-z]+` language summaries. Subject-level rows stay available for inspection but are excluded from both composites. Both evals retain the four-choice 25% floor and each gets one equal share of Knowledge.

## Choosing an aggregate

The prominent **Score calculation** panel offers three modes:

| Config value | UI choice | Calculation |
|---|---|---|
| `standard` | Original weighted score | Average variants within each eval, then evals equally within the category. |
| `english_eval` | English balance per eval | Combine English and other-language means within each eval, then average the eval scores equally. |
| `english_category` | English balance per category | On each language side, average variants within evals and then represented evals equally; combine the two category means. |

For evals with component rules, combine complete components first and use complete language/protocol groups in place of variants in the table above. All modes apply the configured category weights last. The selector affects both model score cards, category/eval contributions, effective weights, and weighted delta bars. Raw comparison columns and descriptive language/category breakdowns retain their meanings.

Optional top-level fields in the **weighting profile** persist the choice and shares:

```yaml
aggregate: english_eval
english_weights:
  Code: 0.5
  Math: 0.5
  Reasoning: 0.5
  Knowledge: 0.5
  Commonsense: 0.5
  Reading: 0.5
  Translation: 0.5
  Language: 0.5
  Instruction following: 0.5
```

The weight editor has one category per row. **English share applies only when either English-balance mode is selected at the top.** Switching modes preserves the stored shares; they are inactive under Original. Keys must be configured categories and values must be numbers from 0 to 1. Omitted categories default to 0. Zero disables the split for that category and retains its original calculation. Positive shares apply inside every eval in that category under `english_eval`, or to the category mean under `english_category`. Shares do not sum to 1 across categories; outer category weights still do.

A share of 0.5 gives English half and other languages half collectively wherever both language groups exist. When an eval (per-eval mode) or category (per-category mode) contains only one language side, that side automatically retains the full weight regardless of its configured positive share. Code and Instruction following can therefore use 0.5 without requiring the user to know their language coverage. No scores means exclusion, not an invented score.

Language groups use explicit assignments: `eng_Latn` is English; other `single` assignments are non-English. Translation uses **target language**: into English counts as English, out of English to another language counts as non-English. Known non-English assignments, including pooled codes and the Croatian/Serbian score assigned to `srp_Latn`, count as other languages. Unknown assignments and mixed-language pools (`mul`, including Language ID) count as English **for weighting only**. This is a scoring convention, not an inferred language assignment: language views and labels retain Unknown or the pooled identifier. The configuration tab explains the convention and each variant’s scoring details show its weighting group. All supplied categories, including Language, default to share 0.5. Non-English languages share their portion collectively; neither mode adds an equal-per-language averaging layer.

### Why the two English-balance modes differ

Suppose one eval has English score 80 and non-English variants scoring 20 and 40, while a second eval is English-only and scores 100. At an English share of 0.5:

- **Per eval:** the first eval scores `0.5 × 80 + 0.5 × 30 = 55`; the English-only eval keeps 100. Their equally weighted category score is `(55 + 100) / 2 = 77.5`.
- **Per category:** the English mean is `(80 + 100) / 2 = 90`, and the other-language mean is 30. The category score is `0.5 × 90 + 0.5 × 30 = 60`.

Per-eval balancing preserves equal eval weights, but does not guarantee English is exactly half of a category containing English-only evals. Per-category balancing guarantees the configured category language split where both groups exist, but changes effective eval weights: the multilingual eval gets 75% in the example, and the English-only eval 25%. In this data, MGSM supplies all non-English Math scores and PolyMath supplies all non-English Reasoning scores, so category-level balancing gives those subsets substantial weight.

**Inside a category** shows effective eval weights. The expandable **English / other-language components** table displays eval components for `english_eval` and category components for `english_category`. Weighted delta coefficients use shared comparison coverage and remain fixed when inspection filters are applied, so filtered contributions still add up to the corresponding part of the full difference.

`analysis.json` includes all three modes under `aggregates`; its `models` and score CSVs use the config's selected mode. The build reports available data per model, while the interactive comparison uses the models' shared measurements.

## Missing comparison data

Model comparisons use the intersection of selected measurements, matching task, metric, extraction filter, shot count, harness, and backend. A measurement present only in A or only in B is excluded from **both** score calculations and listed in a comparison-coverage warning. If no measurements remain for an eval, that eval is excluded from both scores and the remaining evals share its category weight equally. An empty category is excluded and remaining category weights are rescaled proportionally to sum to 1. No shared scores leaves the composite unavailable. Data warnings apply to the selected models; the configuration audit retains all loaded real exports.


The weights table shows effective weights after exclusions; the editor preserves the configured weights. Missing named-set requirements and unconfigured tasks remain visible in Warnings. Unused global catalogue rules are allowed. The build's model summaries are per-model summaries of available data; the interactive dashboard applies the common comparison coverage when two models are selected.

## Data validation and failure behavior

Builds and browser imports use the same CSV parser. Required columns are `checkpoint`, `task`, `metric`, `filter`, `n_shot`, `harness`, `backend`, and `value`. Identity fields must contain nonempty text; `filter` may be blank. `n_shot` must be a nonnegative integer written as digits (`0`, `5`, etc.). CSV supports UTF-8, an optional BOM, LF/CRLF line endings, and quoted commas, doubled quotes, and embedded newlines. Empty lines are ignored; empty records, duplicate or blank headers, and malformed records are rejected.

| Issue | Behavior |
| --- | --- |
| Empty CSV, missing columns, invalid identity fields, malformed quotes, inconsistent row widths | Reject the file with an error. |
| Invalid YAML/schema, ambiguous eval matches, duplicate selected measurements within a model | Reject the config or file; never silently pick a rule or duplicate. |
| Selected score is blank, nonnumeric, nonfinite, or outside `0..score.scale` | Reject with CSV row, model, task, and metric in the error. Decimal and scientific notation are accepted; booleans and hexadecimal values are not scores. |
| New model uses an already loaded checkpoint name or a name starting with the reserved `SYNTHETIC demo — ` prefix | Reject the import. Give the model a distinct checkpoint label. |
| Task has no eval config, or lacks the configured metric/filter/shots | Warn and exclude from scoring. Alternate metrics remain inspectable and never silently substitute for the configured metric. |
| Measurements match only one of the compared models | Warn; use only shared measurements and redistribute weights. |
| Named set requirement is missing from either or both models | Warn and mark the set incomplete; compare the shared subset. |
| Eval/task data is not selected by a named set or freeform exclusion | Show **Not used** and exclude it, even if only an alternate metric exists; keep it in the audit. |
| Catalogue rule has no results in either model | No warning unless required by the selected named set. |
| Shared category has no profile weight | Warn; zero contribution until a weight is assigned. |
| Selected task has no explicit language assignment | For component evals, warn and exclude the group. Otherwise warn and retain the score. Language views show Unknown; English-balance modes use the English fallback. Known mixed-language pools use the documented fallback without claiming a resolved single language. |
| Selected variants use inconsistent scoring settings | Warn; component evals require completeness independently within each protocol. Ordinary evals retain scores for review. |
| Aggregation rules or named-set component selections are incompatible | Reject the config; preserve the active dashboard or previous build output. Components share parent scoring settings and must be selected completely at compatible shot settings. |
| Valid component selection has missing data or multiple exported results for a component | Warn and exclude the whole language/protocol group from both scores. Keep raw data inspectable; never average only the remaining components. |
| Matched A/B measurements report different positive `n_samples` | Warn and retain scores; sample count does not determine score weights. Review whether dataset coverage is comparable. |
| Supplied `n_samples` is not a positive integer | Warn and retain scores; omit it from sample-count comparisons. Absent/blank sample counts are allowed. |
| Eval has a YAML `warning` | Show the caveat in Warnings when the eval has shared comparison data. Always show it in its configuration details. Excluded evals get **Not used**, not an active scoring caveat. |
| No shared data with positive category weight | Show an unavailable composite (`—`), never an invented zero. |

Invalid model/config imports leave the active models, settings, and scores unchanged, including multi-model files where a later model is invalid. Build input validation completes before existing output files are replaced. Warnings are calculated from the current config and loaded results; fixing or removing the underlying issue removes its warning. Fields not used for scoring, such as source paths and standard errors, remain audit information; their presence is not a guarantee that dataset revisions or prompts match. Invalid values in excluded alternate metrics remain visible but are not normalized using the selected metric's scale.

## Synthetic comparison

The automatically generated synthetic model perturbs the first model’s selected raw scores using seed `20260930` and Gaussian noise with a standard deviation of 2 raw score points. Raw values are clipped to 0–100 before applying the eval’s normalization. Regenerating with the same ordered source rows is deterministic. These scores are for interface exploration, not evidence about another training method.
