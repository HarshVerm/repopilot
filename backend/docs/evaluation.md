# RepoPilot Evaluation and Hardening

## Run the Evaluation Harness

Dry-run validates the suite, fixtures, hidden-test manifests, base SHAs, and
configuration without calling model providers:

```bash
python scripts/run_evals.py --suite repopilot-eval-v1 --dry-run
```

Live benchmark execution is opt-in and requires:

```bash
EVALUATION_MODE=true python scripts/run_evals.py --suite repopilot-eval-v1 --live
```

Useful filters:

```bash
python scripts/run_evals.py --dry-run --task eval-001-react-search-debounce
python scripts/run_evals.py --dry-run --difficulty medium --max-tasks 3
python scripts/run_evals.py --dry-run --category "Python bug"
```

Reports are written to `evals/reports/<run-id>.json` and
`evals/reports/<run-id>.md`.

## Suite Structure

`evals/tasks/repopilot-eval-v1/tasks.json` defines 20 tasks. Each task records:

- suite version
- difficulty and category
- agent-visible issue title/body
- fixture path and deterministic base commit SHA
- evaluator-only relevant and expected modified files
- protected files
- hidden test manifest path

The agent-visible payload intentionally excludes hidden tests, expected files,
relevant-file annotations, and any gold solution.

## Hidden-Test Isolation

Fixture repositories live under `evals/fixtures`. Hidden tests live separately
under `evals/hidden_tests`. The runner copies a clean fixture to an evaluation
workspace, lets RepoPilot plan/code/debug normally, and only then copies hidden
test files into a Docker sandbox copy for final scoring.

## Add a New Benchmark Task

1. Add or update a fixture under `evals/fixtures`.
2. Compute the deterministic fixture hash and base commit SHA with the dry-run
   helper or by running `python scripts/run_evals.py --dry-run`.
3. Add a task entry in the next suite version.
4. Add evaluator-only relevant files and optional expected modified files.
5. Add a hidden test manifest under `evals/hidden_tests/<suite-version>`.
6. Run dry-run.
7. Run a targeted live eval only with `EVALUATION_MODE=true`.
8. Inspect JSON and Markdown reports.

## Metric Definitions

Task success requires a generated patch, preserved policy/security boundaries,
visible verification pass, hidden verification pass, and zero applied critical
security violations.

Retrieval Recall@K is file-level:

`relevant files retrieved in top K / total relevant files`

Precision@5 is file-level:

`relevant files in top 5 unique retrieved files / 5`

First-pass success counts tasks whose first coder patch passed verification
before debugger repair. Debug recovery only considers tasks with at least one
debug attempt.

Cost is null when pricing is not configured for a model.

## Readiness

`GET /health` is cheap and only reports process liveness.

`GET /ready` checks PostgreSQL, workspace root, sandbox root, Docker availability,
and startup configuration. It does not call OpenAI, GitHub, or create PRs.

Production readiness reports keep hard gates for critical security violations;
one critical applied violation makes the system not ready even if quality metrics
look good.

## Required Environment

Live evals require provider credentials and Docker availability:

- `OPENAI_API_KEY`
- database configured by `DATABASE_URL`
- Docker daemon reachable for sandbox and hidden verification
- `EVALUATION_MODE=true`

Do not put secrets in suite definitions, fixtures, reports, or hidden tests.
