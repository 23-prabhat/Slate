import copy
import tempfile
from pathlib import Path
import unittest
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QImage,QTextCursor,QTextDocument
from PySide6.QtWidgets import QApplication
from folio_notepad.editor import NoteEditor,SafeDocument,png_bytes
from folio_notepad.storage import Note,pack_note,unpack_note

app=QApplication.instance() or QApplication([])


class EditorTests(unittest.TestCase):
    def editor(self,text=''):
        return NoteEditor(Note(source=text))

    def test_conversion_undo_redo_preserves_text(self):
        e=self.editor('नमस्ते\nhello')
        e.make_rich(); self.assertTrue(e.note.rich)
        e.stack.undo(); self.assertFalse(e.note.rich); self.assertEqual(e.source.toPlainText(),'नमस्ते\nhello')
        e.stack.redo(); self.assertTrue(e.note.rich); self.assertIn('hello',e.plain_text())

    def test_table_edit_and_undo(self):
        e=self.editor(); e.make_rich(); e.insert_table(2,3)
        t=e.formatted.textCursor().currentTable()
        with e.operation('Cell text'): t.cellAt(1,0).firstCursorPosition().insertText('keep me')
        before=e.note.html
        e.table_operation('resize',2,2)
        e.stack.undo()
        self.assertEqual(e.note.html,before)
        self.assertIn('keep me',e.markdown())
        e.stack.redo(); self.assertEqual(e.formatted.document().rootFrame().childFrames()[0].columns(),2)

    def test_literal_pipe_in_table_roundtrips(self):
        e=self.editor(); e.make_rich(); e.insert_table(2,2)
        with e.operation('Cell text'):
            e.formatted.textCursor().currentTable().cellAt(1,0).firstCursorPosition().insertText('a|b \\ c')
        other=NoteEditor(Note(source=e.markdown(),kind='md')); other.make_rich()
        self.assertIn('a|b \\ c',other.plain_text())

    def test_image_and_drawing_survive_package_and_undo(self):
        e=self.editor(); e.make_rich()
        image=QImage(40,20,QImage.Format.Format_RGB32); image.fill(Qt.GlobalColor.red)
        model={'version':1,'strokes':[]}
        key=e.add_image(png_bytes(image),'Red drawing',model)
        self.assertIn('Image:',e.plain_text())
        before=e.note.html
        e.stack.undo(); self.assertNotIn('\ufffc',e.formatted.toPlainText())
        e.stack.redo(); self.assertEqual(e.note.html,before)
        restored=NoteEditor(unpack_note(pack_note(e.note,e.markdown())))
        self.assertIsNotNone(restored.image_position(key))
        self.assertEqual(restored.note.drawings[key],model)

    def test_readonly_source_projection_does_not_dirty(self):
        e=self.editor('hello'); e.make_rich(); e.mark_saved()
        e.view('source'); self.assertTrue(e.source.isReadOnly())
        e.view('formatted'); self.assertFalse(e.note.dirty)

    def test_imported_source_preview_is_unchanged(self):
        source='---\ntitle: exact\n---\n\n[ref]: https://example.com\n'
        e=NoteEditor(Note(source=source,kind='md',imported=True))
        e.view('formatted'); e.view('source')
        self.assertEqual(e.note.source,source); self.assertFalse(e.note.dirty)

    def test_resource_loading_denies_local_and_network(self):
        doc=SafeDocument({})
        for url in ('file:///etc/passwd','https://example.com/image.png'):
            self.assertIsNone(doc.loadResource(QTextDocument.ResourceType.ImageResource,QUrl(url)))

    def test_edit_after_saved_marks_dirty_and_undo_cleans(self):
        e=self.editor('hello'); e.mark_saved(); e.source.insertPlainText('x')
        self.assertTrue(e.note.dirty)
        e.stack.undo(); self.assertFalse(e.note.dirty)

    def test_multiline_table_refuses_lossy_markdown(self):
        e=self.editor(); e.make_rich(); e.insert_table(1,2)
        with e.operation('Multiline'):
            c=e.formatted.textCursor(); c.insertText('one'); c.insertBlock(); c.insertText('two')
        with self.assertRaises(ValueError): e.markdown()
        self.assertIn('one',unpack_note(pack_note(e.note,e.markdown(False))).html)

    def test_nested_table_refused(self):
        e=self.editor(); e.make_rich(); e.insert_table(1,2)
        with self.assertRaises(ValueError): e.insert_table(1,2)

    def test_untouched_unicode_spaces_preserved(self):
        text='a\u00a0b\u2028c'
        e=NoteEditor(Note(source=text))
        e.capture()
        self.assertEqual(e.note.source,text)
        e.source.moveCursor(QTextCursor.MoveOperation.End)
        e.source.insertPlainText('!')
        self.assertIn('\u00a0',e.note.source)

    def test_deleted_assets_are_excluded_from_exports(self):
        import io,zipfile
        e=self.editor(); e.make_rich()
        image=QImage(40,20,QImage.Format.Format_RGB32); image.fill(Qt.GlobalColor.red)
        key=e.add_image(png_bytes(image),'private image')
        position=e.image_position(key)
        with e.operation('Remove image'):
            c=QTextCursor(e.formatted.document()); c.setPosition(position)
            c.setPosition(position+1,QTextCursor.MoveMode.KeepAnchor); c.removeSelectedText()
        self.assertIn(key,e.note.assets)  # available for Undo and recovery
        raw=pack_note(e.note,e.markdown(False))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive: self.assertNotIn(key,archive.namelist())
        e.stack.undo(); self.assertIsNotNone(e.image_position(key))

    def test_tsv_paste_expands_table_and_is_undoable(self):
        e=self.editor(); e.make_rich(); e.insert_table(1,2)
        e.paste_cells('one\ttwo\tthree\nfour\tfive\tsix')
        self.assertIn('six',e.markdown())
        self.assertEqual(e.formatted.document().rootFrame().childFrames()[0].columns(),3)
        e.stack.undo(); self.assertNotIn('six',e.markdown())

    def test_autocorrect_is_separately_undoable(self):
        e=self.editor('teh ')
        e.source.moveCursor(QTextCursor.MoveOperation.End)
        e.autocorrect_last_word()
        self.assertEqual(e.note.source,'the ')
        e.stack.undo(); self.assertEqual(e.note.source,'teh ')

    def test_heading_formats_the_current_paragraph(self):
        from PySide6.QtGui import QFont
        e=self.editor('Title\nBody'); e.make_rich()
        c=e.formatted.textCursor(); c.setPosition(0); e.formatted.setTextCursor(c)
        e.heading(1)
        c.setPosition(1)
        self.assertGreaterEqual(c.charFormat().fontWeight(),QFont.Weight.Bold)
        self.assertEqual(c.blockFormat().headingLevel(),1)
        e.stack.undo(); self.assertEqual(e.formatted.document().firstBlock().blockFormat().headingLevel(),0)
