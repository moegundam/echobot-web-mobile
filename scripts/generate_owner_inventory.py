from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_NAMES = (
    "API_OPERATION_INDEX.md",
    "API_SCHEMA_INDEX.md",
    "MODULE_FILE_INDEX.md",
    "TEST_FILE_INDEX.md",
    "ENVIRONMENT_KEY_INDEX.md",
    "GENERATED_MANIFEST.md",
)
GENERATOR_VERSION = "3"
GENERATION_COMMAND = (
    "python scripts/generate_owner_inventory.py "
    "--output-dir <owner-docs>/generated"
)
HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "trace",
    "websocket",
}
SECRET_NAME_PARTS = {
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "PRIVATE_KEY",
    "API_KEY",
    "ACCESS_KEY",
    "CLIENT_SECRET",
    "DSN",
}


class InventoryError(RuntimeError):
    pass


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise InventoryError(f"Path is outside the repository: {path.name}") from exc


def _parse(path: Path) -> ast.Module:
    if not path.is_file():
        raise InventoryError(f"Required source file is missing: {_relative(path)}")
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=_relative(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise InventoryError(f"Cannot parse {_relative(path)}: {exc}") from exc


def _string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _join_route(prefix: str, path: str) -> str:
    if path == "/":
        return prefix or "/"
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}" or "/"


def _router_prefixes(create_app_path: Path) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(_parse(create_app_path)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "include_router" or not node.args:
            continue
        router = node.args[0]
        if not isinstance(router, ast.Attribute) or router.attr != "router":
            raise InventoryError("Unsupported include_router target in echobot/app/create_app.py")
        if not isinstance(router.value, ast.Name):
            raise InventoryError("Unsupported router reference in echobot/app/create_app.py")
        prefix_node = _keyword(node, "prefix")
        prefix = "" if prefix_node is None else _string(prefix_node)
        if prefix is None:
            raise InventoryError("Router prefix must be a string literal")
        prefixes[router.value.id] = prefix
    if not prefixes:
        raise InventoryError("No FastAPI routers found in echobot/app/create_app.py")
    return prefixes


def _decorated_operations(path: Path, owner: str, prefix: str) -> list[tuple[str, str, str, int]]:
    operations: list[tuple[str, str, str, int]] = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            target = decorator.func.value
            method = decorator.func.attr.lower()
            if not isinstance(target, ast.Name) or target.id != owner or method not in HTTP_METHODS:
                continue
            route = _string(decorator.args[0]) if decorator.args else None
            if route is None:
                raise InventoryError(f"Route path must be a string literal at {_relative(path)}:{decorator.lineno}")
            display_method = "WS" if method == "websocket" else method.upper()
            operations.append(
                (
                    display_method,
                    _join_route(prefix, route),
                    node.name,
                    decorator.lineno,
                )
            )
    return operations


def _web_page_operations(path: Path) -> list[tuple[str, str, str, int]]:
    operations: list[tuple[str, str, str, int]] = []
    for node in _parse(path).body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "WEB_PAGE_ROUTES" or not isinstance(node.value, (ast.Tuple, ast.List)):
            continue
        for item in node.value.elts:
            if not isinstance(item, ast.Call) or len(item.args) < 3:
                raise InventoryError("WEB_PAGE_ROUTES contains an unsupported entry")
            route, _, name = (_string(argument) for argument in item.args[:3])
            if route is None or name is None:
                raise InventoryError("WEB_PAGE_ROUTES values must be string literals")
            operations.append(("GET", route, name, item.lineno))
    if not operations:
        raise InventoryError("No web page routes found in echobot/app/web_pages.py")
    return operations


def _api_index() -> str:
    create_app = ROOT / "echobot/app/create_app.py"
    operations = [
        (*operation, create_app)
        for operation in _decorated_operations(create_app, "app", "")
    ]
    router_dir = ROOT / "echobot/app/routers"
    if not router_dir.is_dir():
        raise InventoryError("Required source directory is missing: echobot/app/routers")
    for module, prefix in _router_prefixes(create_app).items():
        path = router_dir / f"{module}.py"
        operations.extend((*operation, path) for operation in _decorated_operations(path, "router", prefix))
    web_pages = ROOT / "echobot/app/web_pages.py"
    operations.extend((*operation, web_pages) for operation in _web_page_operations(web_pages))
    if not operations:
        raise InventoryError("No API operations discovered")
    operations.sort(key=lambda item: (item[1], item[0], _relative(item[4]), item[3]))

    lines = [
        "# API Operation Index / API 操作索引",
        "",
        "Generated deterministically from FastAPI route declarations in the current source tree.",
        "",
        f"API operations: **{len(operations)}**",
        "",
        "| Method | Path | Handler | Source |",
        "| --- | --- | --- | --- |",
    ]
    for method, route, handler, line, path in operations:
        lines.append(f"| `{method}` | `{route}` | `{handler}` | `{_relative(path)}:{line}` |")
    return "\n".join(lines) + "\n"


def _base_name(node: ast.AST) -> str:
    return ast.unparse(node)


def _schema_index() -> str:
    path = ROOT / "echobot/app/schemas.py"
    classes = {node.name: node for node in _parse(path).body if isinstance(node, ast.ClassDef)}
    pydantic_names = {"BaseModel"}
    changed = True
    while changed:
        changed = False
        for name, node in classes.items():
            if name not in pydantic_names and {_base_name(base) for base in node.bases} & pydantic_names:
                pydantic_names.add(name)
                changed = True
    models = [classes[name] for name in classes if name in pydantic_names]
    if not models:
        raise InventoryError("No Pydantic classes found in echobot/app/schemas.py")

    field_count = 0
    lines = [
        "# API Schema Index / API 結構索引",
        "",
        "Generated by static inspection of `echobot/app/schemas.py`; fields are declarations on each class.",
        "",
        f"Pydantic classes: **{len(models)}**",
        "",
        "| Class | Base classes | Field | Type | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for model in models:
        bases = ", ".join(_base_name(base) for base in model.bases)
        fields = [item for item in model.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)]
        if not fields:
            lines.append(f"| `{model.name}` | `{bases}` | _none declared_ |  | `{_relative(path)}:{model.lineno}` |")
            continue
        for field in fields:
            field_count += 1
            lines.append(
                f"| `{model.name}` | `{bases}` | `{field.target.id}` | `{ast.unparse(field.annotation)}` | "
                f"`{_relative(path)}:{field.lineno}` |"
            )
    lines.insert(5, f"Declared fields: **{field_count}**")
    lines.insert(6, "")
    return "\n".join(lines) + "\n"


def _grouped_paths(paths: Iterable[Path], base: Path) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        relative_parts = path.relative_to(base).parts
        family = relative_parts[0] if len(relative_parts) > 1 else "root"
        grouped[family].append(path)
    return dict(sorted(grouped.items()))


def _module_index() -> str:
    package = ROOT / "echobot"
    web_root = ROOT / "echobot/app/web"
    if not package.is_dir() or not web_root.is_dir():
        raise InventoryError("Required echobot package or web asset directory is missing")
    python_files = sorted(path for path in package.rglob("*.py") if path.is_file())
    web_assets = sorted(path for path in web_root.rglob("*") if path.is_file())
    if not python_files or not web_assets:
        raise InventoryError("Python module or web asset discovery returned no files")

    lines = [
        "# Module File Index / 模組檔案索引",
        "",
        "Generated from the current `echobot` source tree.",
        "",
        f"Python modules: **{len(python_files)}**",
        f"Web assets: **{len(web_assets)}**",
        "",
        "## Python modules / Python 模組",
    ]
    for family, paths in _grouped_paths(python_files, package).items():
        lines.extend(("", f"### `{family}` ({len(paths)})", ""))
        lines.extend(f"- `{_relative(path)}`" for path in paths)
    lines.extend(("", "## Web assets / Web 資產"))
    for family, paths in _grouped_paths(web_assets, web_root).items():
        lines.extend(("", f"### `{family}` ({len(paths)})", ""))
        lines.extend(f"- `{_relative(path)}`" for path in paths)
    return "\n".join(lines) + "\n"


def _test_functions(path: Path) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(_parse(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ]


def _has_main_entrypoint(path: Path) -> bool:
    tree = _parse(path)
    has_main = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        for node in tree.body
    )
    has_guard = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and ast.unparse(node.test) == "__name__ == '__main__'"
        for node in tree.body
    )
    return has_main and has_guard


def _test_index() -> str:
    tests_dir = ROOT / "tests"
    scripts_dir = ROOT / "scripts"
    if not tests_dir.is_dir() or not scripts_dir.is_dir():
        raise InventoryError("Required tests or scripts directory is missing")
    test_files = sorted(tests_dir.glob("test_*.py"))
    entrypoints = sorted(
        path
        for path in scripts_dir.glob("*.py")
        if ("smoke" in path.stem or path.stem.startswith("check_")) and _has_main_entrypoint(path)
    )
    if not test_files or not entrypoints:
        raise InventoryError("Test or smoke/check entrypoint discovery returned no files")
    counts = [(path, len(_test_functions(path))) for path in test_files]
    total = sum(count for _, count in counts)

    lines = [
        "# Test File Index / 測試檔案索引",
        "",
        "Generated by static inspection of tests and smoke/check script entrypoints.",
        "",
        f"Test files: **{len(test_files)}**",
        f"Test functions/methods: **{total}**",
        f"Smoke/check entrypoints: **{len(entrypoints)}**",
        "",
        "## Tests / 測試",
        "",
        "| File | Test functions/methods |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{_relative(path)}` | {count} |" for path, count in counts)
    lines.extend(("", "## Smoke/check entrypoints / Smoke 與檢查入口", ""))
    lines.extend(f"- `{_relative(path)}`" for path in entrypoints)
    return "\n".join(lines) + "\n"


def _tracked_env_templates() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InventoryError("Cannot enumerate tracked files with git") from exc
    paths = [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    templates = sorted(
        ROOT / path
        for path in paths
        if fnmatch.fnmatch(Path(path).name, "*.env*.example")
    )
    if not templates:
        raise InventoryError("No tracked *.env*.example files found")
    return templates


def _is_secret_name(key: str) -> bool:
    upper = key.upper()
    return any(part in upper for part in SECRET_NAME_PARTS)


def _environment_index() -> str:
    assignment = re.compile(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)")
    entries: list[tuple[str, str, int, str]] = []
    templates = _tracked_env_templates()
    for path in templates:
        declared_keys: set[str] = set()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise InventoryError(f"Cannot read {_relative(path)}") from exc
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = assignment.fullmatch(stripped)
            if match is None:
                raise InventoryError(f"Unsupported env template line at {_relative(path)}:{line_number}")
            key = match.group(1)
            if key in declared_keys:
                raise InventoryError(
                    f"Duplicate env key in {_relative(path)}: {key}"
                )
            declared_keys.add(key)
            classification = "secret-looking" if _is_secret_name(key) else "non-secret-looking"
            entries.append((key, _relative(path), line_number, classification))
    if not entries:
        raise InventoryError("Tracked env templates contain no keys")
    entries.sort(key=lambda item: (item[0], item[1], item[2]))

    lines = [
        "# Environment Key Index / 環境變數索引",
        "",
        "Generated from tracked `*.env*.example` files. Values are intentionally omitted.",
        "",
        f"Environment key declarations: **{len(entries)}**",
        f"Tracked templates: **{len(templates)}**",
        "",
        "| Key | Classification | Source |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| `{key}` | {classification} | `{source}:{line}` |"
        for key, source, line, classification in entries
    )
    return "\n".join(lines) + "\n"


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InventoryError("Cannot resolve the source snapshot with git") from exc


def _add_manifest_link(content: str) -> str:
    marker = "\n\n"
    if marker not in content:
        raise InventoryError("Generated index is missing its heading separator")
    provenance = "Provenance: [Generation Manifest](./GENERATED_MANIFEST.md)"
    return content.replace(marker, f"{marker}{provenance}{marker}", 1)


def _manifest(indexes: dict[str, str]) -> str:
    source_sha = _git_output("rev-parse", "HEAD")
    source_commit_time = _git_output("show", "-s", "--format=%cI", "HEAD")
    tree_state = (
        "dirty"
        if _git_output("status", "--porcelain", "--untracked-files=normal")
        else "clean"
    )
    lines = [
        "# Generated Inventory Manifest / 產生索引清單",
        "",
        "This file binds every generated owner index to one repository snapshot.",
        "",
        f"Source SHA: **`{source_sha}`**",
        f"Source tree state: **{tree_state}**",
        f"Source commit time: **{source_commit_time}**",
        f"Generator version: **{GENERATOR_VERSION}**",
        f"Generation command: `{GENERATION_COMMAND}`",
        "",
        "| Index | SHA-256 |",
        "| --- | --- |",
    ]
    for name, content in indexes.items():
        fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()
        lines.append(f"| `{name}` | `{fingerprint}` |")
    return "\n".join(lines) + "\n"


def generate() -> dict[str, str]:
    indexes = {
        "API_OPERATION_INDEX.md": _api_index(),
        "API_SCHEMA_INDEX.md": _schema_index(),
        "MODULE_FILE_INDEX.md": _module_index(),
        "TEST_FILE_INDEX.md": _test_index(),
        "ENVIRONMENT_KEY_INDEX.md": _environment_index(),
    }
    outputs = {
        name: _add_manifest_link(content)
        for name, content in indexes.items()
    }
    outputs["GENERATED_MANIFEST.md"] = _manifest(outputs)
    if tuple(outputs) != OUTPUT_NAMES:
        raise InventoryError("Internal output set does not match the required inventory files")
    return outputs


def _atomic_write_all(output_dir: Path, outputs: dict[str, str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for name, content in outputs.items():
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=output_dir,
                prefix=f".{name}.",
                delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                staged.append((Path(handle.name), output_dir / name))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def _check_all(output_dir: Path, outputs: dict[str, str]) -> list[str]:
    issues: list[str] = []
    for name, expected in outputs.items():
        path = output_dir / name
        if not path.is_file():
            issues.append(f"missing: {name}")
            continue
        try:
            actual = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            issues.append(f"unreadable: {name}")
            continue
        if actual != expected:
            issues.append(f"stale: {name}")
    if output_dir.is_dir():
        for path in sorted(output_dir.iterdir()):
            if path.is_file() and path.name not in outputs:
                issues.append(f"unexpected: {path.name}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic owner inventory Markdown files.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when the output directory is missing or stale; do not write files.",
    )
    arguments = parser.parse_args()
    try:
        outputs = generate()
        if arguments.check:
            issues = _check_all(arguments.output_dir, outputs)
            if issues:
                for issue in issues:
                    print(issue, file=sys.stderr)
                return 1
        else:
            _atomic_write_all(arguments.output_dir, outputs)
    except InventoryError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
