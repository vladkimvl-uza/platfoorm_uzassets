"""Audit Russian user-facing backend strings without importing the application.

The scanner uses Python's AST so comments, SQL and arbitrary source fragments do
not become false translation keys. HTTPException details are translated by the
global exception handler when both dictionaries contain the exact key. Other
response fields must call ``tr()`` explicitly.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


CYRILLIC = re.compile(r"[А-Яа-яЁё]")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
USER_FIELDS = {
    "body", "detail", "error", "hint", "message", "reason", "status_line",
    "subject", "subtitle", "text", "title",
}
LOCALIZER_CALLS = {"tr"}
AUTO_TRANSLATED_CALLS = {"HTTPException"}
TECHNICAL_CALLS = {
    "debug", "exception", "info", "print", "warning",
}
INTERNAL_LANGUAGE_MEDIATED = {
    # Tool results are private model context, not HTTP/UI payloads. The AI
    # service appends ai_language_instruction() to every system prompt.
    "app/services/ai_tools.py",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    context: str
    text: str
    dictionary_covered: bool


def _call_name(call: ast.Call) -> str:
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return ""


def _contains(root: ast.AST, target: ast.AST) -> bool:
    return any(node is target for node in ast.walk(root))


def _dictionary_keys(locale_dir: Path) -> tuple[set[str], set[str]]:
    uz: set[str] = set()
    en: set[str] = set()
    for path in locale_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
            value = node.value
            if not isinstance(target, ast.Name) or target.id not in {"UZ", "EN"}:
                continue
            if not isinstance(value, ast.Dict):
                continue
            bucket = uz if target.id == "UZ" else en
            for key in value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    bucket.add(key.value)
    return uz, en


def _dictionary_integrity(locale_dir: Path) -> list[str]:
    """Validate static dictionaries without importing application modules."""
    global_values: dict[str, dict[str, tuple[str, str]]] = {"UZ": {}, "EN": {}}
    issues: list[str] = []
    for path in sorted(locale_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        module_values: dict[str, dict[str, str]] = {"UZ": {}, "EN": {}}
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
            value = node.value
            if (
                not isinstance(target, ast.Name)
                or target.id not in module_values
                or not isinstance(value, ast.Dict)
            ):
                continue
            locale = target.id
            for key_node, value_node in zip(value.keys, value.values):
                if not (
                    isinstance(key_node, ast.Constant)
                    and isinstance(key_node.value, str)
                    and isinstance(value_node, ast.Constant)
                    and isinstance(value_node.value, str)
                ):
                    continue
                key, translated = key_node.value, value_node.value
                previous_local = module_values[locale].get(key)
                if previous_local is not None and previous_local != translated:
                    issues.append(
                        f"{path.name}: duplicate {locale} key with different values: {key!r}"
                    )
                module_values[locale][key] = translated

                previous_global = global_values[locale].get(key)
                if previous_global is not None and previous_global[0] != translated:
                    issues.append(
                        f"{locale} conflict for {key!r}: "
                        f"{previous_global[1]} <> {path.name}"
                    )
                global_values[locale][key] = (translated, path.name)

                source_vars = Counter(PLACEHOLDER.findall(key))
                translated_vars = Counter(PLACEHOLDER.findall(translated))
                if source_vars != translated_vars:
                    issues.append(
                        f"{path.name}: {locale} placeholder mismatch for {key!r}"
                    )

        uz_keys = set(module_values["UZ"])
        en_keys = set(module_values["EN"])
        for key in sorted(uz_keys - en_keys):
            issues.append(f"{path.name}: missing EN key {key!r}")
        for key in sorted(en_keys - uz_keys):
            issues.append(f"{path.name}: missing UZ key {key!r}")
    return issues


def _is_docstring(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> bool:
    expr = parents.get(node)
    owner = parents.get(expr) if isinstance(expr, ast.Expr) else None
    return bool(
        isinstance(expr, ast.Expr)
        and isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and owner.body
        and owner.body[0] is expr
    )


def _context_for(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> tuple[str, bool]:
    current: ast.AST | None = node
    dynamic = False
    while current is not None:
        parent = parents.get(current)
        if isinstance(parent, (ast.JoinedStr, ast.BinOp)):
            dynamic = True
        if isinstance(parent, ast.Call):
            name = _call_name(parent)
            if name in LOCALIZER_CALLS:
                return "localized", False
            if name in TECHNICAL_CALLS:
                return "technical", False
            for kw in parent.keywords:
                if kw.arg in USER_FIELDS and _contains(kw.value, node):
                    template_arg = f"{kw.arg}_template"
                    if any(other.arg == template_arg for other in parent.keywords):
                        return "localized", False
                    suffix = ".dynamic" if dynamic else ""
                    return f"{name or 'call'}.{kw.arg}{suffix}", name in AUTO_TRANSLATED_CALLS and not dynamic
            if name in AUTO_TRANSLATED_CALLS:
                suffix = ".dynamic" if dynamic else ""
                return f"{name}{suffix}", not dynamic
        if isinstance(parent, ast.Dict):
            for key, value in zip(parent.keys, parent.values):
                if not _contains(value, node):
                    continue
                if isinstance(key, ast.Constant) and key.value in USER_FIELDS:
                    return f"dict.{key.value}", False
        current = parent
    return "internal", False


def scan(app_dir: Path, locale_dir: Path) -> list[Finding]:
    uz, en = _dictionary_keys(locale_dir)
    findings: list[Finding] = []
    for path in sorted(app_dir.rglob("*.py")):
        if locale_dir in path.parents:
            continue
        relative_path = str(path.relative_to(app_dir.parent)).replace("\\", "/")
        if relative_path in INTERNAL_LANGUAGE_MEDIATED:
            continue
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            text = node.value.strip()
            if not text or not CYRILLIC.search(text) or _is_docstring(node, parents):
                continue
            if "i18n-audit: ignore" in lines[node.lineno - 1]:
                continue
            context, auto_translated = _context_for(node, parents)
            if context in {"localized", "technical", "internal"}:
                continue
            covered = text in uz and text in en
            if auto_translated and covered:
                continue
            findings.append(Finding(
                path=relative_path,
                line=node.lineno,
                context=context,
                text=text.replace("\n", " "),
                dictionary_covered=covered,
            ))
    return findings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--unique", action="store_true")
    parser.add_argument("--write-json", type=Path)
    args = parser.parse_args()
    backend_dir = Path(__file__).resolve().parents[1]
    locale_dir = backend_dir / "app" / "locale_dict"
    findings = scan(backend_dir / "app", locale_dir)
    dictionary_issues = _dictionary_integrity(locale_dir)
    displayed = findings
    if args.unique:
        displayed = list({item.text: item for item in findings}.values())
    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(
            json.dumps([asdict(item) for item in displayed], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps([asdict(item) for item in displayed], ensure_ascii=False, indent=2))
    else:
        suffix = f"; unique={len(displayed)}" if args.unique else ""
        print(f"Unlocalized user-facing backend strings: {len(findings)}{suffix}")
        print(f"Backend dictionary integrity issues: {len(dictionary_issues)}")
        for item in displayed[:args.limit or None]:
            state = "dict-only" if item.dictionary_covered else "missing"
            print(f"{item.path}:{item.line} [{item.context}; {state}] {item.text}")
        for issue in dictionary_issues[:args.limit or None]:
            print(f"dictionary: {issue}")
    return 1 if args.strict and (findings or dictionary_issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
