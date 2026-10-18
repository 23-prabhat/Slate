#!/usr/bin/python3
"""Prepare one version's Fedora installer and checksums for GitHub Releases."""
import argparse
import hashlib
from pathlib import Path
import re
import runpy
import shutil
import subprocess


def main():
    root=Path(__file__).resolve().parents[1]
    version=runpy.run_path(str(root/'src/folio_notepad/__init__.py'))['__version__']
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',default='v'+version)
    args=parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or args.tag!='v'+version:
        parser.error(f'Tag must match the source version exactly: v{version}')
    packages=sorted((root/'dist').glob(f'folio-notepad-{version}-*.noarch.rpm'))
    if len(packages)!=1:
        parser.error(f'Expected exactly one RPM for {version}; found {len(packages)}. Run make rpm in a clean checkout.')
    package=packages[0]
    metadata=subprocess.check_output(['rpm','-qp','--qf','%{NAME}\n%{VERSION}\n%{RELEASE}\n%{ARCH}',str(package)],text=True).splitlines()
    if len(metadata)!=4 or metadata[0]!='folio-notepad' or metadata[1]!=version or metadata[3]!='noarch' or not metadata[2].endswith('.fc44'):
        parser.error('RPM metadata does not match this version and Fedora 44 target.')
    subprocess.run(['rpm','-K',str(package)],check=True)
    output=root/'dist/release'/args.tag
    output.mkdir(parents=True,exist_ok=True)
    # Refuse stale or unrelated files rather than accidentally uploading them.
    allowed={package.name,'SHA256SUMS','RELEASE_NOTES.md'}
    unexpected=[p.name for p in output.iterdir() if p.name not in allowed]
    if unexpected:
        parser.error(f'Unexpected files in {output}: {unexpected}. Use a clean release output directory.')
    shutil.copy2(package,output/package.name)
    checksum=hashlib.sha256(package.read_bytes()).hexdigest()
    (output/'SHA256SUMS').write_text(f'{checksum}  {package.name}\n')
    (output/'RELEASE_NOTES.md').write_text(f'''# Folio Notepad {version}

Development release for **Fedora KDE 44**. The installer includes the application,
launcher, icons and file-type metadata. It requires Python 3.11+ and PySide6 6.8+;
DNF installs missing runtime dependencies from your configured Fedora repositories.

## Install or upgrade

Download `{package.name}` from this release's Assets section. Open it with your
local package installer, or run this once from the download directory:

```bash
sudo dnf install ./{package.name}
```

Search for **Folio Notepad** in the application menu and pin it if desired.
Kernel updates do not require rebuilding the app or running repair commands.
Close an already running copy and reopen it after upgrading.

## Verify the download

Download `SHA256SUMS` beside the RPM, then run:

```bash
sha256sum -c SHA256SUMS
```

This development RPM is unsigned. GitHub Releases provide downloads; they do not
configure an automatic application-update repository. This asset targets Fedora 44;
it is not an installer for Ubuntu, Debian or Arch. Other desktop sessions still
need direct desktop QA. Flatpak remains an unverified recipe, not a release asset.

Save visual notes as `.folio` to preserve tables, images and editable drawings.
See the repository's `CHANGELOG.md` and `docs/status.md` for changes and limitations.
''')
    print(f'Prepared {output.relative_to(root)}: {package.name}, SHA256SUMS, RELEASE_NOTES.md')


if __name__=='__main__':
    main()
