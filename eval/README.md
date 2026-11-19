# Evaluation results (M4)

**Deliverable for M4 1.1: [`Testing Results_1.1.csv`](Testing%20Results_1.1.csv).** It holds all 10 test cases (E1–E10) from the M3 evaluation plan: input, expected output, actual output, pass/fail, critic-agent score, and the failure cause and analysis for every failed case. It also has rows for the overall pass rate (**7/10, 70%**) and the two hard gates.

Everything else in this folder is the evidence behind that file.

| Folder / file | What it is |
|---|---|
| `baseline/results.md` | Full per-run details for the baseline (the unchanged M3 agent), with the failure analysis |
| `baseline/eval_run.log`, `baseline/raw/*.json` | Console log and complete raw output of the full suite run, 17 Nov 2026 |
| `baseline/grounding_bullets.csv` | Every bullet the critic agent (qwen3) scored 1–5, with its cited headline |
| `baseline/e9_run2/`, `baseline/e9_run3/` | E9 reruns on 18 Nov 2026 (3-run reliability rule), with critic scores |
| `human/human_spotcheck.csv` | E10 human spot-check: 20 random bullets judged against the critic (16/20 agreement) |
| `human/Human_Review_1.csv`, `human/Human_Review_2.csv` | Two raters' relevance, tone and single-study framing scores (32 bullets) |
| `human/human_review_rubric.md`, `human/human_review_results.md` | The rubric the raters used, and the scored results |
| `after_1.2/eval_run.log` | Rerun after the five 1.2 agent changes (E1–E8; see the README's CHANGES section) |

Reproduce: `python tests/run_eval.py` runs the full suite (about 1 hour, needs the NRP key); `--only E4 E6` runs selected cases, and `--out` sets the output folder (default `eval/latest/`). Cases are defined in `tests/eval_cases.json`.
