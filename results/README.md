# Share evaluation results

Add a CSV directly to this directory to make its models available on the [shared dashboard](https://openeurollm.github.io/quickdash/). You can use GitHub’s **Add file → Upload files** or submit a pull request. After the change reaches `main`, the Pages workflow validates the inputs and rebuilds the site.

When this directory contains no CSVs, Pages shows the [sample dataset and synthetic comparisons](../examples/README.md). Adding the first shared CSV replaces the sample. Remove `default.yaml` as well when removing all shared CSVs, so stale model references do not prevent the fallback build.

The shared files are `flag-evals-471` exports retrieved on 2026-10-09 from
`/scratch/project_465002530/poppelko/flag-evals/results/` on LUMI. Each contains
2,123 measurement rows, including 101 rows for 33 `_cot` reasoning and `_cont`
code-continuation tasks. The default `flagship-1` set selects these corrected
protocols using `pass@1`, filter `all`, at 0 shots (3 for `mbpp_cont`). Original
protocol rows remain inspectable under separate catalogue entries but do not
contribute to this set. Missing corrected results produce incomplete coverage;
there is no fallback to original runs. **Any available** can include both
protocols. See the [protocol selection rules](../docs/configuration.md#choose-weights-and-expected-coverage).
The exports retain their original metric values, shot counts, checkpoint labels,
and source metadata.

Choose the models shown on first opening the dashboard in [default.yaml](default.yaml):

```yaml
a: v1annealC_120k_l0fix
b: v2anneal_120k
```

Use exact `checkpoint` labels from the CSVs, not filenames. All other models remain selectable. This file only sets the initial A/B selection; it does not change scoring, user selections, or temporary imports. Missing labels, extra keys, and malformed defaults fail the build before replacing output. Without this optional file, the dashboard starts with the first two checkpoint labels alphabetically (or a synthetic comparison when only one model is loaded). Direct single-CSV builds do not read this file.

**This repository and its dashboard are public.** Commit only results you intend to share publicly, including any source paths or metadata in the CSV. For private comparisons, use the dashboard’s **Add model CSV** button instead; those files stay in your browser. The ignored `data/` directory is for local exports.

Use a descriptive filename such as `method-a-100k.csv`. Each row needs these columns:

```csv
checkpoint,task,metric,filter,n_shot,harness,backend,value
method-a-100k,my_eval_en,acc_norm,none,0,lm-eval,vllm,0.72
```

The row above illustrates the format; `my_eval_en` needs a matching eval entry and an explicit language assignment in the global catalogue. See [CSV requirements](../docs/configuration.md#data-validation-and-failure-behavior) and [adding configurations](../configs/README.md).

- Use a distinct `checkpoint` label for each model/run. A file may contain several models, but a label cannot occur in two files. Replace a model’s existing file when updating it, or give a new run a new label.
- Keep raw metric values in their original scale. The config chooses the metric and applies normalization.
- Only CSV files directly in this directory are loaded; subdirectories are not scanned.
- Malformed files, duplicate labels, and invalid selected scores stop the build. One-sided coverage, missing named-set requirements, or an unconfigured task appears as a warning in the dashboard; it is excluded from the relevant score.
- Review the selected comparison’s warnings. Any available needs no expected-eval list; a named set checks missing and extra measurements. Weights can be changed independently of that choice.

To check a contribution locally:

```sh
python3 -m app.build --results-dir results --output output/shared
```

Open `output/shared/index.html`, select your model, and inspect **Warnings** and **Eval configuration**. Removing a CSV and rebuilding removes its models from the published page. A failed build leaves the last successful site online.
