# Folio application icon

The new asset is a lavender tile with a warm ivory folded note and a purple pencil. It matches the app's soft purple interface and remains recognizable at launcher/taskbar sizes. The previous SVG remains in the source tree as a fallback; it was not overwritten.

- Master: `resources/icons/folio-notepad-v2.png` — 1254 × 1254, RGBA PNG with a transparent outer margin.
- Desktop exports: `resources/icons/hicolor/{size}x{size}/apps/org.local.FolioNotepad.png` — 16, 22, 24, 32, 48, 64, 96, 128, 256, 512 and 1024 pixels.
- Preview on light/dark surfaces: `dist/folio-icon-preview.png`.
- Regenerate size exports with `python3 scripts/export_icons.py`. Exports scale the existing artwork; they do not generate new artwork.
- The application loads the master PNG. Installation copies the size exports into the hicolor desktop icon theme under the existing application ID.

The artwork was generated with the built-in image-generation tool and `transparent_background=true`. The generated original was copied into the project; no API key or fallback CLI was used. The preview and size exports use Qt image rendering. The icon was inspected on light/dark backgrounds and at 24, 32, 48 and 64 pixels.

## Final generation prompt

> Use case: logo-brand. Asset type: a finished Linux desktop application icon for Folio Notepad, a minimal notes app with text, tables and inline drawing. Generate ONE square icon, centered, with a genuinely transparent background outside the icon. Design: a soft rounded-square lavender-purple tile, with one large warm ivory note sheet inside, a beautifully folded upper-right corner, and two bold short violet writing strokes. Integrate a simple small purple pencil nib at the lower-right of the sheet to suggest drawing; everything stays inside the tile silhouette. Palette: muted plum #8170aa, pale lavender #c3b2e6, warm ivory #fffdf8, deeper purple #594576. Style: refined, minimal, crisp vector-like silhouettes with a very subtle tonal gradient and restrained dimensional depth; soft modern desktop-app aesthetic, not glossy plastic. Readable and recognizable at 24px and 32px, strong uncluttered geometry, generous internal spacing. Composition: icon occupies about 88-90 percent of the square, consistent transparent safety margin on all sides. No words, no letters, no numbers, no labels, no watermark, no surrounding scene, no mockup, no alternate icons, no checkerboard drawn into the image. This should be a production icon asset, not a presentation board.
