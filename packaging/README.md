# Building the beta downloads

The app is packaged with PyInstaller on each target operating system. The
GitHub workflow runs the source tests, builds the native app, then launches
that packaged app in an isolated smoke test. It publishes a prerelease only
after all four packages pass: Windows x64, Linux x64, Mac arm64 and Mac x64.

## Build locally

Use Python 3.12 with Tkinter on the target OS:

```sh
python -m pip install -r packaging/requirements-build.txt
python packaging/build.py
```

Linux additionally needs Xvfb/xauth for the packaged GUI check. Output is in
`release-assets/`; temporary build files are under `build/`.
Mac builds use `hdiutil`, and PyInstaller performs ad-hoc signing. No developer
certificate, Windows Authenticode signature or Apple notarisation is included.

## Publishing another beta

Update `APP_VERSION`, the download filenames in the release notes and READMEs,
and merge the change to `main`. The workflow creates a draft, uploads all four
packages and checksums, then marks the release as a public prerelease.
Published versions are never replaced. If a build fails, inspect Actions;
fix it and rerun with a new beta version when necessary.

The publish job uses GitHub's temporary repository token with `contents: write`
only for that job. No personal access token or stored signing secret is needed.
