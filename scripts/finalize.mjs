// `npm run finalize [-- --allow-partial | --skip-live | --out-dir DIR]`: runs scripts/finalize.py with the repo venv
// when it exists, else python3 / python. Exits with the Python process's status (2 = a required input is missing).
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const candidates = [
  join(root, ".venv", "Scripts", "python.exe"),
  join(root, ".venv", "bin", "python"),
].filter((p) => existsSync(p));
candidates.push("python3", "python");

const env = { ...process.env, PYTHONPATH: root + (process.env.PYTHONPATH ? (process.platform === "win32" ? ";" : ":") + process.env.PYTHONPATH : ""), PYTHONIOENCODING: "utf-8" };
for (const py of candidates) {
  const r = spawnSync(py, ["-m", "scripts.finalize", ...process.argv.slice(2)], { cwd: root, env, stdio: "inherit" });
  if (r.error && r.error.code === "ENOENT") continue; // interpreter not installed: try the next one
  if (r.error) {
    console.error(`finalize: could not run ${py}: ${r.error.message}`);
    process.exit(1);
  }
  process.exit(r.status ?? 1);
}
console.error("finalize: ERROR: no Python found (.venv, python3 or python)");
process.exit(1);
