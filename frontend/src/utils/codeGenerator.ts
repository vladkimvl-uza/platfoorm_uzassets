/**
 * Code snippet generators for the public devdocs (Phase 5.5-5.6).
 *
 * Pure functions — take a CatalogEndpoint + vars, return a string suitable
 * for direct copy/paste. Examples are reactive: every change in the catalog
 * regenerates them. Body samples are best-effort placeholders since we don't
 * have the full request schema loaded here yet.
 */
import type { CatalogEndpoint, CatalogEndpointWithSubstitution } from "@/api/apiCatalog";

// 2026-05-26: было hardcoded "https://platform.uz-assets.uz/api" →
// staging-деплой генерировал примеры со ссылкой на prod. Теперь берётся
// из env (VITE_PUBLIC_API_BASE_URL) с fallback на текущий origin + /api.
const BASE_URL = (
  (import.meta.env.VITE_PUBLIC_API_BASE_URL as string | undefined)
  || (typeof window !== "undefined"
      ? `${window.location.origin}/api`
      : "/api")
);

function substitute(path: string, vars: Record<string, string>): string {
  let out = path;
  for (const [k, v] of Object.entries(vars)) {
    out = out.replace(new RegExp(`\\{${k}\\}`, "g"), v);
  }
  return out;
}

function _pathWithVars(e: CatalogEndpoint | CatalogEndpointWithSubstitution, vars: Record<string, string>): string {
  const base = (e as any).display_path || e.path;
  return substitute(base, vars);
}

function needsBody(e: CatalogEndpoint): boolean {
  return ["POST", "PATCH", "PUT"].includes(e.method.toUpperCase());
}

function exampleBody(e: CatalogEndpoint): Record<string, any> {
  // Best-effort placeholder — would be improved by parsing OpenAPI schema
  return { example: "see schema in /api-catalog/openapi.enriched.json" };
}

/* ─────────────── curl ─────────────── */
export function generateCurl(
  e: CatalogEndpoint,
  vars: Record<string, string> = {},
  opts: { token?: string } = {},
): string {
  const url = `${BASE_URL}${_pathWithVars(e, vars)}`;
  const lines: string[] = [`curl -X ${e.method.toUpperCase()} '${url}'`];
  if (e.required_permission || (e as any).access_level !== "public") {
    lines.push(`  -H 'Authorization: Bearer ${opts.token || "<your_jwt_here>"}'`);
  }
  if (needsBody(e)) {
    lines.push(`  -H 'Content-Type: application/json'`);
    lines.push(`  -d '${JSON.stringify(exampleBody(e))}'`);
  }
  return lines.join(" \\\n");
}

/* ─────────────── Python ─────────────── */
export function generatePython(
  e: CatalogEndpoint,
  vars: Record<string, string> = {},
  opts: { token?: string } = {},
): string {
  const url = `${BASE_URL}${_pathWithVars(e, vars)}`;
  const method = e.method.toLowerCase();
  const tokVar = opts.token || "YOUR_JWT_HERE";
  const headersBlock = (e.required_permission || (e as any).access_level !== "public")
    ? `headers = {"Authorization": "Bearer ${tokVar}"}`
    : `headers = {}`;
  const bodyBlock = needsBody(e)
    ? `data = ${JSON.stringify(exampleBody(e), null, 2)}\n`
    : "";
  const callArgs = needsBody(e)
    ? `"${url}", headers=headers, json=data`
    : `"${url}", headers=headers`;
  return `import httpx

${headersBlock}
${bodyBlock}r = httpx.${method}(${callArgs})
print(r.status_code, r.json())`;
}

/* ─────────────── JavaScript (fetch) ─────────────── */
export function generateJS(
  e: CatalogEndpoint,
  vars: Record<string, string> = {},
  opts: { token?: string } = {},
): string {
  const url = `${BASE_URL}${_pathWithVars(e, vars)}`;
  const lines: string[] = [];
  lines.push(`const resp = await fetch("${url}", {`);
  lines.push(`  method: "${e.method.toUpperCase()}",`);
  const headers: string[] = [];
  if (e.required_permission || (e as any).access_level !== "public") {
    headers.push(`    "Authorization": \`Bearer ${opts.token || "<your_jwt_here>"}\``);
  }
  if (needsBody(e)) headers.push(`    "Content-Type": "application/json"`);
  if (headers.length) {
    lines.push(`  headers: {`);
    lines.push(headers.join(",\n"));
    lines.push(`  },`);
  }
  if (needsBody(e)) {
    lines.push(`  body: JSON.stringify(${JSON.stringify(exampleBody(e), null, 2).replace(/\n/g, "\n  ")}),`);
  }
  lines.push(`});`);
  lines.push(`const data = await resp.json();`);
  lines.push(`console.log(resp.status, data);`);
  return lines.join("\n");
}

/* ─────────────── Go (net/http) ─────────────── */
export function generateGo(
  e: CatalogEndpoint,
  vars: Record<string, string> = {},
  opts: { token?: string } = {},
): string {
  const url = `${BASE_URL}${_pathWithVars(e, vars)}`;
  const method = e.method.toUpperCase();
  const tokVar = opts.token || "YOUR_JWT_HERE";
  const bodyLit = needsBody(e)
    ? `body := strings.NewReader(\`${JSON.stringify(exampleBody(e))}\`)\n  req, _ := http.NewRequest("${method}", "${url}", body)`
    : `req, _ := http.NewRequest("${method}", "${url}", nil)`;
  const authLine = (e.required_permission || (e as any).access_level !== "public")
    ? `  req.Header.Set("Authorization", "Bearer ${tokVar}")`
    : "";
  return `package main

import (
  "fmt"
  "io"
  "net/http"${needsBody(e) ? `\n  "strings"` : ""}
)

func main() {
  ${bodyLit}
${authLine}${needsBody(e) ? `\n  req.Header.Set("Content-Type", "application/json")` : ""}

  resp, _ := http.DefaultClient.Do(req)
  defer resp.Body.Close()
  data, _ := io.ReadAll(resp.Body)
  fmt.Println(resp.StatusCode, string(data))
}`;
}

export function generators(e: CatalogEndpoint, vars: Record<string, string> = {}, opts: { token?: string } = {}) {
  return {
    curl:   generateCurl(e, vars, opts),
    python: generatePython(e, vars, opts),
    js:     generateJS(e, vars, opts),
    go:     generateGo(e, vars, opts),
  };
}
