"""Table geometry and native contextual controls.

Dimensions are document pixels. Row height is a minimum: content is never clipped.
"""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFontMetricsF, QTextCursor, QTextDocumentFragment, QTextLength, QTextTableCellFormat, QTextFormat
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
                              QSpinBox, QToolButton, QWidget)


BASE_PADDING = 8.0


def tables(document):
    from PySide6.QtGui import QTextTable
    return [frame for frame in document.rootFrame().childFrames() if isinstance(frame, QTextTable)]


def grid(document, table):
    """Return outer cell boundaries in document coordinates, including padding."""
    layout = document.documentLayout()
    layout.documentSize()  # Ensure layout has been recalculated after an edit.
    default = table.format().cellPadding()
    border = table.format().border()
    def padding(cell, side):
        fmt = cell.format().toTableCellFormat()
        prop = {'left': fmt.leftPadding, 'right': fmt.rightPadding,
                'top': fmt.topPadding, 'bottom': fmt.bottomPadding}[side]
        property_name=getattr(QTextFormat.Property,'TableCell'+side.capitalize()+'Padding')
        return prop() if fmt.hasProperty(property_name) else default
    xs = []
    for column in range(table.columns()):
        cell = table.cellAt(0, column)
        block = layout.blockBoundingRect(cell.firstCursorPosition().block())
        xs.append(block.left() - padding(cell, 'left') - border/2)
    cell = table.cellAt(0, table.columns()-1)
    block = layout.blockBoundingRect(cell.firstCursorPosition().block())
    xs.append(block.right() + padding(cell, 'right') + border/2)
    ys = []
    for row in range(table.rows()):
        tops = []
        for column in range(table.columns()):
            cell = table.cellAt(row,column)
            block = layout.blockBoundingRect(cell.firstCursorPosition().block())
            tops.append(block.top() - padding(cell,'top') - border/2)
        ys.append(min(tops))
    bottoms = []
    for column in range(table.columns()):
        cell = table.cellAt(table.rows()-1,column)
        block = layout.blockBoundingRect(cell.lastCursorPosition().block())
        bottoms.append(block.bottom() + padding(cell,'bottom') + border/2)
    ys.append(max(bottoms))
    return xs,ys


def widths(document,table):
    constraints = table.format().columnWidthConstraints()
    if len(constraints)==table.columns() and all(v.type()==QTextLength.Type.FixedLength for v in constraints):
        return [v.rawValue() for v in constraints]
    xs,_ = grid(document,table)
    return [max(40,xs[i+1]-xs[i]) for i in range(table.columns())]


def set_widths(table,values):
    if any(not 40<=value<=2000 for value in values):
        raise ValueError('Column widths must be between 40 and 2,000 px.')
    fmt = table.format()
    fmt.setColumnWidthConstraints([QTextLength(QTextLength.Type.FixedLength,float(v)) for v in values])
    fmt.setWidth(QTextLength(QTextLength.Type.FixedLength,sum(values)))
    table.setFormat(fmt)


def set_row_height(document,table,row,height):
    if not 24<=height<=2000:
        raise ValueError('Row minimum heights must be between 24 and 2,000 px.')
    layout=document.documentLayout()
    layout.documentSize()
    content=[]
    for column in range(table.columns()):
        cell=table.cellAt(row,column)
        first=layout.blockBoundingRect(cell.firstCursorPosition().block())
        last=layout.blockBoundingRect(cell.lastCursorPosition().block())
        content.append(last.bottom()-first.top())
    extra=max(0,height-max(content)-BASE_PADDING*2-table.format().border())/2
    for column in range(table.columns()):
        cell=table.cellAt(row,column)
        fmt=cell.format().toTableCellFormat()
        fmt.setTopPadding(BASE_PADDING+extra)
        fmt.setBottomPadding(BASE_PADDING+extra)
        cell.setFormat(fmt)


def fit_row(table,row):
    for column in range(table.columns()):
        cell=table.cellAt(row,column)
        fmt=cell.format().toTableCellFormat()
        fmt.setTopPadding(BASE_PADDING)
        fmt.setBottomPadding(BASE_PADDING)
        cell.setFormat(fmt)


def cell_content(cell):
    cursor=cell.firstCursorPosition()
    cursor.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
    return QTextDocumentFragment(cursor),QTextTableCellFormat(cell.format().toTableCellFormat())


def replace_cell(cell,content):
    fragment,fmt=content
    cursor=cell.firstCursorPosition()
    cursor.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
    cursor.insertFragment(fragment)
    cell.setFormat(fmt)


class TableControls(QWidget):
    command = Signal(str)
    column_width = Signal(int)
    row_height = Signal(int)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('TableControls')
        layout=QGridLayout(self)
        layout.setContentsMargins(12,6,12,6)
        self.items=[]
        self.position=QLabel('Table')
        self.items.append(self.position)
        for label,ops in [('+ Row',[('Insert above','row_above'),('Insert below','row_below')]),
                          ('+ Column',[('Insert left','col_left'),('Insert right','col_right')])]:
            button=QToolButton()
            button.setText(label)
            button.setAccessibleName(label.replace('+','Add'))
            menu=QMenu(button)
            for text,op in ops: menu.addAction(text,lambda checked=False,op=op:self.command.emit(op))
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.items.append(button)
        self.items.append(QLabel('Column width'))
        self.width_input=QSpinBox()
        self.width_input.setRange(40,2000)
        self.width_input.setSuffix(' px')
        self.width_input.setKeyboardTracking(False)
        self.width_input.setFixedWidth(90)
        self.width_input.setAccessibleName('Selected column width')
        self.width_input.editingFinished.connect(lambda:self.column_width.emit(self.width_input.value()))
        self.items.append(self.width_input)
        self.items.append(QLabel('Min row height'))
        self.height_input=QSpinBox()
        self.height_input.setRange(24,2000)
        self.height_input.setSuffix(' px')
        self.height_input.setKeyboardTracking(False)
        self.height_input.setFixedWidth(90)
        self.height_input.setAccessibleName('Selected row minimum height')
        self.height_input.setToolTip('Rows grow when their content needs more space.')
        self.height_input.editingFinished.connect(lambda:self.row_height.emit(self.height_input.value()))
        self.items.append(self.height_input)
        self.more=QToolButton()
        self.more.setText('More ⋯')
        self.more.setAccessibleName('More table actions')
        menu=QMenu(self.more)
        for text,op in [('Table size…','resize'),('Size columns equally','equal_columns'),
                        ('Size rows equally','equal_rows'),('Fit columns to content','fit_columns'),
                        ('Fit this row to content','fit_row'),('Duplicate row','duplicate_row'),
                        ('Duplicate column','duplicate_col'),('Move row up','move_row_up'),
                        ('Move row down','move_row_down'),('Move column left','move_col_left'),
                        ('Move column right','move_col_right'),('Delete row','del_row'),
                        ('Delete column','del_col'),('Delete table','delete')]:
            menu.addAction(text,lambda checked=False,op=op:self.command.emit(op))
        self.more.setMenu(menu)
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.items.append(self.more)
        self.set_compact(False)
        self.setVisible(False)

    def set_compact(self,compact):
        self.compact=compact
        layout=self.layout()
        while layout.count(): layout.takeAt(0)
        for col in range(9): layout.setColumnStretch(col,0)
        if compact:
            self.items[3].setText('Column width')
            self.items[5].setText('Min row height')
            self.more.setText('More ⋯')
            layout.setContentsMargins(0,0,0,0)
            layout.addWidget(self.items[0],0,0,1,2)
            layout.addWidget(self.items[1],1,0)
            layout.addWidget(self.items[2],1,1)
            for row,label,field in ((2,3,4),(3,5,6)):
                layout.addWidget(self.items[label],row,0)
                layout.addWidget(self.items[field],row,1)
            layout.addWidget(self.more,4,0,1,2)
        else:
            self.items[3].setText('Width')
            self.items[5].setText('Height')
            self.more.setText('⋯')
            layout.setContentsMargins(8,2,8,2)
            for col,widget in enumerate(self.items): layout.addWidget(widget,0,col)
            layout.setColumnStretch(8,1)

    def update_selection(self,document,table,row,column):
        if table is None:
            self.hide()
            return
        self.position.setText(f'Row {row+1}/{table.rows()} · Col {column+1}/{table.columns()}' if self.compact else f'R{row+1} · C{column+1}')
        xs,ys=grid(document,table)
        for spin,value in ((self.width_input,widths(document,table)[column]),
                           (self.height_input,ys[row+1]-ys[row])):
            if spin.hasFocus(): continue
            spin.blockSignals(True)
            spin.setValue(round(value))
            spin.blockSignals(False)
        self.show()
