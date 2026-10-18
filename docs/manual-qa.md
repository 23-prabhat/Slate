# Desktop release QA

Automated tests use Qt offscreen. These manual checks remain required on real KDE hardware:

- Install the RPM through Discover/available local package installer on clean Fedora KDE 44. Search, launch and pin the app; open TXT/MD/FOLIO via Dolphin Open With. Do not change defaults unless chosen.
- Restart and update the kernel normally. Launch from the pinned icon without running any repair/build command. Named files, unnamed drafts, images and editable strokes must remain intact.
- Check Wayland, 100/150/200% scaling, dark/light/system themes, small windows, large fonts, keyboard focus, menus and screen-reader labels.
- Switch Notes/Insert, reorder/close/move tabs, hide Properties during a table edit, then resize between narrow and wide windows. Table controls must follow the note and remain usable. Test panel and zoom controls with keyboard navigation.
- Compose Hindi text using an IME; test combining characters, emoji and RTL. Verify saved encoding and source output.
- Type continuously, wait for Draft protected, force-kill/relaunch, and compare recovery content. Also test a controlled VM power interruption; do not claim last-keystroke power-loss durability.
- Test read-only/full disks, removed drives, failed close flushes and external file edits. Disk bytes and editor content must not be silently overwritten.
- Create a table, insert/delete/resize rows and columns, paste TSV, type literal pipes, and undo/redo. Multiline cells must be preserved in FOLIO and rejected for lossy Markdown export.
- Insert images, delete original source photos, resize/replace/remove in the editor, move the saved FOLIO elsewhere and reopen. Removed images must not appear in a new share bundle.
- Draw directly inside a note with mouse and real stylus. Test every tool, eraser, clear/undo, Text/Escape, Save during drawing, scrolling/resizing, tab/window movement and reopening saved strokes. Verify the overlay matches the document image at 100/150/200% scaling.
- Check print preview and a physical printer, custom headers/footers and multipage PDF output including images/tables; inspect clipping, text direction and page numbering.
- Verify ZIP sharing in an actual target app, unavailable-target fallback, file lifetime and explicit user sending.
- Test a configured local AI model, cancellation, server failure, 120s timeout and document-revision protection. Rejected text must leave the note unchanged.
- Build the Flatpak on an authorized development system. Verify portal selected files/folders, attachment siblings, saving/reopening, revoked access and offline permissions.
- Upgrade an installed application/runtime. Test recovery with the previous schema fixture. Choose and test the real public update/signing channel before release.
