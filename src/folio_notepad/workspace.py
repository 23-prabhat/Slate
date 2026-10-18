"""Native design workspace: navigation, insert library and contextual properties."""
from pathlib import Path
from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QStackedWidget, QToolButton,
    QVBoxLayout, QWidget)

# Small, bundled vector icons keep tools legible with or without a desktop icon theme.
PATHS = {
    'theme': '<path d="M20 14A8 8 0 0 1 10 4a8 8 0 1 0 10 10Z"/>',
    'new': '<path d="M12 5v14M5 12h14"/>',
    'notes': '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    'insert': '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M17.5 14v7M14 17.5h7"/>',
    'table': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16M15 4v16"/>',
    'image': '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    'draw': '<path d="m4 16-1 5 5-1L20 8l-4-4Z M14 6l4 4M3 21h17"/>',
    'text': '<path d="M4 5h16M12 5v15M8 20h8M4 5v3M20 5v3"/>',
    'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    'settings': '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
    'properties': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M14 4v16M17 8h1M17 12h1M17 16h1"/>',
    'open': '<path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9v3M3 10h18l-3 10H2Z"/>',
    'save': '<path d="M4 3h13l4 4v14H3V3ZM7 3v6h10V3M7 21v-8h10v8"/>',
    'share': '<path d="M12 16V3m-4 4 4-4 4 4M5 12H3v9h18v-9h-2"/>',
    'undo': '<path d="m8 4-5 5 5 5M3 9h11a6 6 0 0 1 0 12"/>',
    'redo': '<path d="m16 4 5 5-5 5M21 9H10a6 6 0 0 0 0 12"/>',
    'link': '<path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(1 -1) scale(.92)"/>',
    'bold': '<path d="M7 4h6a4 4 0 0 1 0 8H7V4Zm0 8h7a4 4 0 0 1 0 8H7v-8Z" stroke-width="2.6"/>',
    'italic': '<path d="M10 4h8M6 20h8M14 4l-4 16"/>',
    'strike': '<path d="M17 6c-1-3-9-3-10 1-.5 2 1 3 5 4M7 18c1 3 10 3 10-2 0-1-1-2-2-2M3 12h18"/>',
    'bullets': '<path d="M9 6h12M9 12h12M9 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    'numbers': '<path d="M10 6h11M10 12h11M10 18h11M3 3h1v6M2 11c0-2 4-2 4 0 0 1-4 3-4 4h4M2 18h3l-2 2c4-1 4 3 0 3"/>',
    'code': '<path d="m8 6-6 6 6 6M16 6l6 6-6 6M14 3l-4 18"/>',
    'close': '<path d="m6 6 12 12M6 18 18 6"/>',
    'minus': '<path d="M5 12h14"/>',
    'line': '<path d="m4 20 16-16"/>',
    'rectangle': '<rect x="3" y="5" width="18" height="14" rx="1"/>',
    'ellipse': '<ellipse cx="12" cy="12" rx="9" ry="7"/>',
    'arrow': '<path d="M4 20 20 4M10 4h10v10"/>',
    'eraser': '<path d="m4 13 9-9 7 7-9 9H8Zm5-5 7 7M11 20h10"/>',
}


def icon(name, palette=None):
    palette=palette or QPalette()
    result=QIcon()
    for mode, color in ((QIcon.Mode.Normal,palette.color(QPalette.ColorRole.WindowText)),
                        (QIcon.Mode.Disabled,palette.color(QPalette.ColorGroup.Disabled,QPalette.ColorRole.WindowText))):
        for size in (24,48,72):
            svg=(f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24">'
                 f'<g fill="none" stroke="{color.name()}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
                 f'{PATHS.get(name,PATHS["notes"])}</g></svg>')
            pixmap=QPixmap()
            pixmap.loadFromData(QByteArray(svg.encode()),'SVG')
            result.addPixmap(pixmap,mode)
    return result


def button(action, label=None, object_name=None):
    result=QToolButton()
    result.setDefaultAction(action)
    result.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    result.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if label: result.setText(label)
    if label: result.setProperty('folioLabel',label)
    if object_name: result.setObjectName(object_name)
    result.setAccessibleName(label or action.text())
    return result


def caption(text):
    result=QLabel(text)
    result.setObjectName('SectionCaption')
    return result


class LibraryPanel(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window=window
        self.setObjectName('LibraryPanel')
        self.setMinimumWidth(182)
        self.setMaximumWidth(280)
        outer=QVBoxLayout(self)
        outer.setContentsMargins(12,12,12,12)
        outer.setSpacing(10)
        self.title=QLabel('Insert')
        self.title.setObjectName('PanelTitle')
        outer.addWidget(self.title)
        self.pages=QStackedWidget()
        outer.addWidget(self.pages,1)
        insert=QWidget()
        insert.setObjectName('InsertLibraryPage')
        content=QVBoxLayout(insert)
        content.setContentsMargins(0,0,0,0)
        content.setSpacing(8)
        content.addWidget(caption('ADD TO YOUR NOTE'))
        self.insert_buttons={}
        for label, action, subtitle in [('Table','Table…','Arrange information'),('Image','Image…','From your computer'),
                                         ('Drawing','Drawing…','Sketch, shapes & arrows'),('Link','Link…','Connect to a page')]:
            b=button(window.actions[action],label,'InsertCard')
            b.setToolTip(subtitle)
            b.setMinimumHeight(36)
            b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            content.addWidget(b)
            self.insert_buttons[label]=b
        self.table_button=self.insert_buttons['Table']
        window.configure_table_picker(self.table_button)
        content.addSpacing(16)
        content.addWidget(caption('TEXT STYLES'))
        for label,level in [('Title',1),('Heading',2),('Body text',0)]:
            b=QPushButton(label)
            b.setObjectName('TextStyle'+str(level))
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.clicked.connect(lambda checked=False,level=level:window.set_heading(level))
            content.addWidget(b)
        content.addSpacing(8)
        content.addWidget(button(window.actions['Bullet list'],'Bullet list','QuietButton'))
        content.addWidget(button(window.actions['Code block'],'Code block','QuietButton'))
        content.addStretch()
        scroll=QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(insert)
        self.pages.addWidget(scroll)
        notes=QWidget()
        notes.setObjectName('NotesLibraryPage')
        content=QVBoxLayout(notes)
        content.setContentsMargins(0,0,0,0)
        content.setSpacing(12)
        new=button(window.actions['New note'],'New note','InsertCard')
        new.setMinimumHeight(40)
        content.addWidget(new)
        content.addWidget(caption('OPEN NOTES'))
        self.note_list=QListWidget()
        self.note_list.setAccessibleName('Open notes')
        self.note_list.setWordWrap(True)
        self.note_list.currentRowChanged.connect(self.select_note)
        content.addWidget(self.note_list,1)
        content.addWidget(button(window.actions['Open…'],'Open a file','QuietButton'))
        content.addWidget(button(window.actions['Draft recovery…'],'Recover a draft','QuietButton'))
        self.pages.addWidget(notes)

    def show_page(self, page):
        self.pages.setCurrentIndex(0 if page=='Insert' else 1)
        self.title.setText(page)

    def select_note(self,index):
        if index>=0: self.window.tabs.setCurrentIndex(index)

    def refresh(self):
        tabs=self.window.tabs
        labels=[tabs.tabText(i) for i in range(tabs.count())]
        if labels!=[self.note_list.item(i).text() for i in range(self.note_list.count())]:
            self.note_list.blockSignals(True)
            self.note_list.clear()
            for i,label in enumerate(labels):
                item=QListWidgetItem(label)
                item.setToolTip(tabs.tabToolTip(i))
                self.note_list.addItem(item)
            self.note_list.blockSignals(False)
        self.note_list.blockSignals(True)
        self.note_list.setCurrentRow(tabs.currentIndex())
        self.note_list.blockSignals(False)


class PropertiesPanel(QFrame):
    """Hosts the selected editor's existing table controls, keeping one source of truth."""
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.bound=None
        self.setObjectName('PropertiesPanel')
        self.setMinimumWidth(250)
        self.setMaximumWidth(290)
        outer=QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        content=QWidget()
        content.setObjectName('InspectorContent')
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout=QVBoxLayout(content)
        layout.setContentsMargins(16,20,16,16)
        layout.setSpacing(12)
        title=QHBoxLayout()
        label=QLabel('Properties'); label.setObjectName('PanelTitle')
        title.addWidget(label,1)
        close=QToolButton()
        close.setProperty('folioIcon','close')
        close.setToolTip('Hide properties')
        close.setAccessibleName('Hide properties')
        close.clicked.connect(lambda:window.properties_action.setChecked(False))
        title.addWidget(close)
        layout.addLayout(title)
        self.context=QLabel('Document')
        self.context.setObjectName('ContextPill')
        layout.addWidget(self.context)
        layout.addWidget(caption('TEXT'))
        row=QHBoxLayout()
        for name in ('Bold','Italic','Strikethrough'):
            b=button(window.actions[name]); b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            b.setMinimumSize(36,34); row.addWidget(b)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(button(window.actions['Font…'],'Choose font…','QuietButton'))
        self.table_section=QWidget()
        table_layout=QVBoxLayout(self.table_section)
        table_layout.setContentsMargins(0,0,0,0)
        table_layout.setSpacing(12)
        table_layout.addWidget(caption('TABLE LAYOUT'))
        self.table_host=QVBoxLayout()
        self.table_host.setContentsMargins(0,0,0,0)
        table_layout.addLayout(self.table_host)
        note=QLabel('Drag table borders to resize.\nRow height grows to fit your text.')
        note.setObjectName('MutedLabel'); note.setWordWrap(True)
        table_layout.addWidget(note)
        layout.addWidget(self.table_section)
        self.no_table=QLabel('Select a table cell to adjust its rows, columns and dimensions.')
        self.no_table.setObjectName('InspectorHint'); self.no_table.setWordWrap(True)
        layout.addWidget(self.no_table)
        layout.addStretch()
        layout.addWidget(caption('DOCUMENT'))
        self.details=QLabel(); self.details.setWordWrap(True); self.details.setObjectName('MutedLabel')
        layout.addWidget(self.details)
        layout.addWidget(button(window.actions['Export PDF…'],'Export as PDF','QuietButton'))

    def bind(self,editor):
        if self.bound is editor: return
        if self.bound:
            controls=self.bound.table_controls
            self.table_host.removeWidget(controls)
            controls.set_compact(False)
            self.bound.layout().insertWidget(0,controls)
            self.bound.update_table_controls()
        self.bound=editor
        if editor:
            controls=editor.table_controls
            editor.layout().removeWidget(controls)
            controls.set_compact(True)
            self.table_host.addWidget(controls)

    def refresh(self,editor):
        if not self.isVisible():
            self.bind(None)
            return
        self.bind(editor)
        if not editor: return
        table=editor.formatted.textCursor().currentTable() if editor.editable else None
        self.table_section.setVisible(table is not None)
        self.no_table.setVisible(table is None)
        self.context.setText(f'Table · {table.rows()} × {table.columns()}' if table else ('Formatted note' if editor.note.rich else 'Plain text / Markdown'))
        self.details.setText(('Portable note' if editor.note.rich else ('Markdown' if editor.note.kind=='md' else 'Plain text'))+
                             '\n'+('Saved to a file' if editor.note.path else 'Unnamed draft'))
        editor.update_table_controls()


class ZoomControl(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window=window
        layout=QHBoxLayout(self)
        layout.setContentsMargins(6,0,6,0)
        layout.setSpacing(6)
        for name,amount in [('minus',-10),('new',10)]:
            b=QToolButton()
            b.setProperty('folioIcon',name)
            b.setAccessibleName('Zoom out' if amount<0 else 'Zoom in')
            b.setToolTip(b.accessibleName())
            b.clicked.connect(lambda checked=False,n=amount:window.zoom(n))
            if amount<0: layout.addWidget(b)
            else: self.plus=b
        self.slider=QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(50,300)
        self.slider.setSingleStep(10)
        self.slider.setFixedWidth(90)
        self.slider.setAccessibleName('Document zoom')
        self.slider.valueChanged.connect(self.change)
        layout.addWidget(self.slider)
        layout.addWidget(self.plus)
        self.label=QPushButton('100%')
        self.label.setObjectName('ZoomLabel')
        self.label.setToolTip('Reset zoom')
        self.label.clicked.connect(lambda:window.zoom(0))
        layout.addWidget(self.label)

    def change(self,value):
        if self.window.editor:
            self.window.editor.set_zoom(value)
            self.window.refresh()

    def refresh(self,percent):
        self.slider.blockSignals(True)
        self.slider.setValue(percent)
        self.slider.blockSignals(False)
        self.label.setText(f'{percent}%')


def apply_style(window):
    """Style only this shell; document text, colours and file content stay intact."""
    palette=window.controller.app.palette()
    dark=palette.color(QPalette.ColorRole.Window).lightness()<128
    surface='#292b32' if dark else '#fcfbfe'
    canvas='#25272e' if dark else '#f6f5f9'
    border='#393b44' if dark else '#eae8ef'
    text='#e9eaf3' if dark else '#252738'
    muted='#a7adbf' if dark else '#73798a'
    hover='#34343f' if dark else '#f0edf7'
    accent='#b6a6e2' if dark else '#78649e'
    selected='#3d374b' if dark else '#efe9f6'
    chevron=(Path(__file__).resolve().parents[2]/'resources/ui'/
             ('chevron-down-dark.svg' if dark else 'chevron-down-light.svg')).as_posix()
    window.setStyleSheet(f'''
        QMainWindow {{ background: {surface}; }}
        QMenuBar {{ background: {surface}; color: {text}; padding: 3px 12px; border-bottom: 1px solid {border}; }}
        QMenuBar::item {{ padding: 5px 9px; border-radius: 4px; }}
        QMenuBar::item:selected {{ background: {hover}; }}
        QToolBar {{ background: {surface}; border: none; border-bottom: 1px solid {border}; spacing: 3px; padding: 4px 8px; }}
        QToolBar::separator {{ background: {border}; width: 1px; margin: 4px 8px; }}
        QToolButton {{ border: 1px solid transparent; border-radius: 9px; padding: 5px; color: {text}; }}
        QToolButton:hover, QPushButton:hover {{ background: {hover}; }}
        QToolButton:pressed, QToolButton:checked {{ background: {selected}; color: {accent}; }}
        QToolButton:focus {{ border-color: {accent}; }}
        QToolButton:disabled {{ color: {muted}; }}
        QToolButton[popupMode="2"] {{ padding-right: 18px; }}
        QToolButton[popupMode="1"] {{ padding-right: 20px; }}
        QToolButton::menu-indicator {{ image: url("{chevron}"); width: 10px; height: 6px; subcontrol-origin: padding; subcontrol-position: right center; right: 4px; }}
        QToolButton[popupMode="1"]::menu-indicator {{ image: none; width: 0; }}
        QToolButton::menu-button {{ subcontrol-origin: border; subcontrol-position: right center; border: none; background: transparent; width: 20px; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
        QToolButton::menu-arrow {{ image: url("{chevron}"); width: 10px; height: 6px; }}
        QToolButton#InsertCard {{ background: {surface}; border: 1px solid {border}; text-align: left; padding: 7px; }}
        QToolButton#InsertCard:hover {{ background: {hover}; border-color: {accent}; }}
        QToolButton#InsertCard[popupMode="1"] {{ padding-right: 20px; }}
        QToolButton#PrimaryButton {{ background: #8170aa; color: white; padding: 5px 12px; border-radius: 10px; font-weight: 600; }}
        QToolButton#PrimaryButton:hover {{ background: #9380bd; }}
        QToolButton#AppMenuButton {{ font-weight: 600; color: {accent}; padding: 5px 18px 5px 8px; }}
        QToolButton#SoftAccentButton {{ background: {selected}; color: {accent}; padding: 5px 9px; }}
        QToolButton#TabClose {{ padding: 1px; border-radius: 6px; }}
        QWidget#SearchPanel QLineEdit {{ border: 1px solid {border}; background: {canvas}; border-radius: 8px; padding: 5px 9px; }}
        QWidget#SearchPanel QPushButton {{ border: 1px solid {border}; border-radius: 8px; padding: 5px 9px; }}
        QToolButton#QuietButton {{ text-align: left; padding: 8px 2px; }}
        QToolButton#TableEdgeButton {{ background: {selected}; color: {accent}; border: 1px solid {border}; padding: 0; border-radius: 5px; font-size: 16px; }}
        QToolButton#TableEdgeButton::menu-indicator {{ image: none; width: 0; }}
        QFrame#LibraryPanel, QFrame#PropertiesPanel {{ background: {surface}; border: none; }}
        QFrame#LibraryPanel {{ border-right: 1px solid {border}; }}
        QFrame#PropertiesPanel {{ border-left: 1px solid {border}; }}
        QWidget#InsertLibraryPage, QWidget#NotesLibraryPage, QWidget#InspectorContent, QScrollArea {{ background: {surface}; }}
        QLabel {{ background: transparent; }}
        QWidget#NavigationRail {{ background: {surface}; border-right: 1px solid {border}; }}
        QWidget#NavigationRail QToolButton {{ padding: 6px; }}
        QLabel#Brand {{ font-size: 20px; font-weight: 700; color: {accent}; padding-right: 18px; }}
        QLabel#DocumentTitle {{ font-size: 14px; font-weight: 600; color: {text}; }}
        QLabel#HeaderState, QLabel#MutedLabel {{ color: {muted}; font-size: 11px; }}
        QLabel#PanelTitle {{ font-size: 17px; font-weight: 600; color: {text}; }}
        QLabel#SectionCaption {{ color: {muted}; font-size: 10px; font-weight: 600; letter-spacing: 1px; }}
        QLabel#ContextPill {{ background: {selected}; color: {accent}; padding: 8px; border-radius: 6px; font-size: 11px; }}
        QLabel#InspectorHint {{ background: {canvas}; color: {muted}; padding: 12px; border-radius: 8px; font-size: 11px; }}
        QPushButton#TextStyle1, QPushButton#TextStyle2, QPushButton#TextStyle0 {{ text-align: left; border: none; border-radius: 6px; padding: 8px; color: {text}; }}
        QPushButton#TextStyle1 {{ font-size: 22px; font-weight: 700; }}
        QPushButton#TextStyle2 {{ font-size: 16px; font-weight: 600; }}
        QPushButton#TextStyle0 {{ font-size: 12px; }}
        QListWidget {{ border: none; background: {surface}; outline: none; }}
        QListWidget::item {{ padding: 12px 8px; border-radius: 6px; margin-bottom: 4px; }}
        QListWidget::item:selected {{ background: {selected}; color: {accent}; }}
        QWidget#NoteCanvas {{ background: {canvas}; }}
        QWidget#DrawingBackdrop {{ background: {canvas}; border-radius: 8px; }}
        QFrame#DrawingTools QToolButton {{ text-align: left; padding: 9px; }}
        QStackedWidget#DocumentSurface {{ background: palette(base); border: 1px solid {border}; border-radius: 12px; }}
        QTextEdit[folioEditor="true"], QPlainTextEdit[folioEditor="true"] {{ border: none; background: palette(base); padding: 12px; selection-background-color: palette(highlight); }}
        QTabWidget::pane {{ border: none; }}
        QTabBar {{ background: {canvas}; }}
        QTabBar::tab {{ background: transparent; color: {muted}; padding: 6px 12px; border-bottom: 1px solid transparent; border-top-left-radius: 9px; border-top-right-radius: 9px; min-width: 80px; max-width: 200px; }}
        QTabBar::tab:selected {{ background: {surface}; color: {accent}; border-bottom-color: {accent}; }}
        QTabBar::tab:hover {{ background: {hover}; }}
        QComboBox {{ padding: 3px 4px 3px 8px; border: 1px solid {border}; border-radius: 8px; min-height: 16px; background: {surface}; color: {text}; }}
        QComboBox::drop-down {{ subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
        QComboBox::down-arrow {{ image: url("{chevron}"); width: 10px; height: 6px; }}
        QSpinBox {{ padding: 6px; border: 1px solid {border}; border-radius: 5px; min-height: 20px; }}
        QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 14px; background: transparent; }}
        QSplitter::handle {{ background: {border}; }}
        QStatusBar {{ background: {surface}; color: {muted}; border-top: 1px solid {border}; padding: 1px 8px; font-size: 10px; }}
        QStatusBar QLabel {{ color: {muted}; }}
        QStatusBar::item {{ border: none; }}
        QPushButton#ZoomLabel {{ border: none; padding: 4px; color: {text}; min-width: 42px; }}
        QSlider::groove:horizontal {{ height: 3px; background: {border}; border-radius: 1px; }}
        QSlider::handle:horizontal {{ background: {accent}; width: 10px; height: 10px; margin: -4px 0; border-radius: 5px; }}
    ''')
    for action in window.actions.values():
        name=action.property('folioIcon')
        if name: action.setIcon(icon(name,palette))
    for tool in window.findChildren(QToolButton):
        name=tool.property('folioIcon')
        if name: tool.setIcon(icon(name,palette))
        label=tool.property('folioLabel')
        if label: tool.setText(label)
        if tool.objectName()=='PrimaryButton':
            primary_palette=QPalette(palette)
            primary_palette.setColor(QPalette.ColorRole.WindowText,QColor('white'))
            tool.setIcon(icon('share',primary_palette))
