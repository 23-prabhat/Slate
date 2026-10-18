#!/usr/bin/python3
"""Export the generated master to standard Linux desktop icon sizes."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

root=Path(__file__).resolve().parents[1]
master=QImage(str(root/'resources/icons/folio-notepad-v2.png'))
if master.isNull() or not master.hasAlphaChannel():
    raise SystemExit('Expected a readable master PNG with transparency.')
for size in (16,22,24,32,48,64,96,128,256,512,1024):
    directory=root/'resources/icons/hicolor'/f'{size}x{size}'/'apps'
    directory.mkdir(parents=True,exist_ok=True)
    output=master.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    if not output.save(str(directory/'org.local.FolioNotepad.png')):
        raise SystemExit(f'Could not export {size}px icon.')
print('Exported 11 transparent PNG sizes, 16–1024 px.')
