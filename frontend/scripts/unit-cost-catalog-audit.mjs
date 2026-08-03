#!/usr/bin/env node
/** Ensure every backend Unit Cost seed value has UZ and EN catalog entries. */
import fs from "node:fs";
import path from "node:path";

import ts from "typescript";

const cwd = process.cwd();
const seedPath = path.resolve(cwd, "../backend/app/services/unit_cost/seed_data.json");
const catalogPath = path.resolve(cwd, "src/locale/dict/unit_cost_catalog.ts");
const seed = JSON.parse(fs.readFileSync(seedPath, "utf8"));

function propertyName(node) {
  if (ts.isIdentifier(node) || ts.isStringLiteralLike(node) || ts.isNumericLiteral(node)) return node.text;
  return null;
}

function catalogKeys() {
  const source = fs.readFileSync(catalogPath, "utf8");
  const sf = ts.createSourceFile(catalogPath, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const syntaxErrors = sf.parseDiagnostics || [];
  if (syntaxErrors.length) {
    const message = syntaxErrors.map((item) => ts.flattenDiagnosticMessageText(item.messageText, "\n")).join("; ");
    throw new Error(`Unit Cost catalog syntax error: ${message}`);
  }

  const locales = { uz: new Set(), en: new Set() };
  for (const statement of sf.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || !(declaration.name.text in locales)) continue;
      if (!declaration.initializer || !ts.isObjectLiteralExpression(declaration.initializer)) continue;
      for (const property of declaration.initializer.properties) {
        if (!ts.isPropertyAssignment(property)) continue;
        const key = propertyName(property.name);
        if (key != null && ts.isStringLiteralLike(property.initializer)) locales[declaration.name.text].add(key);
      }
    }
  }
  return locales;
}

const products = new Set();
const units = new Set();
const components = new Set();
for (const company of Object.values(seed.companies || {})) {
  for (const product of company.products || []) {
    if (product.name) products.add(product.name);
    if (product.unit) units.add(product.unit);
    for (const component of product.components || []) {
      if (component.name) components.add(component.name);
    }
  }
}

const fuels = ["Электроэнергия", "Природный газ", "Дизель", "Мазут", "Уголь", "Керосин"];
const priceUnits = ["сум/кВт·ч", "сум/м³", "сум/т"];
const editorDefaults = ["Новый продукт", "ед.", "т"];
const expected = new Set([...products, ...units, ...components, ...fuels, ...priceUnits, ...editorDefaults]);
const locales = catalogKeys();
const missing = Object.fromEntries(
  Object.entries(locales).map(([locale, keys]) => [locale, [...expected].filter((key) => !keys.has(key)).sort()]),
);

console.log(`Unit Cost seed: products=${products.size}; units=${units.size}; components=${components.size}; expected=${expected.size}`);
console.log(`Unit Cost catalog: uz=${locales.uz.size}; en=${locales.en.size}; missing uz=${missing.uz.length}; en=${missing.en.length}`);

if (missing.uz.length || missing.en.length) {
  for (const locale of ["uz", "en"]) {
    if (missing[locale].length) console.error(`${locale} missing: ${missing[locale].join(" | ")}`);
  }
  process.exitCode = 1;
}
