import argparse
import functools
import json
import os
import platform
import queue
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, NoReturn, Optional, Tuple

import yaml

print = functools.partial(print, flush=True)

STDERR_HEADER = '''====================================================
==============         STDERR          =============
====================================================
'''

STDOUT_HEADER = '''====================================================
==============         STDOUT          =============
====================================================
'''

# timeouts in seconds
MAX_TIMEOUT = 3600
DEFAULT_TIMEOUT = 600

# Number of timed (warm) runs recorded per query. Each query is run once in the beginning cold.
RUNS = 10

# Alias the DuckLake catalog is attached under before running the queries.
DUCKLAKE_ALIAS = "ducklake_bench"

# Alias and table names of the DuckLake instance the results are written to.
RESULTS_ALIAS = "results_lake"
RUNS_TABLE = "runs"
QUERY_RESULTS_TABLE = "query_results"

STORAGE_TYPES = ("duckdb", "ducklake")

# Matches the timing line emitted by the DuckDB CLI when `.timer on` is set, e.g.
#   Run Time (s): real 0.008 user 0.000769 sys 0.001329
RUN_TIME_RE = re.compile(r"^Run Time \(s\): real ([0-9.eE+-]+)")

# A pinned DuckDB release tag such as v1.5.5 (or 1.5.5), or alpha releases
# 2.0.0-alpha36255. Floating refs like "latest" are intentionally rejected so
# recorded timings always map to a known DuckDB version.
VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$")

# The official DuckDB install script installs a pinned CLI to ~/.duckdb/cli/<version>/duckdb.
DUCKDB_CLI_ROOT = os.path.expanduser("~/.duckdb/cli")
DUCKDB_INSTALL_URL = "https://install.duckdb.org"


def install_release_cli(version: str) -> str:
    """Install (and cache) a pinned DuckDB release via the official install script,
    returning the path to its CLI. `version` has no leading 'v' (e.g. 1.5.5)."""
    binary = os.path.join(DUCKDB_CLI_ROOT, version, "duckdb")
    if os.path.isfile(binary):  # already available: reuse without re-installing
        return binary
    if shutil.which("curl") is None:
        raise RuntimeError("curl is required to install a DuckDB release but was not found on PATH")

    print(f"Installing DuckDB {version} via {DUCKDB_INSTALL_URL}")
    
    env = {**os.environ, "DUCKDB_VERSION": version}
    proc = subprocess.run(
        f"curl -fsSL {DUCKDB_INSTALL_URL} | sh",
        shell=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stdout.strip() or f"install script exited with status {proc.returncode}"
        raise RuntimeError(f"Failed to install DuckDB {version}: {detail}")
    # The outer `curl | sh` can report success even if fetching the script failed (the pipe
    # hides curl's exit status), so confirm the expected binary was actually produced.
    if not os.path.isfile(binary):
        raise RuntimeError(f"DuckDB install script did not produce a CLI at {binary} (no such version?)")
    return binary


def resolve_duckdb_binary(value: str) -> str:
    """Resolve the `duckdb_binary` config value to a path to a duckdb executable.

    The value is either an existing local binary path (used as-is) or a pinned release
    version such as v1.5.5 (installed via the official script and cached under
    ~/.duckdb/cli/<version>/)."""
    if os.path.isfile(value):
        return value
    if not VERSION_RE.match(value):
        raise ValueError(
            f"'duckdb_binary' is neither an existing file nor a pinned version "
            f"(e.g. v1.5.5): {value!r}"
        )
    version = value[1:] if value.startswith("v") else value
    return install_release_cli(version)


@dataclass
class BenchmarkConfig:
    "Configuration for the benchmark harness, loaded from a YAML file."

    benchmark_name: str
    duckdb_binary: str
    storage_type: str
    storage_path: str
    queries: str
    answers: str
    results_ducklake: str
    results_data_path: Optional[str] = None
    timeout: int = DEFAULT_TIMEOUT
    threads: Optional[int] = None
    memory_limit: Optional[str] = None

    @classmethod
    def from_file(cls, config_path: str) -> "BenchmarkConfig":
        with open(config_path, 'r') as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"Config file {config_path} must contain a YAML mapping")

        required = ["benchmark_name", "duckdb_binary", "storage", "queries", "answers", "results"]
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ValueError(f"Config file {config_path} is missing required keys: {', '.join(missing)}")

        storage = raw["storage"]
        if not isinstance(storage, dict) or not storage.get("type") or not storage.get("path"):
            raise ValueError("'storage' must be a mapping with 'type' and 'path' keys")
        storage_type = storage["type"]
        if storage_type not in STORAGE_TYPES:
            raise ValueError(f"'storage.type' must be one of {STORAGE_TYPES}, got: {storage_type!r}")

        results = raw["results"]
        if not isinstance(results, dict) or not results.get("ducklake"):
            raise ValueError("'results' must be a mapping with a 'ducklake' target")

        timeout = raw.get("timeout", DEFAULT_TIMEOUT)
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"'timeout' must be a positive integer, got: {timeout!r}")

        threads = raw.get("threads")
        if threads is not None and (not isinstance(threads, int) or threads <= 0):
            raise ValueError(f"'threads' must be a positive integer, got: {threads!r}")

        memory_limit = raw.get("memory_limit")
        if memory_limit is not None and (not isinstance(memory_limit, str) or not memory_limit.strip()):
            raise ValueError(f"'memory_limit' must be a non-empty string (e.g. '4GB'), got: {memory_limit!r}")

        config = cls(
            benchmark_name=raw["benchmark_name"],
            duckdb_binary=raw["duckdb_binary"],
            storage_type=storage_type,
            storage_path=storage["path"],
            queries=raw["queries"],
            answers=raw["answers"],
            results_ducklake=results["ducklake"],
            results_data_path=results.get("data_path"),
            timeout=timeout,
            threads=threads,
            memory_limit=memory_limit,
        )
        config.validate_paths()
        return config

    def validate_paths(self) -> None:
        for key, path in (("queries", self.queries), ("answers", self.answers)):
            if not os.path.isdir(path):
                raise FileNotFoundError(f"'{key}' path does not exist or is not a directory: {path}")

        # A DuckDB storage path is always a local file. A DuckLake path may be a local
        # metadata file or a connection string (e.g. postgres:...); only validate the
        # former, and let DuckDB report attach errors for connection strings.
        if self.storage_type == "duckdb":
            if not os.path.isfile(self.storage_path):
                raise FileNotFoundError(f"'storage.path' database file does not exist: {self.storage_path}")
        elif ":" not in self.storage_path and not os.path.exists(self.storage_path):
            raise FileNotFoundError(f"'storage.path' DuckLake metadata file does not exist: {self.storage_path}")


class QueryFailure(Exception):
    """A failure of a single query: the query is skipped and recorded in the
    report, but the benchmark run continues with the remaining queries."""

    def __init__(self, reason: str, detail: str = "", stdout: str = "", stderr: str = ""):
        super().__init__(reason)
        self.reason = reason    # concise, single-line — goes in the report's `error` column
        self.detail = detail    # optional multi-line context (e.g. a diff) — printed to stdout
        self.stdout = stdout
        self.stderr = stderr


@dataclass
class QueryResult:
    "Outcome of a benchmarked query."

    name: str
    status: str                 # "ok" or "failed"
    error: str = ""             # failure reason (empty when status is "ok")
    cold_timing: Optional[float] = None
    timings: List[float] = field(default_factory=list)
    median: Optional[float] = None


class BenchmarkRunner:
    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.duckdb_binary = resolve_duckdb_binary(config.duckdb_binary)
        self.query_files = self.discover_queries()
        self.run_id = str(uuid.uuid4())

    def duckdb_version(self) -> str:
        """The actual CLI version, parsed from `--version` (e.g. 'v1.5.4 (Variegata)
        08e34c447b' -> 'v1.5.4'). Read from the binary since `duckdb_binary` may be a local
        build path that carries no version."""
        proc = subprocess.run(
            [self.duckdb_binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return proc.stdout.strip().split()[0] if proc.stdout.strip() else ""

    def discover_queries(self) -> List[str]:
        query_files = sorted(
            os.path.join(self.config.queries, name)
            for name in os.listdir(self.config.queries)
            if name.endswith(".sql")
        )
        if not query_files:
            raise FileNotFoundError(f"No .sql query files found in {self.config.queries}")
        return query_files

    def answer_path_for(self, query_path: str) -> str:
        stem = os.path.splitext(os.path.basename(query_path))[0]
        answer_path = os.path.join(self.config.answers, stem + ".csv")
        if not os.path.isfile(answer_path):
            raise FileNotFoundError(f"No answer file for query {os.path.basename(query_path)}: expected {answer_path}")
        return answer_path

    def build_command(self) -> List[str]:
        """The duckdb invocation. A DuckDB file is opened positionally; a DuckLake is
        attached in-script against an in-memory catalog."""
        cmd = [self.duckdb_binary]
        if self.config.storage_type == "duckdb":
            cmd.append(self.config.storage_path)
        return cmd

    def init_setup(self) -> List[str]:
        lines: List[str] = []
        if self.config.threads is not None:
            lines.append(f"SET threads = {self.config.threads};")
        if self.config.memory_limit is not None:
            lines.append(f"SET memory_limit = '{self.config.memory_limit}';")
        if self.config.storage_type == "ducklake":
            lines += [
                "INSTALL ducklake;",
                "LOAD ducklake;",
                f"ATTACH 'ducklake:{self.config.storage_path}' AS {DUCKLAKE_ALIAS};",
                f"USE {DUCKLAKE_ALIAS};",
            ]
        return lines

    def run_query(self, query_path: str) -> Tuple[Optional[float], List[float]]:
        with open(query_path, 'r') as f:
            query_sql = f.read().strip()
        # Each run is fed as a separate statement, so the query must be terminated.
        if not query_sql.endswith(";"):
            query_sql += ";"

        total_runs = RUNS + 1  # 1 cold + RUNS warm (recorded)
        return self.execute_runs(query_path, query_sql, total_runs)

    def execute_runs(self, query_path: str, query_sql: str, total_runs: int) -> Tuple[Optional[float], List[float]]:
        """Run `query_sql` `total_runs` times in one DuckDB subprocess (so the warm runs
        reuse the cold run's cache). Each run's result is validated as it completes, so a
        wrong result aborts the query early. Returns (cold_timing, warm_timings)."""
        answer_path = self.answer_path_for(query_path)
        with open(answer_path, 'r') as f:
            expected = f.read().strip()

        proc = subprocess.Popen(
            self.build_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_lines: "queue.Queue[Optional[str]]" = queue.Queue()
        stderr_chunks: List[str] = []
        out_reader = threading.Thread(target=self._pump, args=(proc.stdout, stdout_lines), daemon=True)
        err_reader = threading.Thread(target=lambda: stderr_chunks.append(proc.stderr.read()), daemon=True)
        out_reader.start()
        err_reader.start()

        def exited() -> NoReturn:
            # stdout closed / broken pipe: DuckDB ended (typically a query error). Surface it.
            proc.wait()
            err_reader.join(timeout=5)
            raise QueryFailure("DuckDB exited with a non-zero status", stderr="".join(stderr_chunks))

        def await_run() -> Tuple[float, str]:
            """Read one run's output, up to `timeout` seconds for its `Run Time` line."""
            result_lines: List[str] = []
            deadline = time.monotonic() + self.config.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise QueryFailure(f"timeout after {self.config.timeout}s")
                try:
                    line = stdout_lines.get(timeout=remaining)
                except queue.Empty:
                    raise QueryFailure(f"timeout after {self.config.timeout}s")
                if line is None:
                    exited()
                match = RUN_TIME_RE.match(line)
                if match:
                    return float(match.group(1)), "\n".join(result_lines).strip()
                result_lines.append(line)

        try:
            # `.bail on` makes DuckDB stop and exit non-zero on the first error 
            # instead of continuing; that surfaces the error via `exited()` rather than
            # letting a failed statement look like an empty result.
            setup = "\n".join([".bail on", *self.init_setup(), ".timer on", ".mode list", ""])
            self._write(proc, setup, exited)
            cold_timing: Optional[float] = None
            warm_timings: List[float] = []
            for run_index in range(total_runs):
                self._write(proc, query_sql + "\n", exited)
                timing, result_block = await_run()
                try:
                    self.validate(result_block, expected, answer_path)
                except QueryFailure as mismatch:
                    # A DuckDB error still returns an empty result plus a `Run time` line causing also a result mismatch.
                    # The only signal that separates this case from an actual query mismatch error is whether the process stays alive.
                    # In case of DuckDB error, the process exits. So on a mismatch failure we ask exactly that.
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        raise mismatch  # process healthy — it really is a wrong result
                    exited()
                if run_index == 0:  # the first run is the cold run; recorded separately
                    cold_timing = timing
                else:
                    warm_timings.append(timing)
            self._write(proc, ".quit\n", lambda: None)
            return cold_timing, warm_timings
        finally:
            if proc.poll() is None:
                proc.kill()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    stream.close()
                except OSError:
                    pass
            proc.wait()

    @staticmethod
    def _pump(stream, out_queue: "queue.Queue[Optional[str]]") -> None:
        for line in stream:
            out_queue.put(line.rstrip("\n"))
        out_queue.put(None)  # EOF sentinel

    def _write(self, proc: "subprocess.Popen[str]", data: str, on_broken) -> None:
        try:
            proc.stdin.write(data)
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            on_broken()

    def validate(self, result_block: str, expected: str, answer_path: str) -> None:
        if result_block != expected:
            raise QueryFailure(
                "result does not match expected answer",
                detail=f"Expected answer: {answer_path}\n"
                f"---- EXPECTED ----\n{expected}\n---- ACTUAL ----\n{result_block}",
            )

    def print_failure(self, query_path: str, failure: QueryFailure) -> None:
        print(f"Failed to run benchmark {os.path.basename(query_path)}")
        print(failure.reason)
        if failure.detail:
            print(failure.detail)
        if failure.stderr:
            print(STDERR_HEADER)
            print(failure.stderr)
        if failure.stdout:
            print(STDOUT_HEADER)
            print(failure.stdout)

    def run(self) -> List[QueryResult]:
        results: List[QueryResult] = []
        for query_path in self.query_files:
            name = os.path.splitext(os.path.basename(query_path))[0]
            try:
                cold_timing, timings = self.run_query(query_path)
            except QueryFailure as failure:
                self.print_failure(query_path, failure)
                results.append(QueryResult(name, status="failed", error=failure.reason))
                continue
            median = statistics.median(timings)
            print(f"{name}: median {median}s over {RUNS} warm runs")
            results.append(
                QueryResult(name, status="ok", cold_timing=cold_timing, timings=timings, median=median)
            )
        return results

    def run_record(self) -> dict:
        """The single `runs` row: identity + environment + settings for this run."""
        return {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "benchmark_name": self.config.benchmark_name,
            "duckdb_version": self.duckdb_version(),
            "os": "macos" if platform.system() == "Darwin" else platform.system().lower(),
            "cpu_arch": platform.machine(),
            "threads": self.config.threads,
            "memory_limit": self.config.memory_limit,
            "storage_type": self.config.storage_type,
            "timeout": self.config.timeout,
            "warm_runs": RUNS,
        }

    def query_records(self, results: List[QueryResult]) -> List[dict]:
        """One `query_results` row per query, tagged with this run's id."""
        return [
            {
                "run_id": self.run_id,
                "query": r.name,
                "status": r.status,
                "error": r.error or None,
                "cold_timing": r.cold_timing,
                "median_seconds": r.median,
                "timings_seconds": r.timings,
            }
            for r in results
        ]

    def write_results(self, results: List[QueryResult]) -> None:
        """Write this run into the results DuckLake: stage the rows as JSON, then attach the
        DuckLake and INSERT (creating the tables on first use)."""
        with tempfile.TemporaryDirectory() as tmp:
            runs_json = os.path.join(tmp, "runs.json")
            query_results_json = os.path.join(tmp, "query_results.json")
            with open(runs_json, "w") as f:
                json.dump([self.run_record()], f)
            with open(query_results_json, "w") as f:
                json.dump(self.query_records(results), f)

            script = self.results_load_script(runs_json, query_results_json)
            proc = subprocess.run(
                [self.duckdb_binary], input=script, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Failed to write results to DuckLake:\n{proc.stderr.strip()}")
        print(f"Wrote run {self.run_id} ({len(results)} queries) to DuckLake {self.config.results_ducklake}")

    def results_load_script(self, runs_json: str, query_results_json: str) -> str:
        data_path = f" (DATA_PATH '{self.config.results_data_path}')" if self.config.results_data_path else ""
        return f"""
INSTALL ducklake;
LOAD ducklake;
ATTACH 'ducklake:{self.config.results_ducklake}' AS {RESULTS_ALIAS}{data_path};
USE {RESULTS_ALIAS};
CREATE TABLE IF NOT EXISTS {RUNS_TABLE} (
  run_id VARCHAR, timestamp TIMESTAMP, benchmark_name VARCHAR, duckdb_version VARCHAR,
  os VARCHAR, cpu_arch VARCHAR, threads INTEGER, memory_limit VARCHAR,
  storage_type VARCHAR, timeout INTEGER, warm_runs INTEGER
);
CREATE TABLE IF NOT EXISTS {QUERY_RESULTS_TABLE} (
  run_id VARCHAR, query VARCHAR, status VARCHAR, error VARCHAR,
  cold_timing DOUBLE, median_seconds DOUBLE, timings_seconds DOUBLE[]
);
INSERT INTO {RUNS_TABLE} BY NAME
  SELECT * FROM read_json_auto('{runs_json}');
INSERT INTO {QUERY_RESULTS_TABLE} BY NAME
  SELECT * FROM read_json('{query_results_json}', columns = {{
    'run_id': 'VARCHAR', 'query': 'VARCHAR', 'status': 'VARCHAR', 'error': 'VARCHAR',
    'cold_timing': 'DOUBLE', 'median_seconds': 'DOUBLE', 'timings_seconds': 'DOUBLE[]'
  }});
"""


def main():
    parser = argparse.ArgumentParser(description="Run DuckDB benchmark queries defined by a YAML config.")
    parser.add_argument("--config", type=str, required=True, help="Path to the YAML configuration file.")
    args = parser.parse_args()

    try:
        config = BenchmarkConfig.from_file(args.config)
        runner = BenchmarkRunner(config)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError) as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    results = runner.run()
    try:
        runner.write_results(results)
    except RuntimeError as e:
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
