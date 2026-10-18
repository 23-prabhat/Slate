"""Paged printing with native printer settings and Notepad-style header tokens."""
import math
import re
from PySide6.QtCore import QDateTime,QRectF,QSizeF,Qt,QUrl
from PySide6.QtGui import QFont,QPainter,QTextDocument,QAbstractTextDocumentLayout,QPalette,QColor


def expand_header(template,title,page):
    now=QDateTime.currentDateTime()
    values={'&f':title,'&p':str(page),'&d':now.toString('yyyy-MM-dd'),'&t':now.toString('hh:mm'),'&&':'&'}
    return re.sub(r'&&|&[fpdt]',lambda m:values[m.group()],template)


def draw_header(painter,template,title,page,rect):
    text=expand_header(template,title,page)
    sections=re.split(r'(&[lcr])',text)
    alignment=Qt.AlignmentFlag.AlignHCenter
    for part in sections:
        if part in ('&l','&c','&r'):
            alignment={'&l':Qt.AlignmentFlag.AlignLeft,'&c':Qt.AlignmentFlag.AlignHCenter,'&r':Qt.AlignmentFlag.AlignRight}[part]
        elif part:
            painter.drawText(rect,alignment|Qt.AlignmentFlag.AlignVCenter,part)


def print_document(document,printer,title,header='&f',footer='Page &p'):
    doc=document.clone()
    from .editor import decode_image
    for key,raw in getattr(document,'assets',{}).items():
        try:
            doc.addResource(QTextDocument.ResourceType.ImageResource,QUrl(key),decode_image(raw))
        except ValueError: pass
    scale=printer.logicalDpiX()/96
    rect=printer.pageLayout().paintRectPixels(printer.resolution())
    width,height=rect.width()/scale,rect.height()/scale
    head=30 if header else 0
    foot=30 if footer else 0
    body_height=height-head-foot
    if body_height<=0: raise OSError('Printable page is too small.')
    doc.setPageSize(QSizeF(width,body_height))
    painter=QPainter()
    if not painter.begin(printer): raise OSError('Could not open the printer or output file.')
    first=max(1,printer.fromPage() or 1)
    last=min(doc.pageCount(),printer.toPage() or doc.pageCount())
    try:
        for page in range(first,last+1):
            if page!=first and not printer.newPage(): raise OSError('Could not create the next print page.')
            painter.save()
            painter.scale(scale,scale)
            header_font=QFont('sans-serif')
            header_font.setPixelSize(12)
            painter.setFont(header_font)
            if header: draw_header(painter,header,title,page,QRectF(0,0,width,head))
            if footer: draw_header(painter,footer,title,page,QRectF(0,height-foot,width,foot))
            painter.translate(0,head-(page-1)*body_height)
            clip=QRectF(0,(page-1)*body_height,width,body_height)
            painter.setClipRect(clip)
            context=QAbstractTextDocumentLayout.PaintContext()
            context.clip=clip
            # Print on white paper even when the editor follows a dark desktop palette.
            paper=QPalette()
            for role in (QPalette.ColorRole.Text,QPalette.ColorRole.WindowText):
                paper.setColor(role,QColor('#000000'))
            for role in (QPalette.ColorRole.Base,QPalette.ColorRole.Window):
                paper.setColor(role,QColor('#ffffff'))
            context.palette=paper
            doc.documentLayout().draw(painter,context)
            painter.restore()
    finally:
        painter.end()
