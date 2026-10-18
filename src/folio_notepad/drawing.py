"""Editable vector strokes with a portable JSON model and PNG preview."""
import copy
import math
from PySide6.QtCore import QObject, QEvent, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTextCursor, QUndoCommand, QUndoStack, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox,
    QToolButton, QVBoxLayout, QWidget)
from .storage import validate_drawing
from .editor import png_bytes


def paint_stroke(painter, stroke, width, height):
    points = [QPointF(x*width, y*height) for x, y in stroke['points']]
    if not points:
        return
    painter.save()
    color = QColor(stroke['color'])
    if stroke['tool'] == 'highlighter': color.setAlpha(85)
    painter.setPen(QPen(color, stroke['width'], Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    tool = stroke['tool']
    if tool in ('pen', 'highlighter'):
        path = QPainterPath(points[0])
        for point in points[1:]: path.lineTo(point)
        if len(points) == 1: painter.drawPoint(points[0])
        else: painter.drawPath(path)
    else:
        a, b = points[0], points[-1]
        rect = QRectF(a, b).normalized()
        if tool == 'rectangle': painter.drawRect(rect)
        elif tool == 'ellipse': painter.drawEllipse(rect)
        else:
            painter.drawLine(a, b)
            if tool == 'arrow':
                angle = math.atan2(b.y()-a.y(), b.x()-a.x())
                for delta in (-0.5, 0.5):
                    end = QPointF(b.x()-18*math.cos(angle+delta), b.y()-18*math.sin(angle+delta))
                    painter.drawLine(b, end)
    painter.restore()


class DrawingCommand(QUndoCommand):
    def __init__(self, canvas, before, after):
        super().__init__('Drawing stroke')
        self.canvas, self.before, self.after = canvas, before, after

    def undo(self):
        self.canvas.strokes = copy.deepcopy(self.before)
        self.canvas.update()

    def redo(self):
        self.canvas.strokes = copy.deepcopy(self.after)
        self.canvas.update()


class Canvas(QWidget):
    def __init__(self, model=None, parent=None):
        super().__init__(parent)
        if model: validate_drawing(model)
        self.strokes = copy.deepcopy(model['strokes']) if model else []
        self.current = None
        self.before = []
        self.stack = QUndoStack(self)
        self.stack.setUndoLimit(100)
        self.tool, self.color, self.stroke_width = 'pen', '#26364b', 3
        self.setFixedSize(900, 520)
        self.setAccessibleName('Drawing canvas')
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for stroke in self.strokes + ([self.current] if self.current else []):
            paint_stroke(p, stroke, self.width_px(), self.height())

    def width_px(self):
        return QWidget.width(self)

    def point(self, pos):
        return [max(0, min(1, pos.x()/self.width_px())), max(0, min(1, pos.y()/self.height()))]

    def begin(self, pos):
        self.before = copy.deepcopy(self.strokes)
        point = self.point(pos)
        if self.tool == 'eraser':
            self.erase(point)
        else:
            self.current = {'tool': self.tool, 'color': self.color, 'width': self.stroke_width, 'points': [point]}
        self.update()

    def move(self, pos):
        point = self.point(pos)
        if self.tool == 'eraser': self.erase(point)
        elif self.current:
            if self.tool in ('pen', 'highlighter'):
                if len(self.current['points']) < 20000: self.current['points'].append(point)
            else: self.current['points'] = [self.current['points'][0], point]
        self.update()

    def end(self):
        if self.current:
            self.strokes.append(self.current)
            self.current = None
        if self.before != self.strokes:
            self.stack.push(DrawingCommand(self, self.before, copy.deepcopy(self.strokes)))
        self.update()

    def erase(self, point):
        px,py=point[0]*self.width_px(),point[1]*self.height()
        def hit(stroke):
            points=[(a*self.width_px(),b*self.height()) for a,b in stroke['points']]
            radius=12+stroke['width']/2
            for a,b in zip(points,points[1:] or points):
                dx,dy=b[0]-a[0],b[1]-a[1]
                factor=max(0,min(1,((px-a[0])*dx+(py-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
                if math.hypot(px-a[0]-factor*dx,py-a[1]-factor*dy)<=radius: return True
            return False
        self.strokes=[s for s in self.strokes if not hit(s)]

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.begin(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton: self.move(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.end()

    def tabletEvent(self, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.TabletPress: self.begin(event.position())
        elif event.type() == QEvent.Type.TabletMove: self.move(event.position())
        elif event.type() == QEvent.Type.TabletRelease: self.end()
        event.accept()

    def model(self):
        model = {'version': 1, 'strokes': copy.deepcopy(self.strokes)}
        validate_drawing(model)
        return model

    def image(self):
        image = QImage(900, 520, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for stroke in self.strokes: paint_stroke(p, stroke, 900, 520)
        p.end()
        return png_bytes(image)


class DrawingDialog(QDialog):
    def __init__(self, model=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Drawing — Folio Notepad')
        self.resize(1160, 760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,16,20,16)
        layout.setSpacing(16)
        heading=QLabel('Make room for a little imagination.')
        heading.setObjectName('PanelTitle')
        layout.addWidget(heading)
        toolbar = QHBoxLayout()
        self.canvas = Canvas(model)
        color = QPushButton('Color…')
        def pick():
            value = QColorDialog.getColor(QColor(self.canvas.color), self)
            if value.isValid(): self.canvas.color = value.name()
        color.clicked.connect(pick)
        toolbar.addWidget(color)
        width = QSpinBox()
        width.setAccessibleName('Drawing stroke width')
        width.setRange(1, 40)
        width.setValue(3)
        width.setSuffix(' px')
        width.valueChanged.connect(lambda n: setattr(self.canvas, 'stroke_width', n))
        toolbar.addWidget(QLabel('Stroke'))
        toolbar.addWidget(width)
        self.undo_action=self.canvas.stack.createUndoAction(self,'Undo')
        self.undo_action.setShortcut(QKeySequence('Ctrl+Z'))
        self.addAction(self.undo_action)
        self.redo_action=self.canvas.stack.createRedoAction(self,'Redo')
        self.redo_action.setShortcuts([QKeySequence('Ctrl+Y'),QKeySequence('Ctrl+Shift+Z')])
        self.addAction(self.redo_action)
        undo = QPushButton('Undo')
        undo.clicked.connect(self.canvas.stack.undo)
        toolbar.addWidget(undo)
        redo = QPushButton('Redo')
        redo.clicked.connect(self.canvas.stack.redo)
        toolbar.addWidget(redo)
        clear = QPushButton('Clear')
        def reset():
            self.canvas.stack.push(DrawingCommand(self.canvas, copy.deepcopy(self.canvas.strokes), []))
        clear.clicked.connect(reset)
        toolbar.addWidget(clear)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        workspace=QHBoxLayout()
        workspace.setSpacing(16)
        tools=QFrame()
        tools.setObjectName('DrawingTools')
        tools.setFixedWidth(146)
        tool_layout=QVBoxLayout(tools)
        tool_layout.setContentsMargins(0,0,0,0)
        tool_layout.setSpacing(6)
        from .workspace import caption, icon
        tool_layout.addWidget(caption('DRAW & SHAPE'))
        self.tool_group=QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons={}
        for text,key,mark in [('Pen','pen','draw'),('Highlighter','highlighter','draw'),
                              ('Stroke eraser','eraser','eraser'),('Line','line','line'),
                              ('Rectangle','rectangle','rectangle'),('Ellipse','ellipse','ellipse'),('Arrow','arrow','arrow')]:
            b=QToolButton()
            b.setText(text); b.setAccessibleName(text)
            b.setIcon(icon(mark,self.palette()))
            b.setIconSize(QSize(20,20))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setCheckable(True); b.setChecked(key=='pen')
            self.tool_group.addButton(b)
            b.clicked.connect(lambda checked=False,key=key:setattr(self.canvas,'tool',key))
            tool_layout.addWidget(b)
            self.tool_buttons[key]=b
        tool_layout.addSpacing(20)
        tool_layout.addWidget(caption('QUICK COLOURS'))
        swatches=QGridLayout()
        for i,value in enumerate(('#26364b','#7953d8','#e15d76','#de9234','#268875','#367bd6')):
            b=QPushButton()
            b.setFixedSize(30,30)
            b.setAccessibleName('Ink '+value)
            b.setToolTip(value)
            b.setStyleSheet(f'background:{value};border:2px solid palette(mid);border-radius:15px;')
            b.clicked.connect(lambda checked=False,value=value:setattr(self.canvas,'color',value))
            swatches.addWidget(b,i//3,i%3)
        tool_layout.addLayout(swatches)
        tool_layout.addStretch()
        workspace.addWidget(tools)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        backdrop=QWidget()
        backdrop.setObjectName('DrawingBackdrop')
        paper=QVBoxLayout(backdrop)
        paper.setContentsMargins(24,24,24,24)
        paper.addWidget(self.canvas,alignment=Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(backdrop)
        workspace.addWidget(scroll,1)
        layout.addLayout(workspace,1)
        layout.addWidget(QLabel('Draw with your mouse or pen. Drawings stay editable in .folio notes.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Update drawing' if model else 'Insert drawing')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class InlineCanvas(Canvas):
    """Ink over the actual drawing image in a note, using the note's history."""
    def __init__(self,session):
        super().__init__(parent=session.editor.formatted.viewport())
        self.session=session
        self.setMinimumSize(0,0)
        self.setMaximumSize(16777215,16777215)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Draw directly in this note')

    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),Qt.GlobalColor.white)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.save()
        p.scale(self.width_px()/900,self.height()/520)
        for stroke in self.strokes+([self.current] if self.current else []):
            paint_stroke(p,stroke,900,520)
        p.restore()
        p.setPen(QPen(QColor('#b5a6df'),1,Qt.PenStyle.DashLine))
        p.drawRoundedRect(self.rect().adjusted(0,0,-1,-1),5,5)

    def end(self):
        if self.current:
            self.strokes.append(self.current)
            self.current=None
        if self.before!=self.strokes: self.session.commit()
        self.update()

    def event(self,event):
        from PySide6.QtCore import QEvent
        if event.type() in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress):
            mods=event.modifiers()
            ctrl=Qt.KeyboardModifier.ControlModifier
            undo=event.key()==Qt.Key.Key_Z and mods==ctrl
            redo=(event.key()==Qt.Key.Key_Y and mods==ctrl) or (event.key()==Qt.Key.Key_Z and mods==(ctrl|Qt.KeyboardModifier.ShiftModifier))
            if undo or redo:
                event.accept()
                if event.type()==QEvent.Type.KeyPress:
                    self.session.editor.stack.undo() if undo else self.session.editor.stack.redo()
                return True
            if event.key()==Qt.Key.Key_Escape:
                event.accept()
                if event.type()==QEvent.Type.KeyPress: self.session.finish()
                return True
        return super().event(event)

    def wheelEvent(self,event):
        bar=self.session.editor.formatted.verticalScrollBar()
        delta=event.pixelDelta().y() or event.angleDelta().y()
        bar.setValue(bar.value()-delta)
        event.accept()


class InlineDrawing(QObject):
    """Each completed stroke becomes a versioned, undoable image in the document."""
    def __init__(self,editor,key=None):
        super().__init__(editor)
        self.editor=editor
        self.keys=set()
        self.key=key
        self.finished=False
        self.committing=True
        self.canvas=InlineCanvas(self)
        edit=editor.formatted
        if key:
            if key not in editor.note.drawings or editor.image_position(key) is None:
                self.canvas.deleteLater()
                raise ValueError('Drawing is no longer in this note.')
            self.canvas.strokes=copy.deepcopy(editor.note.drawings[key]['strokes'])
        else:
            available=edit.document().documentLayout().blockBoundingRect(edit.textCursor().block()).width()
            width=max(80,min(600,available,edit.viewport().width()-24))
            self.key=editor.add_image(self.canvas.image(),'Drawing',self.canvas.model(),width=width)
        self.keys.add(self.key)
        self.committing=False
        edit.viewport().installEventFilter(self)
        edit.verticalScrollBar().valueChanged.connect(self.sync)
        edit.horizontalScrollBar().valueChanged.connect(self.sync)
        edit.document().documentLayout().documentSizeChanged.connect(self.sync)
        editor.stack.indexChanged.connect(self.sync)
        self.sync()
        edit.ensureCursorVisible()
        self.canvas.setFocus()

    def image_format(self):
        position=self.editor.image_position(self.key)
        cursor=QTextCursor(self.editor.formatted.document())
        cursor.setPosition(position)
        cursor.setPosition(position+1,QTextCursor.MoveMode.KeepAnchor)
        return cursor.charFormat().toImageFormat()

    def commit(self):
        try:
            model=self.canvas.model()
            width=self.image_format().width()
            self.committing=True
            key=self.editor.add_image(self.canvas.image(),'Drawing',model,replace=self.key,width=width)
            self.key=key
            self.keys.add(key)
        except ValueError as exc:
            self.canvas.strokes=copy.deepcopy(self.canvas.before)
            self.editor.operation_error.emit(str(exc))
        finally:
            self.committing=False
        self.sync()

    def sync(self,*_):
        if self.finished or self.committing or self.editor.busy: return
        if not self.editor.editable:
            self.finish()
            return
        position=self.editor.image_position(self.key)
        if position is None:
            for key in self.keys:
                position=self.editor.image_position(key)
                if position is not None:
                    self.key=key
                    break
            else:
                self.finish()
                return
        self.canvas.strokes=copy.deepcopy(self.editor.note.drawings[self.key]['strokes'])
        cursor=QTextCursor(self.editor.formatted.document())
        cursor.setPosition(position)
        rect=self.editor.formatted.cursorRect(cursor)
        fmt=self.image_format()
        bounds=QRect(rect.x(),rect.y(),round(fmt.width()),round(fmt.height()))
        self.canvas.setGeometry(bounds)
        self.canvas.setVisible(bounds.intersects(self.editor.formatted.viewport().rect()))
        self.canvas.raise_()
        self.canvas.update()

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Resize:
            self.sync()
        return False

    def finish(self):
        if self.finished: return
        self.finished=True
        edit=self.editor.formatted
        edit.viewport().removeEventFilter(self)
        for signal in (edit.verticalScrollBar().valueChanged,edit.horizontalScrollBar().valueChanged,
                       edit.document().documentLayout().documentSizeChanged,self.editor.stack.indexChanged):
            signal.disconnect(self.sync)
        self.canvas.hide()
        self.canvas.deleteLater()
        self.editor.ink=None
        self.editor.position_changed.emit()
        edit.setFocus()
        self.deleteLater()


class InlineDrawingTools(QWidget):
    """Compact tools replace text formatting while the current note is in ink mode."""
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.setObjectName('InlineDrawingTools')
        layout=QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(3)
        from .workspace import icon
        self.tool_buttons={}
        for label,key,mark in [('Pen','pen','draw'),('Highlighter','highlighter','draw'),('Eraser','eraser','eraser')]:
            b=QToolButton()
            b.setIcon(icon(mark,window.controller.app.palette()))
            b.setProperty('folioIcon',mark)
            b.setToolTip(label); b.setAccessibleName(label)
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False,key=key:self.choose(key))
            layout.addWidget(b)
            self.tool_buttons[key]=b
        shape=QToolButton()
        shape.setProperty('folioIcon','rectangle')
        shape.setAccessibleName('Drawing shapes'); shape.setToolTip('Line, rectangle, ellipse or arrow')
        from PySide6.QtWidgets import QMenu
        menu=QMenu(shape)
        for label,key in [('Line','line'),('Rectangle','rectangle'),('Ellipse','ellipse'),('Arrow','arrow')]:
            menu.addAction(label,lambda checked=False,key=key:self.choose(key))
        shape.setMenu(menu); shape.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(shape)
        self.shape_button=shape
        color=QToolButton(); color.setText('Ink'); color.setAccessibleName('Drawing ink colour')
        color.clicked.connect(self.pick_color); layout.addWidget(color)
        self.color_button=color
        self.width=QSpinBox(); self.width.setRange(1,40); self.width.setSuffix(' px')
        self.width.setFixedWidth(72); self.width.setAccessibleName('Drawing stroke width')
        self.width.setKeyboardTracking(False)
        self.width.valueChanged.connect(self.set_width)
        layout.addWidget(self.width)
        clear=QToolButton(); clear.setText('Clear'); clear.setToolTip('Clear drawing (can be undone)')
        clear.clicked.connect(self.clear); layout.addWidget(clear)
        done=QToolButton(); done.setText('Text'); done.setObjectName('SoftAccentButton')
        done.setToolTip('Return to typing (Esc)'); done.setAccessibleName('Finish drawing and return to text')
        done.clicked.connect(self.finish); layout.addWidget(done)

    @property
    def session(self):
        return self.window.editor.ink if self.window.editor else None

    def choose(self,key):
        if self.session:
            self.session.canvas.tool=key
            self.refresh()
            self.session.canvas.setFocus()

    def set_width(self,value):
        if self.session: self.session.canvas.stroke_width=value

    def pick_color(self):
        if not self.session: return
        color=QColorDialog.getColor(QColor(self.session.canvas.color),self.window,'Drawing ink')
        if color.isValid(): self.session.canvas.color=color.name()
        self.refresh()

    def clear(self):
        if self.session and self.session.canvas.strokes:
            canvas=self.session.canvas
            canvas.before=copy.deepcopy(canvas.strokes)
            canvas.strokes=[]
            self.session.commit()

    def finish(self):
        if self.session: self.session.finish()

    def refresh(self):
        session=self.session
        if not session: return
        for key,b in self.tool_buttons.items(): b.setChecked(session.canvas.tool==key)
        shape=session.canvas.tool in ('line','rectangle','ellipse','arrow')
        self.shape_button.setProperty('folioIcon',session.canvas.tool if shape else 'rectangle')
        from .workspace import icon
        self.shape_button.setIcon(icon(session.canvas.tool if shape else 'rectangle',self.window.controller.app.palette()))
        self.width.blockSignals(True); self.width.setValue(session.canvas.stroke_width); self.width.blockSignals(False)
        self.color_button.setStyleSheet(f'border-bottom: 3px solid {session.canvas.color};')
