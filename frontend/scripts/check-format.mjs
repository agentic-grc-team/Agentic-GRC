import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, extname, relative, resolve, sep } from "node:path";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(frontendRoot, "..");
const supported = new Set([".css", ".html", ".js", ".jsx", ".json", ".mjs"]);

function git(...args) {
  return execFileSync("git", args, { cwd: repoRoot, encoding: "utf8" }).split("\0").filter(Boolean);
}

const baseIndex = process.argv.indexOf("--base");
const base = baseIndex === -1 ? "origin/main" : process.argv[baseIndex + 1];
if (!base || base.startsWith("--")) {
  throw new Error("Provide a commit or ref after --base.");
}

const changed = new Set([
  ...git("diff", "--name-only", "--diff-filter=ACMRT", "-z", `${base}...HEAD`, "--", "frontend"),
  ...git("diff", "--name-only", "--diff-filter=ACMRT", "-z", "HEAD", "--", "frontend"),
  ...git("ls-files", "--others", "--exclude-standard", "-z", "--", "frontend"),
]);

const files = [...changed]
  .map((path) => resolve(repoRoot, path))
  .filter((path) => {
    const inFrontend = relative(frontendRoot, path);
    return inFrontend && !inFrontend.startsWith(`..${sep}`) && supported.has(extname(path));
  })
  .sort();

if (files.length === 0) {
  console.log("No changed frontend files require formatting checks.");
} else {
  const result = spawnSync(
    process.execPath,
    [resolve(frontendRoot, "node_modules/prettier/bin/prettier.cjs"), "--check", ...files],
    {
      cwd: frontendRoot,
      stdio: "inherit",
    },
  );
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
}
