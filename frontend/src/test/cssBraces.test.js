import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// Vite concatenates every stylesheet into one file. A single unclosed block swallows every rule
// after it, which left the deployed Beta unstyled after a merge. Catch that before it ships.
const srcDir = join(__dirname, "..");

function cssFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return name.endsWith(".css") ? [path] : [];
  });
}

function unbalancedLine(css) {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, " "));
  let depth = 0;
  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    for (const char of lines[index]) {
      if (char === "{") depth += 1;
      if (char === "}") depth -= 1;
      if (depth < 0) return index + 1;
    }
  }
  return depth === 0 ? null : lines.length;
}

describe("stylesheets", () => {
  it.each(cssFiles(srcDir).map((path) => [relative(srcDir, path), path]))(
    "%s has balanced braces",
    (_name, path) => {
      expect(unbalancedLine(readFileSync(path, "utf8"))).toBeNull();
    },
  );
});
