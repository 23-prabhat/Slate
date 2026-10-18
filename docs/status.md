# Implementation status — 0.4.2 development release

The repository contains a working native desktop application and a locally built Fedora RPM. This is a substantial implementation of the offline product, not completion of every release gate in `plan.md`.

## Delivered

- Compact native Qt workspace: one toolbar, Folio command menu, one title per tab, small navigation rail, panels on demand, full-width writing surface and per-note zoom control. Softer theme surfaces and reduced margins. Responsive/toggleable panels preserve access to table controls. Accessible control names, reorderable/closable tabs and multiple windows.
- Open/save/save-as/save-all, recents, duplicate/rename unnamed notes, move tabs to new windows, reopen/restore closed drafts.
- Plain/source editing, formatted documents, split/read-only previews, Markdown formatting, lists, headings, code and quotes.
- Coherent undo/redo for typing, formatting, table edits, image/drawing insertion, conversion and accepted generated text.
- Exact-size blank table insertion, no generated header/labels, contextual toolbar and edge buttons, row/column insert/remove/duplicate/move, drag and numeric column width / row minimum height, equal sizing / content fitting, resize with nonempty-cell warning, column alignment, cell Tab navigation and TSV paste. Table geometry survives portable save/reopen and Undo.
- Visible, persistent System/Light/Dark theme menu/button, synchronized across windows, with theme-neutral default note text and view-only contrast adjustment for light-filled legacy table cells.
- PNG/JPEG/WebP import, explicit folder-granted local Markdown image previews, clipboard/drop image insertion, proportional resize, alt text, replacement/removal; owned bytes survive moving the original image.
- Editable pen/highlighter/eraser/shape drawing directly inside the note, mouse/tablet events, shared document undo/redo per completed stroke, versioned JSON and PNG previews. Save and recovery work during drawing; existing drawings reopen in place.
- `.txt`, `.md` plus visible assets, `.folio` portable notes, ZIP share bundles and paged PDF export; print preview/page setup/header/footer controls.
- UTF-8/BOM/UTF-16 and line ending controls; byte-identical untouched text including mixed endings; strict invalid-input refusal.
- Find/replace/replace-all with literal replacement, case/whole-word/regex matching, line navigation, date/time insertion, `.LOG` behavior, zoom/wrap/font/theme.
- Optional spelling through available dictionaries and undoable common-English autocorrect.
- Optional Ollama-compatible Write/Rewrite/Summarize dialog with bounded streamed preview, explicit sending/acceptance, cancellation, timeout, session-only token and revision protection.
- Atomic writes with checked commit and no unsafe fallback, external conflict checks, deliberate symlink handling and refusal to break hard links.
- Background transactional SQLite recovery, multi-window/tab order and cursor/scroll bookmarks, two close policies, bounded revisions and closed-draft retention.
- Owned images no longer visible in a note are omitted from portable/share exports; resources cannot automatically read arbitrary local files or fetch remote URLs.
- Archive limits, entry/path/schema/checksum validation and drawing-object limits.
- Launcher/icon/MIME/AppStream metadata; isolated installation script, reproducible RPM build, Flatpak recipe and CI definition.

## Deliberate differences / incomplete plan items

- Uses PySide6 instead of C++20, stdlib ZIP/SQLite instead of libarchive/Qt SQL, PyEnchant instead of Sonnet. Rationale: `decisions/001-native-qt-bindings.md`.
- Formatted source is a read-only projection. Arbitrary imported Markdown must remain in source mode or be explicitly copied for formatted editing. Full source-aware rich/source editing is not implemented.
- Sharing prepares an export and opens the containing folder. Direct Purpose/KDE Connect targets and their sandbox integration are not implemented.
- Flatpak has not been built/run here. The recipe needs builder/SDK/BaseApp access; sibling Markdown assets require directory portal/access work. No Flatpak or RPM update repository has been published.
- There is no included AI model or tested live provider session. The protocol decoder and editor acceptance boundaries are testable offline; actual inference requires the user's configured server/model. No secure credential persistence is offered; tokens are session-only.
- Spelling depends on installed dictionaries. Hindi UI/input content is supported as Unicode, but no Hindi dictionary was present to validate. Autocorrect is a short English substitution list, not a learned correction engine.
- Search-in-selection, shortcut customization, persistent per-note spelling settings, editable image width metadata in Markdown, paper-pressure variation/zoom in the drawing canvas, advanced selection/moving shapes, line-number gutter/focus mode and task lists remain enhancements.
- The drawing eraser removes entire strokes. Large-file editing uses bounded undo history but does not yet have the full planned reduced-feature large-file mode.
- Recovery revisions store complete note snapshots including asset bytes, so very image-heavy sessions can use significant disk space. Compression/content-addressed deduplication, a storage-management UI, recovery-revision browsing and explicit draft deletion UI are still needed.
- Window geometry uses a global last-window preference; per-window geometry and persistent text selections/view mode are not complete. Current cursor/scroll and zoom are restored.
- Refusal/retry banners protect failed drafts; granular retry/save-as/discard recovery-failure buttons are not yet implemented.
- There is no Windows reference installation audit, translation catalog, What's New flow, or full screen-reader/stylus/live KDE QA certification.
- This is a local development identity and unsigned RPM. AppStream's missing public homepage is intentional until a real repository/domain is chosen. No fabricated homepage is supplied.

## Verification performed

**90 automated tests pass** with Qt 6.11.2 on Fedora 44, including inline pointer drawing, stroke undo/redo, save/recovery during drawing, scrolling and moving drawing tabs, compact command and search access, responsive panel and tab transitions without document changes, properties-host cleanup, actual Ctrl+Z / Ctrl+Y keyboard events across editing modes and drawings, menu availability after Undo/Redo, simulated mouse border dragging, blank-table counts, numeric layout save/reopen and Undo, contextual row/column controls, theme persistence and clean-state preservation, dark-mode PDF body-text pixel verification, PDF images, deleted-attachment privacy, multi-tab close cancellation and moving an editor with its undo history. See `tests/` for automated codec, save-failure, package, table/image/drawing, undo, source-fidelity, export, conflict, close-policy and killed-process recovery tests. Focused dropdown checks verify bounded arrow geometry, complete labels and pointer opening in both themes at 100/150/200% Qt scaling. The app starts and exits through its real launcher in an isolated profile. A staged installation tests relocation separately from the source checkout. Qt offscreen screenshots and rendered PDFs are inspected during development.

Before a stable release, perform `manual-qa.md`, build/test the Flatpak, finalize public identity/update/signing infrastructure, and complete the outstanding plan requirements. This version must not be marketed as full modern Windows Notepad parity.
