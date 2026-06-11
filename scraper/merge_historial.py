#!/usr/bin/env python3
"""
Merge historial arrays from two data.json versions (ours vs theirs).
Called by the GitHub Actions workflow when git rebase has a conflict on data.json.

Usage: python scraper/merge_historial.py
  Reads docs/data.json.ours and docs/data.json.theirs, writes merged docs/data.json.
"""
import json, sys, os

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "docs", "data.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge(ours, theirs):
    """Keep the newer meta/national data; union historial deduplicated by ts."""
    base = ours  # ours has the newer snapshot data
    hist_ours   = {h["ts"]: h for h in ours.get("historial",   [])}
    hist_theirs = {h["ts"]: h for h in theirs.get("historial", [])}

    merged = {**hist_theirs, **hist_ours}  # ours wins on same ts
    base["historial"] = sorted(merged.values(), key=lambda h: h["ts"])
    return base


if __name__ == "__main__":
    ours_path   = DATA + ".ours"
    theirs_path = DATA + ".theirs"

    if not os.path.exists(ours_path) or not os.path.exists(theirs_path):
        print("[MERGE] No se encontraron archivos .ours/.theirs — nada que hacer.")
        sys.exit(0)

    ours   = load(ours_path)
    theirs = load(theirs_path)
    result = merge(ours, theirs)

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total = len(result["historial"])
    print(f"[MERGE] Historial unificado: {total} entradas → {DATA}")
