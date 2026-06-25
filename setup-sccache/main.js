const childProcess = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

function appendFile(envName, text) {
  const file = process.env[envName];
  if (!file) {
    throw new Error(`${envName} is not set`);
  }
  fs.appendFileSync(file, text);
}

function appendLine(envName, line) {
  appendFile(envName, `${line}${os.EOL}`);
}

function input(name, defaultValue) {
  const envName = `INPUT_${name.toUpperCase().replace(/-/g, "_")}`;
  const value = process.env[envName];
  return value && value.trim() ? value.trim() : defaultValue;
}

function resolveWorkdir(workdir) {
  if (path.isAbsolute(workdir)) {
    return path.normalize(workdir);
  }
  const workspace = process.env.GITHUB_WORKSPACE || process.cwd();
  return path.resolve(workspace, workdir);
}

function run(command, args, options = {}) {
  const result = childProcess.spawnSync(command, args, {
    encoding: "utf8",
    stdio: options.capture ? ["ignore", "pipe", "inherit"] : "inherit",
  });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}`);
  }
  return result.stdout || "";
}

function resolveTarget() {
  const arch = os.arch();
  if (arch === "x64") {
    return { toolCacheArch: "x64", releaseTarget: "x86_64-unknown-linux-musl" };
  }
  if (arch === "arm64") {
    return { toolCacheArch: "arm64", releaseTarget: "aarch64-unknown-linux-musl" };
  }
  throw new Error(`Unsupported architecture for sccache: ${arch}`);
}

function installSccache(version) {
  const { toolCacheArch, releaseTarget } = resolveTarget();
  const toolCacheRoot =
    process.env.RUNNER_TOOL_CACHE ||
    path.join(process.env.RUNNER_TEMP || os.tmpdir(), "setup-sccache", "tool-cache");
  const sccacheDir = path.join(toolCacheRoot, "sccache", version, toolCacheArch);
  const compilerLauncher = path.join(sccacheDir, "sccache");

  if (fs.existsSync(compilerLauncher)) {
    fs.chmodSync(compilerLauncher, 0o755);
    return compilerLauncher;
  }

  const runnerTemp = process.env.RUNNER_TEMP || os.tmpdir();
  const downloadDir = path.join(runnerTemp, "setup-sccache", "download");
  fs.rmSync(downloadDir, { recursive: true, force: true });
  fs.mkdirSync(downloadDir, { recursive: true });
  fs.mkdirSync(sccacheDir, { recursive: true });

  const archive = path.join(downloadDir, "sccache.tar.gz");
  const url = `https://github.com/mozilla/sccache/releases/download/v${version}/sccache-v${version}-${releaseTarget}.tar.gz`;
  run("curl", [
    "--fail",
    "--retry",
    "5",
    "--retry-all-errors",
    "--location",
    "--output",
    archive,
    url,
  ]);
  run("tar", ["-xzf", archive, "-C", downloadDir]);

  const extracted = path.join(downloadDir, `sccache-v${version}-${releaseTarget}`, "sccache");
  fs.copyFileSync(extracted, compilerLauncher);
  fs.chmodSync(compilerLauncher, 0o755);
  return compilerLauncher;
}

function main() {
  const key = input("key", "ccache");
  const version = input("version", "0.16.0");
  const workdir = resolveWorkdir(input("workdir", "."));
  // Extensions check out DuckDB as a duckdb/ submodule under the workdir.
  const baseDirs = [workdir, path.join(workdir, "duckdb")];
  const compilerLauncher = installSccache(version);

  const nscEnv = run("nsc", ["cache", "sccache", "setup", "--cache_name", key], { capture: true });
  appendFile("GITHUB_ENV", nscEnv);
  if (!nscEnv.endsWith(os.EOL)) {
    appendLine("GITHUB_ENV", "");
  }

  appendLine("GITHUB_ENV", `CMAKE_C_COMPILER_LAUNCHER=${compilerLauncher}`);
  appendLine("GITHUB_ENV", `CMAKE_CXX_COMPILER_LAUNCHER=${compilerLauncher}`);
  appendLine("GITHUB_ENV", `SCCACHE_BASEDIRS=${baseDirs.join(path.delimiter)}`);
  appendLine("GITHUB_PATH", path.dirname(compilerLauncher));
  appendLine("GITHUB_OUTPUT", `compiler-launcher=${compilerLauncher}`);
  appendLine("GITHUB_STATE", `compiler_launcher=${compilerLauncher}`);
}

main();
