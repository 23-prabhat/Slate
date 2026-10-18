import codecs
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from folio_notepad.storage import (Note, RecoveryStore, TextFormat, atomic_write,
    digest, pack_note, read_note, unpack_note, validate_drawing)


class TextTests(unittest.TestCase):
    def test_exact_roundtrip(self):
        for raw in (b'',b'no final newline',b'a\r\nb\nc\rd',b'\xef\xbb\xbfx\r\n',
                    codecs.BOM_UTF16_LE+'नमस्ते🙂\r\n'.encode('utf-16-le'),
                    codecs.BOM_UTF16_BE+'مرحبا'.encode('utf-16-be')):
            with self.subTest(raw=raw):
                text,fmt=TextFormat.decode(raw)
                self.assertEqual(fmt.encode(text),raw)

    def test_mixed_endings_survive_edit(self):
        text,fmt=TextFormat.decode(b'a\r\nb\nc\rd')
        self.assertEqual(fmt.encode(text+'!'),b'a\r\nb\nc\rd!')

    def test_bad_input_rejected(self):
        for raw in (b'\xff',b'a\x00b'):
            with self.assertRaises((ValueError,UnicodeError)): TextFormat.decode(raw)

    def test_atomic_save_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.txt'; path.write_bytes(b'original')
            link=Path(d)/'link.txt'; link.symlink_to(path)
            atomic_write(link,b'new')
            self.assertTrue(link.is_symlink())
            self.assertEqual(path.read_bytes(),b'new')
            self.assertEqual(read_note(str(path)).source,'new')

    def test_hardlink_refused_without_damage(self):
        with tempfile.TemporaryDirectory() as d:
            import os
            path=Path(d)/'file'; path.write_bytes(b'original')
            os.link(path,Path(d)/'alias')
            with self.assertRaises(OSError): atomic_write(path,b'changed')
            self.assertEqual(path.read_bytes(),b'original')

    def test_commit_failure_preserves_original(self):
        from PySide6.QtCore import QSaveFile
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'file'; path.write_bytes(b'original')
            with patch.object(QSaveFile,'commit',return_value=False):
                with self.assertRaises(OSError): atomic_write(path,b'changed')
            self.assertEqual(path.read_bytes(),b'original')


class PackageTests(unittest.TestCase):
    def test_roundtrip_all_content(self):
        drawing={'version':1,'strokes':[{'tool':'pen','color':'#123456','width':3,'points':[[0.1,0.2],[0.8,0.9]]}]}
        note=Note(source='# Hello',html='<b>Hello</b><img src="assets/x.png">',rich=True,assets={'assets/x.png':b'image'},drawings={'assets/x.png':drawing})
        result=unpack_note(pack_note(note,note.source))
        self.assertEqual(result.source,note.source)
        self.assertEqual(result.html,note.html)
        self.assertEqual(result.drawings,note.drawings)
        self.assertEqual(result.assets,note.assets)

    def rewrite(self,raw,name,value):
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(out,'w') as target:
            for entry in original.namelist(): target.writestr(entry,value if entry==name else original.read(entry))
        return out.getvalue()

    def test_checksum_failure(self):
        raw=pack_note(Note(source='safe'),'safe')
        with self.assertRaises(ValueError): unpack_note(self.rewrite(raw,'content.md',b'corrupt'))

    def test_future_version(self):
        raw=pack_note(Note(),'')
        with zipfile.ZipFile(io.BytesIO(raw)) as z: manifest=json.loads(z.read('manifest.json'))
        manifest['schemaVersion']=999
        with self.assertRaises(ValueError): unpack_note(self.rewrite(raw,'manifest.json',json.dumps(manifest).encode()))

    def test_path_traversal_and_duplicates(self):
        for name in ('../escape','/absolute','assets/../escape','assets\\escape'):
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z: z.writestr(name,b'unsafe')
            with self.assertRaises(ValueError): unpack_note(out.getvalue())

    def test_bad_drawing_points(self):
        with self.assertRaises(ValueError): validate_drawing({'version':1,'strokes':[{'tool':'pen','color':'#123456','width':3,'points':[[float('nan'),0]]}]})


class RecoveryTests(unittest.TestCase):
    def test_drafts_assets_and_closed_note(self):
        with tempfile.TemporaryDirectory() as d:
            store=RecoveryStore(d)
            n=Note(source='unsaved',dirty=True,assets={'assets/x.png':b'owned'})
            store.protect([n]); store.close()
            store=RecoveryStore(d)
            self.assertEqual(store.load()[0].assets,n.assets)
            store.protect([],closed=[n])
            self.assertEqual(store.load(),[])
            self.assertEqual(store.load(False)[0].source,'unsaved')
            store.discard(n.id)
            self.assertEqual(store.load(False),[])
            store.close()

    def test_failed_transaction_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            store=RecoveryStore(d); n=Note(source='protected'); store.protect([n])
            store.db.execute("CREATE TRIGGER fail_write BEFORE INSERT ON drafts BEGIN SELECT RAISE(ABORT,'disk full'); END")
            store.db.commit(); n.source='later'
            with self.assertRaises(sqlite3.Error): store.protect([n])
            self.assertEqual(store.load()[0].source,'protected')
            store.close()

    def test_revision_retention_and_future_schema(self):
        with tempfile.TemporaryDirectory() as d:
            store=RecoveryStore(d); n=Note()
            for i in range(15): n.revision=i; n.source=str(i); store.protect([n])
            self.assertEqual(store.db.execute('SELECT count(*) FROM revisions').fetchone()[0],10)
            store.db.execute('PRAGMA user_version=99'); store.db.commit(); store.close()
            with self.assertRaises(ValueError): RecoveryStore(d)
