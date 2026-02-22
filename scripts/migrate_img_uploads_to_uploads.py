#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

OLD_ROOT = Path("app/static/img/uploads")
NEW_ROOT = Path("app/static/uploads")


@dataclass
class Stats:
    moved: int = 0
    skipped: int = 0
    conflicts: int = 0
    directories_created: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Перенос файлов из app/static/img/uploads в app/static/uploads с сохранением структуры."
    )
    parser.add_argument("--dry-run", action="store_true", help="Показать действия без реального переноса")
    return parser.parse_args()


def resolve_conflict(dst: Path) -> tuple[Path, bool]:
    if not dst.exists():
        return dst, False

    stem = dst.stem
    suffix = dst.suffix
    parent = dst.parent
    i = 1
    while True:
        candidate = parent / f"{stem}__migrated_{i}{suffix}"
        if not candidate.exists():
            return candidate, True
        i += 1


def ensure_parent(path: Path, dry_run: bool, stats: Stats) -> None:
    if path.parent.exists():
        return
    if dry_run:
        print(f"[dry-run] mkdir -p {path.parent}")
        stats.directories_created += 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    stats.directories_created += 1


def migrate_file(src: Path, dry_run: bool, stats: Stats) -> None:
    rel = src.relative_to(OLD_ROOT)
    dst_base = NEW_ROOT / rel
    dst, had_conflict = resolve_conflict(dst_base)

    ensure_parent(dst, dry_run, stats)

    if had_conflict:
        stats.conflicts += 1
        print(f"[conflict] {dst_base} -> {dst}")

    if dry_run:
        print(f"[dry-run] move {src} -> {dst}")
        stats.moved += 1
        return

    shutil.move(str(src), str(dst))
    print(f"[moved] {src} -> {dst}")
    stats.moved += 1


def main() -> int:
    args = parse_args()
    dry_run = bool(args.dry_run)

    if not OLD_ROOT.exists():
        print(f"Источник не найден: {OLD_ROOT}")
        return 0

    files = sorted([p for p in OLD_ROOT.rglob("*") if p.is_file()])
    if not files:
        print("Файлы для переноса не найдены.")
        return 0

    stats = Stats()

    for src in files:
        try:
            migrate_file(src, dry_run=dry_run, stats=stats)
        except Exception as exc:
            stats.skipped += 1
            print(f"[skip] {src}: {exc}")

    print("\n=== Итог ===")
    print(f"Перенесено: {stats.moved}")
    print(f"Конфликтов имён: {stats.conflicts}")
    print(f"Создано директорий: {stats.directories_created}")
    print(f"Пропущено: {stats.skipped}")
    print(f"Режим: {'dry-run' if dry_run else 'real'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
