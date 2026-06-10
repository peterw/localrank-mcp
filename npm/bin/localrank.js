#!/usr/bin/env node
/**
 * npm wrapper for the LocalRank CLI (Python).
 *
 * Finds (or installs) Astral's `uv` and runs the Python package through
 * `uvx`, passing all arguments straight through. Keeps stdout clean: the
 * Python CLI prints JSON results to stdout and JSON errors to stderr.
 *
 * Auth: export LOCALRANK_API_KEY (create one at https://app.localrank.so/mcp).
 */

"use strict";

const { spawnSync, execSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

// Switch to "localrank" (the PyPI name) once the package is published there.
const PACKAGE_SPEC = "git+https://github.com/peterw/localrank-mcp";
const ENTRYPOINT = "localrank";

function findUvx() {
  const candidates = [
    "uvx",
    path.join(os.homedir(), ".local", "bin", "uvx"),
    path.join(os.homedir(), ".cargo", "bin", "uvx"),
  ];
  for (const candidate of candidates) {
    const probe = spawnSync(candidate, ["--version"], { stdio: "ignore" });
    if (probe.status === 0) return candidate;
  }
  return null;
}

function installUv() {
  if (process.platform === "win32") {
    console.error(
      JSON.stringify(
        {
          error: "The uv runtime is required and was not found.",
          fix: 'Install it with: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" — then re-run this command.',
        },
        null,
        2
      )
    );
    process.exit(1);
  }
  console.error("localrank: installing the uv runtime (one-time setup)...");
  try {
    execSync("curl -LsSf https://astral.sh/uv/install.sh | sh", {
      stdio: ["ignore", "inherit", "inherit"],
    });
  } catch (err) {
    console.error(
      JSON.stringify(
        {
          error: "Automatic uv install failed.",
          fix: "Install uv manually (https://docs.astral.sh/uv/getting-started/installation/) and re-run.",
        },
        null,
        2
      )
    );
    process.exit(1);
  }
  return findUvx();
}

function main() {
  let uvx = findUvx();
  if (!uvx) uvx = installUv();
  if (!uvx) {
    console.error(
      JSON.stringify(
        {
          error: "uv was installed but uvx is not on PATH yet.",
          fix: "Open a new shell (or add ~/.local/bin to PATH) and re-run.",
        },
        null,
        2
      )
    );
    process.exit(1);
  }

  const result = spawnSync(
    uvx,
    ["--from", PACKAGE_SPEC, ENTRYPOINT, ...process.argv.slice(2)],
    { stdio: "inherit" }
  );
  process.exit(result.status === null ? 1 : result.status);
}

main();
