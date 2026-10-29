"""Find (and optionally repair) text whose symbols were saved with the wrong encoding.

    python docs\fix_encoding.py          only report
    python docs\fix_encoding.py --fix    repair, after copying every changed file to a backup folder
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
SKIP_FOLDERS = {"__pycache__", "media", "staticfiles", "migrations", "node_modules", ".git"}
SUFFIXES = {".html", ".js", ".css", ".py", ".txt", ".md"}

# UTF-8 text wrongly read as Windows-1252 looks like: one lead character
# followed by one to three "continuation" characters.
LEAD = "\u00c2-\u00f4"
CONTINUATION = (
    "\u0080-\u00bf\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192\u02c6\u02dc"
    "\u2013\u2014\u2018\u2019\u201a\u201c\u201d\u201e\u2020\u2021\u2022\u2026"
    "\u2030\u2039\u203a\u20ac\u2122"
)
BROKEN = re.compile("[" + LEAD + "][" + CONTINUATION + "]{1,3}")


def fix_run(match):
    run = match.group(0)
    for size in range(len(run), 1, -1):
        try:
            return run[:size].encode("cp1252").decode("utf-8") + run[size:]
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return run


def candidate_files():
    for path in sorted(BACKEND.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() in SUFFIXES
            and not SKIP_FOLDERS.intersection(path.parts)
        ):
            yield path


def main():
    fix = "--fix" in sys.argv
    backup_root = Path(tempfile.gettempdir()) / "ecommerce_encoding_backup"
    damaged, unreadable, lost, no_charset = [], [], [], []

    for path in candidate_files():
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            unreadable.append(path)
            continue
        if "\ufffd" in text:
            lost.append(path)
        if path.suffix == ".html" and "<html" in text.lower() and "charset" not in text.lower():
            no_charset.append(path)

        fixed = BROKEN.sub(fix_run, text)
        if fixed == text:
            continue
        damaged.append(path)
        print("\n" + str(path.relative_to(ROOT)))
        shown = 0
        for before, after in zip(text.split("\n"), fixed.split("\n")):
            if before != after and shown < 3:
                print("   before:", ascii(before.strip()[:110]))
                print("   after: ", ascii(after.strip()[:110]))
                shown += 1
        if fix:
            target = backup_root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            path.write_bytes(fixed.encode("utf-8"))

    print()
    if not damaged:
        print("No broken characters found in your backend files.")
    elif fix:
        print(f"Repaired {len(damaged)} file(s). Originals are saved in {backup_root}")
    else:
        print(f"{len(damaged)} file(s) have broken characters. Run again with --fix to repair them.")
    if unreadable:
        print("\nNot valid UTF-8 (open in VS Code and re-save with encoding UTF-8):")
        for path in unreadable:
            print("  ", path.relative_to(ROOT))
    if lost:
        print("\nContain the replacement character (the original symbol is lost, retype it):")
        for path in lost:
            print("  ", path.relative_to(ROOT))
    if no_charset:
        print('\nHTML pages with no charset (add <meta charset="utf-8"> inside <head>):')
        for path in no_charset:
            print("  ", path.relative_to(ROOT))


main()
