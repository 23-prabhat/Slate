"""Real pointer/keyboard checks for drawing inside a note and the compact shell."""
import copy
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QToolButton
from folio_notepad.application import Controller
from folio_notepad.storage import RecoveryStore, referenced_assets, unpack_note

app=QApplication.instance() or QApplication([])
CTRL=Qt.KeyboardModifier.ControlModifier


class InlineDrawingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=Controller(app,self.temp.name,False)
        self.w=self.c.windows[0]
        self.w.resize(1400,900); self.w.activateWindow()
        app.processEvents()
        self.e=self.w.editor

    def tearDown(self):
        self.c.closing=True
        for window in self.c.windows: window.close()
        self.c.executor.shutdown(wait=True)
        app.processEvents()
        self.temp.cleanup()

    def start(self):
        self.w.actions['Drawing…'].trigger()
        app.processEvents()
        self.assertIsNotNone(self.e.ink)
        return self.e.ink

    def stroke(self,ink,offset=0):
        QTest.mousePress(ink.canvas,Qt.MouseButton.LeftButton,pos=QPoint(40,50+offset))
        QTest.mouseMove(ink.canvas,QPoint(140,90+offset))
        QTest.mouseRelease(ink.canvas,Qt.MouseButton.LeftButton,pos=QPoint(140,90+offset))
        app.processEvents()

    def key(self,widget,key,mods=CTRL):
        widget.setFocus(); QTest.keyClick(widget,key,mods); app.processEvents()

    def test_draw_is_in_the_note_without_a_dialog(self):
        ink=self.start()
        self.assertIs(ink.canvas.parentWidget(),self.e.formatted.viewport())
        self.assertFalse(any(isinstance(w,QDialog) and w.isVisible() for w in app.topLevelWidgets()))
        self.assertTrue(self.w.drawing_tools.isVisible())
        self.stroke(ink)
        self.assertEqual(len(self.e.note.drawings[ink.key]['strokes']),1)
        self.assertIn(ink.key,referenced_assets(self.e.note,self.e.markdown(False)))

    def test_strokes_undo_redo_with_ctrl_z_and_ctrl_y(self):
        ink=self.start(); self.stroke(ink); self.stroke(ink,70)
        self.key(ink.canvas,Qt.Key.Key_Z)
        self.assertEqual(len(ink.canvas.strokes),1)
        self.assertTrue(self.w.actions['Redo'].isEnabled())
        self.key(ink.canvas,Qt.Key.Key_Y)
        self.assertEqual(len(ink.canvas.strokes),2)
        self.assertEqual(self.e.note.drawings[ink.key]['strokes'],ink.canvas.strokes)

    def test_undo_drawing_insertion_exits_ink_safely(self):
        ink=self.start(); self.stroke(ink)
        self.key(ink.canvas,Qt.Key.Key_Z)
        self.key(ink.canvas,Qt.Key.Key_Z)
        self.assertIsNone(self.e.ink)
        self.assertFalse(referenced_assets(self.e.note,self.e.markdown(False)))
        self.key(self.e.formatted,Qt.Key.Key_Y)
        self.assertEqual(len(referenced_assets(self.e.note,self.e.markdown(False))),1)

    def test_escape_returns_to_text_without_losing_strokes(self):
        ink=self.start(); self.stroke(ink)
        key=ink.key
        self.key(ink.canvas,Qt.Key.Key_Escape,Qt.KeyboardModifier.NoModifier)
        self.assertIsNone(self.e.ink)
        self.assertTrue(self.w.normal_tools.isVisible())
        self.assertEqual(len(self.e.note.drawings[key]['strokes']),1)
        self.assertIn(key,referenced_assets(self.e.note,self.e.markdown(False)))

    def test_editing_existing_drawing_updates_in_place(self):
        self.e.source.setPlainText('Keep this text.\n')
        self.e.source.moveCursor(QTextCursor.MoveOperation.End)
        ink=self.start(); self.stroke(ink); key=ink.key
        self.w.drawing_tools.finish()
        count=self.e.formatted.document().characterCount()
        self.w.edit_image(key); app.processEvents()
        ink=self.e.ink
        self.assertEqual(len(ink.canvas.strokes),1)
        self.stroke(ink,60)
        self.assertEqual(self.e.formatted.document().characterCount(),count)
        self.assertEqual(len(referenced_assets(self.e.note,self.e.markdown(False))),1)
        self.assertIn('Keep this text.',self.e.formatted.toPlainText())

    def test_save_and_recovery_capture_strokes_before_exiting_draw_mode(self):
        ink=self.start(); self.stroke(ink)
        path=Path(self.temp.name)/'inline.folio'
        self.assertTrue(self.w.export('folio',str(path)))
        restored=unpack_note(path.read_bytes())
        self.assertEqual(len(restored.drawings[ink.key]['strokes']),1)
        self.c.protect_sync()
        store=RecoveryStore(self.temp.name)
        try: draft=store.load()[0]
        finally: store.close()
        self.assertEqual(len(draft.drawings[ink.key]['strokes']),1)

    def test_clear_is_undoable(self):
        ink=self.start(); self.stroke(ink)
        self.w.drawing_tools.clear()
        self.assertEqual(ink.canvas.strokes,[])
        self.key(ink.canvas,Qt.Key.Key_Z)
        self.assertEqual(len(ink.canvas.strokes),1)

    def test_toolbar_selects_shapes_and_eraser(self):
        ink=self.start()
        self.w.drawing_tools.choose('rectangle'); self.stroke(ink)
        self.assertEqual(ink.canvas.strokes[0]['tool'],'rectangle')
        self.w.drawing_tools.tool_buttons['eraser'].click()
        self.assertEqual(ink.canvas.tool,'eraser')
        self.w.drawing_tools.width.setValue(8)
        self.assertEqual(ink.canvas.stroke_width,8)

    def test_overlay_follows_scrolling_and_resize(self):
        ink=self.start(); self.stroke(ink)
        before=copy.deepcopy(self.e.note.snapshot())
        self.w.resize(900,650); app.processEvents()
        pos=self.e.image_position(ink.key)
        cursor=QTextCursor(self.e.formatted.document()); cursor.setPosition(pos)
        self.assertEqual(ink.canvas.pos(),self.e.formatted.cursorRect(cursor).topLeft())
        self.e.formatted.verticalScrollBar().setValue(30); app.processEvents()
        self.assertEqual(ink.canvas.pos(),self.e.formatted.cursorRect(cursor).topLeft())
        self.assertEqual(self.e.note.snapshot(),before)

    def test_switching_tabs_preserves_the_correct_session(self):
        ink=self.start(); self.stroke(ink)
        other=self.w.add_note()
        self.assertFalse(self.w.drawing_tools_action.isVisible())
        self.assertIsNone(other.ink)
        self.w.tabs.setCurrentWidget(self.e); app.processEvents()
        self.assertTrue(self.w.drawing_tools_action.isVisible())
        self.assertIs(self.e.ink,ink)
        self.assertEqual(len(ink.canvas.strokes),1)

    def test_view_switch_finishes_inline_mode(self):
        ink=self.start(); self.stroke(ink)
        self.w.set_view('source')
        self.assertIsNone(self.e.ink)
        self.assertEqual(len(referenced_assets(self.e.note,self.e.markdown(False))),1)

    def test_compact_defaults_keep_all_commands_and_keyboard_find(self):
        self.assertFalse(self.w.library.isVisible())
        self.assertFalse(self.w.inspector.isVisible())
        self.assertLess(self.w.formatting_toolbar.height(),56)
        self.assertLess(self.w.tabs.tabBar().height(),40)
        self.assertTrue(self.w.menuBar().isHidden())
        self.assertEqual(len(self.w.app_menu_button.menu().actions()),7)
        self.key(self.e.source,Qt.Key.Key_F)
        self.assertTrue(self.w.search.isVisible())
        self.assertFalse(self.w.replace_row.isVisible())
        self.key(self.w.query,Qt.Key.Key_H)
        self.assertTrue(self.w.replace_row.isVisible())

    def test_theme_change_does_not_change_saved_ink(self):
        ink=self.start(); self.stroke(ink); self.e.mark_saved()
        before=copy.deepcopy(self.e.note.snapshot())
        self.c.theme('Dark'); app.processEvents(); self.c.theme('Light'); app.processEvents()
        self.assertEqual(self.e.note.snapshot(),before)
        self.assertFalse(self.e.note.dirty)
        self.assertEqual(len(ink.canvas.strokes),1)

    def test_moving_a_drawing_tab_keeps_its_history(self):
        ink=self.start(); self.stroke(ink)
        self.w.move_window(); app.processEvents()
        other=self.c.windows[-1]
        self.assertIs(other.editor,self.e)
        self.assertTrue(other.drawing_tools_action.isVisible())
        self.key(ink.canvas,Qt.Key.Key_Z)
        self.assertEqual(ink.canvas.strokes,[])
        self.key(ink.canvas,Qt.Key.Key_Y)
        self.assertEqual(len(ink.canvas.strokes),1)

    def test_scrolled_document_undo_keeps_the_overlay(self):
        self.e.source.setPlainText('Paragraph\n'*45)
        self.e.source.moveCursor(QTextCursor.MoveOperation.End)
        ink=self.start(); self.stroke(ink)
        self.assertGreater(self.e.formatted.verticalScrollBar().value(),0)
        self.key(ink.canvas,Qt.Key.Key_Z)
        self.assertIs(self.e.ink,ink)
        self.assertEqual(ink.canvas.strokes,[])
        self.key(ink.canvas,Qt.Key.Key_Y)
        self.assertEqual(len(ink.canvas.strokes),1)

    def test_small_table_controls_use_one_compact_row(self):
        self.w.resize(680,600)
        self.e.make_rich(); self.e.insert_table(2,2); app.processEvents()
        self.assertEqual(self.w.width(),680)
        self.assertLess(self.e.table_controls.height(),48)
