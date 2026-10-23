PREFIX ?= /usr/local
DESTDIR ?=
PYTHON ?= python3
APPDIR = $(PREFIX)/share/folio-notepad

.PHONY: test run install rpm srpm clean
run:
	./folio-notepad

test:
	QT_QPA_PLATFORM=offscreen PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

install:
	install -d $(DESTDIR)$(APPDIR)/src $(DESTDIR)$(APPDIR)/resources/icons $(DESTDIR)$(APPDIR)/resources/ui $(DESTDIR)$(PREFIX)/bin
	cp -R src/folio_notepad $(DESTDIR)$(APPDIR)/src/
	find $(DESTDIR)$(APPDIR)/src -type d -name __pycache__ -exec rm -rf {} +
	install -m755 folio-notepad $(DESTDIR)$(APPDIR)/folio-notepad
	ln -sf ../share/folio-notepad/folio-notepad $(DESTDIR)$(PREFIX)/bin/folio-notepad
	install -m644 resources/icons/org.local.FolioNotepad.svg $(DESTDIR)$(APPDIR)/resources/icons/
	install -m644 resources/icons/folio-notepad-v2.png $(DESTDIR)$(APPDIR)/resources/icons/
	install -m644 resources/ui/*.svg $(DESTDIR)$(APPDIR)/resources/ui/
	install -d $(DESTDIR)$(PREFIX)/share/icons/hicolor
	cp -R resources/icons/hicolor/. $(DESTDIR)$(PREFIX)/share/icons/hicolor/
	install -Dm644 packaging/desktop/org.local.FolioNotepad.desktop $(DESTDIR)$(PREFIX)/share/applications/org.local.FolioNotepad.desktop
	install -Dm644 packaging/appstream/org.local.FolioNotepad.metainfo.xml $(DESTDIR)$(PREFIX)/share/metainfo/org.local.FolioNotepad.metainfo.xml
	install -Dm644 packaging/mime/org.local.FolioNotepad.xml $(DESTDIR)$(PREFIX)/share/mime/packages/org.local.FolioNotepad.xml

rpm:
	$(PYTHON) scripts/build_rpm.py

srpm:
	$(PYTHON) scripts/build_rpm.py --srpm

clean:
	rm -rf build
