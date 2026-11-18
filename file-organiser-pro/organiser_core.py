"""Filesystem engine for File Organiser Pro 1.1.1 (no GUI dependencies).

No automatic deletion, no replacement of existing destination paths.
The scan and plan are advisory; every move is validated again at execution.
"""
from __future__ import annotations

import copy
import errno
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

APP_NAME = "File Organiser Pro"
APP_VERSION = "1.1.1"
CONFIG_FILE = Path.home() / ".file_organiser_pro.json"
HISTORY_FILE = Path.home() / ".file_organiser_pro_history.json"

DEFAULT_CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif", ".ico", ".heic", ".raw"],
    "Videos": [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".mpeg", ".mpg", ".m4v", ".3gp"],
    "Audio": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".aiff", ".opus"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", ".md", ".epub"],
    "Spreadsheets": [".xls", ".xlsx", ".csv", ".ods", ".tsv"],
    "Presentations": [".ppt", ".pptx", ".odp", ".key"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
    "Programs": [".exe", ".msi", ".dmg", ".pkg", ".deb", ".apk", ".appimage", ".bat", ".sh"],
    "Code": [".py", ".java", ".cpp", ".c", ".h", ".html", ".css", ".js", ".ts", ".json", ".php", ".sql", ".xml", ".yml", ".yaml", ".go", ".rs", ".swift", ".ipynb"],
    "Fonts": [".ttf", ".otf", ".woff", ".woff2"],
    "3D Files": [".blend", ".obj", ".fbx", ".stl", ".gltf", ".glb", ".dae"],
    "Design": [".psd", ".ai", ".eps", ".indd", ".xcf", ".fig", ".sketch"],
    "Database": [".db", ".sqlite", ".sqlite3", ".mdb"],
}

# All keys used in older releases remain valid. New keys are additive.
DEFAULT_SETTINGS = {
    "recursive": False,
    "skip_hidden": True,
    "output_folder": "Organised",
    "ignore_patterns": [".tmp", ".temp", ".part", ".crdownload", "desktop.ini", "Thumbs.db", ".DS_Store"],
    "custom_categories": {},
    "ignored_extensions": [],
    "organisation_mode": "Category",
    "last_folder": "",
    "excluded_directories": [".git", ".venv", "node_modules", "__pycache__"],
    "include_extensions": [],
    "filename_pattern": "",
    "min_size": "",
    "max_size": "",
    "theme": "Dark",
}
MODES = ["Category", "Extension", "Date Modified", "Date Created", "File Size"]

Progress = Optional[Callable[[int, Optional[int], str], None]]
Logger = Optional[Callable[[str], None]]


class Cancelled(Exception):
    """Cooperative cancellation at a safe file boundary."""


class FileChangedError(OSError):
    """An input changed since it was previewed."""


def cancelled(event) -> None:
    if event is not None and event.is_set():
        raise Cancelled("Operation cancelled")


def emit(logger: Logger, text: str) -> None:
    if logger:
        logger(text)


def parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_extensions(items) -> list[str]:
    return sorted({((str(x).strip().lower() if str(x).strip().startswith(".") else "." + str(x).strip().lower()))
                   for x in items if str(x).strip()})


def load_settings(path: Path = CONFIG_FILE) -> dict:
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            settings.update(saved)
    except (OSError, ValueError, UnicodeError):
        pass
    for field in ("ignore_patterns", "ignored_extensions", "excluded_directories", "include_extensions"):
        if not isinstance(settings.get(field), list):
            settings[field] = copy.deepcopy(DEFAULT_SETTINGS[field])
    if not isinstance(settings.get("custom_categories"), dict):
        settings["custom_categories"] = {}
    if settings.get("organisation_mode") not in MODES:
        settings["organisation_mode"] = "Category"
    if settings.get("theme") not in ("Dark", "Light"):
        settings["theme"] = "Dark"
    return settings


def save_json_atomic(path: Path, data: dict) -> None:
    """Best-effort atomic update of small JSON metadata files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as f:
            name = f.name
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(name, 0o600)
        except OSError:
            pass
        os.replace(name, path)  # Replacement is intentional for the metadata file only.
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def validate_component(name: str) -> str:
    """One safe folder name across Windows, macOS and Linux."""
    if not isinstance(name, str) or not name or name in (".", "..") or name != name.strip():
        raise ValueError("A folder name must be nonempty and have no leading/trailing spaces.")
    if name.endswith(".") or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name):
        raise ValueError(f"Unsafe folder name: {name!r}")
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", name, re.I):
        raise ValueError(f"Reserved Windows folder name: {name!r}")
    return name


def get_root(folder: str | Path) -> Path:
    if not str(folder).strip():
        raise ValueError("Please select a folder first.")
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise ValueError("Please select an existing folder.")
    return root.resolve()


def get_output(root: Path, settings: dict) -> Path:
    name = validate_component(str(settings.get("output_folder", "")))
    out = root / name
    if out.is_symlink() or is_junction(out):
        raise ValueError("Output folder cannot be a symbolic link or junction.")
    if out.exists() and not out.is_dir():
        raise ValueError("The output folder points to an existing file.")
    return out


def is_junction(path: Path) -> bool:
    method = getattr(path, "is_junction", None)
    if method:
        return bool(method())
    # Python <3.12 has no Path.is_junction(). On Windows, skip reparse
    # points conservatively instead of risking traversal through a junction.
    if os.name == "nt":
        try:
            flags = getattr(path.lstat(), "st_file_attributes", 0)
            return bool(flags & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        except OSError:
            return False
    return False


def hidden(path: Path, attributes=None) -> bool:
    if path.name.startswith("."):
        return True
    if attributes is None:
        try:
            attributes = path.lstat().st_file_attributes
        except (AttributeError, OSError):
            return False
    return bool(attributes & stat.FILE_ATTRIBUTE_HIDDEN) if hasattr(stat, "FILE_ATTRIBUTE_HIDDEN") else False


def pattern_matches(path: Path, root: Path, patterns: list[str]) -> bool:
    name = path.name.lower()
    rel = path.relative_to(root).as_posix().lower()
    suffix = path.suffix.lower()
    for raw in patterns:
        pattern = str(raw).strip().lower()
        if not pattern:
            continue
        if fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(rel, pattern):
            return True
        # Original defaults included bare extensions such as '.tmp'.
        if pattern.startswith(".") and not any(x in pattern for x in "*?[]/") and suffix == pattern:
            return True
    return False


def parse_size(raw) -> Optional[int]:
    """Accept 400, 10 KB, 2.5MB, 1 GiB; plain numbers mean bytes."""
    if raw is None or str(raw).strip() == "":
        return None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB|KIB|MIB|GIB|TIB)?\s*", str(raw), re.I)
    if not m:
        raise ValueError("Enter sizes such as 500 B, 10 KB, 2 MB or 1 GB.")
    n = float(m.group(1))
    if not (0 <= n < 1e17):
        raise ValueError("File-size filter is out of range.")
    scale = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4,
             "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3, "TIB": 1024**4}
    return int(n * scale[(m.group(2) or "B").upper()])


def validate_filters(settings: dict):
    min_size = parse_size(settings.get("min_size", ""))
    max_size = parse_size(settings.get("max_size", ""))
    if min_size is not None and max_size is not None and min_size > max_size:
        raise ValueError("Minimum file size cannot exceed maximum file size.")
    if settings.get("organisation_mode") not in MODES:
        raise ValueError("Unknown organisation method.")
    return min_size, max_size


def is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def signature(path: Path) -> dict:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise FileChangedError(f"Not a regular file: {path}")
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "dev": st.st_dev, "ino": st.st_ino}


def signature_matches(expected: dict, actual: dict) -> bool:
    return all(expected.get(key) == actual.get(key) for key in ("size", "mtime_ns", "dev", "ino"))


def should_include_file(path: Path, root: Path, settings: dict, min_size, max_size) -> bool:
    if not is_regular_file(path):
        return False
    if settings.get("skip_hidden", True) and hidden(path):
        return False
    if path.name.startswith("~$"):
        return False
    if path.suffix.lower() in normalize_extensions(settings.get("ignored_extensions", [])):
        return False
    if pattern_matches(path, root, settings.get("ignore_patterns", [])):
        return False
    includes = normalize_extensions(settings.get("include_extensions", []))
    if includes and path.suffix.lower() not in includes:
        return False
    name_pattern = str(settings.get("filename_pattern", "")).strip().lower()
    if name_pattern and not fnmatch.fnmatchcase(path.name.lower(), name_pattern):
        return False
    size = path.lstat().st_size
    if min_size is not None and size < min_size:
        return False
    if max_size is not None and size > max_size:
        return False
    return True


def scan(folder: str | Path, settings: dict, progress: Progress = None, logger: Logger = None, cancel=None) -> list[dict]:
    root = get_root(folder)
    output = get_output(root, settings)
    min_size, max_size = validate_filters(settings)
    records = []
    count = 0
    errors = 0

    def consider(path: Path):
        nonlocal count, errors
        cancelled(cancel)
        count += 1
        try:
            if should_include_file(path, root, settings, min_size, max_size):
                records.append({"source": str(path), "snapshot": signature(path)})
        except (OSError, ValueError) as exc:
            errors += 1
            emit(logger, f"SCAN ERROR: {path}: {exc}")
        if progress and (count % 50 == 0):
            progress(count, None, path.name)

    if settings.get("recursive", False):
        def onerror(err):
            nonlocal errors
            errors += 1
            emit(logger, f"SCAN ERROR: {err}")

        for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
            cancelled(cancel)
            parent = Path(current)
            filtered = []
            for name in dirs:
                path = parent / name
                try:
                    if path == output or path.is_symlink() or is_junction(path):
                        continue
                    if settings.get("skip_hidden", True) and hidden(path):
                        continue
                    if pattern_matches(path, root, settings.get("excluded_directories", [])):
                        continue
                    if pattern_matches(path, root, settings.get("ignore_patterns", [])):
                        continue
                    filtered.append(name)
                except OSError as exc:
                    errors += 1
                    emit(logger, f"SKIPPED DIRECTORY: {path}: {exc}")
            dirs[:] = filtered
            for name in filenames:
                consider(parent / name)
    else:
        try:
            for path in root.iterdir():
                consider(path)
        except OSError as exc:
            errors += 1
            emit(logger, f"SCAN ERROR: {exc}")

    records.sort(key=lambda record: record["source"].casefold())
    if progress:
        progress(count, count, "Scan complete")
    emit(logger, f"Scan completed: {len(records)} matching files, {errors} errors.")
    return records


def categories_for(settings: dict) -> dict:
    # Custom categories take precedence over defaults, so a user can assign
    # .pdf to "Receipts" instead of the built-in "Documents" category.
    result = {}
    for name, extensions in settings.get("custom_categories", {}).items():
        validate_component(name)
        if not isinstance(extensions, list):
            raise ValueError(f"Invalid extensions in category {name!r}")
        result[name] = normalize_extensions(extensions)
    for name, extensions in DEFAULT_CATEGORIES.items():
        if name not in result:
            result[name] = list(extensions)
    return result


def category_for(path: Path, settings: dict, snapshot: dict, category_map: Optional[dict] = None) -> str:
    mode = settings.get("organisation_mode", "Category")
    if mode == "Category":
        for category, extensions in (category_map if category_map is not None else categories_for(settings)).items():
            if path.suffix.lower() in extensions:
                return category
        return "Others"
    if mode == "Extension":
        return path.suffix.lower().lstrip(".").upper() or "No Extension"
    if mode in ("Date Modified", "Date Created"):
        stat_info = path.stat()
        if mode == "Date Modified":
            when = stat_info.st_mtime
        elif hasattr(stat_info, "st_birthtime"):
            when = stat_info.st_birthtime
        elif sys.platform == "win32":
            when = stat_info.st_ctime
        else:
            # Linux often has no portable birth time; mtime is the honest fallback.
            when = stat_info.st_mtime
        date = datetime.fromtimestamp(when)
        return f"{date.year}/{date:%m - %B}"
    if mode == "File Size":
        size = snapshot["size"]
        if size < 1024**2:
            return "Small - Under 1 MB"
        if size < 100 * 1024**2:
            return "Medium - 1 to 100 MB"
        if size < 1024**3:
            return "Large - 100 MB to 1 GB"
        return "Huge - Over 1 GB"
    raise ValueError("Unknown organisation method")


def lexists(path: Path) -> bool:
    return os.path.lexists(path)


def safe_ancestors(root: Path, directory: Path, create: bool = False) -> None:
    """Reject symlink/junction ancestors, including output/category folders."""
    rel = directory.relative_to(root)
    if ".." in rel.parts:
        raise ValueError(f"Path escapes the selected root: {directory}")
    if root.is_symlink() or is_junction(root) or not root.is_dir():
        raise ValueError(f"Root directory is no longer safe: {root}")
    check = root
    for component in rel.parts:
        check = check / component
        if check.is_symlink() or is_junction(check):
            raise ValueError(f"Refusing to follow a symlink/junction: {check}")
        if not check.exists():
            if not create:
                continue
            check.mkdir()  # Fails rather than treating a preexisting file as a directory.
        if check.exists() and not check.is_dir():
            raise ValueError(f"Parent path is not a directory: {check}")
        if check.is_symlink() or is_junction(check):
            raise ValueError(f"Refusing to follow a symlink/junction: {check}")


def build_plan(records: list[dict], folder: str | Path, settings: dict,
               logger: Logger = None, cancel=None) -> list[dict]:
    root = get_root(folder)
    output = get_output(root, settings)
    validate_filters(settings)
    reserved = set()
    next_suffix = {}
    plan = []
    category_map = categories_for(settings) if settings.get("organisation_mode") == "Category" else None
    for record in records:
        cancelled(cancel)
        source = Path(record["source"])
        snap = record["snapshot"]
        try:
            if not signature_matches(snap, signature(source)):
                raise FileChangedError("File changed since scan")
            category = category_for(source, settings, snap, category_map)
            # Only Date sorting is allowed to create subfolders.
            for comp in category.split("/"):
                validate_component(comp)
            parent = output.joinpath(*category.split("/"))
            safe_ancestors(root, parent, create=False)
            destination = parent / source.name
            collision_key = str(destination).casefold()
            index = next_suffix.get(collision_key, 1)
            while lexists(destination) or os.path.normcase(str(destination)).casefold() in reserved:
                destination = parent / f"{source.stem}_{index}{source.suffix}"
                index += 1
            next_suffix[collision_key] = index
            reserved.add(os.path.normcase(str(destination)).casefold())
            plan.append({"source": str(source), "destination": str(destination), "category": category,
                         "snapshot": snap, "size": snap["size"], "selected": True})
        except (OSError, ValueError) as exc:
            emit(logger, f"PREVIEW SKIPPED: {source}: {exc}")
    return plan


def _check_source(source: Path, expected: dict, root: Path) -> None:
    safe_ancestors(root, source.parent)
    if not signature_matches(expected, signature(source)):
        raise FileChangedError(f"Source changed since preview: {source}")


def _exclusive_copy_and_unlink(source: Path, dest: Path, expected: dict,
                               root: Path, cancel=None) -> dict:
    """Cross-device fallback, with O_EXCL and a checked source descriptor."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, flags)
    dest_fd = None
    created_identity = None
    try:
        with os.fdopen(source_fd, "rb") as reader:
            source_fd = None
            st = os.fstat(reader.fileno())
            if not stat.S_ISREG(st.st_mode) or not signature_matches(expected, {
                "size": st.st_size, "mtime_ns": st.st_mtime_ns, "dev": st.st_dev, "ino": st.st_ino
            }):
                raise FileChangedError("Source changed before copy")
            dest_fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
            created_stat = os.fstat(dest_fd)
            created_identity = (created_stat.st_dev, created_stat.st_ino)
            with os.fdopen(dest_fd, "wb") as writer:
                dest_fd = None
                while True:
                    cancelled(cancel)
                    chunk = reader.read(1024 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            st = os.fstat(reader.fileno())
            after = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "dev": st.st_dev, "ino": st.st_ino}
            if not signature_matches(expected, after):
                raise FileChangedError("Source changed during copy")
            _check_source(source, expected, root)
            shutil.copystat(source, dest, follow_symlinks=False)
            cancelled(cancel)
            _check_source(source, expected, root)
            final_sig = signature(dest)
            if (final_sig["dev"], final_sig["ino"]) != created_identity:
                raise FileChangedError("Destination changed during copy")
            if any(final_sig[key] != expected[key] for key in ("size", "mtime_ns")):
                raise FileChangedError("Destination metadata differs from source")
        # Windows will not unlink the source while our reader is still open.
        # Complete every fallible validation before removing the original.
        cancelled(cancel)
        _check_source(source, expected, root)
        safe_ancestors(root, dest.parent)
        source.unlink()
    except BaseException:
        if dest_fd is not None:
            os.close(dest_fd)
        if source_fd is not None:
            os.close(source_fd)
        if created_identity and lexists(dest):
            try:
                st = dest.lstat()
                if (st.st_dev, st.st_ino) == created_identity:
                    dest.unlink()
            except OSError:
                pass
        raise
    return final_sig


def move_exclusive(source: str | Path, destination: str | Path, expected: dict,
                   root: str | Path, cancel=None) -> dict:
    """Move one regular file, never replacing a destination.

    Same-volume hard-link+unlink avoids clobbering on POSIX (where os.rename
    would overwrite). Cross-volume copy uses O_EXCL. Active external writers
    can still race a move; metadata is checked immediately before/after.
    """
    source, destination, root = Path(source), Path(destination), Path(root)
    cancelled(cancel)
    _check_source(source, expected, root)
    safe_ancestors(root, destination.parent, create=True)
    if lexists(destination):
        raise FileExistsError(f"Destination already exists: {destination}")
    cancelled(cancel)
    link_created = False
    try:
        try:
            os.link(source, destination, follow_symlinks=False)
            link_created = True
        except (OSError, NotImplementedError) as exc:
            fallback_errors = {errno.EXDEV, errno.EPERM, errno.EACCES, errno.ENOTSUP,
                               getattr(errno, "EOPNOTSUPP", errno.ENOTSUP), errno.ENOSYS}
            if isinstance(exc, OSError) and exc.errno not in fallback_errors:
                raise
            return _exclusive_copy_and_unlink(source, destination, expected, root, cancel=cancel)
        else:
            _check_source(source, expected, root)
            final_sig = signature(destination)
            if not signature_matches(expected, final_sig):
                raise FileChangedError("Destination changed during link creation")
            cancelled(cancel)
            source.unlink()
    except BaseException:
        if link_created and lexists(destination):
            try:
                snap = signature(destination)
                if snap["dev"] == expected["dev"] and snap["ino"] == expected["ino"]:
                    destination.unlink()
            except OSError:
                pass
        raise
    # No filesystem reads after unlink: an error here must never trigger
    # cleanup of what is now the only remaining copy.
    return final_sig


def format_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def load_history(path: Path = HISTORY_FILE) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("moves"), list):
            return value
    except (OSError, ValueError, UnicodeError):
        pass
    return {"version": 1, "timestamp": "", "moves": []}


def save_history(history: dict, path: Path = HISTORY_FILE) -> None:
    save_json_atomic(path, history)


def organise(plan: list[dict], root: str | Path, progress: Progress = None,
             logger: Logger = None, cancel=None, history_path: Path = HISTORY_FILE) -> dict:
    selected = [p for p in plan if p.get("selected", True)]
    root = get_root(root)
    previous_history = load_history(history_path)
    history = {"version": 1, "root": str(root), "timestamp": datetime.now().isoformat(timespec="seconds"), "moves": []}
    moved, errors, skipped = 0, 0, 0
    history_checked = False
    history_error = False
    total = len(selected)
    processed = 0
    cancelled_early = False
    for index, item in enumerate(selected, 1):
        if cancel is not None and cancel.is_set():
            cancelled_early = True
            break
        source, dest = Path(item["source"]), Path(item["destination"])
        if progress:
            progress(index - 1, total, source.name)
        try:
            # Check journal access without discarding the previous operation.
            if not history_checked:
                try:
                    save_history(previous_history, history_path)
                except OSError as exc:
                    history_error = True
                    errors += 1
                    emit(logger, f"HISTORY ERROR: No files moved; cannot write undo history: {exc}")
                    break
                history_checked = True
            final_sig = move_exclusive(source, dest, item["snapshot"], root, cancel=cancel)
            history["moves"].append({"source": str(source), "destination": str(dest), "snapshot": final_sig})
            moved += 1
            processed += 1
            try:
                save_history(history, history_path)
            except OSError as exc:
                history_error = True
                errors += 1
                emit(logger, f"HISTORY ERROR: Stopped after moving {source} -> {dest}. "
                     f"This move was not saved for undo; keep this path for manual recovery. {exc}")
                break
            emit(logger, f"MOVED: {source} -> {dest}")
        except Cancelled:
            cancelled_early = True
            break
        except (OSError, ValueError, shutil.Error) as exc:
            processed += 1
            if isinstance(exc, (FileChangedError, FileExistsError, FileNotFoundError)):
                skipped += 1
                emit(logger, f"SKIPPED: {source}: {exc}")
            else:
                errors += 1
                emit(logger, f"ERROR: {source}: {exc}")
        if progress:
            progress(index, total, source.name)
    if progress:
        progress(processed, total,
                 "Stopped" if cancelled_early or history_error else "Complete")
    return {"moved": moved, "errors": errors, "skipped": skipped,
            "cancelled": cancelled_early, "remaining": len(history["moves"]),
            "history_error": history_error}


def undo(history_path: Path = HISTORY_FILE, progress: Progress = None,
         logger: Logger = None, cancel=None) -> dict:
    history = load_history(history_path)
    moves = list(reversed(history.get("moves", [])))
    restored = errors = skipped = 0
    cancelled_early = False
    history_error = False
    if moves:
        try:
            save_history(history, history_path)
        except OSError as exc:
            emit(logger, f"HISTORY ERROR: No files restored; cannot write undo history: {exc}")
            return {"restored": 0, "errors": 1, "skipped": 0, "cancelled": False,
                    "remaining": len(moves), "history_error": True}
    for index, move in enumerate(moves, 1):
        if cancel is not None and cancel.is_set():
            cancelled_early = True
            break
        source = Path(move["source"])
        dest = Path(move["destination"])
        if progress:
            progress(index - 1, len(moves), dest.name)
        try:
            # Validate the destination before undo, and do not overwrite anything
            # that appeared in the original location after the move.
            root = get_root(history.get("root") or history_root_for(dest, source))
            _check_source(dest, move["snapshot"], root)
            if lexists(source):
                raise FileExistsError(f"Original path already exists: {source}")
            safe_ancestors(root, source.parent, create=True)
            move_exclusive(dest, source, move["snapshot"], root, cancel=cancel)
            history["moves"].remove(move)
            restored += 1
            emit(logger, f"RESTORED: {source}")
            try:
                save_history(history, history_path)
            except OSError as exc:
                history_error = True
                errors += 1
                emit(logger, f"HISTORY ERROR: Stopped after restoring {source}; "
                     f"the undo journal was not updated. {exc}")
                break
        except Cancelled:
            cancelled_early = True
            break
        except (OSError, ValueError) as exc:
            if isinstance(exc, (FileChangedError, FileExistsError, FileNotFoundError)):
                skipped += 1
                emit(logger, f"UNDO SKIPPED: {source}: {exc}")
            else:
                errors += 1
                emit(logger, f"UNDO ERROR: {source}: {exc}")
        if progress:
            progress(index, len(moves), dest.name)
    return {"restored": restored, "errors": errors, "skipped": skipped,
            "cancelled": cancelled_early, "remaining": len(history["moves"]),
            "history_error": history_error}


def history_root_for(destination: Path, source: Path) -> Path:
    """Infer common selected root from stored paths for backward compat.

    The new journal always stores 'root'; this fallback exists only for older
    journaling data that lacked it.
    """
    common = Path(os.path.commonpath([str(destination), str(source)]))
    if not common.is_dir():
        raise ValueError("Original parent directory is not available")
    return common


def sha256_file(path: Path, expected: dict, cancel=None) -> str:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as reader:
        st = os.fstat(reader.fileno())
        f_sig = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "dev": st.st_dev, "ino": st.st_ino}
        if not stat.S_ISREG(st.st_mode) or not signature_matches(expected, f_sig):
            raise FileChangedError(f"File changed before hashing: {path}")
        digest = hashlib.sha256()
        while True:
            cancelled(cancel)
            buf = reader.read(1024 * 1024)
            if not buf:
                break
            digest.update(buf)
        if not signature_matches(expected, signature(path)):
            raise FileChangedError(f"File changed while hashing: {path}")
        return digest.hexdigest()


def find_duplicates(records: list[dict], progress: Progress = None, logger: Logger = None,
                    cancel=None) -> list[dict]:
    """Size prefilter, then SHA-256. Only complete matching hashes are reported."""
    by_size = defaultdict(list)
    for record in records:
        by_size[record["snapshot"]["size"]].append(record)
    candidates = [r for group in by_size.values() if len(group) > 1 for r in group]
    hashed = defaultdict(list)
    for index, record in enumerate(candidates, 1):
        cancelled(cancel)
        path = Path(record["source"])
        if progress:
            progress(index - 1, len(candidates), path.name)
        try:
            digest = sha256_file(path, record["snapshot"], cancel=cancel)
            hashed[(record["snapshot"]["size"], digest)].append(record["source"])
        except (OSError, ValueError) as exc:
            emit(logger, f"DUPLICATE SKIPPED: {path}: {exc}")
        if progress:
            progress(index, len(candidates), path.name)
    groups = [{"size": size, "sha256": digest, "paths": sorted(paths)}
              for (size, digest), paths in hashed.items() if len(paths) > 1]
    groups.sort(key=lambda x: (-x["size"], x["sha256"]))
    return groups
