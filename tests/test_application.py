import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtGui import QTextCursor
from folio_notepad.application import Controller
from folio_notepad.storage import Note,RecoveryStore,read_note

app=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)
        self.c=Controller(app,self.directory/'state',False)
        self.w=self.c.windows[0]
        self.c.idle.stop(); self.c.periodic.stop()

    def tearDown(self):
        self.c.closing=True
        for w in self.c.windows: w.close()
        self.c.executor.shutdown(wait=True)
        app.processEvents()
        self.temp.cleanup()

    def test_save_as_retargets_only_after_success(self):
        self.w.editor.source.setPlainText('hello')
        original=self.w.editor.note.path
        with patch.object(self.w,'target',return_value=str(self.directory/'bad'/'note.txt')),patch.object(self.w,'error'):
            self.assertFalse(self.w.save_current(True))
        self.assertEqual(self.w.editor.note.path,original)
        self.assertTrue(self.w.editor.note.dirty)
        path=self.directory/'saved.txt'
        with patch.object(self.w,'target',return_value=str(path)):
            self.assertTrue(self.w.save_current(True))
        self.assertEqual(path.read_text(),'hello')
        self.assertFalse(self.w.editor.note.dirty)

    def test_original_markdown_bytes_not_rewritten(self):
        raw=b'---\r\ntitle: x\r\n---\n\n[ref]: https://example.com\n'
        path=self.directory/'original.md'; path.write_bytes(raw)
        self.w.open_path(str(path)); self.w.set_view('formatted'); self.w.set_view('source')
        self.assertTrue(self.w.save_current())
        self.assertEqual(path.read_bytes(),raw)

    def test_export_does_not_mark_saved_or_retarget(self):
        e=self.w.editor; e.source.setPlainText('draft')
        self.assertTrue(self.w.export('md',str(self.directory/'copy.md')))
        self.assertTrue(e.note.dirty); self.assertEqual(e.note.path,'')
        self.assertTrue(self.w.export('pdf',str(self.directory/'copy.pdf')))
        self.assertTrue((self.directory/'copy.pdf').read_bytes().startswith(b'%PDF'))

    def test_close_reopen_and_multiple_window_recovery(self):
        self.w.editor.source.setPlainText('first')
        self.c.new_window().editor.source.setPlainText('second')
        self.c.protect_sync()
        notes=self.c.snapshot()
        self.assertEqual({n.source for n in notes},{'first','second'})
        self.assertEqual(len({n.window for n in notes}),2)
        self.w.close_tab(0)
        self.assertIn('first',[n.source for n in self.c.recoverable()])

    def test_external_change_is_not_silently_overwritten(self):
        path=self.directory/'external.txt'; path.write_text('original')
        self.w.open_path(str(path)); self.w.editor.source.insertPlainText('edited')
        path.write_text('someone else')
        # Cancel the conflict dialog; keep the external bytes and editor dirty.
        with patch.object(QMessageBox,'exec',return_value=0):
            self.assertFalse(self.w.save_current())
        self.assertEqual(path.read_text(),'someone else')
        self.assertTrue(self.w.editor.note.dirty)

    def test_find_replace_literal_and_regex(self):
        e=self.w.editor; e.source.setPlainText('cat cat\ncatfish')
        self.w.query.setText('cat'); self.w.words.setChecked(True); self.w.replacement.setText('dog')
        self.w.replace_all(); self.assertEqual(e.note.source,'dog dog\ncatfish')
        e.stack.undo(); self.assertEqual(e.note.source,'cat cat\ncatfish')
        self.w.query.setText('['); self.w.regex.setChecked(True)
        self.w.replace_all(); self.assertTrue(self.w.search_result.text())

    def test_traditional_discard_is_not_restored(self):
        self.c.settings.setValue('keep_drafts',False)
        e=self.w.editor; e.source.setPlainText('discard this'); key=e.note.id
        self.c.protect_sync()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.w.close_tab(0))
        self.assertNotIn(key,[n.id for n in self.c.recoverable()])

    def test_preview_actions_do_not_edit_hidden_source(self):
        e=self.w.editor; e.source.setPlainText('original'); self.w.set_view('formatted')
        self.assertTrue(e.active.isReadOnly())
        self.w.insert_text('hidden edit')
        self.assertEqual(e.note.source,'original')

    def test_moving_tab_retains_undo_history(self):
        e=self.w.editor; e.source.setPlainText('content')
        count=e.stack.count()
        self.w.move_window()
        moved=self.c.windows[-1].editor
        self.assertIs(moved,e)
        self.assertEqual(moved.stack.count(),count)
        moved.stack.undo(); self.assertEqual(moved.note.source,'')

    def test_pdf_contains_rendered_image(self):
        from PySide6.QtGui import QImage
        from PySide6.QtCore import Qt
        from folio_notepad.editor import png_bytes
        e=self.w.editor; e.make_rich()
        image=QImage(80,40,QImage.Format.Format_RGB32); image.fill(Qt.GlobalColor.blue)
        e.add_image(png_bytes(image),'Blue rectangle')
        path=self.directory/'image.pdf'
        self.assertTrue(self.w.export('pdf',str(path)))
        self.assertIn(b'/Subtype /Image',path.read_bytes())



class CrashTests(unittest.TestCase):
    def test_process_kill_restores_committed_unnamed_draft(self):
        with tempfile.TemporaryDirectory() as d:
            script='''
import time
from PySide6.QtWidgets import QApplication
from folio_notepad.application import Controller
app=QApplication([])
c=Controller(app,DATA,False)
c.windows[0].editor.source.setPlainText('crash-safe नमस्ते')
c.protect_sync()
print('PROTECTED',flush=True)
time.sleep(120)
'''.replace('DATA',repr(d))
            process=subprocess.Popen([sys.executable,'-c',script],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'QT_QPA_PLATFORM':'offscreen'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(),'PROTECTED')
                process.kill(); process.wait(timeout=10)
                store=RecoveryStore(d)
                self.assertEqual(store.load()[0].source,'crash-safe नमस्ते')
                store.close()
                result=subprocess.run([str(ROOT/'folio-notepad'),'--data-dir',d,'--smoke-test'],env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
            finally:
                if process.poll() is None: process.kill(); process.wait()
                process.stdout.close(); process.stderr.close()

class CloseCancellationTests(unittest.TestCase):
    setUp=WorkflowTests.setUp
    tearDown=WorkflowTests.tearDown
    # This case intentionally exercises a modal multi-tab close boundary.
    def test_cancel_later_tab_does_not_discard_earlier_draft(self):
        from PySide6.QtGui import QCloseEvent
        self.c.settings.setValue('keep_drafts',False)
        first=self.w.editor; first.source.setPlainText('first stays')
        self.w.add_note().source.setPlainText('second stays')
        self.c.protect_sync()
        event=QCloseEvent()
        with patch.object(QMessageBox,'question',side_effect=[QMessageBox.StandardButton.Discard,QMessageBox.StandardButton.Cancel]):
            self.w.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertFalse(getattr(first.note,'discard_requested',False))
        self.c.protect_sync()
        store=RecoveryStore(self.directory/'state')
        self.assertIn('first stays',[n.source for n in store.load()]); store.close()
