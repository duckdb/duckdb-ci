# Benchmark harness

Runs a set of SQL benchmark queries against DuckDB storage using the DuckDB CLI, times
each query, validates its output against expected answers, and writes the per-query
execution time to a CSV file. All inputs are supplied through a single YAML config file.

## Usage

```sh
python3 run_benchmark.py --config config.yaml
```

See [`config.example.yaml`](config.example.yaml) for the config schema. Requires Python 3
and `pyyaml`.

## DuckDB binary

The `duckdb_binary` config field accepts either:

- **A path to an existing CLI executable** (e.g. a local build) — used as-is, or
- **A pinned release version** such as `v1.5.5` — the harness installs that release via the
  official DuckDB install script (`curl https://install.duckdb.org | sh` with
  `DUCKDB_VERSION` set) and uses the resulting `~/.duckdb/cli/<version>/duckdb`. An
  already-installed version is reused without re-installing.

Only pinned versions are accepted; floating refs like `latest` are rejected so recorded
timings always correspond to a known DuckDB version. On a cache miss the run fetches and
runs the install script from `install.duckdb.org` (so `curl` must be on PATH).

## Storage

The `storage` field selects what the queries run against:

- `type: duckdb` — `path` is a DuckDB database file, opened directly by the CLI.
- `type: ducklake` — `path` is a DuckLake target (a local `.ducklake` metadata file or a
  connection string such as `postgres:...`). The harness attaches it before running the
  queries:

  ```sql
  INSTALL ducklake;
  LOAD ducklake;
  ATTACH 'ducklake:<path>' AS ducklake_bench;
  USE ducklake_bench;
  ```

## DuckDB settings

The optional `threads` and `memory_limit` config fields are applied via the CLI as
`SET threads = <n>;` and `SET memory_limit = '<value>';`. Omit either to leave DuckDB at its
default. Together with the storage setup, they run **once per subprocess** before
`.timer on`, so they are set once per query (not per run) and are never included in the
recorded query time.

## How it works

Each `qNN.sql` is benchmarked in a **single DuckDB subprocess**: the one-time setup, then
the query executed 11 times under `.timer on` — a cold run to warm the caches followed by
10 timed warm runs. Running all iterations in one process means the warm runs share the
cache the cold run populated. The `timeout` parameter applies **per query run**.

```sh
# conceptually, per query:
printf '.bail on\nSET threads = 4;\n.timer on\n.mode list\n<query>\n<query>\n...' | duckdb <data.db>
```

- Setup runs **before** `.timer on`, so it is not timed and only the query executions emit
  result rows.
- `.bail on` makes DuckDB stop and exit non-zero on the first error, so a failing statement
  is reported as an error (with DuckDB's message) rather than a silent empty result.
- `.mode list` produces pipe-delimited output with a header row, matching the format of
  the answer files.
- `.timer on` appends a `Run Time (s): real <seconds> ...` line after each execution, and
  the harness parses one timing per run (pure query execution, excluding CLI startup).

The 10 warm runs' results are validated against `answers/qNN.csv` (same stem as the query),
and the report records those 10 timings plus their median. A query that **fails** — wrong
result, timeout, non-zero DuckDB exit, or unparseable output — is recorded in the report
(`status=failed` with a short `error`, and the full diff printed to stdout) and the run
continues with the next query. The process still exits 0; the `status` column is how you
tell which queries failed.

## Layout

```
queries/
  q01.sql        # one query statement per file
  q02.sql
answers/
  q01.csv        # expected result, pipe-delimited, with header
  q02.csv
data.db          # DuckDB database (or a DuckLake) the queries run against
```

## Output

Results are written into a **DuckLake** (configured via `results.ducklake`). Each
invocation is one benchmark *run*, identified by a generated UUID. 
Two tables are created on first use:

**`runs`** — one row per invocation:

| column | notes |
|---|---|
| `run_id` | uuid4, logical key |
| `timestamp` | run start, UTC |
| `benchmark_name` | from config |
| `duckdb_version` | from the CLI's `--version` (e.g. `v1.5.4`) |
| `os`, `cpu_arch` | e.g. `macos` / `arm64` |
| `threads`, `memory_limit`, `storage_type`, `timeout`, `warm_runs` | run settings |

**`query_results`** — one row per query per run, logical key `(run_id, query)`:

| column | notes |
|---|---|
| `run_id` | foreign key to `runs.run_id` |
| `query` | `qNN` stem |
| `status` | `ok` / `failed` |
| `error` | failure reason, `NULL` when `ok` |
| `cold_seconds` | cold run's time |
| `median_seconds` | median of the warm runs (`NULL` when failed) |
| `timings_seconds` | `DOUBLE[]` of the 10 warm timings (`[]` when failed) |

The harness stages the rows as JSON and loads them via a `duckdb` subprocess
(`ATTACH 'ducklake:…'` + `INSERT`), so writing results needs the `ducklake` extension at
run time.

### Results DuckDB

Because the version under test (`duckdb_binary`) may be an alpha or a build without the
`ducklake` extension, the DuckLake write uses a **separate pinned stable DuckDB** —
overridable via `results.duckdb_version`. Before loading,
the harness probes `duckdb_extensions()` and aborts with a clear message if `ducklake`
(or `httpfs`, for S3) is missing. The `runs.duckdb_version` column always records the
version *under test*, not this writer.

### S3-backed DuckLake

Point `results.ducklake` / `results.data_path` at `s3://…` and add a `results.s3` block
(`region`, optional `endpoint`/`url_style`). The harness loads `httpfs` and creates an S3
secret with `PROVIDER credential_chain`.
DuckDB reads s3 credentials from the environment and injects them at invocation; the harness stays secret-store-agnostic.
