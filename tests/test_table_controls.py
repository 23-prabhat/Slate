"""User workflows for blank tables, layout, contextual actions and themes."""
import copy
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QPoint,Qt
from PySide6.QtGui import QPalette,QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from folio_notepad.application import Controller
from folio_notepad.editor import NoteEditor
from folio_notepad.storage import Note,pack_note,unpack_note
from folio_notepad import tabletools

app=QApplication.instance() or QApplication([])


class TableTests(unittest.TestCase):
    def setUp(self):
        self.e=NoteEditor(Note())
        self.e.resize(1120,740); self.e.show(); self.e.make_rich()
        self.e.insert_table(3,3)
        self.e.table_requested.connect(self.e.table_operation)
        app.processEvents()

    def tearDown(self):
        self.e.close(); self.e.deleteLater(); app.processEvents()

    @property
    def table(self):
        return self.e.formatted.document().rootFrame().childFrames()[0]

    def cell_text(self,row,col):
        return tabletools.cell_content(self.table.cellAt(row,col))[0].toPlainText()

    def set_text(self,row,col,text):
        with self.e.operation('Cell text'):
            self.table.cellAt(row,col).firstCursorPosition().insertText(text)

    def test_requested_size_has_no_extra_or_label_row(self):
        self.assertEqual((self.table.rows(),self.table.columns()),(3,3))
        self.assertEqual(self.table.format().headerRowCount(),0)
        self.assertNotIn('Column 1',self.e.markdown())
        self.assertTrue(all(not self.cell_text(r,c) for r in range(3) for c in range(3)))

    def test_first_row_can_be_inserted_above_and_deleted(self):
        self.set_text(0,0,'first')
        self.e.table_operation('row_above')
        self.assertEqual(self.table.rows(),4)
        self.assertEqual(self.cell_text(1,0),'first')
        self.e.formatted.setTextCursor(self.table.cellAt(0,0).firstCursorPosition())
        self.e.table_operation('del_row')
        self.assertEqual(self.table.rows(),3)
        self.assertEqual(self.cell_text(0,0),'first')

    def test_numeric_dimensions_roundtrip_with_undo(self):
        e=self.e
        e.table_controls.width_input.setValue(260)
        e.table_controls.width_input.editingFinished.emit()
        e.table_controls.height_input.setValue(100)
        e.table_controls.height_input.editingFinished.emit()
        self.assertAlmostEqual(tabletools.widths(e.formatted.document(),self.table)[0],260)
        _,ys=tabletools.grid(e.formatted.document(),self.table)
        self.assertAlmostEqual(ys[1]-ys[0],100,delta=2)
        result=NoteEditor(unpack_note(pack_note(e.note,e.markdown(False))))
        restored=tabletools.tables(result.formatted.document())[0]
        self.assertAlmostEqual(tabletools.widths(result.formatted.document(),restored)[0],260)
        _,ys=tabletools.grid(result.formatted.document(),restored)
        self.assertAlmostEqual(ys[1]-ys[0],100,delta=2)
        e.stack.undo()
        _,ys=tabletools.grid(e.formatted.document(),self.table)
        self.assertLess(ys[1]-ys[0],60)
        e.stack.undo()
        self.assertEqual(tabletools.widths(e.formatted.document(),self.table),[160]*3)
        result.close(); result.deleteLater()

    def test_edge_buttons_and_context_controls(self):
        self.assertTrue(self.e.table_controls.isVisible())
        self.assertTrue(self.e.formatted.row_add_button.isVisible())
        self.e.formatted.row_add_button.click()
        self.assertEqual(self.table.rows(),4)
        self.e.formatted.column_add_button.click()
        self.assertEqual(self.table.columns(),4)
        self.e.formatted.moveCursor(QTextCursor.MoveOperation.Start)
        self.assertFalse(self.e.table_controls.isVisible())
        self.assertFalse(self.e.formatted.row_add_button.isVisible())

    def test_mouse_border_resize_is_one_undoable_change(self):
        edit=self.e.formatted
        xs,ys=edit.table_bounds(self.table)
        start=QPoint(round(xs[1]),round((ys[0]+ys[1])/2))
        QTest.mousePress(edit.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
        QTest.mouseMove(edit.viewport(),start+QPoint(60,0))
        QTest.mouseRelease(edit.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start+QPoint(60,0))
        self.assertAlmostEqual(tabletools.widths(edit.document(),self.table)[0],220,delta=2)
        self.e.stack.undo()
        self.assertAlmostEqual(tabletools.widths(edit.document(),self.table)[0],160,delta=2)
        xs,ys=edit.table_bounds(self.table)
        start=QPoint(round((xs[0]+xs[1])/2),round(ys[1]))
        QTest.mousePress(edit.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
        QTest.mouseMove(edit.viewport(),start+QPoint(0,40))
        QTest.mouseRelease(edit.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start+QPoint(0,40))
        _,changed=tabletools.grid(edit.document(),self.table)
        self.assertAlmostEqual(changed[1]-changed[0],ys[1]-ys[0]+40,delta=2)

    def test_duplicate_and_move_keep_contents_and_sizes(self):
        self.set_text(0,0,'A'); self.set_text(1,0,'B')
        self.e.resize_row(90,0)
        self.e.table_operation('duplicate_row')
        self.assertEqual(self.cell_text(1,0),'A')
        self.e.table_operation('move_row_down')
        self.assertEqual(self.cell_text(1,0),'B')
        self.assertEqual(self.cell_text(2,0),'A')
        self.e.resize_column(250,0)
        self.e.table_operation('duplicate_col')
        self.assertEqual(tabletools.widths(self.e.formatted.document(),self.table)[:2],[250,250])
        self.assertEqual(self.cell_text(0,1),self.cell_text(0,0))
        self.e.table_operation('move_col_right')
        self.assertEqual(tabletools.widths(self.e.formatted.document(),self.table)[:3],[250,160,250])

    def test_equal_sizes_and_fit_row(self):
        self.e.resize_column(280,0)
        self.e.table_operation('equal_columns')
        values=tabletools.widths(self.e.formatted.document(),self.table)
        self.assertLess(max(values)-min(values),1)
        self.e.resize_row(100,0)
        self.e.table_operation('equal_rows')
        _,ys=tabletools.grid(self.e.formatted.document(),self.table)
        values=[ys[i+1]-ys[i] for i in range(self.table.rows())]
        self.assertLess(max(values)-min(values),2)
        self.e.table_operation('fit_row')
        _,ys=tabletools.grid(self.e.formatted.document(),self.table)
        self.assertLess(ys[1]-ys[0],60)

    def test_last_row_or_column_can_be_deleted_safely(self):
        self.e.table_operation('resize',1,1)
        self.e.table_operation('del_row')
        self.assertFalse(tabletools.tables(self.e.formatted.document()))
        self.e.stack.undo()
        self.e.formatted.setTextCursor(self.table.cellAt(0,0).firstCursorPosition())
        self.e.table_operation('del_col')
        self.assertFalse(tabletools.tables(self.e.formatted.document()))


class ThemeTests(unittest.TestCase):
    def test_theme_controls_persist_and_sync_without_modifying_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            controller=Controller(app,directory,False)
            first=controller.windows[0]
            first.editor.source.setPlainText('Existing note')
            first.editor.make_rich(); first.editor.mark_saved()
            before=copy.deepcopy(first.editor.note.snapshot())
            second=controller.new_window()
            try:
                first.theme_actions['Dark'].trigger()
                app.processEvents()
                self.assertEqual(controller.settings.value('theme'),'Dark')
                self.assertEqual(second.theme_button.text(),'Theme: Dark')
                self.assertTrue(second.theme_actions['Dark'].isChecked())
                self.assertLess(app.palette().color(QPalette.ColorRole.Base).lightness(),80)
                self.assertFalse(first.editor.note.dirty)
                self.assertEqual(first.editor.note.snapshot(),before)
                first.theme_actions['Light'].trigger()
                self.assertGreater(app.palette().color(QPalette.ColorRole.Base).lightness(),200)
                controller.settings.sync()
                self.assertIn('Light',Path(directory,'settings.ini').read_text())
            finally:
                controller.closing=True
                for window in controller.windows: window.close()
                controller.executor.shutdown(wait=True)
                app.processEvents()

class TableExportTests(unittest.TestCase):
    def test_geometry_save_defaults_to_portable_and_markdown_loss_is_explicit(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QFileDialog,QMessageBox
        with tempfile.TemporaryDirectory() as directory:
            controller=Controller(app,directory,False)
            window=controller.windows[0]
            try:
                window.editor.make_rich(); window.editor.insert_table(2,2)
                with patch.object(QFileDialog,'getSaveFileName',return_value=('','')) as picker:
                    window.target()
                    self.assertTrue(picker.call_args.args[2].endswith('.folio'))
                    self.assertEqual(picker.call_args.args[4],'Portable note (*.folio)')
                target=Path(directory)/'copy.md'
                with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):
                    self.assertFalse(window.export('md',str(target)))
                self.assertFalse(target.exists())
                bundle=Path(directory)/'share.zip'
                self.assertTrue(window.export('zip',str(bundle)))
                import zipfile
                with zipfile.ZipFile(bundle) as archive:
                    self.assertIn('editable.folio',archive.namelist())
            finally:
                controller.closing=True
                for w in controller.windows: w.close()
                controller.executor.shutdown(wait=True); app.processEvents()

    @unittest.skipUnless(__import__('shutil').which('pdftoppm'),'Poppler is needed for PDF pixel verification')
    def test_dark_editor_prints_readable_text_on_white_paper(self):
        import subprocess
        from PySide6.QtGui import QImage
        with tempfile.TemporaryDirectory() as directory:
            controller=Controller(app,directory,False)
            window=controller.windows[0]
            try:
                controller.theme('Dark')
                window.editor.source.setPlainText('Readable dark theme text')
                window.editor.make_rich()
                # Exercise reopening a saved representation in dark mode as well.
                restored=unpack_note(pack_note(window.editor.note,window.editor.markdown(False)))
                window.add_note(restored)
                pdf=Path(directory)/'print.pdf'
                self.assertTrue(window.export('pdf',str(pdf)))
                rendered=Path(directory)/'rendered'
                subprocess.run(['pdftoppm','-scale-to','1000','-png','-singlefile',str(pdf),str(rendered)],check=True,capture_output=True)
                image=QImage(str(rendered)+'.png')
                self.assertFalse(image.isNull())
                # Ignore header/footer: only body text in the upper-left paper area counts.
                dark=0
                for y in range(round(image.height()*.05),round(image.height()*.18)):
                    for x in range(round(image.width()*.03),round(image.width()*.70)):
                        dark+=image.pixelColor(x,y).lightness()<100
                self.assertGreater(dark,20,'Body text must remain dark enough to read on paper.')
            finally:
                controller.closing=True
                for w in controller.windows: w.close()
                controller.executor.shutdown(wait=True); app.processEvents()
