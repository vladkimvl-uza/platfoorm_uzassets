#!/usr/bin/env node
/**
 * Audits static t("Russian source key") calls against every locale dictionary.
 * Dynamic t(variable) calls are reported separately because they require a
 * deliberate review of the value source.
 *
 *   node scripts/i18n-audit.mjs
 *   node scripts/i18n-audit.mjs --bucket ai
 *   node scripts/i18n-audit.mjs --file AiChat.vue
 */
import fs from "node:fs";
import path from "node:path";

import { parse as parseSfc } from "@vue/compiler-sfc";
import ts from "typescript";

const cwd = process.cwd();
const srcRoot = path.resolve(cwd, "src");
const dictRoot = path.join(srcRoot, "locale", "dict");
const args = process.argv.slice(2);
const bucketName = args.includes("--bucket") ? args[args.indexOf("--bucket") + 1] : null;
const fileFilter = args.includes("--file") ? args[args.indexOf("--file") + 1] : null;
const summaryOnly = args.includes("--summary");
const writeMissingPath = args.includes("--write-missing") ? args[args.indexOf("--write-missing") + 1] : null;
const writeConflictsPath = args.includes("--write-conflicts") ? args[args.indexOf("--write-conflicts") + 1] : null;
const writeDynamicPath = args.includes("--write-dynamic") ? args[args.indexOf("--write-dynamic") + 1] : null;
const NEEDS_TRANSLATION = /[\u0400-\u04ff]/;

let bucketFiles = null;
if (bucketName) {
  const buckets = JSON.parse(fs.readFileSync(path.resolve(cwd, "../.i18n_buckets.json"), "utf8"));
  if (!buckets[bucketName]) throw new Error(`Unknown bucket: ${bucketName}`);
  bucketFiles = new Set(buckets[bucketName].files.map((file) => path.resolve(cwd, file)));
}

function walk(dir, accept) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full, accept));
    else if (accept(full)) out.push(full);
  }
  return out;
}

function lineOf(source, offset) {
  return source.slice(0, offset).split("\n").length;
}

function staticString(node) {
  return ts.isStringLiteralLike(node) ? node.text : null;
}

function scanTs(source, file, result) {
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const visit = (node) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && ["t", "tr", "translateUi", "i18nKey"].includes(node.expression.text)) {
      const arg = node.arguments[0];
      const key = arg ? staticString(arg) : null;
      if (key != null) result.static.push({ key, file, line: lineOf(source, node.getStart(sourceFile)) });
      else result.dynamic.push({ expression: arg?.getText(sourceFile) || "<missing>", file, line: lineOf(source, node.getStart(sourceFile)) });
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
}

function decodeLiteral(quote, body) {
  const source = `const value = ${quote}${body}${quote};`;
  const sf = ts.createSourceFile("literal.ts", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const statement = sf.statements[0];
  if (!statement || !ts.isVariableStatement(statement)) return null;
  return staticString(statement.declarationList.declarations[0]?.initializer);
}

function scanTemplate(source, file, result) {
  const withoutComments = source.replace(/<!--[\s\S]*?-->/g, "");
  const staticCall = /\b(?:t|tr|translateUi|i18nKey)\(\s*(["'`])((?:\\.|(?!\1)[\s\S])*?)\1/g;
  for (const match of withoutComments.matchAll(staticCall)) {
    const key = decodeLiteral(match[1], match[2]);
    if (key != null) result.static.push({ key, file, line: lineOf(withoutComments, match.index) });
  }
  const dynamicCall = /\b(?:t|tr|translateUi)\(\s*(?!["'`])([^,)\n]+)/g;
  for (const match of withoutComments.matchAll(dynamicCall)) {
    result.dynamic.push({ expression: match[1].trim(), file, line: lineOf(withoutComments, match.index) });
  }
}

function sourceFiles() {
  return walk(srcRoot, (file) => {
    const normalized = file.replace(/\\/g, "/");
    if (!/\.(?:ts|vue)$/.test(file) || /\.(?:test|spec)\.ts$/.test(file)) return false;
    if (normalized.includes("/locale/") || normalized.includes("/sdk/") || normalized.includes("/__tests__/")) return false;
    if (bucketFiles && !bucketFiles.has(path.resolve(file))) return false;
    if (fileFilter && !normalized.includes(fileFilter.replace(/\\/g, "/"))) return false;
    return true;
  });
}

function scanSources() {
  const result = { static: [], dynamic: [] };
  const files = sourceFiles();
  for (const file of files) {
    const source = fs.readFileSync(file, "utf8");
    if (file.endsWith(".ts")) {
      scanTs(source, file, result);
      continue;
    }
    const { descriptor, errors } = parseSfc(source, { filename: file });
    if (errors.length) continue;
    if (descriptor.script) scanTs(descriptor.script.content, file, result);
    if (descriptor.scriptSetup) scanTs(descriptor.scriptSetup.content, file, result);
    if (descriptor.template) scanTemplate(descriptor.template.content, file, result);
  }
  return { files, ...result };
}

function propertyName(node) {
  if (ts.isIdentifier(node) || ts.isStringLiteralLike(node) || ts.isNumericLiteral(node)) return node.text;
  if (ts.isComputedPropertyName(node) && ts.isStringLiteralLike(node.expression)) return node.expression.text;
  return null;
}

function loadDictionaries() {
  const locales = { uz: new Map(), en: new Map(), cyr: new Map() };
  const duplicates = [];
  const files = walk(dictRoot, (file) => file.endsWith(".ts"));
  for (const file of files) {
    const source = fs.readFileSync(file, "utf8");
    const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
    for (const statement of sf.statements) {
      if (!ts.isVariableStatement(statement)) continue;
      for (const declaration of statement.declarationList.declarations) {
        if (!ts.isIdentifier(declaration.name) || !["uz", "en", "cyr"].includes(declaration.name.text)) continue;
        if (!declaration.initializer || !ts.isObjectLiteralExpression(declaration.initializer)) continue;
        const locale = declaration.name.text;
        for (const property of declaration.initializer.properties) {
          if (!ts.isPropertyAssignment(property)) continue;
          const key = propertyName(property.name);
          const value = staticString(property.initializer);
          if (key == null || value == null) continue;
          const previous = locales[locale].get(key);
          if (previous && previous.value !== value) {
            duplicates.push({ locale, key, files: [previous.file, file], values: [previous.value, value] });
          }
          locales[locale].set(key, { value, file });
        }
      }
    }
  }
  return { files, locales, duplicates };
}

function placeholders(value) {
  return [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort().join(",");
}

function short(file) {
  return path.relative(cwd, file).replace(/\\/g, "/");
}

const source = scanSources();
const dictionaries = loadDictionaries();
const byKey = new Map();
for (const usage of source.static) {
  if (!byKey.has(usage.key)) byKey.set(usage.key, usage);
}
const relevantDuplicates = bucketName || fileFilter
  ? dictionaries.duplicates.filter((entry) => byKey.has(entry.key))
  : dictionaries.duplicates;

const missingUz = [];
const missingEn = [];
const placeholderErrors = [];
for (const [key, usage] of byKey) {
  const uz = dictionaries.locales.uz.get(key);
  const en = dictionaries.locales.en.get(key);
  if (NEEDS_TRANSLATION.test(key) && !uz) missingUz.push(usage);
  if (NEEDS_TRANSLATION.test(key) && !en) missingEn.push(usage);
  for (const [locale, entry] of [["uz", uz], ["en", en]]) {
    if (entry && placeholders(key) !== placeholders(entry.value)) {
      placeholderErrors.push({ locale, key, value: entry.value, file: entry.file });
    }
  }
}

console.log(`Source files: ${source.files.length}`);
console.log(`Static t() keys: ${byKey.size}; calls: ${source.static.length}`);
console.log(`Dynamic t() calls (manual review): ${source.dynamic.length}`);
console.log(`Dictionary entries: uz=${dictionaries.locales.uz.size}; en=${dictionaries.locales.en.size}; cyr=${dictionaries.locales.cyr.size}`);
console.log(`Missing: uz=${missingUz.length}; en=${missingEn.length}; placeholder mismatches=${placeholderErrors.length}; conflicting duplicates=${relevantDuplicates.length}`);

if (writeMissingPath) {
  const target = path.resolve(cwd, writeMissingPath);
  const rows = [...byKey.entries()]
    .filter(([key]) => NEEDS_TRANSLATION.test(key))
    .map(([key, usage]) => ({
      key,
      file: short(usage.file),
      line: usage.line,
      missingUz: !dictionaries.locales.uz.has(key),
      missingEn: !dictionaries.locales.en.has(key),
    }))
    .filter((row) => row.missingUz || row.missingEn);
  fs.writeFileSync(target, `${JSON.stringify(rows, null, 2)}\n`, "utf8");
  console.log(`Missing-key manifest: ${short(target)}`);
}

if (writeConflictsPath) {
  const target = path.resolve(cwd, writeConflictsPath);
  const rows = relevantDuplicates.map((entry) => ({
    locale: entry.locale,
    key: entry.key,
    files: entry.files.map(short),
    values: entry.values,
  }));
  fs.writeFileSync(target, `${JSON.stringify(rows, null, 2)}\n`, "utf8");
  console.log(`Conflict manifest: ${short(target)}`);
}

if (writeDynamicPath) {
  const target = path.resolve(cwd, writeDynamicPath);
  const rows = source.dynamic.map((entry) => ({
    expression: entry.expression,
    file: short(entry.file),
    line: entry.line,
  }));
  fs.writeFileSync(target, `${JSON.stringify(rows, null, 2)}\n`, "utf8");
  console.log(`Dynamic-call manifest: ${short(target)}`);
}

for (const [label, entries] of summaryOnly ? [] : [["MISSING UZ", missingUz], ["MISSING EN", missingEn]]) {
  if (!entries.length) continue;
  console.log(`\n${label}`);
  for (const entry of entries) console.log(`  ${short(entry.file)}:${entry.line}  ${JSON.stringify(entry.key)}`);
}
if (!summaryOnly && placeholderErrors.length) {
  console.log("\nPLACEHOLDER MISMATCHES");
  for (const entry of placeholderErrors) console.log(`  ${entry.locale} ${short(entry.file)}  ${JSON.stringify(entry.key)} -> ${JSON.stringify(entry.value)}`);
}
if (!summaryOnly && relevantDuplicates.length) {
  console.log("\nCONFLICTING DUPLICATES");
  for (const entry of relevantDuplicates) console.log(`  ${entry.locale} ${JSON.stringify(entry.key)}  ${entry.files.map(short).join(" <> ")}`);
}
if (!summaryOnly && source.dynamic.length) {
  console.log("\nDYNAMIC CALLS");
  for (const entry of source.dynamic) console.log(`  ${short(entry.file)}:${entry.line}  t(${entry.expression})`);
}

if (missingUz.length || missingEn.length || placeholderErrors.length || relevantDuplicates.length) process.exitCode = 1;
