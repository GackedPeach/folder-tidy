# File Organiser Pro 🗂️

**Early development — v1.0 (prototype)**

File Organiser Pro is a small, local-first desktop file organiser built with Python and Tkinter for Windows, Linux and macOS. It is a personal utility, not an attempt to reinvent file management.

## Why I started it

My main use case is cleaning up the sprawling folders that can result from downloading data through **Google Takeout**: Google Photos, videos, device backups, documents and whatever else has accumulated over the years. Those downloads can contain tens of thousands of files and nested directories, and it is not always convenient to sort through them using a regular file manager.

I wanted a straightforward tool that could preview where files will go, organise them using different rules, and give me a bit more control over how I deal with messy backups. It may also be useful for ordinary Downloads folders and other local collections.

**This is not a Google Takeout parser.** It does not reconstruct albums, interpret Takeout JSON sidecars, reconcile duplicate image versions or preserve original Google Photos metadata beyond what the filesystem already exposes. Those would require separate, purpose-built features.

## What v1.0 does

- Organises by file category, extension, modified date, creation-date metadata or size.
- Provides a Tkinter desktop interface and a preview before moving files.
- Optionally scans nested subfolders, with basic hidden-file and ignore-pattern controls.
- Supports custom extension categories and an activity log.
- Avoids known destination names when planning moves and offers an in-session undo for successful moves.
- Saves preferences to `~/.file_organiser_pro.json`.

## Run

Python 3.10+ recommended. No third-party Python dependencies.

```sh
python file_organiser_pro.py
```

On Windows, `py file_organiser_pro.py` may be appropriate. Debian/Ubuntu users may need to install `python3-tk`.

## ⚠️ Early prototype — protect your data

**Use copies and a disposable test folder first, especially for Google Takeout archives or irreplaceable photos.** This version moves files rather than copying them, and the initial preview and undo mechanisms have limitations:

- Large operations run on the UI thread and can become unresponsive.
- Undo history is lost when the application exits.
- Changing settings after a preview may leave a stale plan.
- A race between destination checks and moving a file may cause an unexpected overwrite on some platforms.
- Recursive scanning does not fully exclude hidden directories.
- Linux `st_ctime` is not equivalent to file creation time.

The next version focuses on safer moves, better scanning and previews, persistent undo, background processing, filters and duplicate inspection.

## Development

This is a personal learning project and is still changing. ChatGPT and Grok have been used as coding assistants during development.

## Repository

This project lives alongside the smaller `tidy.py` CLI utility in the parent repository. The two are separate tools.
