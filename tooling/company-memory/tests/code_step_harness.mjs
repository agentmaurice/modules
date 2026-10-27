// Exécute le source d'une étape code_execution comme le fait le sandbox de chatserver :
// chaque clé de `context` devient une liaison `const` (internal/business/core/sandbox_service.go,
// generateUserModule), le contexte arrive en JSON (context.json) et le source ne contient
// aucune donnée d'exécution. Entrée : JSON sur stdin {"code": "...", "context": {...}}.
// Sortie : JSON sur stdout {"ok": true, "result": ...} ou {"ok": false, "error": "..."}.
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
