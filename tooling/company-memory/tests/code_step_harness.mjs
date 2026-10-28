// Run a code_execution step with the chatserver sandbox bindings: each context
// key becomes a const, context arrives as JSON, and source contains no runtime data.
// Input: JSON on stdin {"code": "...", "context": {...}}.
// Output: JSON on stdout {"ok": true, "result": ...} or {"ok": false, "error": "..."}.
import { readFileSync } from "node:fs";

const input = JSON.parse(readFileSync(0, "utf8"));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const bindings = Object.keys(input.context)
  .map((key) => `const ${key} = __ctx[${JSON.stringify(key)}];`)
  .join("\n");
const source = `${bindings}\nreturn await (async () => {\n${input.code}\n})();`;

try {
  const run = new AsyncFunction("__ctx", source);
  const result = await run(input.context);
  process.stdout.write(JSON.stringify({ ok: true, result: result === undefined ? null : result }));
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error: String((error && error.message) || error) }));
}
