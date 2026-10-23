# Packaging and release

## Publish installers on GitHub

The repository is `https://github.com/23-prabhat/Slate`. The application and installer are currently named **Folio Notepad**. A desktop app does not need a web server deployment: publish its installer as a GitHub Release. Keep `dist/` and RPMs ignored in Git; the workflow uploads generated installers as release assets.

The `Publish Fedora installer` workflow in `.github/workflows/release.yml` runs on `v*` tag pushes. It validates the tag against `src/folio_notepad/__init__.py`, runs the editor tests, validates desktop metadata, builds the Fedora 44 RPM and prepares a SHA-256 checksum. A separate publish job downloads and verifies the tested files, uploads them to a draft GitHub release and publishes it as a development pre-release. It uses GitHub's automatic workflow token; no personal access token or cloud server is needed.

For the first release, commit and push the workflow changes, then create the version tag:

```bash
git add .github/workflows scripts/prepare_release.py docs/packaging.md README.md
git commit -m "Add automated Fedora installer releases"
git push origin main
git tag -a v0.4.2 -m "Folio Notepad 0.4.2"
git push origin v0.4.2
```

Watch `https://github.com/23-prabhat/Slate/actions`. After the **Publish Fedora installer** workflow succeeds, open `https://github.com/23-prabhat/Slate/releases` and expand **Assets**. Download `folio-notepad-0.4.2-1.fc44.noarch.rpm`; the automatically generated Source code ZIP is not the installer. Release access follows the repository's visibility/access settings.

Install or upgrade once from the download directory:

```bash
sudo dnf install ./folio-notepad-0.4.2-1.fc44.noarch.rpm
```

Then launch **Folio Notepad** from the desktop application menu. This installs the launcher and icon; no terminal command is needed for normal launches or after kernel updates. KDE Discover/local package installation can also be used where available. The current asset is a Fedora 44 development RPM; it does not claim Ubuntu/Debian/Arch or verified Flatpak support.

Before future releases, update the source version, RPM spec version and AppStream release entry, then create a new matching tag such as `v0.4.3`. Also update the changelog. The workflow rejects mismatched versions. Do not move/reuse a published tag to distribute changed binaries. A rerun fails if a release with that tag already exists; inspect a failed draft before deciding whether to retry it or use a corrected new version.

To prepare release files locally without publishing:

```bash
make rpm
python3 scripts/prepare_release.py --tag v0.4.2
```

The versioned directory `dist/release/v0.4.2/` contains exactly the RPM, `SHA256SUMS` and `RELEASE_NOTES.md`. Upload only these prepared files. To verify a download, keep the RPM and checksum file together and run `sha256sum -c SHA256SUMS`.

GitHub Actions builds have not been executed from this development environment. Confirm the first remote run completes before sharing its download link. If a run fails, its step log is available under Actions. The workflow grants release-write permission only to the publish job; repository/organization policy must allow that permission. GitHub Releases provide downloads, not automatic application updates through DNF; a maintained signing/update repository or a verified Flatpak channel is separate work.

References: [GitHub CLI in workflows](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-github-cli), [release creation and asset upload](https://cli.github.com/manual/gh_release_create).

## Publish a DNF repository with Copr

Copr builds source RPMs and hosts a DNF repository. It is a separate service from GitHub Releases. This repository now supports `make srpm`; creating a Copr account/project and uploading the package still need to be done by the maintainer.

1. Register at [Fedora Accounts](https://accounts.fedoraproject.org/), complete account verification, and sign into [Copr](https://copr.fedorainfracloud.org/) with that account. Your personal Copr owner name is your Fedora account username, which can differ from your GitHub username. If you already have an account, sign in and check your profile/account menu.
2. Create a project named `folio-notepad`. Use the GitHub repository as its homepage, describe the application, and enable the `fedora-44-x86_64` build target. Start with this supported target; other distributions/releases need their own dependency and runtime checks.
3. Build the source package locally:

   ```bash
   cd ~/code/notepad
   make srpm
   ```

   On Fedora 44, the output is `dist/folio-notepad-0.4.2-1.fc44.src.rpm`. If build tools are missing, install them first with `sudo dnf install rpm-build make python3`. The `.src.rpm` contains source and the build recipe; the existing `.noarch.rpm` is the end-user installer.
4. In the Copr project, start a new build using **Direct Upload** and select that `.src.rpm`. Wait for a successful build for Fedora 44. If it fails, inspect the build log before sharing installation commands. Copr rebuilds the installer and publishes it in the project's repository.

After a successful build, users enable the repository once and install the app:

```bash
sudo dnf copr enable YOUR_FEDORA_USERNAME/folio-notepad
sudo dnf install folio-notepad
```

Replace `YOUR_FEDORA_USERNAME` with the actual project owner. If DNF does not recognize `copr`, install `dnf5-plugins` on Fedora 44. Users can launch **Folio Notepad** from their application menu. They do not clone the GitHub repository or build the app.

For updates, increase the package Version or Release appropriately, rebuild the source RPM, and upload it again. Once a newer package is published, users receive it through normal DNF updates. Merely pushing changes to GitHub does not trigger Copr builds in this direct-upload setup. A Git webhook/SCM build pipeline is optional future work.

See [Copr's source upload and account documentation](https://docs.copr.fedorainfracloud.org/user_documentation.html) and [Fedora's Copr repository guide](https://developer.fedoraproject.org/deployment/copr/copr-cli.html). Copr is a community repository; this does not add the package to Fedora's default repositories.

## Fedora RPM

Run `make rpm` with Fedora's rpm-build and make installed. This creates a noarch package in `dist/`, declares `python3-pyside6 >= 6.8`, and recommends system spelling support. It contains the app, icon, desktop entry, custom `.folio` MIME type and AppStream metadata. It does not change the default editor or install kernel hooks. Install once using KDE's local package installer where supported, or `dnf install ./dist/<filename>.rpm`.

The package is unsigned. It has no automatic update repository; new application releases require a new package until signing/repository hosting is configured. Runtime dependencies receive Fedora's ordinary updates. Kernel upgrades do not require recompilation of this application.

`make install PREFIX=/tmp/folio-stage` exercises the installed layout without modifying the host. `scripts/install-user.sh` is an alternative that installs a relocatable copy under the user's prefix and writes an absolute, escaped launcher target. It leaves existing user notes alone.

## Flatpak recipe (unverified build)

The development recipe uses `org.kde.Platform` / `org.kde.Sdk` / `io.qt.PySide.BaseApp` branch 6.11. PySide BaseApp explicitly documents this supported branch; the host's installed KDE runtime alone does not contain the required Python Qt bindings. See [BaseApp documentation](https://github.com/flathub/io.qt.PySide.BaseApp).

On a development system with builder, SDK and BaseApp installed:

```bash
flatpak-builder --user --install --force-clean build/flatpak packaging/flatpak/org.local.FolioNotepad.json
flatpak run org.local.FolioNotepad
```

Do not call this a verified distribution until these steps succeed in a clean environment. Review all metadata, runtime/baseapp compatibility and cleanup results. The default finish permissions allow graphical desktop/printing integration, with no home-directory or network grant. Portal-backed selected files are intended; sibling attachment folders and atomic replacement through document portals still need validation. Prefer portable `.folio` files until that is resolved. Optional AI has no networking inside this default offline sandbox.

Package optional spelling backends/dictionaries separately when their sources/checksums are available. The app degrades to editing without spelling if they are missing. Do not copy the host's ABI-dependent Python bindings into a different Flatpak Python runtime.

Before a stable store release, replace the local namespace with one the maintainer owns, add a real homepage/screenshots, sign releases, and configure a maintained repository or seek Flathub inclusion. Standalone bundles do not establish an update channel by themselves.
