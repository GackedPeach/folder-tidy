# File Organiser Pro

A small desktop app for organising messy downloads, photos, videos and backup
exports. It creates sorted **copies** in a **Files Sorted** folder, keeping
your originals in place.

**Version 1.2 public beta — a work in progress, ready for testing.**

## Download and run

**[Open the beta download page](https://github.com/GackedPeach/folder-tidy/releases/tag/v1.2.0-beta.1)**

You do not need to install Python or download the code to use these builds.

| Your computer | App download |
| --- | --- |
| Windows 10/11, 64-bit | [Download the Windows .exe](https://github.com/GackedPeach/folder-tidy/releases/download/v1.2.0-beta.1/FileOrganiserPro-v1.2.0-beta.1-windows-x64.exe) |
| Mac with Apple Silicon (M1 or newer), macOS 15+ | [Download the Apple Silicon Mac app](https://github.com/GackedPeach/folder-tidy/releases/download/v1.2.0-beta.1/FileOrganiserPro-v1.2.0-beta.1-macos-arm64.dmg) |
| Intel Mac, macOS 15+ | [Download the Intel Mac app](https://github.com/GackedPeach/folder-tidy/releases/download/v1.2.0-beta.1/FileOrganiserPro-v1.2.0-beta.1-macos-x64.dmg) |
| Linux 64-bit, glibc 2.35+ (Ubuntu 22.04+ and compatible) | [Download the Linux app](https://github.com/GackedPeach/folder-tidy/releases/download/v1.2.0-beta.1/FileOrganiserPro-v1.2.0-beta.1-linux-x64.tar.gz) |

**Windows:** open the `.exe`. **Mac:** open the `.dmg` and drag the app to
Applications. **Linux:** extract the whole archive and open `FileOrganiserPro`
inside it; keep its `_internal` folder alongside it. Linux needs a graphical
X11/XWayland desktop.

These are unsigned community beta builds. Windows or macOS may require manual
approval on first launch. The Mac apps are not Apple-notarised.

## What it does

- Group copies by file type, extension, modified/created date, or size.
- Use year, month or day folders when sorting by date.
- Preview destinations and choose individual files before copying.
- Filter files, check for duplicates, and save a report of each run.
- Keep originals in place, verify copies, and never replace existing files.
- Work locally with a dark or light interface and cancellable background jobs.

Date sorting uses filesystem dates. Photo capture metadata and Google Takeout
sidecars are not interpreted. Filters apply, so review Advanced options to
choose whether hidden files and other exclusions are included.

## Try it and report problems

Start with a small sample of files during beta testing. If something goes
wrong, [report a bug](https://github.com/GackedPeach/folder-tidy/issues/new?template=bug_report.yml)
with your operating system, app version and what happened. We can improve the
app as issues are found.

## Source code

[App source and full instructions](file-organiser-pro/) ·
[Build instructions](packaging/) ·
[Release downloads](https://github.com/GackedPeach/folder-tidy/releases)

The app is written in Python/Tkinter, with no runtime third-party Python
packages. Native downloads bundle the runtime. Development has included brief
AI coding assistance from ChatGPT and Grok.

## Original Folder Tidy script

The repository also keeps the earlier, smaller command-line organiser in
[`tidy.py`](tidy.py), with its tests in [`test_tidy.py`](test_tidy.py). That
legacy script **moves files** when run with `--apply`; the desktop app above
is the copy-only program.

```sh
python tidy.py "path/to/folder"          # preview only
python tidy.py "path/to/folder" --apply  # legacy move operation
python -m unittest -v                   # legacy script tests
```
