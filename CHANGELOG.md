# Changes

## 0.4.2 — Application icon

- New lavender folded-note-and-pencil icon with transparent margins, matching the softer UI.
- Export 11 PNG sizes from 16 to 1024 pixels, install them into the desktop hicolor theme, and use the new master for the application window icon.
- Keep the previous SVG as a source fallback and document the generation prompt and reproducible size export.

## 0.4.1 — Dropdown arrows

- Give combo boxes and menu buttons dedicated arrow space and bounded, theme-aware SVG chevrons. Remove the native arrow-button frames that could overlap the rounded controls.
- Keep full paragraph/view labels visible, including Preview. Preserve split table-button behaviour and tiny table-edge controls.
- Bundle the chevrons in installed packages. Verify label/arrow geometry, mouse menu opening and small-window layout at 100%, 150% and 200% scaling in both themes.

## 0.4.0 — Minimal workspace and drawing in the note

- Replace the large title header and separate formatting row with one compact toolbar. Show the note title once in its tab; keep all menus and shortcuts under Folio.
- Open Notes, Insert and Properties on demand. Reset old always-open panel defaults once, then retain user choices. Use a compact navigation rail, smaller page margins, full-width writing space and softer colours, rounded controls and custom tab close buttons.
- Find uses one small row; reveal Replace only when requested. Keep all search options available in its menu. Table controls also fit in one row.
- Draw directly over an inline drawing in the current document. Pen, highlighter, eraser, shapes, colour and width controls replace formatting tools while drawing. Text / Escape returns to typing.
- Commit each completed stroke to the note immediately, using versioned drawing images for Ctrl+Z / Ctrl+Y, Save, draft recovery and portable reopen. Overlay follows scrolling, layout, tab and window changes.
- Preserve the caret when enabling formatting so inserts stay at the intended position. Fix dark-mode placeholder contrast.
- Sixteen regression tests cover inline drawing and compact controls, including actual pointer/key events, save/recovery, shape selection, scroll/resize, moving tabs, theme changes and shared history.

## 0.3.0 — Design workspace

- Separate document header with file actions and draft status, compact text formatting toolbar, and a padded writing surface.
- Left navigation rail, open-notes list and insert library with table picker, images, drawings, links and text styles.
- Contextual Properties panel hosts the active note's existing table controls. Controls return above the document when the panel is hidden.
- Responsive and user-toggleable side panels; keep preferences when temporarily collapsing for smaller windows.
- Bundled vector icons, purple accents, theme-aware surfaces and per-note zoom controls.
- Drawing palette with pen, highlighter, eraser, shapes and quick ink colours.
- Nine workspace regression tests cover selection, reordering, tab movement, panel resizing, note integrity and history.

Layout references: [draw.io panels](https://www.drawio.com/docs/manual/editor/panels/) and [Canva editor tools](https://www.canva.com/help/tools-tab/).

## 0.2.1 — Undo and redo shortcuts

- Route Ctrl+Z and Ctrl+Y to the document history in plain text, Markdown, formatted notes and previews. Ctrl+Shift+Z remains an alternative for Redo.
- Update menu availability after Undo/Redo completes so Redo becomes available immediately after Undo.
- Give the drawing dialog its own Ctrl+Z / Ctrl+Y shortcuts without changing the parent note.
- Add ten regression tests using actual keyboard events, covering text modes, tables, focused tabs, search fields and drawings.

## 0.2.0 — Tables and themes

- Theme button in the top-right corner and View → Theme choices for System, Light and Dark. Changes apply immediately, persist across restarts and synchronize across windows.
- New tables contain exactly the requested number of blank rows/columns. No extra header and no generated column names. Existing table contents are not automatically removed; the first row can now be deleted normally.
- Contextual table toolbar, edge insertion buttons, row/column menus, numeric column widths and minimum row heights, and border dragging. Row heights expand for longer content rather than clipping text.
- Duplicate and move rows/columns, make sizes equal, and fit cells to their content. Keep the editing cursor with the affected cell.
- Save/reopen and Undo preserve dimensions through the portable format. Prefer `.folio` for visual tables, warn before losing layout in Markdown, and include an editable portable note in table share bundles.
- Keep PDF/print text readable on white paper when the editor is in dark mode.
- Fix default text pinned to the previous theme, improve contrast on light-filled legacy cells without modifying document data, restore contextual Undo/Redo, preserve column sizing during TSV expansion, and close a rejected future-version recovery database cleanly.

Interaction references: Canva's [table insertion and row/column editing](https://www.canva.com/help/adding-and-deleting-tables/) and [table sizing controls](https://www.canva.com/help/formatting-tables/). This is a native document-editor adaptation, not a pixel-for-pixel copy or complete Canva table feature parity.

The app remains native Qt through PySide6. The original C++ plan was adapted because the initial environment lacked CMake/Ninja and Qt headers and could not download packages. Rust is viable for a native application, but was not the selected Qt implementation stack; changing language would not by itself address table interactions. See [the stack decision](docs/decisions/001-native-qt-bindings.md).
