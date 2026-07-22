import argparse
import csv
import functools
import os
import re
import subprocess
import sys
from dataclasses import dataclass
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

# Matches the timing line emitted by the DuckDB CLI when `.timer on` is set, e.g.
#   Run Time (s): real 0.008 user 0.000769 sys 0.001329
RUN_TIME_RE = re.compile(r"^Run Time \(s\): real ([0-9.eE+-]+)")


@dataclass
class BenchmarkConfig:
    "Configuration for the benchmark harness, loaded from a YAML file."

    duckdb_binary: str
    data: str
    queries: str
    answers: str
    results: str
    timeout: int = DEFAULT_TIMEOUT

    @classmethod
    def from_file(cls, config_path: str) -> "BenchmarkConfig":
        with open(config_path, 'r') as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"Config file {config_path} must contain a YAML mapping")

        required = ["duckdb_binary", "data", "queries", "answers", "results"]
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ValueError(f"Config file {config_path} is missing required keys: {', '.join(missing)}")

        timeout = raw.get("timeout", DEFAULT_TIMEOUT)
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"'timeout' must be a positive integer, got: {timeout!r}")

        config = cls(
            duckdb_binary=raw["duckdb_binary"],
            data=raw["data"],
            queries=raw["queries"],
            answers=raw["answers"],
            results=raw["results"],
            timeout=timeout,
        )
        config.validate_paths()
        return config

    def validate_paths(self) -> None:
        checks = [
            ("duckdb_binary", self.duckdb_binary, os.path.isfile),
            ("data", self.data, os.path.isfile),
            ("queries", self.queries, os.path.isdir),
            ("answers", self.answers, os.path.isdir),
        ]
        for key, path, check in checks:
            if not check(path):
                kind = "directory" if check is os.path.isdir else "file"
                raise FileNotFoundError(f"'{key}' path does not exist or is not a {kind}: {path}")


class BenchmarkRunner:
    def __init__(self, config: BenchmarkConfig):
        self.config = config
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

    def run_query(self, query_path: str) -> Tuple[float, str]:
        """Run a single query, returning (execution_time_seconds, result_block)."""
        with open(query_path, 'r') as f:
            query_sql = f.read().strip()

        # `.mode list` yields pipe-delimited output with a header row, matching the
        # answer file format. `.timer on` appends a `Run Time (s): real ...` line.
        script = ".timer on\n.mode list\n" + query_sql
        if not script.endswith("\n"):
            script += "\n"

        try:
            proc = subprocess.run(
                [self.config.duckdb_binary, self.config.data],
                input=script,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.config.timeout,
            )
        except subprocess.TimeoutExpired:
            self.fail(query_path, f"Aborted due to exceeding the limit of {self.config.timeout} seconds")

        if proc.returncode != 0:
            self.fail(query_path, "DuckDB exited with a non-zero status", proc.stdout, proc.stderr)

        return self.parse_output(query_path, proc.stdout)

    def parse_output(self, query_path: str, stdout: str) -> Tuple[float, str]:
        result_lines: List[str] = []
        timing: Optional[float] = None
        for line in stdout.splitlines():
            match = RUN_TIME_RE.match(line)
            if match:
                # Keep the last timing line, matching the query statement's execution.
                timing = float(match.group(1))
            else:
                result_lines.append(line)

        if timing is None:
            self.fail(query_path, "Could not parse a 'Run Time (s)' line from DuckDB output", stdout)

        result_block = "\n".join(result_lines).strip()
        return timing, result_block

    def validate(self, query_path: str, result_block: str) -> None:
        answer_path = self.answer_path_for(query_path)
        with open(answer_path, 'r') as f:
            expected = f.read().strip()
        if result_block != expected:
            self.fail(
                query_path,
                f"Result does not match expected answer ({answer_path})",
                extra=f"---- EXPECTED ----\n{expected}\n---- ACTUAL ----\n{result_block}",
            )

    def fail(self, query_path: str, message: str, stdout: str = "", stderr: str = "", extra: str = "") -> None:
        print(f"Failed to run benchmark {os.path.basename(query_path)}")
        print(message)
        if stderr:
            print(STDERR_HEADER)
            print(stderr)
        if stdout:
            print(STDOUT_HEADER)
            print(stdout)
        if extra:
            print(extra)
        sys.exit(1)

    def run(self) -> List[Tuple[str, float]]:
        results: List[Tuple[str, float]] = []
        for query_path in self.query_files:
            name = os.path.splitext(os.path.basename(query_path))[0]
            timing, result_block = self.run_query(query_path)
            self.validate(query_path, result_block)
            print(f"{name}: {timing}s")
            results.append((name, timing))
        return results

    def write_results(self, results: List[Tuple[str, float]]) -> None:
        with open(self.config.results, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["query", "time_seconds"])
            writer.writerows(results)
        print(f"Wrote {len(results)} results to {self.config.results}")


def main():
    parser = argparse.ArgumentParser(description="Run DuckDB benchmark queries defined by a YAML config.")
    parser.add_argument("--config", type=str, required=True, help="Path to the YAML configuration file.")
    args = parser.parse_args()

    try:
        config = BenchmarkConfig.from_file(args.config)
        runner = BenchmarkRunner(config)
    except (OSError, ValueError, yaml.YAMLError) as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    results = runner.run()
    runner.write_results(results)


if __name__ == "__main__":
    main()
