"""Native editors, structured document operations and a shared undo history."""
from __future__ import annotations
import copy
import hashlib
import re
import time
from contextlib import contextmanager
from pathlib import Path
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt, QUrl, QTimer, QEvent, Signal, QPointF, QRectF
from PySide6.QtGui import (QColor, QFont, QImage, QImageReader, QSyntaxHighlighter, QPainter, QPen, QFontMetricsF,
    QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextImageFormat,
    QTextListFormat, QTextTableFormat, QTextDocumentFragment, QTextTable, QUndoCommand, QUndoStack)
from PySide6.QtWidgets import (QHBoxLayout, QApplication, QMenu, QPlainTextEdit, QSplitter,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QToolButton)
from .storage import Note
from . import tabletools


def theme_neutral_html(html):
    """Keep Qt's generated body foreground from pinning notes to the old theme."""
    def clean(match):
        style=re.sub(r'(?<![\w-])color\s*:[^;]*;?', '',match.group(2),flags=re.I)
        return match.group(1)+style+match.group(3)
    return re.sub(r'(<body\b[^>]*\bstyle=")([^"]*)(")',clean,html,flags=re.I)


class SafeDocument(QTextDocument):
    """Never resolve arbitrary local paths or network URLs from untrusted markup."""
    def __init__(self, assets, parent=None):
        super().__init__(parent)
        self.assets = assets
        self.setDocumentMargin(26)

    def loadResource(self, kind, name):
        key = name.toString()
        if kind == QTextDocument.ResourceType.ImageResource and key in self.assets:
            try: return decode_image(self.assets[key])
            except ValueError: return None
        return None


def decode_image(raw: bytes) -> QImage:
    if len(raw) > 25 * 1024 * 1024:
        raise ValueError('Image exceeds 25 MiB. Please choose a smaller image.')
    buffer = QBuffer()
    buffer.setData(raw)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    if bytes(reader.format()).lower() not in (b'png', b'jpeg', b'jpg', b'webp'):
        raise ValueError('Use a PNG, JPEG or WebP image.')
    size = reader.size()
    if not size.isValid() or size.width()*size.height() > 50_000_000:
        raise ValueError('Image dimensions exceed 50 megapixels or are invalid.')
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError('The image could not be decoded.')
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise ValueError('Could not encode image.')
    return bytes(buffer.data())


def table_safe_markdown(document, strict=True):
    """Work around Qt's unescaped literal pipes when writing GFM tables."""
    from uuid import uuid4
    clone = document.clone()
    replacements = []
    for frame in clone.rootFrame().childFrames():
        if not isinstance(frame, QTextTable): continue
        token = 'FOLIOTABLE'+uuid4().hex+'END'
        rows = []
        for r in range(frame.rows()):
            cells = []
            for col in range(frame.columns()):
                cell = frame.cellAt(r,col)
                c = cell.firstCursorPosition()
                c.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
                text = QTextDocumentFragment(c).toMarkdown().strip()
                if strict and '\n' in text:
                    raise ValueError('A table cell contains multiple lines. Save as .folio to preserve it; Markdown tables require single-line cells.')
                cells.append(text.replace('|',r'\|').replace('\n',' '))
            rows.append('| '+' | '.join(cells)+' |')
            if r == 0:
                separators=[]
                for col in range(frame.columns()):
                    alignment=frame.cellAt(0,col).firstCursorPosition().blockFormat().alignment()
                    separators.append(':---:' if alignment & Qt.AlignmentFlag.AlignHCenter else '---:' if alignment & Qt.AlignmentFlag.AlignRight else '---')
                rows.append('| '+' | '.join(separators)+' |')
        replacements.append((frame.firstPosition()-1,frame.lastPosition()+1,token,'\n'.join(rows)))
    for start,end,token,markdown in reversed(replacements):
        c=QTextCursor(clone)
        c.setPosition(start); c.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
        c.insertText('\n'+token+'\n')
    result=clone.toMarkdown()
    for _,_,token,markdown in replacements: result=result.replace(token,markdown)
    return result


def history_context_menu(widget,event):
    menu=widget.createStandardContextMenu()
    editor=getattr(widget,'note_editor',None)
    if editor:
        for action in list(menu.actions()):
            text=action.text().split('\t',1)[0].replace('&','')
            if text in ('Undo','Redo'): menu.removeAction(action)
        actions=menu.actions()
        before=actions[0] if actions else None
        menu.insertAction(before,editor.stack.createUndoAction(menu,'Undo'))
        menu.insertAction(before,editor.stack.createRedoAction(menu,'Redo'))
        menu.insertSeparator(before)
    return menu


class PlainEdit(QPlainTextEdit):
    image_pasted=Signal(object)
    def canInsertFromMimeData(self,data):
        return data.hasImage() or super().canInsertFromMimeData(data)
    def insertFromMimeData(self,data):
        if data.hasImage(): self.image_pasted.emit(data.imageData())
        elif data.hasUrls() and len(data.urls())==1 and data.urls()[0].isLocalFile() and Path(data.urls()[0].toLocalFile()).suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
            self.image_pasted.emit(data.urls()[0].toLocalFile())
        else: super().insertFromMimeData(data)
    def contextMenuEvent(self,event):
        history_context_menu(self,event).exec(event.globalPos())



class RichEdit(QTextEdit):
    image_pasted = Signal(object)
    cells_pasted = Signal(str)
    image_edit = Signal(str)
    table_command = Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.table_editor=None
        self._drag=None
        self._grid_cache=None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.row_add_button=QToolButton(self.viewport())
        self.column_add_button=QToolButton(self.viewport())
        self.row_more_button=QToolButton(self.viewport())
        self.column_more_button=QToolButton(self.viewport())
        for button in (self.row_add_button,self.column_add_button,self.row_more_button,self.column_more_button):
            button.setObjectName('TableEdgeButton')
            button.setFixedSize(24,24)
            button.setAutoRaise(False)
            button.hide()
        self.row_add_button.setText('+')
        self.row_add_button.setToolTip('Add a row below this row')
        self.row_add_button.setAccessibleName('Add row below selected row')
        self.row_add_button.clicked.connect(lambda:self.table_command.emit('row_below'))
        self.column_add_button.setText('+')
        self.column_add_button.setToolTip('Add a column to the right')
        self.column_add_button.setAccessibleName('Add column right of selected column')
        self.column_add_button.clicked.connect(lambda:self.table_command.emit('col_right'))
        for button,label,options in [
            (self.row_more_button,'Row options',[('Insert above','row_above'),('Insert below','row_below'),('Duplicate row','duplicate_row'),('Move up','move_row_up'),('Move down','move_row_down'),('Delete row','del_row')]),
            (self.column_more_button,'Column options',[('Insert left','col_left'),('Insert right','col_right'),('Duplicate column','duplicate_col'),('Move left','move_col_left'),('Move right','move_col_right'),('Delete column','del_col')])]:
            button.setText('⋯'); button.setToolTip(label); button.setAccessibleName(label)
            menu=QMenu(button)
            for text,op in options:
                menu.addAction(text,lambda checked=False,op=op:self.table_command.emit(op))
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def table_bounds(self,table):
        doc=self.document()
        key=(doc.revision(),table.firstPosition(),table.rows(),table.columns(),doc.textWidth(),self.viewport().width())
        if not self._grid_cache or self._grid_cache[0]!=key:
            self._grid_cache=(key,tabletools.grid(doc,table))
        xs,ys=self._grid_cache[1]
        first=table.cellAt(0,0).firstCursorPosition()
        block=doc.documentLayout().blockBoundingRect(first.block())
        rect=self.cursorRect(first)
        dx,dy=rect.x()-block.x(),rect.y()-block.y()
        return [x+dx for x in xs],[y+dy for y in ys]

    def update_table_buttons(self):
        if not hasattr(self,'row_add_button'): return
        buttons=(self.row_add_button,self.column_add_button,self.row_more_button,self.column_more_button)
        editor=getattr(self,'table_editor',None)
        table=self.textCursor().currentTable() if editor and editor.editable and not self.isReadOnly() else None
        if not table:
            for button in buttons: button.hide()
            return
        xs,ys=self.table_bounds(table)
        if not QRectF(xs[0],ys[0],xs[-1]-xs[0],ys[-1]-ys[0]).intersects(QRectF(self.viewport().rect())):
            for button in buttons: button.hide()
            return
        cell=table.cellAt(self.textCursor())
        row_y=(ys[cell.row()]+ys[cell.row()+1])/2-12
        col_x=(xs[cell.column()]+xs[cell.column()+1])/2-12
        positions=[(xs[-1]+6,row_y),(col_x,ys[-1]+6),(xs[0]-28,row_y),(col_x,ys[0]-28)]
        for button,(x,y) in zip(buttons,positions):
            button.move(max(0,min(self.viewport().width()-24,round(x))),max(0,min(self.viewport().height()-24,round(y))))
            button.show(); button.raise_()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'_grid_cache'): self._grid_cache=None
        self.update_table_buttons()

    def border_at(self,point):
        if not self.table_editor or not self.table_editor.editable: return None
        table=self.cursorForPosition(point).currentTable() or self.textCursor().currentTable()
        if not table: return None
        xs,ys=self.table_bounds(table)
        x,y=point.x(),point.y()
        if ys[0]-3<=y<=ys[-1]+3:
            for index,edge in enumerate(xs[1:]):
                if abs(x-edge)<=4:
                    return 'column',index,table,xs,ys
        if xs[0]-3<=x<=xs[-1]+3:
            for index,edge in enumerate(ys[1:]):
                if abs(y-edge)<=4:
                    return 'row',index,table,xs,ys
        return None

    def mousePressEvent(self,event):
        hit=self.border_at(event.position().toPoint()) if event.button()==Qt.MouseButton.LeftButton else None
        if hit:
            axis,index,table,xs,ys=hit
            cell=table.cellAt(self.cursorForPosition(event.position().toPoint()))
            row=max(0,cell.row()) if cell.isValid() else 0
            column=max(0,cell.column()) if cell.isValid() else 0
            row=index if axis=='row' else row
            column=index if axis=='column' else column
            self.setTextCursor(table.cellAt(row,column).firstCursorPosition())
            size=tabletools.widths(self.document(),table)[index] if axis=='column' else ys[index+1]-ys[index]
            self._drag={'axis':axis,'index':index,'start':event.position(),'point':event.position(),'size':size,'xs':xs,'ys':ys}
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._drag:
            self._drag['point']=event.position()
            self.viewport().update()
            event.accept(); return
        hit=self.border_at(event.position().toPoint())
        self.viewport().setCursor(Qt.CursorShape.SplitHCursor if hit and hit[0]=='column' else Qt.CursorShape.SplitVCursor if hit else Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)

    def paintEvent(self,event):
        super().paintEvent(event)
        drag=getattr(self,'_drag',None)
        if not drag: return
        painter=QPainter(self.viewport())
        painter.setPen(QPen(self.palette().highlight().color(),2,Qt.PenStyle.DashLine))
        if drag['axis']=='column':
            x=drag['point'].x()
            painter.drawLine(QPointF(x,drag['ys'][0]),QPointF(x,drag['ys'][-1]))
        else:
            y=drag['point'].y()
            painter.drawLine(QPointF(drag['xs'][0],y),QPointF(drag['xs'][-1],y))

    def canInsertFromMimeData(self,data):
        return data.hasImage() or data.hasUrls() or super().canInsertFromMimeData(data)

    def insertFromMimeData(self, data):
        if data.hasImage():
            self.image_pasted.emit(data.imageData())
        elif data.hasUrls():
            for url in data.urls():
                if url.isLocalFile():
                    self.image_pasted.emit(url.toLocalFile())
        elif self.textCursor().currentTable() and '\t' in data.text():
            self.cells_pasted.emit(data.text())
        else:
            # Avoid arbitrary HTML and remote image injection from clipboard content.
            self.textCursor().insertText(data.text())

    def mouseDoubleClickEvent(self, event):
        cursor = self.cursorForPosition(event.position().toPoint())
        for offset in (0, 1):
            c = QTextCursor(cursor)
            c.movePosition(QTextCursor.MoveOperation.NextCharacter,
                           QTextCursor.MoveMode.KeepAnchor, offset)
            fmt = c.charFormat()
            if fmt.isImageFormat():
                self.setTextCursor(c)
                self.image_edit.emit(fmt.toImageFormat().name())
                return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self,event):
        if self._drag:
            drag=self._drag; self._drag=None
            delta=event.position()-drag['start']
            if drag['axis']=='column': self.table_editor.resize_column(drag['size']+delta.x(),drag['index'])
            else: self.table_editor.resize_row(drag['size']+delta.y(),drag['index'])
            self.viewport().update()
            self.update_table_buttons()
            event.accept(); return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            from PySide6.QtGui import QDesktopServices
            url=QUrl(self.anchorAt(event.position().toPoint()))
            if url.scheme() in ('http','https','mailto'):
                QDesktopServices.openUrl(url)
                event.accept(); return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        c = self.textCursor()
        if event.key() == Qt.Key.Key_Tab and c.currentTable() and not self.isReadOnly():
            table = c.currentTable()
            cell = table.cellAt(c)
            if cell.row() == table.rows()-1 and cell.column() == table.columns()-1:
                self.table_command.emit('append')
            c.movePosition(QTextCursor.MoveOperation.NextCell)
            self.setTextCursor(c)
            return
        if event.key() == Qt.Key.Key_Backtab and c.currentTable():
            c.movePosition(QTextCursor.MoveOperation.PreviousCell)
            self.setTextCursor(c)
            return
        if event.key() == Qt.Key.Key_Escape and c.currentTable():
            table = c.currentTable()
            c = table.lastCursorPosition()
            c.movePosition(QTextCursor.MoveOperation.NextBlock)
            self.setTextCursor(c)
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        self.setTextCursor(self.cursorForPosition(event.pos()))
        menu = history_context_menu(self,event)
        # The application's shared history includes text, table, and drawing edits.
        if self.textCursor().currentTable():
            menu.addSeparator()
            for label, op in [('Row above', 'row_above'), ('Row below', 'row_below'),
                              ('Column left', 'col_left'), ('Column right', 'col_right'),
                              ('Delete row', 'del_row'), ('Delete column', 'del_col'),
                              ('Table size…', 'resize'), ('Column width…', 'column_width'),
                              ('Row minimum height…', 'row_height'), ('Size columns equally','equal_columns'),
                              ('Size rows equally','equal_rows'), ('Fit columns to content','fit_columns'),
                              ('Fit row to content','fit_row'), ('Duplicate row','duplicate_row'),
                              ('Duplicate column','duplicate_col'), ('Delete table', 'delete')]:
                menu.addAction(label, lambda op=op: self.table_command.emit(op))
        fmt = self.textCursor().charFormat()
        if fmt.isImageFormat():
            menu.addAction('Edit image / drawing…', lambda: self.image_edit.emit(fmt.toImageFormat().name()))
        menu.exec(event.globalPos())


class ContentCommand(QUndoCommand):
    def __init__(self, editor, before, after, label, merge=False):
        super().__init__(label)
        self.editor, self.before, self.after = editor, before, after
        self.merge, self.created, self.first = merge, time.monotonic(), True

    def id(self):
        return 1 if self.merge else -1

    def mergeWith(self, other):
        if (not isinstance(other, ContentCommand) or other.editor is not self.editor or
                not other.merge or other.created-self.created > 1 or
                self.after['rich'] != other.after['rich']):
            return False
        self.after, self.created = other.after, other.created
        return True

    def redo(self):
        if self.first:
            self.first = False
            return
        self.editor.apply(self.after)

    def undo(self):
        self.editor.apply(self.before)


class MarkdownHighlight(QSyntaxHighlighter):
    def highlightBlock(self, text):
        fmt = QTextCharFormat()
        if re.match(r'^#{1,6} ', text):
            fmt.setForeground(QColor('#5289d8'))
            fmt.setFontWeight(QFont.Weight.Bold)
            self.setFormat(0, len(text), fmt)
        elif text.startswith('```'):
            fmt.setForeground(QColor('#7b9e73'))
            self.setFormat(0, len(text), fmt)


class SpellHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.dictionary = None
        self.fenced = False
        self.ignored = set()

    def language(self, name):
        try:
            import enchant
            self.dictionary = enchant.Dict(name) if name else None
        except Exception:
            self.dictionary = None
        self.rehighlight()
        return self.dictionary is not None

    def highlightBlock(self, text):
        if not self.dictionary:
            return
        previous = self.previousBlockState() == 1
        fenced = not previous if text.lstrip().startswith('```') else previous
        self.setCurrentBlockState(int(fenced))
        if fenced or previous or self.currentBlock().blockFormat().property(QTextFormat.Property.BlockCodeFence):
            return
        excluded = [m.span() for m in re.finditer(r'https?://\S+|`[^`]*`|!\[[^]]*\]\([^)]*\)', text)]
        fmt = QTextCharFormat()
        fmt.setUnderlineColor(QColor('#d35656'))
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        for match in re.finditer(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text, re.UNICODE):
            word = match.group()
            if any(a <= match.start() < b for a, b in excluded) or word in self.ignored:
                continue
            if not self.dictionary.check(word):
                start = len(text[:match.start()].encode('utf-16-le'))//2
                size = len(word.encode('utf-16-le'))//2
                self.setFormat(start, size, fmt)


class NoteEditor(QWidget):
    changed = Signal()
    position_changed = Signal()
    image_requested = Signal(object)
    image_edit = Signal(str)
    table_requested = Signal(str)
    operation_error = Signal(str)
    history_changed = Signal()

    def __init__(self, note: Note, parent=None):
        super().__init__(parent)
        self.note = note
        self.ink = None
        if note.rich: note.html=theme_neutral_html(note.html)
        self.busy = False
        self.depth = 0
        self.command_name = 'Typing'
        self.autocorrect_enabled = False
        self.display_source = ''
        self.stack = QUndoStack(self)
        self.stack.setUndoLimit(120)
        self.stack.indexChanged.connect(self.history_changed)
        self.source = PlainEdit()
        self.source.setAccessibleName('Note source editor')
        self.source.setPlaceholderText('A fresh page. Start writing…')
        self.formatted = RichEdit()
        self.formatted.setAccessibleName('Formatted note editor')
        self.formatted.setPlaceholderText('A fresh page. Start writing…')
        self.formatted.setAcceptRichText(False)
        self.formatted.setDocument(SafeDocument(note.assets, self.formatted))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName('Read-only Markdown preview')
        self.preview.setDocument(SafeDocument(note.assets, self.preview))
        self.splitter = QSplitter()
        self.splitter.addWidget(self.source)
        self.splitter.addWidget(self.preview)
        self.views = QStackedWidget()
        self.views.setObjectName('DocumentSurface')
        self.views.addWidget(self.splitter)
        self.views.addWidget(self.formatted)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        from .tabletools import TableControls
        self.table_controls=TableControls()
        layout.addWidget(self.table_controls)
        self.canvas=QWidget()
        self.canvas.setObjectName('NoteCanvas')
        canvas_layout=QHBoxLayout(self.canvas)
        canvas_layout.setContentsMargins(10,8,10,8)
        canvas_layout.addWidget(self.views)
        layout.addWidget(self.canvas,1)
        for widget in (self.source,self.formatted,self.preview):
            widget.setProperty('folioEditor',True)
        self.table_controls.command.connect(self.table_requested)
        self.table_controls.column_width.connect(lambda value:self.resize_column(value))
        self.table_controls.row_height.connect(lambda value:self.resize_row(value))
        self.formatted.table_editor=self
        self.formatted.note_editor=self
        self.source.note_editor=self
        self.source_spelling = SpellHighlighter(self.source.document())
        self.spelling = SpellHighlighter(self.formatted.document())
        self.spelling.language('en_US')
        self.saved = copy.deepcopy(note.snapshot()) if not note.dirty else None
        self.last = copy.deepcopy(note.snapshot())
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(200)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.apply(note.snapshot(), notify=False)
        for editor in (self.source, self.formatted):
            editor.installEventFilter(self)
            editor.setUndoRedoEnabled(False)
            editor.textChanged.connect(self.on_change)
            editor.cursorPositionChanged.connect(self.position_changed)
        self.formatted.cursorPositionChanged.connect(self.update_table_controls)
        self.formatted.verticalScrollBar().valueChanged.connect(self.update_table_controls)
        self.formatted.horizontalScrollBar().valueChanged.connect(self.update_table_controls)
        self.preview.installEventFilter(self)
        self.source.image_pasted.connect(self.image_requested)
        self.formatted.image_pasted.connect(self.image_requested)
        self.formatted.cells_pasted.connect(self.paste_cells_safely)
        self.formatted.image_edit.connect(self.image_edit)
        self.formatted.table_command.connect(self.table_requested)
        self.set_zoom(note.zoom)
        c = self.active.textCursor()
        c.setPosition(min(note.cursor, self.active.document().characterCount()-1))
        self.active.setTextCursor(c)
        self.active.verticalScrollBar().setValue(note.scroll)
        self.refresh_contrast()

    @property
    def active(self):
        if self.views.currentIndex() == 1: return self.formatted
        if self.source.isHidden() and not self.preview.isHidden(): return self.preview
        return self.source

    @property
    def editable(self):
        return self.note.rich and self.views.currentIndex() == 1

    def capture(self):
        if self.note.rich:
            self.note.html = theme_neutral_html(self.formatted.toHtml())
            self.note.source = self.formatted.document().toMarkdown()
        else:
            display = self.source.document().toRawText().replace('\u2029','\n')
            if display != self.display_source:
                self.note.source = display
                self.display_source = display
        return copy.deepcopy(self.note.snapshot())

    def on_change(self):
        if self.busy or self.depth:
            return
        after = self.capture()
        if after == self.last:
            return
        size = len(after['source'].encode('utf-8')) + len(after['html'].encode('utf-8'))
        if size*max(1,self.stack.count()) > 16*1024*1024: self.stack.clear()
        self.stack.push(ContentCommand(self, self.last, after, 'Typing', merge=True))
        if not self.note.rich and not self.preview.isHidden(): self.preview_timer.start()
        self.last = after
        self.notify()

    def notify(self):
        self.note.revision += 1
        self.note.dirty = self.saved is None or self.note.snapshot() != self.saved
        self.changed.emit()
        self.update_table_controls()
        if self.ink: self.ink.sync()

    def apply(self, state, notify=True):
        position=self.active.textCursor().position()
        self.busy = True
        self.note.restore_content(copy.deepcopy(state))
        self.source.setPlainText(self.note.source)
        self.display_source = self.source.document().toRawText().replace('\u2029','\n')
        self.source.setReadOnly(self.note.rich)
        self.formatted.setHtml(theme_neutral_html(self.note.html)) if self.note.rich else self.formatted.setPlainText('')
        self.views.setCurrentIndex(1 if self.note.rich else 0)
        self.preview.hide()
        cursor=self.active.textCursor()
        cursor.setPosition(min(position,self.active.document().characterCount()-1))
        self.active.setTextCursor(cursor)
        self.last = copy.deepcopy(state)
        self.busy = False
        if notify:
            self.notify()
            self.refresh_contrast()

    @contextmanager
    def operation(self, label):
        before = self.capture()
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1
            after = self.capture()
            if before != after:
                self.stack.push(ContentCommand(self, before, after, label))
                self.last = after
                self.notify()
                self.refresh_contrast()

    def mark_saved(self):
        self.capture()
        self.saved = copy.deepcopy(self.note.snapshot())
        self.last = copy.deepcopy(self.saved)
        self.note.dirty = False
        self.stack.setClean()
        self.changed.emit()

    def refresh_preview(self):
        if not self.note.rich and not self.preview.isHidden():
            self.preview.document().setMarkdown(self.note.source,
                QTextDocument.MarkdownFeature.MarkdownDialectGitHub | QTextDocument.MarkdownFeature.MarkdownNoHTML)

    def view(self, mode):
        if self.ink and mode!='formatted': self.ink.finish()
        if self.note.rich:
            if mode == 'formatted':
                self.views.setCurrentIndex(1)
            else:
                self.source.setPlainText(self.markdown(False))
                self.source.setReadOnly(True)
                self.views.setCurrentIndex(0)
                self.preview.setHtml(self.note.html)
                self.preview.setVisible(mode == 'split')
        else:
            self.views.setCurrentIndex(0)
            self.preview.document().setMarkdown(self.note.source, QTextDocument.MarkdownFeature.MarkdownDialectGitHub |
                                     QTextDocument.MarkdownFeature.MarkdownNoHTML)
            self.preview.setVisible(mode in ('formatted', 'split'))
            self.source.setVisible(mode != 'formatted')
        if self.note.rich:
            self.source.show()
        self.position_changed.emit()
        self.update_table_controls()

    def make_rich(self):
        if self.note.rich:
            self.views.setCurrentIndex(1)
            return
        source_cursor=self.source.textCursor()
        position=source_cursor.position()
        at_end=source_cursor.atEnd()
        with self.operation('Enable formatting'):
            self.busy = True
            if self.note.kind == 'txt':
                self.formatted.setPlainText(self.note.source)
            else:
                self.formatted.document().setMarkdown(self.note.source, QTextDocument.MarkdownFeature.MarkdownDialectGitHub |
                                           QTextDocument.MarkdownFeature.MarkdownNoHTML)
            self.busy = False
            self.note.rich, self.note.kind, self.note.imported = True, 'md', False
            self.views.setCurrentIndex(1)
            cursor=self.formatted.textCursor()
            end=self.formatted.document().characterCount()-1
            cursor.setPosition(end if at_end else min(position,end))
            self.formatted.setTextCursor(cursor)

    def markdown(self, strict=True):
        if not self.note.rich: return self.note.source
        return table_safe_markdown(self.formatted.document(), strict)


    def plain_text(self):
        if not self.note.rich:
            return self.note.source
        # Substitute image object characters while retaining table cells as tab-separated text.
        doc = self.formatted.document().clone()
        positions = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().isImageFormat():
                    fmt = frag.charFormat().toImageFormat()
                    positions.append((frag.position(), frag.length(), f'[Image: {fmt.property(QTextFormat.Property.ImageAltText) or fmt.name()}]'))
                it += 1
            block = block.next()
        for pos, size, label in reversed(positions):
            c = QTextCursor(doc)
            c.setPosition(pos)
            c.setPosition(pos+size, QTextCursor.MoveMode.KeepAnchor)
            c.insertText(label)
        return doc.toPlainText().replace('\ufffc', '[Image]')

    def set_zoom(self, percent):
        self.note.zoom = max(50, min(300, percent))
        for editor in (self.source, self.formatted, self.preview):
            font = QFont(editor.font())
            font.setPointSizeF(11*self.note.zoom/100)
            editor.setFont(font)

    def format_text(self, name):
        with self.operation(name):
            c = self.formatted.textCursor()
            fmt = QTextCharFormat()
            current = c.charFormat()
            if name == 'Bold':
                fmt.setFontWeight(QFont.Weight.Normal if current.fontWeight() >= QFont.Weight.Bold else QFont.Weight.Bold)
            elif name == 'Italic':
                fmt.setFontItalic(not current.fontItalic())
            elif name == 'Strikethrough':
                fmt.setFontStrikeOut(not current.fontStrikeOut())
            elif name == 'Code':
                fmt.setFontFamilies(['monospace'])
            elif name == 'Clear formatting':
                c.setCharFormat(QTextCharFormat())
                block = c.blockFormat()
                block.setHeadingLevel(0)
                c.setBlockFormat(block)
                return
            c.mergeCharFormat(fmt)
            self.formatted.mergeCurrentCharFormat(fmt)

    def heading(self, level):
        with self.operation('Heading'):
            c = self.formatted.textCursor()
            if not c.hasSelection(): c.select(QTextCursor.SelectionType.BlockUnderCursor)
            fmt = c.blockFormat()
            fmt.setHeadingLevel(level)
            c.mergeBlockFormat(fmt)
            char = QTextCharFormat()
            char.setFontWeight(QFont.Weight.Bold if level else QFont.Weight.Normal)
            char.setFontPointSize(11 + (7-level)*2 if level else 11)
            c.mergeCharFormat(char)

    def list_format(self, ordered=False):
        with self.operation('List'):
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.Style.ListDecimal if ordered else QTextListFormat.Style.ListDisc)
            fmt.setIndent(1)
            self.formatted.textCursor().createList(fmt)

    def indent(self, amount):
        with self.operation('Indent'):
            c = self.formatted.textCursor()
            if c.currentList():
                fmt = c.currentList().format()
                fmt.setIndent(max(1, fmt.indent()+amount))
                c.createList(fmt)
            else:
                fmt = c.blockFormat()
                fmt.setIndent(max(0, fmt.indent()+amount))
                c.setBlockFormat(fmt)

    def insert_table(self, rows, columns):
        if self.formatted.textCursor().currentTable():
            raise ValueError('Leave the current table before inserting another table. Nested tables are not supported.')
        self.validate_table(rows,columns)
        with self.operation('Insert table'):
            fmt=QTextTableFormat()
            fmt.setHeaderRowCount(0)
            fmt.setCellPadding(8)
            fmt.setCellSpacing(0)
            fmt.setBorder(1)
            fmt.setBorderBrush(QColor('#8291a7'))
            table=self.formatted.textCursor().insertTable(rows,columns,fmt)
            tabletools.set_widths(table,[160.0]*columns)
            self.formatted.setTextCursor(table.cellAt(0,0).firstCursorPosition())
        self.update_table_controls()

    def update_table_controls(self,*_):
        if not hasattr(self,'table_controls') or self.busy or self.depth: return
        table=self.formatted.textCursor().currentTable() if self.editable else None
        if table:
            cell=table.cellAt(self.formatted.textCursor())
            self.table_controls.update_selection(self.formatted.document(),table,cell.row(),cell.column())
        else:
            self.table_controls.hide()
        self.formatted.update_table_buttons() if hasattr(self.formatted,'update_table_buttons') else None

    def resize_column(self,value,column=None):
        table=self.formatted.textCursor().currentTable()
        if not table or not self.editable: return
        column=table.cellAt(self.formatted.textCursor()).column() if column is None else column
        current=tabletools.widths(self.formatted.document(),table)
        value=max(40,min(2000,value))
        if abs(current[column]-value)<0.5: return
        with self.operation('Resize column'):
            current[column]=value
            tabletools.set_widths(table,current)

    def resize_row(self,value,row=None):
        table=self.formatted.textCursor().currentTable()
        if not table or not self.editable: return
        row=table.cellAt(self.formatted.textCursor()).row() if row is None else row
        with self.operation('Resize row'):
            tabletools.set_row_height(self.formatted.document(),table,row,max(24,min(2000,value)))

    @staticmethod
    def validate_table(rows, columns):
        if not (1 <= rows <= 1000 and 1 <= columns <= 100 and rows*columns <= 20000):
            raise ValueError('Tables support 1–1,000 total rows, 1–100 columns and at most 20,000 cells.')

    def table_operation(self, op, rows=None, columns=None):
        c = self.formatted.textCursor()
        table = c.currentTable()
        if not table:
            raise ValueError('Place the cursor inside a table first.')
        cell = table.cellAt(c)
        new_rows = rows if rows is not None else table.rows()+int(op in ('row_above', 'row_below', 'append', 'duplicate_row'))
        new_cols = columns if columns is not None else table.columns()+int(op in ('col_left', 'col_right', 'duplicate_col'))
        self.validate_table(new_rows, new_cols)
        old_widths=tabletools.widths(self.formatted.document(),table)
        row,column=cell.row(),cell.column()
        with self.operation('Edit table'):
            if op == 'row_above': table.insertRows(cell.row(), 1)
            elif op == 'row_below': table.insertRows(cell.row()+1, 1)
            elif op == 'append': table.appendRows(1)
            elif op == 'col_left': table.insertColumns(cell.column(), 1)
            elif op == 'col_right': table.insertColumns(cell.column()+1, 1)
            elif op == 'del_row': table.removeRows(cell.row(), 1)
            elif op == 'del_col': table.removeColumns(cell.column(), 1)
            elif op == 'resize': table.resize(rows, columns)
            elif op == 'delete':
                first, last = table.firstPosition()-1, table.lastPosition()+1
                c.setPosition(first)
                c.setPosition(last, QTextCursor.MoveMode.KeepAnchor)
                c.removeSelectedText()
            elif op == 'equal_columns':
                tabletools.set_widths(table,[sum(old_widths)/len(old_widths)]*table.columns())
            elif op == 'equal_rows':
                _,ys=tabletools.grid(self.formatted.document(),table)
                height=max(ys[i+1]-ys[i] for i in range(table.rows()))
                for r in range(table.rows()): tabletools.set_row_height(self.formatted.document(),table,r,min(2000,max(24,height)))
            elif op == 'fit_row': tabletools.fit_row(table,row)
            elif op == 'fit_columns':
                metrics=QFontMetricsF(self.formatted.font())
                values=[]
                for col in range(table.columns()):
                    width=40
                    for r in range(table.rows()):
                        fragment,_=tabletools.cell_content(table.cellAt(r,col))
                        width=max(width,max((metrics.horizontalAdvance(line) for line in fragment.toPlainText().splitlines()),default=0)+24)
                    values.append(min(2000,width))
                tabletools.set_widths(table,values)
            elif op == 'duplicate_row':
                content=[tabletools.cell_content(table.cellAt(row,col)) for col in range(table.columns())]
                table.insertRows(row+1,1)
                for col,data in enumerate(content): tabletools.replace_cell(table.cellAt(row+1,col),data)
            elif op == 'duplicate_col':
                content=[tabletools.cell_content(table.cellAt(r,column)) for r in range(table.rows())]
                table.insertColumns(column+1,1)
                for r,data in enumerate(content): tabletools.replace_cell(table.cellAt(r,column+1),data)
            elif op in ('move_row_up','move_row_down'):
                other=row+(-1 if op=='move_row_up' else 1)
                if 0<=other<table.rows():
                    for col in range(table.columns()):
                        a,b=table.cellAt(row,col),table.cellAt(other,col)
                        first,second=tabletools.cell_content(a),tabletools.cell_content(b)
                        tabletools.replace_cell(a,second); tabletools.replace_cell(b,first)
            elif op in ('move_col_left','move_col_right'):
                other=column+(-1 if op=='move_col_left' else 1)
                if 0<=other<table.columns():
                    for r in range(table.rows()):
                        a,b=table.cellAt(r,column),table.cellAt(r,other)
                        first,second=tabletools.cell_content(a),tabletools.cell_content(b)
                        tabletools.replace_cell(a,second); tabletools.replace_cell(b,first)
                    old_widths[column],old_widths[other]=old_widths[other],old_widths[column]
                    tabletools.set_widths(table,old_widths)
            elif op.startswith('align_'):
                align = {'align_left': Qt.AlignmentFlag.AlignLeft,
                         'align_center': Qt.AlignmentFlag.AlignHCenter,
                         'align_right': Qt.AlignmentFlag.AlignRight}[op]
                for row in range(table.rows()):
                    cursor = table.cellAt(row, cell.column()).firstCursorPosition()
                    fmt = cursor.blockFormat()
                    fmt.setAlignment(align)
                    cursor.setBlockFormat(fmt)

            if op in ('col_left','col_right','duplicate_col'):
                insert=column+int(op in ('col_right','duplicate_col'))
                old_widths.insert(insert,old_widths[column])
                tabletools.set_widths(table,old_widths)
            elif op=='del_col' and len(old_widths)>1:
                old_widths.pop(column)
                tabletools.set_widths(table,old_widths)
            elif op=='resize':
                values=old_widths[:columns]+[160.0]*max(0,columns-len(old_widths))
                tabletools.set_widths(table,values)
            # Keep the caret with the affected cell instead of letting fragment edits move it.
            if any(frame is table for frame in tabletools.tables(self.formatted.document())):
                target_row=row+int(op in ('row_below','duplicate_row'))
                target_column=column+int(op in ('col_right','duplicate_col'))
                if op=='move_row_up': target_row=max(0,row-1)
                elif op=='move_row_down': target_row=min(table.rows()-1,row+1)
                elif op=='move_col_left': target_column=max(0,column-1)
                elif op=='move_col_right': target_column=min(table.columns()-1,column+1)
                self.formatted.setTextCursor(table.cellAt(min(target_row,table.rows()-1),min(target_column,table.columns()-1)).firstCursorPosition())
        self.update_table_controls()

    def paste_cells_safely(self,text):
        try: self.paste_cells(text)
        except ValueError as exc: self.operation_error.emit(str(exc))

    def paste_cells(self, text):
        table=self.formatted.textCursor().currentTable()
        if not table: return
        start=table.cellAt(self.formatted.textCursor())
        rows=[line.split('\t') for line in text.rstrip('\n').splitlines()]
        if not rows: return
        new_rows=max(table.rows(),start.row()+len(rows))
        new_cols=max(table.columns(),start.column()+max(map(len,rows)))
        self.validate_table(new_rows,new_cols)
        old_widths=tabletools.widths(self.formatted.document(),table)
        with self.operation('Paste cells'):
            table.resize(new_rows,new_cols)
            tabletools.set_widths(table,old_widths+[160.0]*max(0,new_cols-len(old_widths)))
            for r,values in enumerate(rows):
                for col,value in enumerate(values):
                    cell=table.cellAt(start.row()+r,start.column()+col)
                    c=cell.firstCursorPosition()
                    c.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
                    c.insertText(value)

    def add_image(self, raw, alt='Image', drawing=None, replace=None, width=None):
        image = decode_image(raw)
        # Canonical PNG makes package MIME and resource names unambiguous.
        raw = png_bytes(image)
        from uuid import uuid4
        key = f'assets/{uuid4()}.png'
        if drawing is not None:
            # Distinct identities allow undo of drawing edits without overwriting prior strokes.
            from uuid import uuid4
            key = f'assets/{uuid4()}.png'
            self.note.drawings[key] = copy.deepcopy(drawing)
        self.note.assets[key] = raw
        self.formatted.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(key), image)
        with self.operation('Update image' if replace else 'Insert image'):
            cursor = self.formatted.textCursor()
            if replace:
                position = self.image_position(replace)
                if position is None:
                    raise ValueError('Image is no longer in this document.')
                cursor.setPosition(position)
                cursor.setPosition(position+1, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextImageFormat()
            fmt.setName(key)
            fmt.setProperty(QTextFormat.Property.ImageAltText, alt)
            w = width or min(600, image.width())
            fmt.setWidth(w)
            fmt.setHeight(w*image.height()/image.width())
            cursor.insertImage(fmt)
            self.formatted.setTextCursor(cursor)
        return key

    def start_drawing(self,key=None):
        from .drawing import InlineDrawing
        if self.ink: self.ink.finish()
        if not self.note.rich: self.make_rich()
        self.view('formatted')
        self.ink=InlineDrawing(self,key)
        self.position_changed.emit()

    def image_position(self, name):
        block = self.formatted.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if (frag.isValid() and frag.charFormat().isImageFormat() and
                        frag.charFormat().toImageFormat().name() == name):
                    return frag.position()
                it += 1
            block = block.next()
        return None

    def eventFilter(self, obj, event):
        # QTextEdit/QPlainTextEdit otherwise claim these keys for their disabled
        # native history before the window action can reach our shared stack.
        if event.type() in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress):
            modifiers=event.modifiers()
            undo=event.key()==Qt.Key.Key_Z and modifiers==Qt.KeyboardModifier.ControlModifier
            redo=(event.key()==Qt.Key.Key_Y and modifiers==Qt.KeyboardModifier.ControlModifier) or (
                event.key()==Qt.Key.Key_Z and modifiers==(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier))
            if undo or redo:
                event.accept()
                if event.type()==QEvent.Type.KeyPress:
                    self.stack.undo() if undo else self.stack.redo()
                return True
        if (event.type()==QEvent.Type.KeyPress and getattr(self,'autocorrect_enabled',False) and
                event.key()==Qt.Key.Key_Space and not obj.isReadOnly()):
            QTimer.singleShot(0,self.autocorrect_last_word)
        return super().eventFilter(obj,event)

    def autocorrect_last_word(self):
        if self.active.isReadOnly(): return
        cursor=self.active.textCursor()
        if cursor.blockFormat().property(QTextFormat.Property.BlockCodeFence): return
        before=cursor.block().text()[:cursor.positionInBlock()]
        match=re.search(r'\b(teh|adn|recieve|seperate) $',before,re.I)
        if not match: return
        if not self.note.rich and self.note.kind=='md':
            prefix=self.note.source[:len(self.note.source)]
            if prefix.count('```')%2: return
        word=match.group(1)
        replacement={'teh':'the','adn':'and','recieve':'receive','seperate':'separate'}[word.lower()]
        if word[0].isupper(): replacement=replacement.capitalize()
        with self.operation('Autocorrect'):
            cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
            for _ in word: cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter,QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)

    def refresh_contrast(self):
        # View-only selections keep light-filled legacy cells readable in dark mode.
        # Unlike changing character formats, this never modifies the saved document.
        selections=[]
        default=self.formatted.palette().text().color().lightness()
        for table in tabletools.tables(self.formatted.document()) if self.note.rich else []:
            for row in range(table.rows()):
                for col in range(table.columns()):
                    cell=table.cellAt(row,col)
                    background=cell.format().background()
                    if background.style()==Qt.BrushStyle.NoBrush: continue
                    light=background.color().lightness()
                    color=QColor('#253247') if light>170 and default>160 else QColor('#e8ebf0') if light<80 and default<80 else None
                    if color is None: continue
                    cursor=cell.firstCursorPosition()
                    cursor.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
                    if cursor.hasSelection():
                        selection=QTextEdit.ExtraSelection()
                        selection.cursor=cursor
                        selection.format.setForeground(color)
                        selections.append(selection)
        self.formatted.setExtraSelections(selections)

    def remember_position(self):
        self.note.cursor = self.active.textCursor().position()
        self.note.scroll = self.active.verticalScrollBar().value()
