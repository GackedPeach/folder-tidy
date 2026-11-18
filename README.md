# File Organiser Pro

A little desktop app for sorting messy downloads, photos, videos and backup exports. It puts sorted **copies** in a **Files Sorted** folder and leaves your originals where they are.

**v1.2 public beta** — still being worked on. Try a small folder first and let me know how it goes.

[Download the beta](https://github.com/GackedPeach/folder-tidy/releases/tag/v1.2.0-beta.2) · [App instructions](file-organiser-pro/) · [Source code](file-organiser-pro/file_organiser_pro.py) · [Report a bug](https://github.com/GackedPeach/folder-tidy/issues/new?template=bug_report.yml)

## Get the app

No Python installation needed for these downloads.

| Your computer | Download |
| --- | --- |
| Windows 10/11, 64-bit | [Windows .exe](https://github.com/GackedPeach/folder-tidy/releases/download/v1.2.0-beta.2/FileOrganiserPro-v1.2.0-beta.2-windows-x64.exe) |
| Apple Silicon Mac (M1 or newer), macOS 15+ | [Mac — Apple Silicon](https://github.com/GackedPeach/folder-tidy/releases/download/v1.2.0-beta.2/FileOrganiserPro-v1.2.0-beta.2-macos-arm64.dmg) |
| Intel Mac, macOS 15+ | [Mac — Intel](https://github.com/GackedPeach/folder-tidy/releases/download/v1.2.0-beta.2/FileOrganiserPro-v1.2.0-beta.2-macos-x64.dmg) |
| Linux 64-bit, glibc 2.35+ (Ubuntu 22.04+ and compatible) | [Linux archive](https://github.com/GackedPeach/folder-tidy/releases/download/v1.2.0-beta.2/FileOrganiserPro-v1.2.0-beta.2-linux-x64.tar.gz) |

**Windows:** open the `.exe`. **Mac:** open the `.dmg` and drag the app to Applications. **Linux:** extract the whole archive, then open `FileOrganiserPro`; keep its `_internal` folder alongside it. Linux needs an X11/XWayland desktop.

These beta builds are unsigned, and the Mac apps aren't Apple-notarised. Your system may ask for approval on first launch.

## How it works

1. Pick a folder and choose how to sort it.
2. Preview the files and their destinations. Deselect anything you don't want copied.
3. Click **Organise copies**, then open the results.

You can sort by file type, extension, size, or modified/created date, with year, month or day folders. There are filters, a duplicate finder, dark/light themes, and a report for each run.

Copies are verified, existing files aren't replaced, and originals stay in place. Copies take extra disk space; running it again makes another set. Keep a separate backup of anything irreplaceable.

Date sorting uses filesystem dates, not photo capture dates or Google Takeout sidecars. Check **Advanced options** if you want hidden files or other excluded files included.

## Found something odd?

[Open a bug report](https://github.com/GackedPeach/folder-tidy/issues/new?template=bug_report.yml) with your operating system, app version, and what happened. Feedback from trying it on different machines helps.

## Working on the code

Built with Python and Tkinter, with some AI coding help along the way. The app uses the Python standard library; packaged downloads include the runtime.

[Run from source and full app notes](file-organiser-pro/) · [Build instructions](packaging/) · [All releases](https://github.com/GackedPeach/folder-tidy/releases)

<details>
<summary>The original Folder Tidy script</summary>

This repo started with the smaller command-line script in [`tidy.py`](tidy.py). It's still here, but **it moves files when you use `--apply`**. The desktop app above is copy-only.

```sh
python tidy.py "path/to/folder"          # preview only
python tidy.py "path/to/folder" --apply  # legacy move operation
python -m unittest -v                   # legacy script tests
```

</details>
