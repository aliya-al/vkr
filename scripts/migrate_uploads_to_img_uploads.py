from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "app" / "static"
TARGET_ROOT = STATIC_ROOT / "uploads"
LEGACY_IMG_ROOT = STATIC_ROOT / "img" / "uploads"
KINDS = ("news", "products")


@dataclass
class Stats:
    found: int = 0
    moved_or_copied: int = 0
    skipped_conflict: int = 0
    skipped_same_file: int = 0
    errors: int = 0


def _collect_source_dirs(kind: str) -> list[Path]:
    candidates = [
        LEGACY_IMG_ROOT / kind,
        STATIC_ROOT / "uploads" / kind,
    ]
    out: list[Path] = []
    seen: set[Path] = set()
    for c in candidates:
        rc = c.resolve()
        if rc in seen:
            continue
        seen.add(rc)
        if c.exists() and c.is_dir():
            out.append(c)
    return out


def _iter_files(src: Path):
    for p in src.rglob("*"):
        if p.is_file():
            yield p


def migrate(kind: str, mode: str, dry_run: bool, stats: Stats) -> None:
    target_dir = TARGET_ROOT / kind
    source_dirs = _collect_source_dirs(kind)

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[{kind}] target: {target_dir}")
    for src in source_dirs:
        print(f"  source: {src}")

    for src in source_dirs:
        for file_path in _iter_files(src):
            stats.found += 1
            rel = file_path.relative_to(src)
            dest = target_dir / rel

            try:
                if file_path.resolve() == dest.resolve():
                    stats.skipped_same_file += 1
                    continue
            except FileNotFoundError:
                pass

            if dest.exists():
                stats.skipped_conflict += 1
                print(f"  SKIP conflict: {file_path} -> {dest}")
                continue

            print(f"  {mode.upper()}: {file_path} -> {dest}")
            if dry_run:
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if mode == "copy":
                    shutil.copy2(file_path, dest)
                else:
                    shutil.move(str(file_path), str(dest))
                stats.moved_or_copied += 1
            except Exception as exc:
                stats.errors += 1
                print(f"  ERROR: {file_path} -> {dest}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Миграция загрузок news/products в app/static/uploads/... (из legacy img/uploads)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Показать план без изменений")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--move", action="store_true", help="Перенос файлов (по умолчанию)")
    mode_group.add_argument("--copy", action="store_true", help="Копирование файлов")

    args = parser.parse_args()
    mode = "copy" if args.copy else "move"

    print("Categories folder не затрагивается: app/static/uploads/categories")
    stats = Stats()
    for kind in KINDS:
        migrate(kind, mode, args.dry_run, stats)

    print("\n=== REPORT ===")
    print(f"found: {stats.found}")
    print(f"{mode}d: {stats.moved_or_copied}")
    print(f"skipped_conflict: {stats.skipped_conflict}")
    print(f"skipped_same_file: {stats.skipped_same_file}")
    print(f"errors: {stats.errors}")


if __name__ == "__main__":
    main()
