# Develop and publish Quickdash

Run commands from the repository root. Install the Python package with `python -m pip install -e .` in a virtual environment (Python 3.8+). Building and using the Python library need no Node runtime. Cross-language tests require Node.js 18+; browser tests require Node.js 22+ and Chrome. Activate the environment before running browser tests so their builder subprocess uses the installed dependencies. The scoring config format is documented in the [configuration reference](configuration.md).

## Source layout

| Directory | Contents |
| --- | --- |
| `quickdash/` | Native Python interpretation, analysis, diagnostics, and CLI. |
| `app/` | Python builder, DOM-independent JavaScript engine (`analysis.js`), browser renderer (`app.js`), HTML, and bundled YAML parser. |
| `tests/` | Public contract tests, browser checks, publishing tests, and optional private-export regressions. |
| `scripts/` | Assemble and report GitHub Pages production and PR preview deployments. |
| `configs/` | Catalogue manifest, self-contained `evals/` files, weighting profiles, optional named sets, and fictional examples. |
| `results/` | Public CSV exports contributed to the shared dashboard. |
| `examples/` | Public sample export for Pages and parity tests, plus small fictional quickstart data. |
| `docs/` | Configuration and contributor documentation. |
| `data/`, `output/` | Ignored local inputs and generated files. |

## Build and inspect a change

```sh
python3 -m app.build --results-dir results --sample-csv examples/sample-evals.csv --output output/shared
python3 -m app.build examples/scores.csv --catalogue configs/examples/catalogue.yaml \
  --weights configs/examples/weights.yaml --eval-set configs/examples/eval-set.yaml --output output/demo
```

Open each generated `index.html` in a browser. The shared build embeds the global catalogue, profiles from `configs/weights/`, and sets from `configs/sets/`. Each selector uses its directory's `default.txt`. See the [build flags](configuration.md#build-defaults-and-browser-imports) to supply other inputs.

Check the views affected by your change, including their warnings and failed-input behavior. Generated output is self-contained; do not commit it. Private exports belong in `data/`, never in the public `results/` directory.

## Run tests

Before opening or updating a PR, run the same public checks as CI from your activated Python environment:

```sh
python3 -m tests.check
```

Install the package with `python3 -m pip install -e .` first. The command requires
Node.js 22+ and Chrome, runs the Python/JavaScript suites, and launches an isolated
headless Chrome session for the browser tests. It stops Chrome and removes the
temporary profile afterward. Missing Chrome is an error, not a skipped test.
On macOS it discovers the standard Google Chrome application; on Linux it checks
Chrome/Chromium executables on `PATH`. Set `CHROME_BIN` to override the executable.
No private evaluation exports are needed. The command builds local test dashboards
but does not publish a site or push commits.

For faster iteration, run individual suites:

```sh
python3 -m unittest tests.test_data tests.test_engines
node --test tests/test_data.cjs tests/test_yaml.cjs tests/test_suites.cjs tests/test_warning_policy.cjs tests/test_components.cjs tests/test_view_links.cjs
```

These narrower commands do not replace the full pre-PR check: catalogue renames,
for example, can pass scoring tests while breaking browser selectors.

The shared suite in `tests/test_engines.py` sends the same input cases to native Python and the real browser engine through `tests/engine_adapter.cjs`. Both must satisfy independently specified expectations, then their complete semantic reports are compared. Diagnostic codes, contexts and actions are checked; presentation text is not. Numerical comparison uses absolute tolerance `1e-9` and relative tolerance `1e-12`. Fixtures vary configuration sizes, contents and ordering. The sample matrix discovers all shipped sets and profiles and exercises every aggregation in both strict and relaxed matching. Shared cases cover override inheritance, language exclusions (including both translation endpoints), invalid references, missing requirements, component completeness, and warning conditions. Browser checks additionally verify effective settings, unchanged catalogue exports, set switching, and failed-import rollback. Python tests also exercise warning emission and CLI stdout/stderr without Node on PATH.

They cover input validation, normalization, warning/exclusion behavior, failed-build preservation, Python/JavaScript parity, hierarchy sorting, and deterministic randomized scoring comparisons against an independent calculation.

The public browser suite also checks empty startup, shared models, independent profile/set selection, missing requirements, temporary uploads, rollback, and that file imports make no network requests. Exact scores and warning behavior use controlled fictional fixtures. The production catalogue and sample provide smoke coverage for builds, portable catalogue imports, all shipped profiles and sets, strict/relaxed matching, and view rendering without fixing particular scores, warning counts, or coverage outcomes. To run just that browser suite manually, start an isolated browser session, then run the suite in another terminal:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --no-first-run --no-default-browser-check \
  --remote-debugging-port=9227 \
  --user-data-dir=/tmp/oellm-dashboard-browser about:blank
# In another terminal:
node tests/test_public_browser.mjs
```

Adjust the Chrome executable path for your platform. Stop that isolated Chrome process when finished. GitHub Actions runs `python3 -m tests.check` automatically, including this browser suite.

<details>
<summary>Additional regression tests using the private full export</summary>

The full-export regression tests require the original private CSV at `data/v2zloss_86k.flag-evals-436.tasks.csv` and its freshly built output:

```sh
python3 -m app.build data/v2zloss_86k.flag-evals-436.tasks.csv
python3 -m unittest tests.test_analysis tests.test_data
node --test tests/test_app.cjs tests/test_english.cjs tests/test_data.cjs tests/test_yaml.cjs tests/test_suites.cjs tests/test_warning_policy.cjs tests/test_components.cjs tests/test_view_links.cjs
```

With the isolated Chrome session above running, use `node tests/test_browser.mjs` for the full-export browser checks: filtering, sortable hierarchies, scroll preservation, warnings, model swapping, header alignment, and mobile layouts. Screenshots go into the ignored `output/` directory.

To measure parser/config coverage with Node.js 22+:

```sh
node --test --experimental-test-coverage --test-coverage-include=app/eval_config.js \
  tests/test_data.cjs tests/test_app.cjs tests/test_english.cjs tests/test_yaml.cjs
```

</details>

## Compare a dashboard refactor against a baseline

Preserve the revision being reviewed in a temporary checkout or directory. Build an example or private dashboard with the candidate revision, then compare the calculation paths:

```sh
QUICKDASH_BASELINE=/path/to/baseline-checkout \
  node tests/compare_baseline.cjs output/example/analysis.json
```

This optional check compares included rows, weights, contributions, scores and descriptive trees across profiles, sets, all aggregation modes, and missing coverage. Run the browser suites against both builds as well; arithmetic agreement alone does not establish UI behavior. Record the comparison and any intentional fixes in the PR. Keep private inputs and generated evidence outside tracked files.

## Publish through GitHub Pages

The [workflow](../.github/workflows/pages.yml) runs public tests on pull requests and pushes to `main`. The Python loader and Node filesystem helper both assemble the per-eval files declared by `configs/catalogue.yaml`. Shared tests check assembly, language ownership, file loading, and portable export/import as well as scoring.

After tests pass, it builds the shared dashboard and a separate fictional demo. When `results/` has no CSVs, the shared page embeds `examples/sample-evals.csv`; real shared CSVs take precedence. The sample also runs through both engines in CI for all shipped weighting profiles, eval sets, and aggregation modes, with complete and mismatched coverage. See [contributor requirements](../AGENTS.md). Only `output/site/` is uploaded as the build artifact: `index.html`, `demo.html`, and license files. Build artifacts are retained for 30 days. The repository root and private local output are not published as the site.

In repository **Settings → Pages**, select **GitHub Actions** as the source. Keep the `github-pages` environment restricted to `main`. The [publisher workflow](../.github/workflows/publish-pages.yml) runs after build completions, when a PR closes, on `/deploy <commit-sha>` PR comments, or through **Run workflow**. It executes the publisher script from the default branch and uses successful build artifacts as static data. It never checks out or executes PR code with publishing permissions, including for fork PRs. The build workflow keeps read-only repository access.

[OWNERS](../OWNERS) lists GitHub logins trusted to auto-deploy their PRs and approve other authors' previews. The initial owners are `jonabur` and `spyysalo`. The publisher reads OWNERS from its trusted default-branch checkout; changes to OWNERS within a PR cannot grant that PR access. Logins are case-insensitive, one per line, with optional `#` comments. An empty or malformed list fails publishing.

For another author, the bot explains why it did not auto-deploy and includes a complete `/deploy <40-character-commit-sha>` command in a code block. An OWNER can copy it into a new comment; no manual hash entry is needed. Only a standalone command written by a current OWNER and matching the exact commit grants approval. Bare `/deploy`, partial hashes, quoted commands, and commands from non-owners do not grant access. Successful checks are still required. When that commit is deployed, the bot adds a rocket reaction to the owner's command. Reactions alone do not approve deployment: GitHub Actions has no reaction-created trigger.

Approval is read from PR comments on every reconciliation, so coalesced workflow events cannot lose a command. A new push needs a new approval. A previously approved preview can stay available while the new head awaits approval; the comment labels the older build. Removing an owner or deleting their approval revokes access on the next reconciliation, including previously deployed content that no longer has valid authorization. Use **Run workflow** to apply a revocation immediately. Ordinary comments do not enter the deployment concurrency queue.

The publisher deploys one combined site:

- `/quickdash/` serves the latest successful main build.
- `/quickdash/pr-preview/pr-<number>/` serves that PR’s latest published successful build.
- `/quickdash/pr-preview/` lists open PRs, preview links, and the exact built commits. It labels a retained preview as **Previous successful build** when the current PR head has no successful build yet.

After deployment succeeds, the publisher creates or updates one bot comment in each PR conversation with a prominent **Open preview** link and the built commit, or the owner-approval instructions when deployment is blocked. It reuses the comment without writing when the text is unchanged, and only edits comments owned by `github-actions[bot]` with the publisher’s hidden marker. A preview from an older successful build is labelled explicitly. Closing or merging a PR removes its directory and changes its existing comment to **Preview closed** after deployment succeeds; pending comment cleanup persists across failed deployments and retries. Reopening the PR lets the next successful deployment reuse the comment.

A **Pages preview** check on each current authorized, built PR commit also includes an **Open preview** link in its summary. A failed main build preserves production; a failed PR build preserves its previous authorized preview. Review both the ordinary `build` check and the built commit before assessing a preview. Previews are public and share the Pages origin with the main dashboard. Authorizing a preview means trusting its browser code: read-only data does not stop JavaScript from misleading users or reading same-origin browser storage and files a user imports into that page. The authorization gate is not a browser sandbox. The trusted publisher has `pull-requests: write` for comments and acknowledgment reactions; PR build jobs retain read-only permissions.

Generated files and their source run/commit identifiers persist on the `pages-content` branch, created automatically by the first publisher run. This is storage for the Actions publisher; **do not change Pages to deploy from this branch**. The stored files keep published previews available after their source artifacts expire. Every publisher run reconciles all open PRs and successful main builds, and publishing is serialized so concurrent builds cannot overwrite each other’s previews. Run **Publish dashboard and PR previews** manually to retry a failed deployment or reconcile missed updates. The workflow must be on `main` before automatic previews can run; existing successful artifacts can be picked up during that first deployment.

Only the four expected regular files are accepted from each build artifact, with a 100 MiB limit on each archive layer and its total file content. Unexpected paths, duplicate files, links, and malformed archives are rejected without extracting their paths. Invalid PR artifacts do not prevent production or other previews from publishing. Hidden Git/state files are excluded from the final Pages artifact.

To rehearse assembly with current GitHub artifacts, without pushing a branch, deploying Pages, or writing PR checks:

```sh
python3 scripts/pages_preview.py inspect --repository OpenEuroLLM/quickdash \
  --site output/preview-rehearsal --base-url https://openeurollm.github.io/quickdash
open output/preview-rehearsal/pr-preview/index.html
```

This requires an authenticated GitHub CLI (`gh`). The publisher uses Python’s standard library and `gh`; no package installation is required. `python3 -m tests.check` includes archive validation, snapshot updates, fork build identification, stale-build handling, cleanup, and preview-check regression tests. Review build or deployment failures in the repository’s **Actions** tab.

Before pushing, run the affected tests and check the README, config reference, and contribution instructions for changed commands or behavior. Contributions to [results](../results/README.md) and [configs](../configs/README.md) are validated by the same workflow.
