"""Send actual key events; calling QUndoStack directly misses shortcut conflicts."""
import tempfile
import unittest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from folio_notepad.application import Controller
from folio_notepad.drawing import DrawingDialog
from folio_notepad.storage import Note
from folio_notepad import tabletools

app=QApplication.instance() or QApplication([])
CTRL=Qt.KeyboardModifier.ControlModifier


class KeyboardHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=Controller(app,self.temp.name,False)
        self.w=self.c.windows[0]
        self.w.activateWindow()
        self.e=self.w.editor
        self.e.source.setFocus()
        app.processEvents()

    def tearDown(self):
        self.c.closing=True
        for window in self.c.windows: window.close()
        self.c.executor.shutdown(wait=True)
        app.processEvents()
        self.temp.cleanup()

    def key(self,widget,letter,modifiers=CTRL):
        widget.setFocus()
        QTest.keyClick(widget,letter,modifiers)
        app.processEvents()

    def test_plain_ctrl_z_and_ctrl_y_and_menu_state(self):
        QTest.keyClicks(self.e.source,'hello')
        self.assertEqual(self.e.note.source,'hello')
        self.key(self.e.source,Qt.Key.Key_Z)
        self.assertEqual(self.e.note.source,'')
        self.assertFalse(self.w.actions['Undo'].isEnabled())
        self.assertTrue(self.w.actions['Redo'].isEnabled())
        self.key(self.e.source,Qt.Key.Key_Y)
        self.assertEqual(self.e.note.source,'hello')
        self.assertTrue(self.w.actions['Undo'].isEnabled())
        self.assertFalse(self.w.actions['Redo'].isEnabled())
        self.assertEqual(self.w.actions['Redo'].shortcut().toString(),'Ctrl+Y')

    def test_formatted_ctrl_z_and_ctrl_y(self):
        self.e.make_rich()
        self.e.formatted.setFocus()
        QTest.keyClicks(self.e.formatted,'formatted text')
        self.key(self.e.formatted,Qt.Key.Key_Z)
        self.assertEqual(self.e.formatted.toPlainText(),'')
        self.assertTrue(self.e.note.rich)
        self.key(self.e.formatted,Qt.Key.Key_Y)
        self.assertEqual(self.e.formatted.toPlainText(),'formatted text')

    def test_markdown_source_shortcuts(self):
        e=self.w.add_note(Note(kind='md'))
        QTest.keyClicks(e.source,'# Title')
        self.key(e.source,Qt.Key.Key_Z)
        self.assertEqual(e.note.source,'')
        self.key(e.source,Qt.Key.Key_Y)
        self.assertEqual(e.note.source,'# Title')

    def test_ctrl_shift_z_remains_a_redo_alias(self):
        QTest.keyClicks(self.e.source,'alias')
        self.key(self.e.source,Qt.Key.Key_Z)
        self.key(self.e.source,Qt.Key.Key_Z,CTRL|Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.e.note.source,'alias')

    def test_table_layout_shortcuts_use_document_history(self):
        self.e.make_rich(); self.e.insert_table(2,2)
        self.e.resize_column(280)
        self.key(self.e.formatted,Qt.Key.Key_Z)
        table=tabletools.tables(self.e.formatted.document())[0]
        self.assertEqual(tabletools.widths(self.e.formatted.document(),table)[0],160)
        self.key(self.e.formatted,Qt.Key.Key_Y)
        table=tabletools.tables(self.e.formatted.document())[0]
        self.assertEqual(tabletools.widths(self.e.formatted.document(),table)[0],280)

    def test_shortcuts_only_change_the_focused_note(self):
        QTest.keyClicks(self.e.source,'first')
        other=self.w.add_note()
        QTest.keyClicks(other.source,'second')
        self.key(other.source,Qt.Key.Key_Z)
        self.assertEqual(other.note.source,'')
        self.assertEqual(self.e.note.source,'first')
        self.key(other.source,Qt.Key.Key_Y)
        self.assertEqual(other.note.source,'second')
        self.assertEqual(self.e.note.source,'first')

    def test_search_field_keeps_its_own_undo(self):
        QTest.keyClicks(self.e.source,'note stays')
        self.w.show_search()
        QTest.keyClicks(self.w.query,'query')
        self.key(self.w.query,Qt.Key.Key_Z)
        self.assertEqual(self.w.query.text(),'')
        self.assertEqual(self.e.note.source,'note stays')

    def test_preview_uses_same_document_history(self):
        QTest.keyClicks(self.e.source,'preview text')
        self.e.view('formatted')
        self.key(self.e.preview,Qt.Key.Key_Z)
        self.assertEqual(self.e.note.source,'')
        self.key(self.e.active,Qt.Key.Key_Y)
        self.assertEqual(self.e.note.source,'preview text')

    def test_empty_history_shortcuts_do_not_type_letters(self):
        self.key(self.e.source,Qt.Key.Key_Z)
        self.key(self.e.source,Qt.Key.Key_Y)
        self.assertEqual(self.e.note.source,'')
        self.assertEqual(self.e.stack.count(),0)

    def test_drawing_ctrl_z_and_ctrl_y_are_local_to_dialog(self):
        QTest.keyClicks(self.e.source,'note stays')
        dialog=DrawingDialog(parent=self.w)
        dialog.show(); dialog.activateWindow(); app.processEvents()
        try:
            QTest.mousePress(dialog.canvas,Qt.MouseButton.LeftButton,pos=QPoint(40,40))
            QTest.mouseMove(dialog.canvas,QPoint(80,80))
            QTest.mouseRelease(dialog.canvas,Qt.MouseButton.LeftButton,pos=QPoint(80,80))
            self.assertEqual(len(dialog.canvas.strokes),1)
            self.key(dialog.canvas,Qt.Key.Key_Z)
            self.assertEqual(dialog.canvas.strokes,[])
            self.key(dialog.canvas,Qt.Key.Key_Y)
            self.assertEqual(len(dialog.canvas.strokes),1)
            self.assertEqual(self.e.note.source,'note stays')
        finally:
            dialog.close(); dialog.deleteLater(); app.processEvents()
