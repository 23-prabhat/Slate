"""File formats and transactional draft storage. No widgets or network access."""
from __future__ import annotations
import base64
import codecs
import difflib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import time
import zipfile
from dataclasses import dataclass, field
from uuid import uuid4
from PySide6.QtCore import QIODevice, QSaveFile

MAX_FILE = 64 * 1024 * 1024
MAX_PACKAGE = 500 * 1024 * 1024
MAX_ENTRIES = 5000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(path: str) -> str | None:
    try:
        with open(path, 'rb') as f:
            return digest(f.read(MAX_PACKAGE + 1))
    except FileNotFoundError:
        return None


def atomic_write(path: str | Path, data: bytes) -> None:
    """Resolve symbolic links deliberately; refuse to break hard-link identity."""
    target = Path(path).resolve()
    if target.exists() and target.stat().st_nlink > 1:
        raise OSError('This file has multiple hard links. Use Save As to keep them intact.')
    f = QSaveFile(str(target))
    f.setDirectWriteFallback(False)
    if not f.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(f.errorString())
    if f.write(data) != len(data):
        f.cancelWriting()
        raise OSError(f.errorString())
    if not f.commit():
        raise OSError(f.errorString())


@dataclass
class TextFormat:
    encoding: str = 'utf-8'
    bom: bool = False
    original: str = ''  # original decoded text, including individual line separators
    eol: str = '\n'
    normalize: bool = False

    @classmethod
    def decode(cls, raw: bytes) -> tuple[str, 'TextFormat']:
        encoding, bom, body = 'utf-8', False, raw
        for marker, enc in ((codecs.BOM_UTF8, 'utf-8'),
                            (codecs.BOM_UTF16_LE, 'utf-16-le'),
                            (codecs.BOM_UTF16_BE, 'utf-16-be')):
            if raw.startswith(marker):
                encoding, bom, body = enc, True, raw[len(marker):]
                break
        text = body.decode(encoding, errors='strict')
        if '\x00' in text:
            raise ValueError('This appears to be a binary file, not a text document.')
        endings = re.findall(r'\r\n|\r|\n', text)
        eol = max(set(endings), key=endings.count) if endings else '\n'
        fmt = cls(encoding, bom, text, eol)
        return text.replace('\r\n', '\n').replace('\r', '\n'), fmt

    def encode(self, text: str, normalize: bool | None = None) -> bytes:
        normalize = self.normalize if normalize is None else normalize
        old = self.original.replace('\r\n', '\n').replace('\r', '\n')
        if text == old and not normalize:
            result = self.original
        else:
            old_lines = old.split('\n')
            new_lines = text.split('\n')
            old_endings = re.findall(r'\r\n|\r|\n', self.original)
            endings = [self.eol] * max(0, len(new_lines) - 1)
            if not normalize:
                for block in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_matching_blocks():
                    for offset in range(block.size):
                        a, b = block.a + offset, block.b + offset
                        if a < len(old_endings) and b < len(endings):
                            endings[b] = old_endings[a]
            result = ''.join(line + (endings[i] if i < len(endings) else '')
                             for i, line in enumerate(new_lines))
        raw = result.encode(self.encoding, errors='strict')
        if self.bom:
            raw = {'utf-8': codecs.BOM_UTF8, 'utf-16-le': codecs.BOM_UTF16_LE,
                   'utf-16-be': codecs.BOM_UTF16_BE}[self.encoding] + raw
        return raw

    @property
    def eol_label(self):
        endings = set(re.findall(r'\r\n|\r|\n', self.original))
        return 'Mixed' if len(endings) > 1 else {'\n': 'LF', '\r\n': 'CRLF', '\r': 'CR'}[self.eol]


@dataclass
class Note:
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = 'Untitled'
    path: str = ''
    kind: str = 'txt'
    source: str = ''
    html: str = ''
    rich: bool = False
    imported: bool = False
    assets: dict[str, bytes] = field(default_factory=dict)
    drawings: dict[str, dict] = field(default_factory=dict)
    text_format: TextFormat = field(default_factory=TextFormat)
    baseline: str | None = None
    dirty: bool = False
    revision: int = 0
    cursor: int = 0
    scroll: int = 0
    zoom: int = 100
    window: str = ''

    def snapshot(self) -> dict:
        return {'source': self.source, 'html': self.html, 'rich': self.rich,
                'kind': self.kind, 'imported': self.imported, 'text_format': vars(self.text_format).copy()}

    def restore_content(self, content: dict):
        for key in ('source', 'html', 'rich', 'kind', 'imported'):
            setattr(self, key, content[key])
        if 'text_format' in content: self.text_format = TextFormat(**content['text_format'])

    def to_dict(self) -> dict:
        data = {key: getattr(self, key) for key in self.__dataclass_fields__
                if key not in ('assets', 'text_format')}
        data['assets'] = {key: base64.b64encode(value).decode('ascii') for key, value in self.assets.items()}
        data['text_format'] = vars(self.text_format)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Note':
        data = dict(data)
        data['assets'] = {key: base64.b64decode(value, validate=True) for key, value in data.get('assets', {}).items()}
        data['text_format'] = TextFormat(**data.get('text_format', {}))
        return cls(**data)


def read_note(path: str) -> Note:
    target = Path(path).resolve()
    if target.stat().st_size > MAX_FILE:
        raise ValueError('This version supports files up to 64 MiB. Open a smaller file.')
    raw = target.read_bytes()
    if target.suffix.lower() == '.folio':
        note = unpack_note(raw)
    else:
        source, fmt = TextFormat.decode(raw)
        note = Note(source=source, text_format=fmt,
                    kind='md' if target.suffix.lower() in ('.md', '.markdown') else 'txt', imported=True)
    note.path, note.title, note.baseline = str(target), target.name, digest(raw)
    note.dirty = False
    return note


def _safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name


def referenced_assets(note: Note, markdown: str) -> dict[str, bytes]:
    """Export only visible attachments, never deleted images retained for Undo."""
    if note.rich:
        from html.parser import HTMLParser
        class Images(HTMLParser):
            def __init__(self): super().__init__(); self.names=set()
            def handle_starttag(self,tag,attrs):
                if tag=='img':
                    src=dict(attrs).get('src','')
                    self.names.add(src)
        parser=Images(); parser.feed(note.html)
        names=parser.names
    else:
        names=set(re.findall(r'!\[[^]]*\]\(<?(assets/[^\s)>]+)>?(?:[^)]*)\)',markdown))
    return {key:raw for key,raw in note.assets.items() if key in names}


def pack_note(note: Note, markdown: str) -> bytes:
    entries = {'content.md': markdown.encode('utf-8'), 'content.html': note.html.encode('utf-8')}
    assets = []
    active_assets = referenced_assets(note, markdown)
    for name, raw in active_assets.items():
        if not _safe_name(name) or not name.startswith('assets/'):
            raise ValueError('Invalid attachment path.')
        entries[name] = raw
        assets.append({'path': name, 'sha256': digest(raw)})
    drawings = {}
    for key, drawing in note.drawings.items():
        if key not in active_assets: continue
        if key not in note.assets:
            raise ValueError('Drawing preview is missing.')
        drawings[key] = drawing
    manifest = {'schemaVersion': 1, 'title': note.title, 'rich': note.rich,
                'assets': assets, 'drawings': drawings,
                'contentHash': digest(entries['content.md']), 'htmlHash': digest(entries['content.html'])}
    entries['manifest.json'] = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
    output = io.BytesIO()
    # Stored entries avoid archive-bomb ambiguity and retain already-compressed image bytes.
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, raw in entries.items():
            z.writestr(name, raw)
    result = output.getvalue()
    if len(result) > MAX_FILE:
        raise ValueError('Portable note exceeds the 64 MiB file limit.')
    return result


def unpack_note(raw: bytes) -> Note:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            entries = z.infolist()
            if len(entries) > MAX_ENTRIES or sum(x.file_size for x in entries) > MAX_PACKAGE:
                raise ValueError('Package size or entry count exceeds safe limits.')
            names = set()
            for item in entries:
                mode = item.external_attr >> 16
                if (not _safe_name(item.filename) or item.filename in names or
                        stat.S_ISLNK(mode) or item.flag_bits & 1 or
                        item.file_size > MAX_FILE or item.file_size > max(1, item.compress_size) * 100):
                    raise ValueError('Unsafe or unsupported package entry.')
                names.add(item.filename)
            manifest = json.loads(z.read('manifest.json'))
            if not isinstance(manifest,dict): raise ValueError('Invalid package manifest.')
            if manifest.get('schemaVersion') != 1:
                raise ValueError('Unsupported note version. The original file was not changed.')
            source, html = z.read('content.md'), z.read('content.html')
            if digest(source) != manifest['contentHash'] or digest(html) != manifest['htmlHash']:
                raise ValueError('Document checksum mismatch.')
            assets = {}
            for asset in manifest['assets']:
                name = asset['path']
                if not _safe_name(name) or not name.startswith('assets/') or name in assets:
                    raise ValueError('Invalid attachment reference.')
                data = z.read(name)
                if digest(data) != asset['sha256']:
                    raise ValueError('Attachment checksum mismatch.')
                assets[name] = data
            drawings = manifest.get('drawings', {})
            for key, drawing in drawings.items():
                if key not in assets:
                    raise ValueError('Drawing preview is missing.')
                validate_drawing(drawing)
            return Note(title=str(manifest.get('title', 'Untitled'))[:256], kind='folio',
                        source=source.decode('utf-8'), html=html.decode('utf-8'),
                        rich=bool(manifest.get('rich')), assets=assets, drawings=drawings)
    except (KeyError, TypeError, UnicodeError, zipfile.BadZipFile, json.JSONDecodeError, RuntimeError) as exc:
        raise ValueError(f'Invalid portable note: {exc}') from exc


def validate_drawing(model: dict):
    import math
    if not isinstance(model, dict) or model.get('version') != 1:
        raise ValueError('Unsupported drawing version.')
    strokes = model.get('strokes')
    if not isinstance(strokes, list) or len(strokes) > 10000:
        raise ValueError('Drawing has too many objects.')
    total = 0
    for stroke in strokes:
        if not isinstance(stroke, dict) or stroke.get('tool') not in ('pen', 'highlighter', 'line', 'rectangle', 'ellipse', 'arrow'):
            raise ValueError('Invalid drawing object.')
        width = stroke.get('width')
        if not isinstance(width, (int, float)) or not math.isfinite(width) or not 0.1 <= width <= 100:
            raise ValueError('Invalid stroke width.')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(stroke.get('color'))):
            raise ValueError('Invalid stroke color.')
        points = stroke.get('points')
        if not isinstance(points, list):
            raise ValueError('Invalid drawing points.')
        total += len(points)
        if total > 200000:
            raise ValueError('Drawing has too many points.')
        for point in points:
            if (not isinstance(point, list) or len(point) != 2 or
                    any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in point)):
                raise ValueError('Invalid drawing coordinates.')


class RecoveryStore:
    """One SQLite transaction persists both content and owned asset bytes."""
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.db = sqlite3.connect(self.directory / 'state.sqlite', timeout=5)
        os.chmod(self.directory / 'state.sqlite', 0o600)
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA synchronous=FULL')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            self.db.close()
            raise ValueError('Recovery database is from a newer application version.')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, payload TEXT NOT NULL,
            active INTEGER NOT NULL, ordering INTEGER NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS revisions(id TEXT NOT NULL, revision INTEGER NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY(id, revision));
        PRAGMA user_version=1;
        ''')
        self.db.commit()

    def protect(self, notes: list[Note], *, closed: list[Note] = (), discard: list[str] = ()):
        now = time.time()
        with self.db:
            for key in discard:
                self.db.execute('DELETE FROM drafts WHERE id=?',(key,))
                self.db.execute('DELETE FROM revisions WHERE id=?',(key,))
            # Only the application controller supplies the full list across all windows.
            self.db.execute('UPDATE drafts SET active=0')
            for active, collection in ((1, notes), (0, closed)):
                for order, note in enumerate(collection):
                    payload = json.dumps(note.to_dict(), ensure_ascii=False)
                    self.db.execute('INSERT OR REPLACE INTO drafts VALUES(?,?,?,?,?)',
                                    (note.id, payload, active, order, now))
                    self.db.execute('INSERT OR REPLACE INTO revisions VALUES(?,?,?)',
                                    (note.id, note.revision, payload))
                    self.db.execute('DELETE FROM revisions WHERE id=? AND revision NOT IN '
                                    '(SELECT revision FROM revisions WHERE id=? ORDER BY revision DESC LIMIT 10)',
                                    (note.id, note.id))
            expired = self.db.execute('SELECT id FROM drafts WHERE active=0 AND updated<?',
                                      (now - 30*86400,)).fetchall()
            for (key,) in expired:
                self.db.execute('DELETE FROM drafts WHERE id=?', (key,))
                self.db.execute('DELETE FROM revisions WHERE id=?', (key,))

    def load(self, active=True) -> list[Note]:
        return [Note.from_dict(json.loads(row[0])) for row in self.db.execute(
            'SELECT payload FROM drafts WHERE active=? ORDER BY ordering', (int(active),))]

    def discard(self, key: str):
        with self.db:
            self.db.execute('DELETE FROM drafts WHERE id=?', (key,))
            self.db.execute('DELETE FROM revisions WHERE id=?', (key,))

    def close(self):
        self.db.close()
