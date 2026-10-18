"""Application lifecycle, transactional background recovery and local activation."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
from PySide6.QtCore import (QLockFile, QObject, QSettings, QStandardPaths, QTimer,
                            QUrl, Signal)
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox
from . import APP_ID, __version__
from .storage import Note, RecoveryStore, atomic_write


class RecoveryBridge(QObject):
    finished = Signal(object, object)


class Controller(QObject):
    def __init__(self, app, data_dir, restore=True):
        super().__init__()
        self.app, self.data_dir = app, Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.settings = QSettings(str(self.data_dir/'settings.ini'), QSettings.Format.IniFormat)
        if self.settings.value('workspace_layout_version',0,int)<2:
            self.settings.setValue('library_panel',False)
            self.settings.setValue('properties_panel',False)
            self.settings.setValue('workspace_layout_version',2)
        self.windows = []
        self.protected = {}
        self.counter = 0
        self.closing = False
        self.future = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='folio-recovery')
        self.bridge = RecoveryBridge()
        self.bridge.finished.connect(self.protected_done)
        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.setInterval(1800)
        self.idle.timeout.connect(self.protect_async)
        self.periodic = QTimer(self)
        self.periodic.setInterval(10000)
        self.periodic.timeout.connect(self.protect_async)
        self.periodic.start()
        root = Path(__file__).resolve().parents[2]
        icon_path = root/'resources/icons/folio-notepad-v2.png'
        if not icon_path.exists(): icon_path=root/'resources/icons/org.local.FolioNotepad.svg'
        self.icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon.fromTheme('accessories-text-editor')
        self.system_palette = app.palette()
        self.theme(self.settings.value('theme','System'))
        store = RecoveryStore(self.data_dir)
        try:
            notes = store.load() if restore and self.settings.value('keep_drafts',True,bool) else []
        finally: store.close()
        groups = {}
        for note in notes:
            groups.setdefault(note.window,[]).append(note)
            self.protected[note.id] = note.revision
        if groups:
            for key, collection in groups.items(): self.new_window(collection, key)
        else: self.new_window()

    def next_untitled(self):
        self.counter += 1
        return self.counter

    def new_window(self, notes=(), key=None, empty=False):
        from .window import Window
        window = Window(self, notes, key, empty)
        self.windows.append(window)
        window.show()
        return window

    def editors(self):
        return [window.tabs.widget(i) for window in self.windows for i in range(window.tabs.count())]

    def find_path(self, path):
        for window in self.windows:
            for i in range(window.tabs.count()):
                e = window.tabs.widget(i)
                if not e.note.path: continue
                try:
                    same = os.path.samefile(e.note.path,path)
                except OSError: same = e.note.path == path
                if same: return window,e
        return None

    def recent(self, path):
        if not self.settings.value('remember_recents',True,bool): return
        old = self.settings.value('recents',[],list)
        self.settings.setValue('recents',[path]+[x for x in old if x != path][:19])

    def schedule(self):
        self.idle.start()

    def snapshot(self):
        result = []
        for e in self.editors():
            e.remember_position()
            result.append(Note.from_dict(e.note.to_dict()))
        return result

    def write_snapshot(self, notes, closed=(), discard=()):
        store = RecoveryStore(self.data_dir)
        try: store.protect(notes,closed=closed,discard=discard)
        finally: store.close()

    def protect_async(self):
        if self.closing or (self.future and not self.future.done()): return
        notes = self.snapshot()
        revisions = {n.id:n.revision for n in notes}
        self.future = self.executor.submit(self.write_snapshot,notes)
        def done(future):
            error = future.exception()
            self.bridge.finished.emit(revisions, str(error) if error else '')
        self.future.add_done_callback(done)

    def protected_done(self, revisions, error):
        if error:
            for w in self.windows: w.message('Draft protection failed: '+error+' Use Save As or retry before closing.')
        else:
            self.protected.update(revisions)
            for w in self.windows: w.refresh()

    def protect_sync(self, closed=(), discard_pending=False, discard_ids=()):
        self.idle.stop()
        if self.future:
            try: self.future.result()
            except Exception: pass
        notes = self.snapshot()
        discarded=set(discard_ids)
        if discard_pending:
            discarded.update(e.note.id for e in self.editors() if getattr(e.note,'discard_requested',False))
        notes=[n for n in notes if n.id not in discarded]
        self.write_snapshot(notes,[n for n in closed if n.id not in discarded],list(discarded))
        self.protected.update({n.id:n.revision for n in notes})

    def recoverable(self):
        if self.future: self.future.result()
        store=RecoveryStore(self.data_dir)
        try: return store.load(False)
        finally: store.close()

    def prepare_close(self, editor, parent):
        if self.settings.value('keep_drafts',True,bool): return True
        if not editor.note.dirty: return True
        parent.tabs.setCurrentWidget(editor)
        answer = QMessageBox.question(parent,'Unsaved changes',f'Save changes to {editor.note.title}?',
                                      QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel: return False
        if answer == QMessageBox.StandardButton.Save: return parent.save_current()
        editor.note.discard_requested=True
        return True

    def quit(self):
        for w in self.windows:
            for index in range(w.tabs.count()):
                if not self.prepare_close(w.tabs.widget(index),w):
                    for e in self.editors(): e.note.discard_requested=False
                    return
        try:
            self.protect_sync(discard_pending=True)
            self.closing=True
            self.executor.shutdown(wait=True)
            self.app.quit()
        except Exception as exc:
            if self.windows: self.windows[0].error(exc)

    def theme(self, name):
        if name not in ('System','Light','Dark'): name='System'
        self.settings.setValue('theme',name)
        if name == 'System':
            self.app.setPalette(self.system_palette)
            for window in self.windows: window.update_theme_controls(name)
            for editor in self.editors(): editor.refresh_contrast()
            return
        palette = QPalette(self.system_palette)
        roles = QPalette.ColorRole
        if name == 'Dark':
            values = {roles.Window:'#292b32',roles.WindowText:'#e8ebf0',roles.Base:'#25272e',
                      roles.AlternateBase:'#2c323e',roles.Text:'#e8ebf0',roles.Button:'#303744',
                      roles.ButtonText:'#e8ebf0',roles.Highlight:'#477bbd',roles.HighlightedText:'#ffffff',
                      roles.ToolTipBase:'#303744',roles.ToolTipText:'#e8ebf0'}
            values[roles.PlaceholderText]='#989baa'
        else:
            values = {roles.Window:'#f3f5f8',roles.WindowText:'#253247',roles.Base:'#ffffff',
                      roles.AlternateBase:'#f3f5f8',roles.Text:'#253247',roles.Button:'#f4f6f9',
                      roles.ButtonText:'#253247',roles.Highlight:'#447ed2',roles.HighlightedText:'#ffffff'}
            values[roles.PlaceholderText]='#858493'
        for role,color in values.items(): palette.setColor(role,QColor(color))
        self.app.setPalette(palette)
        for window in self.windows: window.update_theme_controls(name)
        for editor in self.editors(): editor.refresh_contrast()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Folio Notepad — native text and document editor')
    parser.add_argument('files',nargs='*')
    parser.add_argument('--data-dir',help='Separate private state directory (useful for testing)')
    parser.add_argument('--no-restore',action='store_true')
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('--smoke-test',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    app=QApplication([sys.argv[0]])
    app.setApplicationName('Folio Notepad')
    app.setOrganizationName('FolioNotepad')
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    directory = Path(args.data_dir) if args.data_dir else Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=QLockFile(str(directory/'instance.lock'))
    socket_name='folio-'+hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:24]
    inbox=directory/'activation'
    inbox.mkdir(exist_ok=True,mode=0o700)
    if not lock.tryLock(100):
        from uuid import uuid4
        files=[QUrl(p).toLocalFile() if p.startswith('file:') else str(Path(p).resolve()) for p in args.files]
        atomic_write(inbox/(str(uuid4())+'.json'),json.dumps(files).encode())
        return 0
    try: controller=Controller(app,directory,restore=not args.no_restore)
    except Exception as exc:
        QMessageBox.critical(None,'Could not open draft storage',str(exc))
        return 1
    def incoming():
        for entry in list(inbox.glob('*.json'))[:20]:
            try:
                if entry.stat().st_size>1024*1024: raise ValueError('Activation too large')
                files=json.loads(entry.read_text())
                if not isinstance(files,list) or len(files)>1000 or any(not isinstance(p,str) for p in files): raise ValueError('Invalid activation')
                window=controller.windows[0] if controller.windows else controller.new_window()
                for p in files: window.open_path(p)
                window.show(); window.raise_(); window.activateWindow()
            except (OSError,ValueError,TypeError): pass
            finally: entry.unlink(missing_ok=True)
    activation_timer=QTimer()
    activation_timer.setInterval(500)
    activation_timer.timeout.connect(incoming)
    activation_timer.start()
    for path in args.files:
        controller.windows[0].open_path(QUrl(path).toLocalFile() if path.startswith('file:') else path)
    controller.schedule()
    if args.smoke_test: QTimer.singleShot(300,controller.quit)
    try:
        result=app.exec()
    finally:
        controller.idle.stop(); controller.periodic.stop()
        controller.executor.shutdown(wait=True)
        activation_timer.stop(); lock.unlock()
    return result
