"""Sort loose files into folders by file type. Preview unless --apply is used."""

import argparse
from pathlib import Path
import shutil
import sys


GROUPS = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"},
    "Documents": {".pdf", ".txt", ".docx", ".xlsx", ".csv", ".pptx"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a"},
    "Videos": {".mp4", ".mov", ".mkv", ".avi"},
    "Archives": {".zip", ".tar", ".gz", ".7z", ".rar"},
}


def organize(folder, apply=False):
    count = 0
    for source in sorted(folder.iterdir()):
        if source.is_symlink() or not source.is_file() or source.name.startswith("."):
            continue
        group = next(
            (name for name, extensions in GROUPS.items()
             if source.suffix.lower() in extensions),
            None,
        )
        if group is None:
            continue

        destination = folder / group / source.name
        if destination.parent.is_symlink():
            print(f"Skipped {source.name}: {group} is a link.")
            continue
        if destination.parent.exists() and not destination.parent.is_dir():
            print(f"Skipped {source.name}: {group} is not a folder.")
            continue
        if destination.exists() or destination.is_symlink():
            print(f"Skipped {source.name}: destination already exists.")
            continue

        if apply:
            destination.parent.mkdir(exist_ok=True)
            # Exclusive creation prevents overwriting an existing file.
            with source.open("rb") as original, destination.open("xb") as target:
                shutil.copyfileobj(original, target)
            source.unlink()
        action = "Moved" if apply else "Would move"
        print(f"{action}: {source.name} -> {group}/{source.name}")
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder to tidy")
    parser.add_argument("--apply", action="store_true", help="Actually move files")
    args = parser.parse_args()
    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        parser.error(f"Not a folder: {folder}")
    try:
        count = organize(folder, args.apply)
    except OSError as error:
        print(f"Stopped: {error}", file=sys.stderr)
        return 1
    print(f"{count} file(s) {'moved' if args.apply else 'to move'}.")
    if not args.apply:
        print("Preview only. Add --apply to move these files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
