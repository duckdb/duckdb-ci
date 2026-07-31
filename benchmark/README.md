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

The optional `threads` and `memory_limit` config fields are applied via the CLI before each
query, as `SET threads = <n>;` and `SET memory_limit = '<value>';` respectively. Omit either
to leave DuckDB at its default. Like the storage setup, they run before `.timer on`, so they
are not included in the recorded query time.

## How it works

For each `qNN.sql` in the `queries` directory, the harness runs the settings/storage setup
(if any), then the query, under the DuckDB CLI with `.timer on` and `.mode list`:

```sh
printf '.timer on\n.mode list\n<query>' | duckdb <data.db>
```

- Storage setup runs **before** `.timer on`, so only the query is timed and only the query
  emits result rows.
- `.mode list` produces pipe-delimited output with a header row, matching the format of
  the answer files.
- `.timer on` appends a `Run Time (s): real <seconds> ...` line, which is parsed for the
  recorded execution time (pure query execution, excluding CLI startup).

Each query's first run is validated against `answers/qNN.csv` (same stem as the query); only
if it matches does the query run the remaining times, and the report records all 10 timings
plus their median. A query that **fails** — wrong result, timeout, non-zero DuckDB exit, or
unparseable output — is not retried: its failure is recorded in the report (`status=failed`
with a short `error`, and the full diff printed to stdout) and the run continues with the
next query. The process still exits 0; the `status` column is how you tell which queries
failed.

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

CSV with a header and one row per query: `status` (`ok`/`failed`), an `error` reason for
failures, then the median and each of the 10 run timings (all in seconds). A failed query
leaves the timing cells blank:

```
benchmark_name,query,status,error,median_seconds,run_1_seconds,...,run_10_seconds
my_benchmark,q01,ok,,0.008,0.009,0.008,...,0.008
my_benchmark,q02,failed,result does not match expected answer,,,...,
```
