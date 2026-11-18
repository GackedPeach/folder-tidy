# File Organiser Pro — v1.2.0-beta.2

A small, local Python/Tkinter app for sorting messy downloads, photos, videos
and backup exports. It creates **independent copies** in a **Files Sorted**
folder inside the folder you choose. **Your originals stay in place.**

No account, cloud connection or third-party Python packages are needed.
This is a public beta of an early-development personal utility.

## Download the app

**[Get the fixed Windows beta.2 download](https://github.com/GackedPeach/folder-tidy/releases/tag/v1.2.0-beta.2)**

This release is a Windows hotfix. [Older Mac and Linux beta downloads](https://github.com/GackedPeach/folder-tidy/releases/tag/v1.2.0-beta.1) are still available, but those older builds have the Advanced options preview bug.

Packaged downloads include Python and Tkinter; no Python installation is
needed. Windows has a standalone `.exe`, Mac has separate Apple Silicon and
Intel `.dmg` downloads, and Linux has a `.tar.gz` containing the executable and
its support folder. See the release page for system requirements and launch
instructions. Beta builds are unsigned; the Mac apps are not notarised.

## Run from source

Keep `file_organiser_pro.py` and `organiser_core.py` together. Use Python 3.10+
with Tkinter installed, open a terminal in this folder, and run:

```powershell
# Windows
py file_organiser_pro.py
```

```bash
# Linux or macOS
python3 file_organiser_pro.py
```

Some Debian/Ubuntu installations need `sudo apt install python3-tk`.
On macOS, use a Python distribution with Tkinter.

## Organise copies

1. Choose a **Source folder**. Include subfolders is enabled for new settings;
   existing preferences are retained.
2. Choose **Organise by** and name your results folder (default: **Files Sorted**).
3. Click **Preview files**. Review the original paths, groups, copy destinations,
   selected count and additional space needed. Double-click a row or press Space
   to include or exclude it.
4. Click **Organise copies**. The app copies and checks each selected file,
   leaving the original at its existing path. Existing output files are never
   overwritten; collisions found during preview get names such as `photo_1.jpg`.
5. Click **Open results**. A timestamped **Organisation report … .txt** inside
   the results folder lists copied, skipped and failed files and their paths.
   The Activity tab can open the last report or export TXT/CSV logs.

The app checks free space before starting. Copies consume additional disk
space. Repeating an operation creates another set of copies with new names;
it does not merge or replace previous results.

### Sorting layouts

| Organise by | Example inside Files Sorted |
| --- | --- |
| File type | `Images/photo.jpg`, `Videos/clip.mp4`, `Documents/notes.txt` |
| File extension | `JPG/photo.jpg`, `MP4/clip.mp4`, `PDF/receipt.pdf` |
| Date modified | `2024/05 - May/photo.jpg` |
| Date created | `2024/05 - May/photo.jpg` |
| File size | `Small - Under 1 MB/notes.txt` |

For either date method, choose **Year**, **Month** or **Day** grouping. Day
grouping adds a day folder, for example `2024/05 - May/17/photo.jpg`.
Dates use local-time filesystem timestamps. Creation date falls back to
modified date when creation metadata is unavailable. Downloading or extracting
files may change those dates: **photo capture dates, EXIF and Google Takeout
JSON sidecars are not interpreted**.

File-type groups cover common images (including HEIC, AVIF and several RAW
formats), videos, audio, documents, spreadsheets, archives and more. Unknown
extensions go to **Others**. Extension mode creates **No Extension** for files
without a suffix. Custom file types can override built-in category assignments.

### Filters and duplicates

**Advanced options** contains hidden-file handling, ignored names/extensions,
excluded folders, included extensions, a filename pattern and minimum/maximum
size. Lists use commas; filename patterns accept `*` and `?`; sizes accept
values such as `500 KB`, `2 GB` or `1 GiB`. A plain number means bytes.

Hidden files, temporary files and common tool folders are excluded by default.
Review these options if you want them included. Symbolic links and junctions
are always excluded; the chosen output directory is never rescanned.
Only matching, selected regular files are copied; empty folders are not copied.

The **Duplicates** tab finds identical contents using size and SHA-256 hashes.
It is read-only. The app never automatically deletes duplicate files.

## Keeping originals safe

- Copying uses exclusive destination creation, never hard links or moves.
  Editing an organised copy does not edit its original.
- Source identity, size and modification time are checked against the preview
  and again during copying. Changed or missing files are skipped.
- Each completed copy is checked against the streamed source SHA-256 digest.
  File timestamps and permissions are copied where supported by the filesystem.
- Cancellation removes only an unfinished output created by this operation.
  Completed copies and every original remain in place. Closing during work
  requests cancellation and waits for the worker and report to finish.
- The report is created before copying. A report-write failure stops further
  copies and leaves recovery information in Activity. A last-session shortcut
  failure leaves the report in the results folder.
- Activity export also refuses to overwrite an existing file.

Keep a separate backup of irreplaceable files. Copy verification and metadata
checks cannot make a changing filesystem transactional or replace a backup.
A crash, storage failure or external modification can leave an incomplete
output or report. The original is never intentionally deleted by this app.
Metadata changes that preserve all checked attributes may evade stale-file
checks; the app does not interpret photo or backup semantics.

## Settings and previous versions

Settings remain at `~/.file_organiser_pro.json`, with existing preferences
retained and `date_granularity` added. The old default output name `Organised`
is migrated to `Files Sorted`; other custom output names are kept.
The last copy-session shortcut is saved separately at
`~/.file_organiser_pro_last_run.json`.

**Undo was removed in v1.2 because organisation now keeps every original.**
Completed copies are left for you to manage manually. Legacy v1.1 move journals
at `~/.file_organiser_pro_history.json` are neither loaded nor overwritten.
If you need to reverse a move made by an older release, retain that release
and its journal. This version does not convert or replay old move history.

## Development and tests

The core and interface are separate modules; the app uses only the standard
library. From this directory:

```bash
python -m unittest discover -s tests -v
```

Tests use synthetic temporary files and isolated settings. Tk tests use a
withdrawn window and skip if Tk or a display is unavailable. On a headless
Linux system with Xvfb, use:

```bash
xvfb-run -a python -m unittest discover -s tests -v
```

The v1.2 copy engine and Tk workflows have been exercised on Windows with
Python 3.12, including independent copies, date layouts, failure/cancellation,
reports and a 10,000-row preview. Symlink tests skip when the session lacks
permission to create them. The release workflow also runs the source tests and an isolated packaged-app
check on Windows, Linux and both Mac architectures before publishing all
downloads together. The packaged check launches Tk, previews fixture files,
creates independent copies, checks originals and verifies a saved report.
This is automated beta validation; broader testing on users' own machines
and storage setups is still welcome.

## Project background

This is a practical personal tool for sorting very untidy local downloads and
backups, especially Google Takeout exports with thousands of photos, videos
and device files. It is still early development, with reliability, clear
previews and usability taking priority. Development has included AI coding
assistance from ChatGPT and Grok.

Version history: v1.0 prototype → v1.1 safety and usability → v1.1.1 Windows
reliability fixes → v1.2 copy-only organisation, clearer date options and a
refined interface. The separate `tidy.py` in the repository root remains the
original command-line tool and moves files; this desktop app is copy-only.
