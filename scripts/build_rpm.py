#!/usr/bin/python3
"""Build a local Fedora RPM entirely inside the workspace."""
from pathlib import Path
import shutil
import runpy
import subprocess
import tarfile

root=Path(__file__).resolve().parents[1]
version=runpy.run_path(str(root/'src/folio_notepad/__init__.py'))['__version__']
top=root/'build/rpm'
for name in ('BUILD','BUILDROOT','RPMS','SOURCES','SPECS','SRPMS','tmp'):
    (top/name).mkdir(parents=True,exist_ok=True)
source=top/f'SOURCES/folio-notepad-{version}.tar.gz'
with tarfile.open(source,'w:gz') as archive:
    for item in ('src','resources','packaging','docs','README.md','LICENSE','Makefile','folio-notepad'):
        archive.add(root/item,arcname=f'folio-notepad-{version}/'+item,
                    filter=lambda info: None if '__pycache__' in info.name else info)
shutil.copy(root/'packaging/rpm/folio-notepad.spec',top/'SPECS/')
subprocess.run(['rpmbuild','-bb','--define',f'_topdir {top}',
                '--define',f'_tmppath {top}/tmp','--define','_build_id_links none',str(top/'SPECS/folio-notepad.spec')],check=True,cwd=root)
artifacts=root/'dist'; artifacts.mkdir(exist_ok=True)
for rpm in (top/'RPMS').rglob('*.rpm'):
    shutil.copy2(rpm,artifacts/rpm.name)
    print('Created:',artifacts/rpm.name)
