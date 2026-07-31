import argparse
import csv
import functools
import os
import re
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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

# Number of times each query is run; the report records every timing plus their median.
RUNS = 10

# Alias the DuckLake catalog is attached under before running the queries.
DUCKLAKE_ALIAS = "ducklake_bench"

STORAGE_TYPES = ("duckdb", "ducklake")

# Matches the timing line emitted by the DuckDB CLI when `.timer on` is set, e.g.
#   Run Time (s): real 0.008 user 0.000769 sys 0.001329
RUN_TIME_RE = re.compile(r"^Run Time \(s\): real ([0-9.eE+-]+)")

# A pinned DuckDB release tag such as v1.5.5 (or 1.5.5). Floating refs like "latest" are
# intentionally rejected so recorded timings always map to a known DuckDB version.
VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+$")

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
    # DUCKDB_VERSION pins the release. It is passed through the environment (not
    # interpolated into the shell command) so the version string cannot inject shell code.
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
    results: str
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
            results=raw["results"],
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
    timings: List[float] = field(default_factory=list)
    median: Optional[float] = None


class BenchmarkRunner:
    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.duckdb_binary = resolve_duckdb_binary(config.duckdb_binary)
        self.query_files = self.discover_queries()

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

    def build_script(self, query_sql: str) -> str:
        """Storage setup runs before `.timer on` so only the query is timed and only the
        query emits result rows. `.mode list` yields pipe-delimited output with a header
        row, matching the answer file format."""
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
        lines += [".timer on", ".mode list", query_sql]
        script = "\n".join(lines)
        if not script.endswith("\n"):
            script += "\n"
        return script

    def run_query_once(self, query_path: str) -> Tuple[float, str]:
        """Run a query a single time, returning (execution_time_seconds, result_block)."""
        with open(query_path, 'r') as f:
            query_sql = f.read().strip()

        duckdb_cli = self.build_command()
        try:
            proc = subprocess.run(
                duckdb_cli,
                input=self.build_script(query_sql),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.config.timeout,
            )
        except subprocess.TimeoutExpired:
            raise QueryFailure(f"timeout after {self.config.timeout}s")

        if proc.returncode != 0:
            raise QueryFailure(
                "DuckDB exited with a non-zero status", stdout=proc.stdout, stderr=proc.stderr
            )

        return self.parse_output(proc.stdout)

    def parse_output(self, stdout: str) -> Tuple[float, str]:
        result_lines: List[str] = []
        timing: Optional[float] = None
        for line in stdout.splitlines():
            match = RUN_TIME_RE.match(line)
            if match:
                # Only the query runs under the timer, so there is a single timing line.
                timing = float(match.group(1))
            else:
                result_lines.append(line)

        if timing is None:
            raise QueryFailure("could not parse a 'Run Time (s)' line from DuckDB output", stdout=stdout)

        result_block = "\n".join(result_lines).strip()
        return timing, result_block

    def validate(self, query_path: str, result_block: str) -> None:
        answer_path = self.answer_path_for(query_path)
        with open(answer_path, 'r') as f:
            expected = f.read().strip()
        if result_block != expected:
            raise QueryFailure(
                "result does not match expected answer",
                detail=f"Expected answer: {answer_path}\n"
                f"---- EXPECTED ----\n{expected}\n---- ACTUAL ----\n{result_block}",
            )

    def time_query(self, query_path: str) -> List[float]:
        """Validate the query on its first run, then (only if it validated) run it the
        remaining times for timing. Raises QueryFailure if any run fails."""
        timing, result_block = self.run_query_once(query_path)
        self.validate(query_path, result_block)
        timings = [timing]
        for _ in range(RUNS - 1):
            timing, _ = self.run_query_once(query_path)
            timings.append(timing)
        return timings

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
                timings = self.time_query(query_path)
            except QueryFailure as failure:
                self.print_failure(query_path, failure)
                results.append(QueryResult(name, status="failed", error=failure.reason))
                continue
            median = statistics.median(timings)
            print(f"{name}: median {median}s over {RUNS} runs")
            results.append(QueryResult(name, status="ok", timings=timings, median=median))
        return results

    def write_results(self, results: List[QueryResult]) -> None:
        with open(self.config.results, 'w', newline='') as f:
            writer = csv.writer(f)
            run_columns = [f"run_{i}_seconds" for i in range(1, RUNS + 1)]
            writer.writerow(["benchmark_name", "query", "status", "error", "median_seconds", *run_columns])
            for r in results:
                median = r.median if r.median is not None else ""
                # Pad missing timings (a failed query has none) so every row has RUNS columns.
                run_cells = list(r.timings) + [""] * (RUNS - len(r.timings))
                writer.writerow([self.config.benchmark_name, r.name, r.status, r.error, median, *run_cells])
        print(f"Wrote {len(results)} results to {self.config.results}")


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
    runner.write_results(results)


if __name__ == "__main__":
    main()
