const childProcess = require("child_process");
const fs = require("fs");

function main() {
  const compilerLauncher = process.env.STATE_compiler_launcher;
  if (!compilerLauncher || !fs.existsSync(compilerLauncher)) {
    console.log("sccache launcher was not found; skipping stats.");
    return;
  }

  console.log("::group::sccache stats");
  const result = childProcess.spawnSync(compilerLauncher, ["--show-stats"], {
    encoding: "utf8",
  });

  if (result.stdout) {
    process.stdout.write(result.stdout);
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
  if (result.error) {
    console.log(`Unable to collect sccache stats: ${result.error.message}`);
  } else if (result.status !== 0) {
    console.log(`sccache --show-stats exited with ${result.status}`);
  }
  console.log("::endgroup::");
}

main();

