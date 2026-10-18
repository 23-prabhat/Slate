# Packaging and release

## Fedora RPM

Run `make rpm` with Fedora's rpm-build and make installed. This creates a noarch package in `dist/`, declares `python3-pyside6 >= 6.8`, and recommends system spelling support. It contains the app, icon, desktop entry, custom `.folio` MIME type and AppStream metadata. It does not change the default editor or install kernel hooks. Install once using KDE's local package installer where supported, or `dnf install ./dist/<filename>.rpm`.

The package is unsigned. It has no automatic update repository; new application releases require a new package until signing/repository hosting is configured. Runtime dependencies receive Fedora's ordinary updates. Kernel upgrades do not require recompilation of this application.

`make install PREFIX=/tmp/folio-stage` exercises the installed layout without modifying the host. `scripts/install-user.sh` is an alternative that installs a relocatable copy under the user's prefix and writes an absolute, escaped launcher target. It leaves existing user notes alone.

## Flatpak recipe (unverified build)

The development recipe uses `org.kde.Platform` / `org.kde.Sdk` / `io.qt.PySide.BaseApp` branch 6.11. PySide BaseApp explicitly documents this supported branch; the host's installed KDE runtime alone does not contain the required Python Qt bindings. See [BaseApp documentation](https://github.com/flathub/io.qt.PySide.BaseApp).

On a development system with builder, SDK and BaseApp installed:

```bash
flatpak-builder --user --install --force-clean build/flatpak packaging/flatpak/org.local.FolioNotepad.json
flatpak run org.local.FolioNotepad
```

Do not call this a verified distribution until these steps succeed in a clean environment. Review all metadata, runtime/baseapp compatibility and cleanup results. The default finish permissions allow graphical desktop/printing integration, with no home-directory or network grant. Portal-backed selected files are intended; sibling attachment folders and atomic replacement through document portals still need validation. Prefer portable `.folio` files until that is resolved. Optional AI has no networking inside this default offline sandbox.

Package optional spelling backends/dictionaries separately when their sources/checksums are available. The app degrades to editing without spelling if they are missing. Do not copy the host's ABI-dependent Python bindings into a different Flatpak Python runtime.

Before public distribution, replace the local namespace with one the maintainer owns, add a real homepage/screenshots, sign releases, and configure a maintained repository or seek Flathub inclusion. Standalone bundles do not establish an update channel by themselves.
