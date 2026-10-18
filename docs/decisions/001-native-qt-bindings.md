# ADR 001: native Qt through PySide6

Status: accepted for the working development implementation, 18 October 2026.

The plan proposed C++20, Qt Widgets, CMake, libarchive, Sonnet and optional Purpose. The available Fedora sandbox has the matching Qt 6.11.2 Python bindings and optional PyEnchant, but no CMake/Ninja, Qt development headers, or package-server DNS access. Installing host development packages is outside this environment's writable permissions.

Implement the same native Qt Widgets application through PySide6. Use Python's standard-library SQLite and ZIP APIs, Qt's QSaveFile for commit-checked atomic saves, and PyEnchant's system spelling backend. No browser, web server, or runtime package download is introduced. A coherent application undo stack protects structured operations and conversion boundaries.

A local file activation inbox protected by QLockFile provides single-instance operation without requiring Unix socket access, which this sandbox rejects. Filesystem writes are atomic and the inbox is bounded. Recovery writes run on one worker with its own database connection; final close flushes synchronously.

Shipping artifacts use Fedora's maintained Python/PySide packages. Provide an RPM now and a KDE/PySide BaseApp Flatpak recipe. The RPM is not a replacement for the plan's still-unverified Flatpak delivery and update-channel work.

The formatted editor remains the authoritative rich representation, with exact rich HTML in `.folio`. Imported Markdown is edited as preserved source plus preview; enabling visual editing creates an explicit new copy. A formatted note's source view stays read-only to avoid false lossless conversion claims. A future source-aware editor can improve this without changing the file service.

References: [Qt for Python](https://doc.qt.io/qtforpython-6/), [PySide BaseApp supported branches](https://github.com/flathub/io.qt.PySide.BaseApp), [PyEnchant](https://pyenchant.github.io/pyenchant/tutorial.html).
