# demo-shop

A small FastAPI + SQLite orders API. It is the target repo for the
[Dibs](https://github.com/vivekyarra/dibs) live demo: a realistic codebase a junior
developer would work on, with **10 real bugs and feature requests**.

## Run

```bash
uv run pytest -q                       # 24 passed, 1 deselected, 5 xfailed
uv run uvicorn app.main:app --reload   # API on http://127.0.0.1:8000 (header X-API-Key: dev-key)
uv run python -m app.db                # apply migrations to $SHOP_DATABASE (default shop.sqlite3)
uv run python -m app.reports.daily     # yesterday's sales report
```

Layout: `app/api` (routes, errors, rate limiting), `app/orders` (service + SQL repo),
`app/webhooks` (outgoing webhooks), `app/workers` (outbox worker), `app/reports`,
`app/logging.py`, `migrations/` (plain SQL, applied by `app/db.py`), `tests/`.

## The bugs are real, and CI proves it

* `tests/known_bugs/test_known_bugs.py` has one `xfail(strict=True)` test per behavioural
  bug (#2, #3, #6, #8, #10). They show up as **xfailed** today. Fix a bug and its test
  passes, strict mode fails the run, and you delete the marker in the same PR.
* `test_order_totals` (#7) used to be flaky (random prices compared as floats). It now
  uses fixed cases, compares exact cents, and runs in the default suite.

## The issues

`issues.yaml` holds the issues in order. `scripts/create_issues.sh [--dry-run] <owner>/<repo>`
creates them with `gh issue create`, so they get numbers #1 to #10.

| # | Issue | Where | Skills (p = primary, s = secondary) | Est. h |
|---|---|---|---|---|
| 1 | Typo in 404 error message | `app/api/errors.py` | http-handlers:p | 0.1 |
| 2 | GET /orders returns every row: add pagination | `app/api/orders.py` | http-handlers:p, sql-queries:s | 1 |
| 3 | POST /orders creates duplicates when the client retries: make it idempotent | `app/orders/service.py` | idempotency:p, error-handling:s, http-handlers:s | 0.5 |
| 4 | Partition the orders table by month | `migrations/0002_partition.sql` (new) | migrations:p | 3 |
| 5 | Add per-API-key rate limiting | `app/api/ratelimit.py` | concurrency:p, observability:p | 2 |
| 6 | Webhook sender gives up on the first failure: add retries with backoff | `app/webhooks/sender.py` | error-handling:p, concurrency:s | 1 |
| 7 | test_order_totals is flaky | `tests/test_orders.py` | testing:p | 0.5 |
| 8 | N+1 query when listing orders with items | `app/orders/repo.py` | sql-queries:p | 0.5 |
| 9 | Add a correlation id to every log line | `app/logging.py` | observability:p | 1 |
| 10 | Daily report uses server local time instead of UTC | `app/reports/daily.py` | testing:p, error-handling:s | 1 |

## Dibs config

`.dibs/` holds the team (`team.yaml`: senior Ravi, junior Asha and their skill map),
the skill catalog (`skills.yaml`) and the learning-budget policy (`dibs.yaml`).
With these inputs Dibs reserves **#3** for Asha and routes the rest to the builder agent.
