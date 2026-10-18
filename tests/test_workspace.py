"""Exercise workspace layout changes around real document and history state."""
import copy
import tempfile
import unittest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
from folio_notepad.application import Controller

app=QApplication.instance() or QApplication([])


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=Controller(app,self.temp.name,False)
        self.w=self.c.windows[0]
        self.w.resize(1400,900)
        self.w.library_action.setChecked(True)
        self.w.properties_action.setChecked(True)
        app.processEvents()

    def tearDown(self):
        self.c.closing=True
        for window in self.c.windows: window.close()
        self.c.executor.shutdown(wait=True)
        app.processEvents()
        self.temp.cleanup()

    def table_note(self):
        e=self.w.editor
        e.make_rich(); e.insert_table(2,2)
        self.w.refresh(); app.processEvents()
        return e

    def test_table_controls_follow_active_tab_and_history(self):
        e=self.table_note()
        self.assertIs(self.w.inspector.bound,e)
        self.assertTrue(e.table_controls.isVisible())
        other=self.w.add_note()
        self.assertIs(self.w.inspector.bound,other)
        self.assertIs(e.table_controls.parentWidget(),e)
        self.w.tabs.setCurrentWidget(e)
        self.assertIs(self.w.inspector.bound,e)
        e.table_controls.width_input.setValue(270)
        e.table_controls.width_input.editingFinished.emit()
        self.assertEqual(e.table_controls.width_input.value(),270)
        e.stack.undo()
        self.assertEqual(e.table_controls.width_input.value(),160)
        self.assertEqual(other.note.source,'')

    def test_compact_layout_keeps_controls_and_document_unchanged(self):
        e=self.table_note(); e.mark_saved()
        before=copy.deepcopy(e.note.snapshot())
        self.w.resize(800,720); app.processEvents()
        self.assertEqual(self.w.width(),800)
        self.assertFalse(self.w.library.isVisible())
        self.assertFalse(self.w.inspector.isVisible())
        self.assertIs(e.table_controls.parentWidget(),e)
        self.assertTrue(e.table_controls.isVisible())
        self.w.resize(1400,900); app.processEvents()
        self.assertTrue(self.w.library.isVisible())
        self.assertTrue(self.w.inspector.isVisible())
        self.assertIs(self.w.inspector.bound,e)
        self.assertEqual(e.note.snapshot(),before)
        self.assertFalse(e.note.dirty)

    def test_properties_toggle_restores_inline_table_controls(self):
        e=self.table_note()
        self.w.properties_action.trigger()
        app.processEvents()
        self.assertFalse(self.w.inspector.isVisible())
        self.assertIs(e.table_controls.parentWidget(),e)
        self.assertTrue(e.table_controls.isVisible())
        self.w.properties_action.trigger()
        app.processEvents()
        self.assertTrue(self.w.inspector.isVisible())
        self.assertIs(self.w.inspector.bound,e)

    def test_notes_list_tracks_selection_reordering_and_new_note(self):
        first=self.w.editor
        first.source.setPlainText('First')
        self.w.rail_buttons['New'].click()
        second=self.w.editor
        self.w.rail_buttons['Notes'].click()
        self.assertEqual(self.w.library.note_list.count(),2)
        self.w.library.note_list.setCurrentRow(0)
        self.assertIs(self.w.editor,first)
        self.w.tabs.tabBar().moveTab(0,1)
        self.assertEqual([self.w.library.note_list.item(i).text() for i in range(2)],
                         [self.w.tabs.tabText(i) for i in range(2)])
        self.w.library.note_list.setCurrentRow(0)
        self.assertIs(self.w.editor,second)

    def test_moving_note_releases_old_properties_host(self):
        e=self.table_note()
        self.w.move_window(); app.processEvents()
        other=self.c.windows[-1]
        other.resize(1400,900); app.processEvents(); other.refresh()
        self.assertIs(other.editor,e)
        self.assertIs(other.inspector.bound,e)
        self.assertIsNot(self.w.inspector.bound,e)
        self.assertTrue(e.table_controls.isVisible())
        e.resize_column(230); e.stack.undo()
        self.assertEqual(e.table_controls.width_input.value(),160)

    def test_closing_final_tab_releases_host_before_editor_deletion(self):
        e=self.table_note()
        self.assertTrue(self.w.close_tab(0,create=False))
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertIsNone(self.w.inspector.bound)
        self.w.add_note(); app.processEvents()
        self.assertIs(self.w.inspector.bound,self.w.editor)

    def test_panel_preferences_survive_automatic_collapse(self):
        self.w.resize(800,720); app.processEvents()
        self.assertTrue(self.c.settings.value('properties_panel',False,bool))
        self.assertTrue(self.c.settings.value('library_panel',False,bool))
        self.w.resize(1400,900); app.processEvents()
        self.w.properties_action.setChecked(False)
        other=self.c.new_window()
        other.resize(1400,900); app.processEvents()
        self.assertFalse(other.properties_action.isChecked())
        self.assertFalse(other.inspector.isVisible())

    def test_zoom_and_view_controls_track_selected_note(self):
        e=self.w.editor
        e.source.setPlainText('One')
        self.w.zoom_control.slider.setValue(150)
        self.assertEqual(e.note.zoom,150)
        other=self.w.add_note()
        self.assertEqual(self.w.zoom_control.slider.value(),100)
        self.w.set_view('formatted')
        self.assertEqual(self.w.mode.currentText(),'Preview')
        self.w.tabs.setCurrentWidget(e)
        self.assertEqual(self.w.zoom_control.slider.value(),150)
        self.assertEqual(self.w.mode.currentText(),'Edit')
        self.assertEqual(e.note.source,'One')

    def test_narrow_window_can_explicitly_open_insert_panel(self):
        self.w.resize(800,720); app.processEvents()
        self.w.rail_buttons['Insert'].click(); app.processEvents()
        self.assertTrue(self.w.library.isVisible())
        self.w.rail_buttons['Insert'].click(); app.processEvents()
        self.assertFalse(self.w.library.isVisible())
