"""Small native controls for structured document insertion."""
from PySide6.QtCore import Qt,QRect,Signal
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QWidget


class TablePicker(QWidget):
    chosen=Signal(int,int)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.cols,self.rows=0,0
        self.setFixedSize(228,190)
        self.setMouseTracking(True)
        self.setAccessibleName('Table grid picker; use Custom Size for keyboard entry')
    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),self.palette().window())
        p.setPen(self.palette().text().color())
        p.drawText(10,21,f'{self.cols} columns × {self.rows} rows' if self.cols else 'Choose a table size')
        for row in range(6):
            for col in range(8):
                rect=QRect(10+col*26,34+row*25,22,21)
                p.fillRect(rect,QColor('#88afe0') if col<self.cols and row<self.rows else self.palette().base())
                p.setPen(QColor('#9ba7b7')); p.drawRect(rect)
    def mouseMoveEvent(self,event):
        self.cols=max(0,min(8,int((event.position().x()-10)//26)+1))
        self.rows=max(0,min(6,int((event.position().y()-34)//25)+1))
        self.update()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.cols and self.rows:
            self.chosen.emit(self.rows,self.cols)
