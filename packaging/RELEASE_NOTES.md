## File Organiser Pro 1.2.0-beta.2 — Windows preview fix

Small fix for a frustrating one: opening and closing **Advanced options** could leave the controls stuck when you clicked **Preview files**. That's fixed.

### What's changed

- Preview works after closing Advanced options, including after opening it more than once.
- The full results-folder path is shown in the app.
- Scan and preview messages now make it clear that no files have been copied yet.

### Download for Windows

Download **FileOrganiserPro-v1.2.0-beta.2-windows-x64.exe** from the assets below and open it. Windows 10/11, 64-bit. No Python installation needed.

Choose a folder, click **Preview files**, review the list, then click **Organise copies**. Copies go into **Files Sorted** inside your chosen folder. Your originals stay in place.

This is still an unsigned beta, so start with a small sample. Windows may ask for approval on first launch. A SHA-256 checksum is attached.

This is a Windows hotfix. Mac and Linux packages aren't included in this release. [Their previous beta downloads](https://github.com/GackedPeach/folder-tidy/releases/tag/v1.2.0-beta.1) remain available; those older builds still have the preview bug.

Checked with the Windows GUI tests and a packaged scan → close options → preview → copy test. A regression test reproduces the old failure and passes with the fix.

[Report a bug](https://github.com/GackedPeach/folder-tidy/issues/new?template=bug_report.yml) · [Read the instructions](https://github.com/GackedPeach/folder-tidy/tree/main/file-organiser-pro)
