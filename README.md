# Folio Notepad

A native Qt desktop editor for Fedora KDE: plain text, Markdown, tables, images, drawing, local drafts, and portable notes. This is a **0.4.2 development release**, not a certified Windows Notepad clone. The implementation follows [plan.md](plan.md); scope and remaining release work are tracked in [docs/status.md](docs/status.md).

## Install and launch

Published installers are intended to appear under [GitHub Releases](https://github.com/23-prabhat/Slate/releases). In a release's **Assets**, choose the Fedora `.rpm` file; the Source code ZIP is not an installer. The release workflow is prepared in this repository and first needs to be pushed and triggered with a matching version tag. See [publishing instructions](docs/packaging.md#publish-installers-on-github). `dist/` stays ignored in Git because GitHub Actions builds the installer and uploads it separately.

The built Fedora package is in `dist/folio-notepad-0.4.2-1.fc44.noarch.rpm`. Open it in KDE Discover and install it once. Then search for **Folio Notepad** in the application menu and pin it to your taskbar. It uses Fedora's supported Python/Qt packages and needs no rebuild after ordinary kernel updates. This local RPM is unsigned and has no automatic application-update repository yet.

If Discover does not offer local RPM installation on your setup, the one-time alternative is:

```bash
sudo dnf install ./dist/folio-notepad-0.4.2-1.fc44.noarch.rpm
```

The source tree runs directly when Fedora's `python3-pyside6` package is installed:

```bash
./folio-notepad
```

A relocatable user installation is also available with `./scripts/install-user.sh`. It copies the application into `~/.local/share/folio-notepad`, installs the menu entry/icon and executable, and does not change your default file associations. Moving or deleting the original checkout will not break that installed copy. This script is a one-time installation, not a per-launch or per-kernel step.

The implementation environment permits writes only in the project and `/tmp`; an installed menu entry was therefore **not written into your home directory** during development. The RPM has been built and its installed layout tested in an isolated staging directory.

## Everyday use

- **Workspace:** one compact toolbar and a single title in the tab leave more room for writing. **Folio** opens all menus and commands. Side panels start closed; use the left Notes / Insert buttons or **Folio → View** to open them. The Properties button opens the right panel. Table controls appear in one compact row above the note when Properties is hidden. Existing panel preferences reset once on upgrading to the compact layout, then your choices persist.
- **Zoom:** use the bottom-right slider or + / − buttons. Click the percentage to reset. Each note keeps its own zoom.

- **Ctrl+Z:** undo. **Ctrl+Y** or **Ctrl+Shift+Z:** redo. Inline drawing strokes use the same note history.
- **Ctrl+F:** compact Find bar; **Ctrl+H** reveals Replace. Match case, whole words and regex are under Options.
- **Ctrl+N:** new unnamed note. Type immediately. By default drafts are kept locally, including on closing the app.
- **Ctrl+S:** save the current file, or choose a name for a new note. **Ctrl+Shift+S:** Save As. Draft protection does not mean the user file has been saved.
- **View → Create formatted copy:** visually edit an existing text/Markdown file without rewriting its original source. New unnamed notes can enable formatting directly.
- **Insert → Table:** choose a grid or enter total rows and columns. Every cell starts blank; no extra header or “Column 1” labels are inserted. Click a cell for the contextual toolbar: enter column width / minimum row height, use the edge **+** buttons or **⋯** menus to insert, duplicate, move or delete rows/columns, and drag borders to resize. **More** also offers equal sizing and fit-to-content. Table size changes warn before dropping populated cells and can be undone. Save as **`.folio`** to retain exact layout; Markdown cannot store these sizes.
- **Drawing:** click the pencil or **Folio → Insert → Drawing** to draw directly in an area inside the current note. The toolbar switches to pen/highlighter/eraser, shapes, ink colour, stroke width and Clear. Completed strokes are immediately part of the note for Save and draft recovery. Click **Text** or press **Esc** to return to typing; double-click a saved drawing to edit it in place. Save as `.folio` to retain editable strokes.
- **Folio → Insert → Image:** paste/drop local images or pick a file. Double-click an ordinary image for its properties.
- **Source / Preview / Split:** exact editable source for imported text/Markdown; read-only source projection for a formatted note. Split previews update as you type.
- **Export:** create a separate artifact without changing the original file path or clearing unsaved changes. **Share / prepare file** creates a ZIP and opens its containing folder; attach it using your chosen app.
- **Tools → Text encoding and line endings:** UTF-8/UTF-16, BOM, preserve/normalize line endings.
- **Tools → Spelling language / suggestions:** available system dictionaries. English spelling is enabled in formatted notes. Optional autocorrect handles a small explicit set of common English typos; it is not a general grammar checker.
- **Tools → Writing assistant:** optional Ollama-compatible endpoint/model. Nothing is sent until Generate; results stay in preview until Accept. There is no model bundled and credentials are never saved.
- **Theme icon (top right)** or **View → Theme:** System, Light or Dark; changes apply immediately across open windows and persist on restart.
- **Tools → Preferences:** traditional Save/Discard/Cancel closing, theme, recent-file preferences. **Draft recovery** restores closed notes retained for 30 days.

## Choose a format

| Format | Use |
| --- | --- |
| `.txt` | Plain text, with original encoding/BOM and line endings preserved where applicable. Images become descriptions on text export. |
| `.md` | Markdown and single-line Markdown tables. Owned images are copied into a neighboring `assets/` directory. Share that directory too. |
| `.folio` | One ZIP-based portable document containing Markdown, rich document data, owned images, and editable drawing objects. Best for visual notes. |
| `.zip` | Shareable Markdown plus visible attachments, with an editable portable note included when drawings or formatted tables exist. |
| `.pdf` | Rendered, paged output. Printing includes configurable header/footer tokens. |

Multiline table cells cannot be represented faithfully in the supported Markdown table profile. Saving them to `.md` is refused with an explanation; `.folio` preserves them. Literal table pipes are escaped by the app's serializer. Unsupported arbitrary Markdown/HTML remains protected in source mode. Deleted images retained internally for Undo are excluded from portable exports/share bundles.

## Data and privacy

Normal editing is offline. No telemetry, account, hosted backend, or automatic upload. Images referenced in imported markup do not gain arbitrary filesystem or network access. Tools → Load local Markdown images lets you explicitly grant a folder for preview; creating a formatted copy then owns those bytes for portable saving. Drafts are local and unencrypted, with a private SQLite database under Qt's application data directory (normally `~/.local/share/FolioNotepad/Folio Notepad/`; Flatpak uses its private data area). Use **Tools → Open draft storage** to locate it. Back up this directory if unnamed drafts matter to you.

Protection runs after about two idle seconds and periodically while typing. Crash recovery preserves committed snapshots, not a guarantee of the last keystroke during power failure. Closing flushes recovery synchronously and refuses to silently discard on failure. The most recent ten revisions and closed drafts up to 30 days are retained. Selecting Discard in traditional mode deliberately removes that note's recovery data.

A separate test profile is available:

```bash
./folio-notepad --data-dir /tmp/folio-test-profile --no-restore
```

## Development and verification

Runtime requirements: Python 3.11+ and PySide6 6.8+. Optional spelling: PyEnchant plus a dictionary backend. All are distributed as Fedora packages; no pip install is required here.

```bash
make test                  # Qt offscreen tests, including a real killed-process recovery test
make rpm                   # build the Fedora RPM locally using rpm-build
make install PREFIX=/tmp/folio-stage
```

`make install` installs into `PREFIX`; for packaging use `DESTDIR` as well. `scripts/build_rpm.py` needs `rpmbuild` and `make`. Tests use standard-library unittest and native Qt; no test packages are downloaded. CI repeats these checks inside Fedora.

A [Flatpak manifest](packaging/flatpak/org.local.FolioNotepad.json) targets KDE/PySide BaseApp 6.11. It is a recipe, **not a verified built Flatpak** in this environment: flatpak-builder, the SDK/BaseApp, and package-server network access are unavailable. The recipe uses portals and grants no home-directory or Internet access by default. AI networking is unavailable inside that offline Flatpak unless separately granted. See [packaging notes](docs/packaging.md) for the remaining validation steps.

The GUI was inspected with Qt offscreen rendering, and native widgets are used throughout. Physical printing, a real stylus, screen readers, live Wayland session behavior, a kernel upgrade, and store installation still require desktop QA.

## Icon assets

The [transparent master PNG](resources/icons/folio-notepad-v2.png) and [desktop sizes](resources/icons/hicolor/) ship with the app. See the [design prompt and export instructions](docs/icon-design.md).

## License

Application code: GPL-3.0-or-later; see [LICENSE](LICENSE). Qt/PySide and optional dictionary libraries retain their own licenses. The application uses system libraries rather than bundling their binaries into the RPM. A stable store release should first replace the development-only `org.local` identity with an owned namespace.
