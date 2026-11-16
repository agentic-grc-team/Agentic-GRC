import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import postcss from "postcss";
import { describe, expect, it } from "vitest";

// Vite concatenates every stylesheet into one file. A single unclosed block, comment or string
// swallows every rule after it, which left the deployed Beta unstyled after a merge. Parsing each
// file with PostCSS catches all three before they ship, and the error names the line to fix.
const srcDir = join(import.meta.dirname, "..");

function cssFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return name.endsWith(".css") ? [path] : [];
  });
}

// The syntax error of a stylesheet as "line:column reason", or null when it parses.
function cssSyntaxError(css) {
  try {
    postcss.parse(css);
    return null;
  } catch (error) {
    if (error.name !== "CssSyntaxError") throw error;
    return `${error.line}:${error.column} ${error.reason}`;
  }
}

describe("cssSyntaxError", () => {
  it.each([
    ["an unclosed block, at the line where it opens", "a { b: c; }\n@media (x) {\n  a { b: c; }\n", "2:1 Unclosed block"],
    ["an unclosed comment", "a { b: c; }\n/* mobile tweaks\na { b: c; }\n", "2:1 Unclosed comment"],
    ["an unclosed string", 'a { content: "x; }\n', "Unclosed string"],
    ["an extra closing brace", "a { b: c; }\n}\n", "2:1 Unexpected }"],
  ])("reports %s", (_case, css, expected) => {
    expect(cssSyntaxError(css)).toContain(expected);
  });

  it("accepts braces inside strings and attribute selectors", () => {
    const css = '.empty::before { content: "{"; }\n[data-template="{name}"] { color: red; }\n';

    expect(cssSyntaxError(css)).toBeNull();
  });
});

describe("stylesheets", () => {
  it.each(cssFiles(srcDir).map((path) => [relative(srcDir, path), path]))(
    "%s parses without syntax errors",
    (_name, path) => {
      expect(cssSyntaxError(readFileSync(path, "utf8"))).toBeNull();
    },
  );
});
