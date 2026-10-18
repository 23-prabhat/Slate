#!/bin/sh
# One-time, relocatable user installation. Does not change default file associations.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
install_prefix=${1:-"$HOME/.local"}
python3 -c 'from PySide6 import QtWidgets, QtPrintSupport' || {
    echo 'Install Fedora package python3-pyside6 first.' >&2; exit 1;
}
make -C "$project_dir" install PREFIX="$install_prefix"
python3 - "$install_prefix" <<'PY'
from pathlib import Path
import sys
prefix=Path(sys.argv[1]).resolve()
p=prefix/'share/applications/org.local.FolioNotepad.desktop'
s=p.read_text()
executable=str(prefix/'bin/folio-notepad').replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
s=s.replace('Exec=folio-notepad %U',f'Exec="{executable}" %U')
p.write_text(s)
PY
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$install_prefix/share/applications"; fi
if command -v update-mime-database >/dev/null 2>&1; then update-mime-database "$install_prefix/share/mime"; fi
printf '%s\n' 'Installed. Search for Folio Notepad in the application menu. Kernel updates need no repair commands.'
