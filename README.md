# Quickdash

A standalone, offline dashboard for comparing model evaluation scores. Explore category and language breakdowns, inspect scoring configuration, and compare raw differences or contributions to a weighted score.

**[Open the dashboard](https://openeurollm.github.io/quickdash/)** or **[try the fictional example](https://openeurollm.github.io/quickdash/demo.html)**. No installation is needed to use either page.

The main page opens with **v1annealC_120k_l0fix** as A and **v2anneal_120k** as B, using the exports in [results/](results/README.md). Other shared checkpoints, including the merge3 models, and synthetic comparisons remain selectable. The startup pair is configured in [results/default.yaml](results/default.yaml). The default strict matching excludes results whose few-shot settings differ from the catalogue; review **Warnings**, or explicitly select relaxed matching to include them.

## Compare models

1. Select shared models as A and B, or use **Add model CSV** to open your exports. Three labelled synthetic comparisons (perturbed, higher, and lower scores) are supplied for exploring the interface.
2. Choose a **Weighting profile**. **Eval set** starts on **flagship-1**, using corrected CoT reasoning and code-continuation results with its expected coverage and language exclusions. Missing corrected results show incomplete coverage; original runs remain inspectable. Select **Any available** to compare all recognized shared measurements, which can include both protocols. Weights and eval sets are independent. The supplied sets exclude prompted Global PIQA pending scoring validation.
3. Review **Warnings**, then explore the scores and breakdowns. The global catalogue determines how to interpret each eval: category, scoring field, normalization, and language assignments.

**Original** is the startup weighting profile. **Code & math emphasis** gives Code and Math 20% each, with the other category weights adjusted as shown in the [configuration reference](docs/configuration.md#choose-weights-and-expected-coverage).

Copy the browser address to share the current view. The URL anchor records the tab, model comparison, selected configs, calculation, edited weights, filters, sorting, and expanded details. Opening it restores those settings against the data published on that page. **Original** and **Code & math emphasis** remain selectable independently of the eval set.

Files opened here stay in your browser; they are not uploaded or included in links. Views using temporary CSV/config uploads show a notice: recipients need those files separately. **Clear models** removes the loaded models while keeping settings. Under **Eval configuration**, load or export the catalogue, weights, and eval set as separate YAML files. Weight exports include your edits and active score calculation. See [sharing a view](docs/configuration.md#share-a-view) for restoration behavior and limitations.

## Share results and scoring configs

- Add public CSV exports to [results/](results/README.md) to offer their models in the shared dashboard.
- Edit or add a self-contained eval file in [configs/evals/](configs/evals/), such as [polymath.yaml](configs/evals/polymath.yaml). Each file holds its scoring rules and language assignments together; the catalogue combines them automatically.
- Add weighting profiles to [configs/weights/](configs/weights/), or optional named eval sets to [configs/sets/](configs/sets/). Each directory has a `default.txt` choosing its startup selection. See [contributing configs](configs/README.md).

Use a pull request or GitHub’s **Add file → Upload files**. Changes on `main` trigger tests and a GitHub Pages rebuild. PRs authored by a user in [OWNERS](OWNERS) get previews automatically after checks pass. For other authors, the bot supplies a copyable `/deploy <commit-sha>` command that an OWNER can post to approve that commit. Later commits require new approval. Click **Open preview** in the bot comment on the PR conversation; CI updates that same comment with the built commit. The **Pages preview** check and [preview index](https://openeurollm.github.io/quickdash/pr-preview/) also link to it. Previews are removed when the PR closes. The repository, dashboard, and PR previews are public, so use browser imports for private comparisons.

The [build workflow](.github/workflows/pages.yml) checks and packages the dashboard, fictional demo, and licenses. The [Pages publisher](.github/workflows/publish-pages.yml) combines the main dashboard with previews at `pr-preview/pr-<number>/`. Repository maintainers configure **Settings → Pages → Source → GitHub Actions**. Check the repository’s **Actions** tab if an update fails to appear; see [publishing and previews](docs/development.md#publish-through-github-pages).

## Build a standalone file

Building requires Python 3.8+ and the Python package below. Node.js is needed only for development tests; the generated dashboard remains standalone and offline.

```sh
git clone https://github.com/OpenEuroLLM/quickdash.git
cd quickdash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m app.build examples/scores.csv --catalogue configs/examples/catalogue.yaml \
  --weights configs/examples/weights.yaml --eval-set configs/examples/eval-set.yaml --output output/example
open output/example/index.html  # macOS; elsewhere, open it in your browser
```

The example compares two fictional models with a multilingual reasoning eval and an English math eval. The generated HTML contains its data, configs, styles, and code. Share that one file for offline use; recipients need only a browser. It makes no network requests. Source-reference links open external websites only when clicked.

To build the shared dashboard, including all shared results and config choices:

```sh
python3 -m app.build --results-dir results --sample-csv examples/sample-evals.csv --output output/shared
```

The sample is used only when `results/` contains no CSVs. Omit `--sample-csv` to leave an empty results directory upload-ready; omit both options to start without embedded models regardless of shared data.

For private exports, put your CSV in the ignored `data/` directory:

```sh
mkdir -p data
# Copy your export to data/evals.csv, then:
python3 -m app.build data/evals.csv --output output/private
```

The builder replaces the files it generates in the chosen output directory, including audits and score summaries. Use separate output directories to keep builds. `data/` and `output/` are ignored by Git. CSV columns and configuration rules are described in the [configuration reference](docs/configuration.md).

## Review scores

- **Weighted score:** switch between original averaging, English balance per eval, and English balance per category. Inspect category and eval scores with colored A − B differences alongside their weighted contributions, and adjust category weights and English shares. The [worked example](docs/configuration.md#choosing-an-aggregate) explains how the two balance modes differ.
- **Categories:** expand `category → eval → language → variants`.
- **Languages:** expand `language → category → eval → variants`. Click any column heading to sort within each level; click again to reverse. Expanded sections and scroll position are preserved. Translation expands into source/target directions and language pairs in both breakdowns.
- **Delta comparisons:** sortable bars for raw A − B or weighted contribution differences. Start with one row per eval, then expand languages or show all variants.
- **Eval configuration:** inspect every task's category, languages, selected field, raw alternate fields, normalization, and source notes. Load or export YAML here.
- **Warnings:** review missing coverage, scoring inconsistencies, language fallbacks, sample-count issues, and caveats stored in the config.

Catalogue files provide scoring defaults; named eval sets can override the metric, metric filter, or shot count for a whole eval and exclude languages. **Strict matching** is the default. **Relaxed — allow few-shot differences** accepts differing shot counts with explicit warnings and an inconsistency notice; metric, filter, harness, and backend matching remain strict. See [configuration and matching](docs/configuration.md#strict-and-relaxed-matching).

Filters affect inspection views, while composite scores and contribution weights use shared coverage within the selected eval set. A named set with missing requirements is labelled incomplete; it uses the shared subset with redistributed weights. Unmatched measurements are excluded from both compared scores with warnings. Malformed input and invalid selected scores are rejected; failed imports preserve the active dashboard. See the [data-handling policy](docs/configuration.md#data-validation-and-failure-behavior).

Language/category breakdowns show descriptive raw averages for ordinary evals. Evals with configured components, including PolyMath, show calculated scores when collapsed; expand them to see individual raw scores, relative component weights, and contributions. PolyMath stores `relative_weight` values of 1, 2, 4, and 8, divided by their total of 15 when scoring; incomplete language/protocol groups are excluded with warnings. Incompatible component configurations are rejected before taking effect. See [component aggregation](docs/configuration.md#weighted-components-within-an-eval). Weighted scores use configured normalization, whose baselines and limitations are visible per eval. Shared numerical scales do not establish comparable difficulty across benchmarks. Unknown/mixed-language scores use the documented English fallback for balancing; this does not change their language labels.

## Analyze from Python or the command line

The native Python library uses the same CSVs, YAML rules, weighting profiles, and optional eval sets as the dashboard. It returns calculated trees, effective weights, contributions, coverage, and structured diagnostics. Python emits warnings by default; applications can explicitly collect them or reject results with warnings. See the [Python API and CLI guide](docs/python-api.md).

After installing the package as above:

```sh
quickdash examples/scores.csv --catalogue configs/examples/catalogue.yaml \
  --weights configs/examples/weights.yaml --eval-set configs/examples/eval-set.yaml \
  --compare 'Example A' 'Example B'
```

Add `--format json` for a complete report. Diagnostics go to stderr. Python and browser engines run against the same behavioral test cases.

## Development

Application code lives in `app/` and `quickdash/`, tests in `tests/`, and contributor documentation in `docs/`. Before opening a PR, run the same public checks as CI:

```sh
python3 -m tests.check
```

This requires the Python package installed in your active environment, Node.js 22+,
and Chrome. It includes an automatically managed browser session; set `CHROME_BIN`
for a custom Chrome executable. See [development and publishing](docs/development.md)
for setup, focused checks, and the GitHub Pages workflow.

## License

[Apache-2.0](LICENSE). The bundled js-yaml parser has its own [MIT license](app/vendor/js-yaml.LICENSE).
