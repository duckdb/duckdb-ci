# Benchmark harness

Runs a set of SQL benchmark queries against a DuckDB database using the DuckDB CLI
binary, times each query, validates its output against expected answers, and writes the
per-query execution time to a CSV file. All inputs are supplied through a single YAML
config file.

## Usage

```sh
python3 run_benchmark.py --config config.yaml
```

See [`config.example.yaml`](config.example.yaml) for the config schema. Requires Python 3
and `pyyaml`.

## How it works

For each `qNN.sql` in the `queries` directory, the harness feeds the query to the DuckDB
CLI with `.timer on` and `.mode list`:

```sh
printf '.timer on\n.mode list\n<query>' | duckdb <data.db>
```

- `.mode list` produces pipe-delimited output with a header row, matching the format of
  the answer files.
- `.timer on` appends a `Run Time (s): real <seconds> ...` line, which is parsed for the
  recorded execution time (pure query execution, excluding CLI startup).

The query result is compared against `answers/qNN.csv` (same stem as the query). The run
**fails fast** — a non-zero DuckDB exit, a timeout, or a result mismatch prints a diff and
exits non-zero. The results CSV is written only after every query has run and validated,
so a written file always represents a fully-passing run.

## Layout

```
queries/
  q01.sql        # one query statement per file
  q02.sql
answers/
  q01.csv        # expected result, pipe-delimited, with header
  q02.csv
data.db          # DuckDB database the queries run against
```

## Output

CSV with a header and one row per query:

```
query,time_seconds
q01,0.008
q02,0.042
```
