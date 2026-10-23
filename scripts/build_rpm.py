#!/usr/bin/python3
"""Build a local Fedora binary or source RPM inside the workspace."""
import argparse
from pathlib import Path
import shutil
import runpy
import subprocess
import tarfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--srpm',action='store_true',help='Build a source RPM for upload to Copr')
args=parser.parse_args()
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
subprocess.run(['rpmbuild','-bs' if args.srpm else '-bb','--define',f'_topdir {top}',
                '--define',f'_tmppath {top}/tmp','--define','_build_id_links none',str(top/'SPECS/folio-notepad.spec')],check=True,cwd=root)
artifacts=root/'dist'; artifacts.mkdir(exist_ok=True)
package_id=subprocess.check_output(['rpmspec','-q','--srpm','--qf','%{NAME}-%{VERSION}-%{RELEASE}',
                                   str(top/'SPECS/folio-notepad.spec')],text=True).strip()
if args.srpm:
    packages=[top/'SRPMS'/f'{package_id}.src.rpm']
else:
    packages=[top/'RPMS'/'noarch'/f'{package_id}.noarch.rpm']
for rpm in packages:
    shutil.copy2(rpm,artifacts/rpm.name)
    print('Created:',artifacts/rpm.name)
