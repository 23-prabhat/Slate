Name:           folio-notepad
Version:        0.4.2
Release:        1%{?dist}
Summary:        Native notes editor with tables, images and drawings
License:        GPL-3.0-or-later
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.11
Requires:       python3-pyside6 >= 6.8
Recommends:     python3-enchant
Recommends:     hunspell-en-US

%description
A native Qt editor for plain text, Markdown and portable notes, featuring
local draft recovery, editable tables, images, drawings and PDF export.
No account is required for normal editing.

%prep
%setup -q

%build
# Python source uses the system's supported Qt bindings.

%install
make install PREFIX=%{_prefix} DESTDIR=%{buildroot}

%files
%license LICENSE
%doc README.md docs/status.md
%{_bindir}/folio-notepad
%{_datadir}/folio-notepad/
%{_datadir}/applications/org.local.FolioNotepad.desktop
%{_datadir}/icons/hicolor/*/apps/org.local.FolioNotepad.png
%{_datadir}/metainfo/org.local.FolioNotepad.metainfo.xml
%{_datadir}/mime/packages/org.local.FolioNotepad.xml

%changelog
* Sun Oct 18 2026 Folio Notepad contributors 0.4.2-1
- New lavender note-and-pencil application icon and 11 desktop icon sizes

* Sun Oct 18 2026 Folio Notepad contributors 0.4.1-1
- Fix dropdown arrow overlap with bounded chevrons and dedicated arrow space
- Bundle theme-aware chevrons in source and installed layouts

* Sun Oct 18 2026 Folio Notepad contributors 0.4.0-1
- Compact single toolbar, softer surfaces and panels on demand
- Draw in the note with shared undo/redo and automatic stroke persistence
- Preserve the cursor when enabling formatting

* Sun Oct 18 2026 Folio Notepad contributors 0.3.0-1
- New design workspace with insert library, notes navigation and table properties
- Responsive panels, native vector tools, zoom controls and drawing tool palette

* Sun Oct 18 2026 Folio Notepad contributors 0.2.1-1
- Fix Ctrl+Z undo and Ctrl+Y redo in note editors and drawing dialogs
- Refresh Undo and Redo availability after history changes

* Sun Oct 18 2026 Folio Notepad contributors 0.2.0-1
- Blank tables, direct row and column sizing, contextual table controls and themes

* Sun Oct 18 2026 Folio Notepad contributors 0.1.0-1
- Initial native Qt development release
