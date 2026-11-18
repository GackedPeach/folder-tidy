# File Organiser Pro — v1.1.1

A local-first, cross-platform desktop file organiser, written in Python 3.10+ and Tkinter. No cloud access, telemetry, package manager or third-party Python dependencies.

## Getting started

Keep `file_organiser_pro.py` and `organiser_core.py` together in the same directory.

**Windows** (Python installed):

```powershell
py file_organiser_pro.py
```

**Linux / macOS**:

```bash
python3 file_organiser_pro.py
```

On Debian/Ubuntu, install Tkinter if it isn't already available:

```bash
sudo apt install python3-tk
```

On macOS, use a Python distribution that includes Tkinter.

**Start with a disposable test directory and a backup.** This program physically moves files. It does not copy them for ordinary organisation.

## How to use

1. Select a folder. `Include subfolders` is off by default; the chosen output directory is always excluded from scanning.
2. Choose a method: Category, Extension, Date Modified, Date Created, or File Size.
3. Optionally set exclusions, extensions to include, a glob such as `*invoice*`, and file-size limits such as `500 KB` or `2 GB`. A plain number means bytes.
4. Click **Preview Moves**. Double-click a row to toggle whether it is included, or use **Include All**, **Exclude All** and **Toggle Highlighted**.
5. Click **Organise Selected**. The program rechecks source metadata and destination availability before each move. It refuses to overwrite an existing path. **Cancel Job** stops at a safe boundary.
6. Use **Undo Last** to restore the last operation, including after restarting the application. A changed file, missing destination or occupied original path is **not** blindly overwritten.
7. Use **Find Duplicates** to display size-and-SHA-256 matches without deleting anything. The duplicate tab is read-only.
8. Use **Export TXT / CSV…** in Activity Log to save a report from the current session.

## New in v1.1.1

This is a small reliability update to v1.1, keeping the same features and
settings format.

- Fixed the copy fallback on Windows: the source reader is closed before
  removing the original file.
- Finished destination checks before removing the original, so a later
  metadata-read failure cannot trigger deletion of the only remaining copy.
- Check that undo history can be saved before moving or restoring files.
  If a history update fails after a completed move, stop immediately, report
  the completed move accurately, and show its paths in the activity log.
  Keep the app open and export the log if that warning appears; the last
  move may need manual recovery.
- Keep the previous operation's undo history until a new move succeeds.
- Closing during an operation requests cancellation and waits for file work
  and history updates to finish.
- Load large move previews in batches and limit event processing per UI tick,
  allowing the window to respond while displaying thousands of files.
- Reuse collision suffix counters when many files share a name.
- Added regression tests for copy failures, cancellation, undo-history errors,
  safe shutdown, and a 10,000-row preview.

## Included since v1.1

- No-overwrite moves using exclusive destination creation. Same-filesystem regular files use hard-link/unlink where supported; other cases use exclusive-create streaming copy/unlink.
- Source identity, size and modification-time checks at preview and move time.
- Hidden folders, symbolic links, Windows junctions/reparse directories, ignored names, and configurable excluded directory patterns are excluded from recursive scans.
- Previews are invalidated when relevant settings or the selected directory change.
- Background worker threads and a responsive progress indicator with count, remaining files and current filename. All Tkinter widgets update on the main thread.
- Per-file inclusion/exclusion controls.
- Extension, filename glob, minimum-size and maximum-size filters.
- Text/CSV activity-log export.
- Last-used directory restored on launch.
- Persistent, single-level undo journal.
- Light/dark themes.
- SHA-256 duplicate detection with a size pre-filter; zero automatic deletions.
- Custom category definitions can now override extensions assigned by built-in categories.

## Settings and history

The existing settings JSON is retained with its original keys and updated with new optional keys:

- `~/.file_organiser_pro.json` — application configuration, including last-used folder and theme.
- `~/.file_organiser_pro_history.json` — last successful organisation operation for undo.

Both files are updated via temporary-file-and-replace writes. Older settings files remain readable. The undo journal is not a permanent, multiple-version operation history. Starting a new **successful** organisation run replaces the previous operation's undo entries.

## Safety limitations and design choices

- No external process can be completely controlled: another application writing, renaming, or replacing files concurrently can cause race conditions. Metadata checks and exclusive destination creation reduce risk but cannot make an entire multi-file operation transactional.
- A sudden crash or power failure between a file move and the undo-journal write can leave that particular move unjournaled. You can still locate the file inside the destination folder. For irreplaceable data, keep a separate backup.
- Duplicate detection hashes file contents, but does **not** confirm semantic equivalence (e.g. two differently encoded photos may look identical but have different hashes).
- If native creation-time metadata is unavailable, Date Created falls back to modification time on non-Windows systems; it does **not** misinterpret Linux inode-change time as creation time.
- Empty directories are left in place after organising/undoing, by design.
- Hidden-file detection recognises dot-names on POSIX and Windows hidden attributes where available. A filesystem-specific hidden convention may differ.
- Metadata-only stale-preview checks cannot detect an adversary who replaces content while restoring all compared metadata. SHA-256 is used for duplicate detection, not for every file move.
- v1.1 was tested on Linux. The v1.1.1 regression suite was also run on Windows
  with Python 3.12, including Tk interface tests and a forced copy-fallback test.
  Two symbolic-link tests were skipped because this Windows session cannot
  create symlinks. A physical cross-volume move and macOS have not been tested
  for this update.

## Run automated tests

From the extracted project directory:

```bash
python -m unittest discover -s tests -v
```

The tests use temporary directories; they do not organise your real files.
Interface tests use a withdrawn Tk window and isolated settings. They skip
when Tk or a display is unavailable. On a headless Linux machine with Xvfb,
use `xvfb-run -a python -m unittest discover -s tests -v` to include them.

## Project layout

```text
file_organiser_pro_v1_1_1/
├── file_organiser_pro.py     # Tkinter user interface
├── organiser_core.py         # Filesystem and hash operations
├── tests/
│   ├── test_organiser_core.py
│   └── test_gui.py
└── README.md
```

## Project background and direction

This is an early-development personal utility, not a groundbreaking replacement for a file manager. My main use case is sorting very messy local downloads and backups, especially Google Takeout exports containing photos, videos and device files. Such exports can contain tens of thousands of files, and I want more control over how they are sorted. The application is also intended to be useful for other large, untidy folders.

Google Takeout-specific metadata, JSON sidecars, photo albums and backup formats are **not yet interpreted**. This is a general-purpose file organiser, not a dedicated Google Takeout recovery or archival tool. Always back up irreplaceable files, and test on disposable copies first. Even with safer moves, interrupted operations, storage faults or concurrent changes can cause problems.

Development has included brief AI coding assistance from ChatGPT and Grok. Future work will focus on reliability with large datasets, usability, and better handling of complex backup exports.
