"""Desktop shell and user workflows. Persistence stays in storage.py."""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import re
import zipfile
from PySide6.QtCore import QDateTime, QMarginsF, QRegularExpression, QSize, QTimer, Qt, QUrl, QTemporaryFile
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QFont,
    QIcon, QKeySequence, QPalette, QTextBlockFormat, QTextCharFormat, QTextCursor,
    QTextDocument, QTextFormat)
from PySide6.QtPrintSupport import QPageSetupDialog, QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFontDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
    QSizePolicy, QSpinBox, QSplitter, QTabBar, QTabWidget, QTextEdit, QToolBar, QToolButton,
    QVBoxLayout, QWidget, QWidgetAction)
from . import __version__
from .editor import NoteEditor, SafeDocument, decode_image, png_bytes
from .storage import Note, TextFormat, atomic_write, digest, fingerprint, pack_note, read_note, referenced_assets


class Window(QMainWindow):
    def __init__(self, controller, notes=(), window_id=None, empty=False):
        super().__init__()
        from uuid import uuid4
        self.controller = controller
        self.window_id = window_id or str(uuid4())
        self.actions = {}
        self.closed_ids = []
        self.printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self.resize(1320, 840)
        self.setMinimumSize(680, 460)
        self.setWindowTitle('Folio Notepad')
        self.setWindowIcon(controller.icon)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.banner.setStyleSheet('padding: 10px 16px; background: #fff0cb; color: #594213;')
        self.banner.hide()
        layout.addWidget(self.banner)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.refresh)
        self.tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self.tab_menu)
        self.tabs.tabBar().tabMoved.connect(lambda *_: (self.refresh(),self.controller.schedule()))
        plus = QToolButton()
        plus.setText('+')
        plus.setToolTip('New note (Ctrl+N)')
        plus.setAccessibleName('New note')
        plus.clicked.connect(lambda: self.add_note())
        self.tabs.setCornerWidget(plus)
        self.workspace_row=QHBoxLayout()
        self.workspace_row.setContentsMargins(0,0,0,0)
        self.workspace_row.setSpacing(0)
        self.workspace_splitter=QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setHandleWidth(1)
        self.workspace_splitter.addWidget(self.tabs)
        self.workspace_row.addWidget(self.workspace_splitter,1)
        layout.addLayout(self.workspace_row,1)
        self.search = self.search_bar()
        layout.addWidget(self.search)
        self.search.hide()
        self.setCentralWidget(central)
        self.external_stamp = {}
        self.watcher = QTimer(self)
        self.watcher.setInterval(2500)
        self.watcher.timeout.connect(self.check_external)
        self.watcher.start()
        self.build_actions()
        self.build_workspace()
        self.state_label, self.count_label, self.mode_label = QLabel(), QLabel(), QLabel()
        self.statusBar().addWidget(self.state_label, 1)
        self.statusBar().addPermanentWidget(self.count_label)
        self.statusBar().addPermanentWidget(self.mode_label)
        from .workspace import ZoomControl
        self.zoom_control=ZoomControl(self)
        self.statusBar().addPermanentWidget(self.zoom_control)
        self.statusBar().setSizeGripEnabled(True)
        for note in notes: self.add_note(note)
        if not self.tabs.count() and not empty: self.add_note()
        geometry = self.controller.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
            if not any(screen.availableGeometry().intersects(self.frameGeometry()) for screen in QApplication.screens()):
                self.move(QApplication.primaryScreen().availableGeometry().topLeft())
        self.update_workspace_layout()
        from .workspace import apply_style
        apply_style(self)

    @property
    def editor(self) -> NoteEditor | None:
        return self.tabs.currentWidget()

    def action(self, name, callback, shortcut=None, icon=None, check=False):
        a = QAction(QIcon.fromTheme(icon) if icon else QIcon(), name, self)
        if shortcut: a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(check)
        a.triggered.connect(callback)
        self.actions[name] = a
        self.addAction(a)
        return a

    def build_actions(self):
        file = self.menuBar().addMenu('&File')
        file.addAction(self.action('New note', lambda: self.add_note(), 'Ctrl+N', 'document-new'))
        file.addAction(self.action('New window', lambda: self.controller.new_window(), 'Ctrl+Shift+N', 'window-new'))
        file.addAction(self.action('Open…', self.open_dialog, 'Ctrl+O', 'document-open'))
        self.recent_menu = file.addMenu('Recent files')
        self.recent_menu.aboutToShow.connect(self.populate_recents)
        file.addSeparator()
        file.addAction(self.action('Save', self.save_current, 'Ctrl+S', 'document-save'))
        file.addAction(self.action('Save As…', lambda: self.save_current(True), 'Ctrl+Shift+S', 'document-save-as'))
        file.addAction(self.action('Save all', self.save_all, 'Ctrl+Alt+S', 'document-save-all'))
        file.addAction(self.action('Reload from disk…', self.reload_file, icon='view-refresh'))
        file.addSeparator()
        export = file.addMenu('Export')
        for label, suffix in [('Plain text…', 'txt'), ('Markdown + images…', 'md'), ('Portable note…', 'folio'),
                              ('Markdown share bundle…', 'zip'), ('PDF…', 'pdf')]:
            export.addAction(self.action('Export '+label, lambda _=False, s=suffix: self.export(s)))
        file.addAction(self.action('Share / prepare file…', self.share, icon='document-send'))
        file.addSeparator()
        file.addAction(self.action('Page setup…', lambda: QPageSetupDialog(self.printer, self).exec()))
        file.addAction(self.action('Print preview…', self.print_preview))
        file.addAction(self.action('Print…', self.print_document, 'Ctrl+P', 'document-print'))
        file.addSeparator()
        file.addAction(self.action('Close tab', lambda: self.close_tab(self.tabs.currentIndex()), 'Ctrl+W'))
        file.addAction(self.action('Reopen closed tab…', self.reopen, 'Ctrl+Shift+T'))
        file.addAction(self.action('Quit', self.controller.quit, 'Ctrl+Q', 'application-exit'))
        edit = self.menuBar().addMenu('&Edit')
        edit.addAction(self.action('Undo', lambda: self.editor.stack.undo(), 'Ctrl+Z', 'edit-undo'))
        redo=self.action('Redo',lambda:self.editor.stack.redo(),'Ctrl+Y','edit-redo')
        redo.setShortcuts([QKeySequence('Ctrl+Y'),QKeySequence('Ctrl+Shift+Z')])
        edit.addAction(redo)
        edit.addSeparator()
        for name, method, key, icon in [('Cut', 'cut', 'Ctrl+X', 'edit-cut'), ('Copy', 'copy', 'Ctrl+C', 'edit-copy'),
                                        ('Paste', 'paste', 'Ctrl+V', 'edit-paste'), ('Select all', 'selectAll', 'Ctrl+A', 'edit-select-all')]:
            edit.addAction(self.action(name, lambda _=False, m=method: getattr(self.editor.active, m)(), key, icon))
        edit.addAction(self.action('Paste plain text', lambda: self.insert_text(QApplication.clipboard().text()), 'Ctrl+Shift+V'))
        edit.addSeparator()
        edit.addAction(self.action('Find…', self.show_search, 'Ctrl+F', 'edit-find'))
        edit.addAction(self.action('Replace…', lambda:self.show_search(True), 'Ctrl+H', 'edit-find-replace'))
        edit.addAction(self.action('Find next', lambda: self.find(), 'F3'))
        edit.addAction(self.action('Find previous', lambda: self.find(True), 'Shift+F3'))
        edit.addAction(self.action('Go to line…', self.goto, 'Ctrl+G'))
        edit.addAction(self.action('Insert date/time', lambda: self.insert_text(QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm')), 'F5'))
        view = self.menuBar().addMenu('&View')
        for name, mode in [('Source / plain text', 'source'), ('Formatted view', 'formatted'), ('Split preview', 'split')]:
            view.addAction(self.action(name, lambda _=False, m=mode: self.set_view(m)))
        view.addAction(self.action('Create formatted copy', self.formatted_copy))
        self.library_action=self.action('Insert / notes panel',self.update_workspace_layout,check=True)
        self.library_action.setChecked(self.controller.settings.value('library_panel',False,bool))
        self.library_action.toggled.connect(self.update_workspace_layout)
        view.addAction(self.library_action)
        self.properties_action=self.action('Properties panel',self.toggle_properties,icon='view-right-new',check=True)
        self.properties_action.setProperty('folioIcon','properties')
        self.properties_action.setChecked(self.controller.settings.value('properties_panel',False,bool))
        self.properties_action.toggled.connect(self.update_workspace_layout)
        view.addAction(self.properties_action)
        theme_menu=view.addMenu('Theme')
        self.theme_group=QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions={}
        for name in ('System','Light','Dark'):
            action=QAction(name,self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False,name=name:self.controller.theme(name))
            self.theme_group.addAction(action)
            self.theme_actions[name]=action
            theme_menu.addAction(action)
        self.theme_button=QToolButton()
        self.theme_button.setAccessibleName('Choose application theme')
        button_menu=QMenu(self.theme_button)
        button_menu.addActions(self.theme_group.actions())
        self.theme_button.setMenu(button_menu)
        self.theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menuBar().setCornerWidget(self.theme_button,Qt.Corner.TopRightCorner)
        self.update_theme_controls(self.controller.settings.value('theme','System'))
        self.wrap_action = self.action('Word wrap', self.word_wrap, check=True)
        self.wrap_action.setChecked(True)
        view.addAction(self.wrap_action)
        view.addAction(self.action('Font…', self.choose_font))
        for name, amount, key in [('Zoom in', 10, 'Ctrl++'), ('Zoom out', -10, 'Ctrl+-'), ('Reset zoom', 0, 'Ctrl+0')]:
            view.addAction(self.action(name, lambda _=False, a=amount: self.zoom(a), key))
        view.addAction(self.action('Next tab', lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex()+1)%self.tabs.count()), 'Ctrl+Tab'))
        view.addAction(self.action('Previous tab', lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex()-1)%self.tabs.count()), 'Ctrl+Shift+Tab'))
        status = self.action('Status bar', lambda visible: self.statusBar().setVisible(visible), check=True)
        status.setChecked(True)
        view.addAction(status)
        insert = self.menuBar().addMenu('&Insert')
        insert.addAction(self.action('Table…', self.table_dialog, icon='insert-table'))
        insert.addAction(self.action('Image…', self.insert_image, icon='insert-image'))
        insert.addAction(self.action('Drawing…', self.drawing, icon='draw-freehand'))
        insert.addAction(self.action('Link…', self.link, 'Ctrl+K', 'insert-link'))
        insert.addAction(self.action('Code block', self.code_block))
        self.table_menu = insert.addMenu('Table actions')
        for label, op in [('Row above', 'row_above'), ('Row below', 'row_below'), ('Column left', 'col_left'),
                          ('Column right', 'col_right'), ('Delete row', 'del_row'), ('Delete column', 'del_col'),
                          ('Table size…', 'resize'), ('Column width…','column_width'),
                          ('Row minimum height…','row_height'), ('Size columns equally','equal_columns'),
                          ('Size rows equally','equal_rows'), ('Fit columns to content','fit_columns'),
                          ('Fit row to content','fit_row'), ('Duplicate row','duplicate_row'),
                          ('Duplicate column','duplicate_col'), ('Align column left', 'align_left'),
                          ('Align column center', 'align_center'), ('Align column right', 'align_right'), ('Delete table', 'delete')]:
            self.table_menu.addAction(self.action(label, lambda _=False, op=op: self.table_action(op)))
        formatting = self.menuBar().addMenu('F&ormat')
        for name, key, icon in [('Bold', 'Ctrl+B', 'format-text-bold'), ('Italic', 'Ctrl+I', 'format-text-italic'),
                                ('Strikethrough', None, 'format-text-strikethrough'), ('Code', None, 'code-context'),
                                ('Clear formatting', None, 'format-text-remove-formatting')]:
            formatting.addAction(self.action(name, lambda _=False, n=name: self.format(n), key, icon))
        formatting.addAction(self.action('Bullet list', lambda: self.list_format(False), icon='format-list-unordered'))
        formatting.addAction(self.action('Numbered list', lambda: self.list_format(True), icon='format-list-ordered'))
        formatting.addAction(self.action('Increase indent', lambda: self.indent(1), icon='format-indent-more'))
        formatting.addAction(self.action('Decrease indent', lambda: self.indent(-1), icon='format-indent-less'))
        formatting.addAction(self.action('Block quote', self.quote))
        tools = self.menuBar().addMenu('&Tools')
        tools.addAction(self.action('Writing assistant…', self.ai_dialog, icon='tools-wizard'))
        tools.addAction(self.action('Spelling language…', self.spell_language))
        tools.addAction(self.action('Spelling suggestions…', self.spell_suggestions, 'Shift+F7'))
        tools.addAction(self.action('Autocorrect common English typos', lambda checked: setattr(self.editor,'autocorrect_enabled',checked), check=True))
        tools.addAction(self.action('Text encoding and line endings…', self.text_settings))
        tools.addAction(self.action('Load local Markdown images…', self.load_local_images))
        tools.addAction(self.action('Print headers and footers…', self.print_settings))
        tools.addAction(self.action('Preferences…', self.preferences, 'Ctrl+,', 'configure'))
        tools.addAction(self.action('Draft recovery…', self.reopen))
        tools.addAction(self.action('Open draft storage', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.controller.data_dir)))) )
        helpmenu = self.menuBar().addMenu('&Help')
        helpmenu.addAction(self.action('Keyboard shortcuts', self.shortcuts))
        helpmenu.addAction(self.action('About Folio Notepad', self.about))
        from .workspace import button
        toolbar=QToolBar('Tools',self)
        toolbar.setObjectName('MainToolbar')
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18,18))
        self.addToolBar(toolbar)
        self.formatting_toolbar=toolbar
        self.app_menu_button=QToolButton()
        self.app_menu_button.setObjectName('AppMenuButton')
        self.app_menu_button.setText('Folio')
        self.app_menu_button.setAccessibleName('Application menu: all commands')
        app_menu=QMenu(self.app_menu_button)
        for entry in self.menuBar().actions():
            if entry.menu(): app_menu.addMenu(entry.menu())
        self.app_menu_button.setMenu(app_menu)
        self.app_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(self.app_menu_button)
        self.menuBar().setCornerWidget(None)
        self.menuBar().hide()
        self.header_buttons={}
        for name in ('Undo','Redo'):
            b=button(self.actions[name]); b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            toolbar.addWidget(b); self.header_buttons[name]=b
        toolbar.addSeparator()
        self.normal_tools=QWidget()
        normal=QHBoxLayout(self.normal_tools)
        normal.setContentsMargins(0,0,0,0); normal.setSpacing(2)
        self.heading=QComboBox()
        self.heading.setAccessibleName('Paragraph style')
        self.heading.addItems(['Paragraph','Heading 1','Heading 2','Heading 3','Heading 4','Heading 5','Heading 6'])
        self.heading.setFixedWidth(112)
        self.heading.activated.connect(self.set_heading)
        normal.addWidget(self.heading)
        for name in ('Bold','Italic','Bullet list','Table…','Image…','Drawing…'):
            b=button(self.actions[name]); b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            b.setIconSize(QSize(18,18))
            normal.addWidget(b)
            if name=='Table…': self.configure_table_picker(b)
        self.normal_tools_action=toolbar.addWidget(self.normal_tools)
        from .drawing import InlineDrawingTools
        self.drawing_tools=InlineDrawingTools(self)
        self.drawing_tools_action=toolbar.addWidget(self.drawing_tools)
        self.drawing_tools_action.setVisible(False)
        spacer=QWidget(); spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.mode=QComboBox()
        self.mode.setAccessibleName('Document view')
        self.mode.addItems(['Edit','Source','Preview','Split'])
        self.mode.setFixedWidth(88)
        self.mode.activated.connect(lambda i:self.set_view(['edit','source','formatted','split'][i]))
        toolbar.addWidget(self.mode)
        toolbar.addAction(self.properties_action)
        self.theme_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.theme_button.setProperty('folioIcon','theme')
        toolbar.addWidget(self.theme_button)
        for name,label,object_name in [('Save',None,None),('Share / prepare file…','Share','PrimaryButton')]:
            b=button(self.actions[name],label,object_name)
            if name=='Save': b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            toolbar.addWidget(b); self.header_buttons[name]=b
        icons={'New note':'new','Open…':'open','Save':'save','Share / prepare file…':'share',
               'Undo':'undo','Redo':'redo','Bold':'bold','Italic':'italic','Strikethrough':'strike',
               'Code':'code','Code block':'code','Bullet list':'bullets','Numbered list':'numbers',
               'Table…':'table','Image…':'image','Drawing…':'draw','Link…':'link','Font…':'text',
               'Find…':'search','Preferences…':'settings','Clear formatting':'text'}
        for name,key in icons.items(): self.actions[name].setProperty('folioIcon',key)

    def configure_table_picker(self,table_button):
        from .widgets import TablePicker
        table_dropdown=QMenu(table_button)
        picker=TablePicker()
        picker_action=QWidgetAction(table_dropdown)
        picker_action.setDefaultWidget(picker)
        table_dropdown.addAction(picker_action)
        table_dropdown.addAction('Custom size…',self.table_dialog)
        def pick_table(rows,columns):
            table_dropdown.close()
            if self.rich_ready(): self.editor.insert_table(rows,columns)
        picker.chosen.connect(pick_table)
        table_button.setMenu(table_dropdown)
        table_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

    def build_workspace(self):
        from .workspace import LibraryPanel, PropertiesPanel
        rail=QWidget(); rail.setObjectName('NavigationRail'); rail.setFixedWidth(46)
        layout=QVBoxLayout(rail); layout.setContentsMargins(4,8,4,6); layout.setSpacing(6)
        self.rail_buttons={}
        for name,key in [('New','new'),('Notes','notes'),('Insert','insert'),('Draw','draw'),('Find','search')]:
            b=QToolButton()
            b.setText(name); b.setAccessibleName(name); b.setToolTip(name)
            b.setProperty('folioIcon',key)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            b.setIconSize(QSize(20,20)); b.setFixedSize(36,36)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            if name=='Draw': b.setCheckable(True)
            if name in ('Notes','Insert'):
                b.setCheckable(True)
                b.clicked.connect(lambda checked=False,name=name:self.show_library(name))
            else:
                b.clicked.connect({'New':lambda:self.add_note(),'Draw':self.drawing,'Find':self.show_search}[name])
            layout.addWidget(b); self.rail_buttons[name]=b
        layout.addStretch()
        settings=QToolButton(); settings.setProperty('folioIcon','settings')
        settings.setAccessibleName('Preferences'); settings.setToolTip('Preferences')
        settings.clicked.connect(self.preferences); layout.addWidget(settings)
        self.workspace_row.insertWidget(0,rail)
        self.library=LibraryPanel(self)
        self.inspector=PropertiesPanel(self)
        self.workspace_splitter.insertWidget(0,self.library)
        self.workspace_splitter.addWidget(self.inspector)
        self.workspace_splitter.setStretchFactor(1,1)
        self.workspace_splitter.setCollapsible(0,False)
        self.workspace_splitter.setCollapsible(1,False)
        self.workspace_splitter.setCollapsible(2,False)
        self.workspace_splitter.setSizes([208,800,264])
        self.library_page='Insert'
        self.rail_buttons['Insert'].setChecked(True)

    def show_library(self,page):
        if self.library.isVisible() and self.library_page==page:
            self.library_action.setChecked(False)
            self.update_workspace_layout()
            return
        self.library_override=True
        self.library_page=page
        self.library.show_page(page)
        self.library_action.setChecked(True)
        self.update_workspace_layout()

    def toggle_properties(self,checked):
        self.properties_override=checked
        if checked and self.width()<1120: self.library_action.setChecked(False)
        self.update_workspace_layout()

    def update_workspace_layout(self,*_):
        if not hasattr(self,'library'): return
        self.controller.settings.setValue('library_panel',self.library_action.isChecked())
        self.controller.settings.setValue('properties_panel',self.properties_action.isChecked())
        # A narrow window favours writing space; panel preferences return when widened.
        self.library.setVisible(self.library_action.isChecked() and (self.width()>=850 or getattr(self,'library_override',False)))
        self.inspector.setVisible(self.properties_action.isChecked() and (self.width()>=1120 or getattr(self,'properties_override',False)))
        for name in ('Notes','Insert'):
            self.rail_buttons[name].setChecked(self.library.isVisible() and self.library_page==name)
        self.inspector.refresh(self.editor)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_workspace_layout()

    def search_bar(self):
        widget=QWidget(); widget.setObjectName('SearchPanel')
        outer=QVBoxLayout(widget); outer.setContentsMargins(10,5,10,5); outer.setSpacing(4)
        row=QHBoxLayout(); row.setSpacing(6)
        self.query=QLineEdit(); self.query.setPlaceholderText('Find in this note…')
        self.query.setAccessibleName('Find text'); self.query.returnPressed.connect(lambda:self.find())
        row.addWidget(self.query,1)
        for label,callback in [('↑',lambda:self.find(True)),('↓',lambda:self.find())]:
            b=QToolButton(); b.setText(label); b.setAccessibleName('Previous match' if label=='↑' else 'Next match')
            b.clicked.connect(callback); row.addWidget(b)
        self.replace_toggle=QToolButton(); self.replace_toggle.setText('Replace'); self.replace_toggle.setCheckable(True)
        row.addWidget(self.replace_toggle)
        options=QToolButton(); options.setText('Options')
        options.setAccessibleName('Find options')
        menu=QMenu(options)
        self.case=QCheckBox('Match case'); self.words=QCheckBox('Whole words'); self.regex=QCheckBox('Regex')
        for box in (self.case,self.words,self.regex):
            action=QWidgetAction(menu); action.setDefaultWidget(box); menu.addAction(action)
        options.setMenu(menu); options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(options)
        self.search_result=QLabel(''); row.addWidget(self.search_result)
        close=QToolButton(); close.setProperty('folioIcon','close'); close.setAccessibleName('Close find')
        close.clicked.connect(widget.hide); row.addWidget(close)
        outer.addLayout(row)
        self.replace_row=QWidget(); replace_layout=QHBoxLayout(self.replace_row)
        replace_layout.setContentsMargins(0,0,0,0); replace_layout.setSpacing(6)
        self.replacement=QLineEdit(); self.replacement.setAccessibleName('Replacement text')
        self.replacement.setPlaceholderText('Replace with…'); replace_layout.addWidget(self.replacement,1)
        for label,callback in [('Replace',self.replace_one),('Replace all',self.replace_all)]:
            b=QPushButton(label); b.clicked.connect(callback); replace_layout.addWidget(b)
        self.replace_toggle.toggled.connect(self.replace_row.setVisible)
        outer.addWidget(self.replace_row); self.replace_row.hide()
        return widget

    def add_note(self, note=None):
        note = note or Note(title=f'Untitled {self.controller.next_untitled()}')
        note.window = self.window_id
        editor = NoteEditor(note)
        if self.controller.settings.value('editor_font'):
            font=QFont(); font.fromString(self.controller.settings.value('editor_font'))
            for widget in (editor.source,editor.formatted,editor.preview): widget.setFont(font)
        editor.changed.connect(lambda: (self.refresh(), self.controller.schedule()))
        editor.position_changed.connect(self.refresh)
        editor.history_changed.connect(self.refresh)
        editor.image_requested.connect(self.insert_image)
        editor.image_edit.connect(self.edit_image)
        editor.table_requested.connect(self.table_action)
        editor.operation_error.connect(self.message)
        index = self.tabs.addTab(editor, note.title)
        self.tab_close_button(index,editor)
        self.tabs.setCurrentIndex(index)
        editor.active.setFocus()
        self.refresh()
        return editor

    def tab_close_button(self,index,editor):
        from .workspace import icon
        bar=self.tabs.tabBar()
        old=bar.tabButton(index,QTabBar.ButtonPosition.RightSide)
        close=QToolButton()
        close.setObjectName('TabClose'); close.setProperty('folioIcon','close')
        close.setIcon(icon('close',self.controller.app.palette()))
        close.setIconSize(QSize(12,12)); close.setFixedSize(18,18)
        close.setAccessibleName('Close '+editor.note.title)
        close.setToolTip('Close note (Ctrl+W)')
        close.clicked.connect(lambda:self.close_tab(self.tabs.indexOf(editor)))
        bar.setTabButton(index,QTabBar.ButtonPosition.RightSide,close)
        if old: old.deleteLater()

    def refresh(self, *_):
        e = self.editor
        if not e:
            if hasattr(self,'inspector'): self.inspector.bind(None)
            if hasattr(self,'drawing_tools'): self.update_drawing_tools()
            return
        if not hasattr(self, 'state_label'): return
        n = e.note
        self.setWindowTitle(f'{n.title}{" •" if n.dirty else ""} — Folio Notepad')
        for index in range(self.tabs.count()):
            note = self.tabs.widget(index).note
            self.tabs.setTabText(index, note.title + (' •' if note.dirty else ''))
            self.tabs.setTabToolTip(index, note.path or 'Unnamed draft — kept in local recovery storage')
        protected = self.controller.protected.get(n.id) == n.revision
        state = ('Unsaved changes' if n.path else 'Unsaved file') if n.dirty or not n.path else 'Saved'
        self.state_label.setText(('Draft protected · ' if protected and (n.dirty or not n.path) else '') + state)
        text = e.active.toPlainText()
        selected = e.active.textCursor().selectedText()
        cursor = e.active.textCursor()
        counts = f'{len(text.split())} words · {len(text)} characters'
        if selected: counts += f' · {len(selected)} selected'
        if not e.note.rich and e.source.isVisible(): counts = f'Ln {cursor.blockNumber()+1}, Col {len(cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock()*2].decode("utf-16-le", errors="ignore"))+1} · '+counts
        self.count_label.setText(counts)
        self.mode_label.setText(f'   {n.text_format.encoding.upper()}   {n.text_format.eol_label}   ')
        self.update_drawing_tools()
        self.library.refresh()
        self.inspector.refresh(e)
        self.zoom_control.refresh(n.zoom)
        if e.note.rich:
            current_mode=0 if e.views.currentIndex()==1 else (3 if not e.preview.isHidden() else 1)
        else:
            current_mode=3 if not e.preview.isHidden() and not e.source.isHidden() else (2 if e.source.isHidden() else 0)
        self.mode.setCurrentIndex(current_mode)
        self.heading.setCurrentIndex(e.active.textCursor().blockFormat().headingLevel() if e.editable else 0)
        self.actions['Autocorrect common English typos'].setChecked(e.autocorrect_enabled)
        self.actions['Undo'].setEnabled(e.stack.canUndo())
        self.actions['Redo'].setEnabled(e.stack.canRedo())
        self.heading.setEnabled(not e.active.isReadOnly())

    def check_external(self):
        e = self.editor
        if not e or not e.note.path: return
        path = Path(e.note.path)
        try:
            st = path.stat()
            stamp = (st.st_mtime_ns,st.st_size)
        except OSError: stamp = None
        if self.external_stamp.get(str(path),'unchecked') != stamp:
            self.external_stamp[str(path)] = stamp
            if fingerprint(str(path)) != e.note.baseline:
                self.message('This file changed outside Folio. Save As keeps both copies; Reload from disk opens the current disk version.')

    def message(self, text):
        self.banner.setText(text)
        self.banner.show()

    def error(self, exc):
        self.message(str(exc))
        QMessageBox.warning(self, 'Operation could not finish', str(exc))

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Open notes', '', 'Notes (*.txt *.md *.markdown *.folio);;All files (*)')
        for path in paths: self.open_path(path)

    def open_path(self, path):
        try:
            resolved = str(Path(path).resolve())
            existing = self.controller.find_path(resolved)
            if existing:
                window, editor = existing
                window.tabs.setCurrentWidget(editor)
                window.show(); window.raise_(); window.activateWindow()
                return
            note = read_note(resolved)
            self.add_note(note)
            self.controller.recent(resolved)
            self.controller.schedule()
            if note.source.startswith('.LOG\n') or note.source == '.LOG':
                self.editor.source.appendPlainText(QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm'))
        except (OSError, ValueError, UnicodeError) as exc: self.error(exc)

    def populate_recents(self):
        self.recent_menu.clear()
        for path in self.controller.settings.value('recents', [], list):
            self.recent_menu.addAction(path, lambda p=path: self.open_path(p))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction('Clear recent files', lambda: self.controller.settings.setValue('recents', []))

    def target(self, suffix=None):
        e = self.editor
        suggested = e.note.path or e.note.title
        from . import tabletools
        portable=bool(e.note.assets) or bool(e.note.rich and tabletools.tables(e.formatted.document()))
        if not Path(suggested).suffix:
            suggested += '.'+(suffix or ('folio' if portable else 'md' if e.note.rich or e.note.kind=='md' else 'txt'))
        filters = 'Portable note (*.folio);;Markdown (*.md);;Plain text (*.txt);;All files (*)'
        initial = 'Portable note (*.folio)' if portable else 'Markdown (*.md)' if e.note.rich or e.note.kind=='md' else 'Plain text (*.txt)'
        path, chosen = QFileDialog.getSaveFileName(self, 'Save note as', suggested, filters, initial)
        if path and not Path(path).suffix:
            path += '.folio' if '*.folio' in chosen else '.md' if '*.md' in chosen else '.txt'
        return path

    def confirm_markdown_layout(self):
        from . import tabletools
        e=self.editor
        if not e.note.rich or not tabletools.tables(e.formatted.document()): return True
        if getattr(e,'markdown_layout_confirmed',False): return True
        result=QMessageBox.question(self,'Markdown table layout',
            'Markdown keeps table text, but does not store column widths or row heights. Save as .folio to preserve the layout. Continue with Markdown?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        e.markdown_layout_confirmed=result==QMessageBox.StandardButton.Yes
        return e.markdown_layout_confirmed

    def serialize(self, path, e=None):
        e = e or self.editor
        n = e.note
        suffix = Path(path).suffix.lower()
        if suffix == '.folio': return pack_note(n, e.markdown(False))
        if suffix in ('.md', '.markdown'):
            if n.assets:
                folder = Path(path).parent/'assets'
                folder.mkdir(exist_ok=True)
                for key, raw in referenced_assets(n,e.markdown(False)).items():
                    destination = folder/Path(key).name
                    if destination.exists() and fingerprint(str(destination)) != digest(raw):
                        raise ValueError('An attachment with this name already exists with different content. Choose a different folder.')
                    atomic_write(destination, raw)
            return n.text_format.encode(e.markdown()) if n.rich else n.text_format.encode(n.source)
        if n.rich or n.assets:
            return e.plain_text().encode('utf-8')
        return n.text_format.encode(n.source)

    def save_current(self, save_as=False):
        e = self.editor
        if not e: return False
        n = e.note
        path = self.target() if save_as or not n.path else n.path
        if not path: return False
        path = str(Path(path).resolve())
        existing = self.controller.find_path(path)
        if existing and existing[1] is not e:
            self.error(ValueError('That file is already open in another tab. Choose another name.'))
            return False
        if n.path == path and fingerprint(path) != n.baseline:
            box = QMessageBox(self)
            box.setWindowTitle('File changed outside Folio')
            box.setText('Keep both versions with Save As, or explicitly overwrite the disk version.')
            as_button = box.addButton('Save As…', QMessageBox.ButtonRole.AcceptRole)
            overwrite = box.addButton('Overwrite disk version', QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is as_button: return self.save_current(True)
            if box.clickedButton() is not overwrite: return False
        suffix = Path(path).suffix.lower()
        if suffix not in ('.folio','.md','.markdown') and (n.rich or n.assets):
            QMessageBox.information(self, 'Export a text copy', 'Plain text cannot retain formatting, images or editable drawings. A text copy will be exported; your original document stays open and unsaved.')
            try:
                atomic_write(path, self.serialize(path))
                self.message('Text copy exported. The original document is still open.')
                return False
            except (OSError, ValueError) as exc: self.error(exc); return False
        if suffix in ('.md','.markdown') and not self.confirm_markdown_layout(): return False
        if suffix in ('.md','.markdown') and n.drawings:
            if QMessageBox.question(self, 'Drawing data in Markdown', 'Markdown saves drawing previews as images. Use .folio to keep editable strokes in a portable file. Continue with Markdown?',
                                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return False
        try:
            e.capture()
            raw = self.serialize(path)
            atomic_write(path, raw)
            n.path, n.title, n.baseline = path, Path(path).name, digest(raw)
            n.kind = 'folio' if suffix=='.folio' else 'md' if suffix in ('.md','.markdown') else 'txt'
            if not n.rich:
                _, n.text_format = TextFormat.decode(raw) if suffix != '.folio' else (n.source, n.text_format)
            e.mark_saved()
            self.controller.recent(path)
            self.controller.schedule()
            self.banner.hide()
            return True
        except (OSError, ValueError, UnicodeError) as exc:
            self.error(exc)
            return False

    def save_all(self):
        current = self.tabs.currentIndex()
        for index in range(self.tabs.count()):
            e = self.tabs.widget(index)
            if e.note.dirty or not e.note.path:
                self.tabs.setCurrentIndex(index)
                if not self.save_current(): break
        self.tabs.setCurrentIndex(current)

    def reload_file(self):
        e = self.editor
        if not e.note.path: return
        if QMessageBox.question(self, 'Reload file', 'Reload the disk version? Current edits will remain available under Draft recovery.') != QMessageBox.StandardButton.Yes: return
        try:
            self.controller.protect_sync(closed=[e.note])
            note = read_note(e.note.path)
            index = self.tabs.currentIndex()
            self.tabs.removeTab(index)
            e.deleteLater()
            self.add_note(note)
            self.banner.hide()
        except (OSError, ValueError) as exc: self.error(exc)

    def export(self, suffix, path=None):
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, 'Export a copy', Path(self.editor.note.title).stem+'.'+suffix,
                                                f'{suffix.upper()} (*.{suffix})')
        if not path: return False
        if not Path(path).suffix: path += '.'+suffix
        # Export must never overwrite a currently open user document.
        if self.controller.find_path(str(Path(path).resolve())):
            self.error(ValueError('Export to a different filename so the open document stays intact.'))
            return False
        if suffix == 'md' and not self.confirm_markdown_layout(): return False
        try:
            if suffix == 'pdf':
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                temporary=QTemporaryFile(str(Path(path).parent/'.folio-pdf-XXXXXX'))
                if not temporary.open(): raise OSError(temporary.errorString())
                temp_path=temporary.fileName(); temporary.close()
                printer.setOutputFileName(temp_path)
                self.render_print(printer)
                raw=Path(temp_path).read_bytes()
                if not raw.startswith(b'%PDF'): raise OSError('PDF export failed.')
                atomic_write(path,raw)
                temporary.remove()
            elif suffix == 'zip':
                e = self.editor
                markdown = e.markdown()
                if re.search(r'!\[[^]]*\]\((?!assets/)[^)]+\)', markdown):
                    if QMessageBox.question(self, 'External image references', 'This Markdown contains images outside the managed attachments. They will remain references and will not be bundled. Export anyway?') != QMessageBox.StandardButton.Yes: return False
                out = io.BytesIO()
                with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as z:
                    z.writestr('note.md', markdown.encode('utf-8'))
                    for key, raw in referenced_assets(e.note,markdown).items(): z.writestr(key, raw)
                    from . import tabletools
                    if e.note.drawings or (e.note.rich and tabletools.tables(e.formatted.document())):
                        z.writestr('editable.folio', pack_note(e.note, e.markdown(False)))
                atomic_write(path, out.getvalue())
            else:
                if suffix == 'txt' and self.editor.note.rich:
                    if QMessageBox.question(self, 'Export plain text', 'Formatting will become plain text, tables become text, and images become descriptions. The original note will remain open. Continue?') != QMessageBox.StandardButton.Yes: return False
                atomic_write(path, self.serialize(path))
            self.message('Exported '+str(path))
            return True
        except (OSError, ValueError) as exc: self.error(exc); return False

    def share(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Prepare a shareable Markdown bundle', 'note.zip', 'ZIP bundle (*.zip)')
        if path and self.export('zip', path):
            QApplication.clipboard().setText(str(Path(path).resolve()))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve().parent)))
            self.message('Share bundle prepared; its path is copied. Attach the ZIP in your preferred sharing app.')

    def printable(self):
        e = self.editor
        doc = SafeDocument({**e.note.assets,**getattr(e,'preview_images',{})}, self)
        if e.note.rich: doc.setHtml(e.note.html)
        elif e.note.kind == 'md': doc.setMarkdown(e.note.source, QTextDocument.MarkdownFeature.MarkdownDialectGitHub | QTextDocument.MarkdownFeature.MarkdownNoHTML)
        else: doc.setPlainText(e.note.source)
        return doc

    def print_document(self):
        if QPrintDialog(self.printer, self).exec() == QDialog.DialogCode.Accepted:
            try: self.render_print(self.printer)
            except OSError as exc: self.error(exc)

    def print_preview(self):
        dialog = QPrintPreviewDialog(self.printer, self)
        dialog.paintRequested.connect(self.render_print)
        dialog.exec()

    def render_print(self,printer):
        from .printing import print_document
        print_document(self.printable(),printer,self.editor.note.title,
                       self.controller.settings.value('print_header','&f'),
                       self.controller.settings.value('print_footer','Page &p'))

    def print_settings(self):
        dialog=QDialog(self); dialog.setWindowTitle('Print headers and footers')
        layout=QFormLayout(dialog)
        header=QLineEdit(self.controller.settings.value('print_header','&f'))
        footer=QLineEdit(self.controller.settings.value('print_footer','Page &p'))
        layout.addRow('Header:',header); layout.addRow('Footer:',footer)
        layout.addRow(QLabel('Tokens: &f filename, &p page, &d date, &t time; &l / &c / &r alignment. Empty fields disable them.'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.controller.settings.setValue('print_header',header.text())
            self.controller.settings.setValue('print_footer',footer.text())

    def load_local_images(self):
        e=self.editor
        if e.note.rich:
            self.message('Formatted notes already own their attachments. Use Insert > Image to add another.'); return
        folder=QFileDialog.getExistingDirectory(self,'Grant access to the Markdown document folder',str(Path(e.note.path).parent) if e.note.path else '')
        if not folder: return
        from urllib.parse import unquote
        root=Path(folder).resolve()
        images={}
        total=0
        try:
            for match in re.finditer(r'!\[[^]]*\]\(<?([^\s)>]+)>?\)',e.note.source):
                key=match.group(1)
                if QUrl(key).scheme() or Path(key).is_absolute(): continue
                candidate=(root/unquote(key)).resolve()
                if not candidate.is_relative_to(root) or not candidate.is_file(): continue
                if candidate.stat().st_size>25*1024*1024: continue
                raw=png_bytes(decode_image(candidate.read_bytes()))
                total+=len(raw)
                if total>64*1024*1024: raise ValueError('Combined preview images exceed 64 MiB.')
                images[key]=raw
            e.preview_images=images
            e.preview.document().assets={**e.note.assets,**images}
            e.view('split')
            self.message(f'Loaded {len(images)} local image(s) for preview. Create formatted copy to own these images in a portable note. Original Markdown is unchanged.')
        except (OSError,ValueError) as exc: self.error(exc)

    def text_settings(self):
        e=self.editor
        if e.note.kind=='folio':
            self.message('Portable notes use UTF-8 internally. Encoding options apply to text and Markdown files.'); return
        dialog=QDialog(self); dialog.setWindowTitle('Text format')
        layout=QFormLayout(dialog)
        encoding=QComboBox(); encoding.addItems(['utf-8','utf-16-le','utf-16-be'])
        encoding.setCurrentText(e.note.text_format.encoding)
        bom=QCheckBox('Write byte-order mark'); bom.setChecked(e.note.text_format.bom)
        ending=QComboBox(); ending.addItems(['Preserve existing endings','LF','CRLF','CR'])
        layout.addRow('Encoding:',encoding); layout.addRow(bom); layout.addRow('Line endings:',ending)
        layout.addRow(QLabel('Changes take effect on Save. Existing bytes stay intact until the save succeeds.'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            with e.operation('Text format'):
                e.note.text_format.encoding=encoding.currentText()
                e.note.text_format.bom=bom.isChecked()
                if ending.currentIndex():
                    e.note.text_format.eol={'LF':'\n','CRLF':'\r\n','CR':'\r'}[ending.currentText()]
                    e.note.text_format.normalize=True

    def rich_ready(self):
        e = self.editor
        if e.note.rich:
            e.view('formatted')
            return True
        if e.note.imported:
            return self.formatted_copy()
        if e.note.path and e.note.kind == 'txt':
            return self.formatted_copy()
        e.make_rich()
        return True

    def formatted_copy(self):
        e = self.editor
        if not e: return False
        if QMessageBox.question(self, 'Create formatted copy', 'Create a new unnamed formatted note? Markdown may be normalized. Unsupported markup may not carry over. The original file and source will stay unchanged.') != QMessageBox.StandardButton.Yes: return False
        source=e.markdown(False)
        assets=copy.deepcopy(e.note.assets)
        preview_images=getattr(e,'preview_images',{})
        def own_image(match):
            key=match.group(2)
            if key not in preview_images: return match.group(0)
            from uuid import uuid4
            owned='assets/'+str(uuid4())+'.png'
            assets[owned]=preview_images[key]
            return match.group(1)+owned+match.group(3)
        source=re.sub(r'(!\[[^]]*\]\()<?([^\s)>]+)>?(\))',own_image,source)
        n = Note(title=Path(e.note.title).stem+' — formatted copy', kind=e.note.kind,
                 source=source, assets=assets, drawings=copy.deepcopy(e.note.drawings))
        new = self.add_note(n)
        new.make_rich()
        return True

    def set_view(self, mode):
        e = self.editor
        if mode == 'edit':
            mode = 'formatted' if e.note.rich else 'source'
        e.view(mode)
        if e.note.rich and mode != 'formatted':
            self.message('Source is a read-only projection of this formatted note. Return to Edit to keep images, drawing data and undo history intact.')
        elif not e.note.rich and mode == 'formatted':
            self.message('Preview is read-only. Use Source to edit exact Markdown, or Create formatted copy for visual editing.')
        else: self.banner.hide()
        self.refresh()

    def format(self, name):
        if self.rich_ready(): self.editor.format_text(name)

    def set_heading(self, level):
        if self.rich_ready(): self.editor.heading(level)

    def list_format(self, ordered):
        if self.rich_ready(): self.editor.list_format(ordered)

    def indent(self, amount):
        if self.rich_ready(): self.editor.indent(amount)

    def quote(self):
        if not self.rich_ready(): return
        e = self.editor
        with e.operation('Block quote'):
            c = e.formatted.textCursor()
            fmt = c.blockFormat()
            fmt.setProperty(QTextFormat.Property.BlockQuoteLevel, 1)
            fmt.setLeftMargin(24)
            c.setBlockFormat(fmt)

    def code_block(self):
        if not self.rich_ready(): return
        e = self.editor
        with e.operation('Code block'):
            c = e.formatted.textCursor()
            fmt = c.blockFormat()
            fmt.setProperty(QTextFormat.Property.BlockCodeFence, '```')
            c.setBlockFormat(fmt)
            f = QTextCharFormat()
            f.setFontFamilies(['monospace'])
            c.mergeCharFormat(f)

    def dimensions(self, title, rows=3, columns=3):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QFormLayout(dialog)
        r, c = QSpinBox(), QSpinBox()
        r.setRange(1,1000); r.setValue(rows)
        c.setRange(1,100); c.setValue(columns)
        layout.addRow('Rows:', r)
        layout.addRow('Columns:', c)
        layout.addRow(QLabel('Maximum 20,000 cells. Shrinking removes cells; Undo restores them.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        return (r.value(), c.value()) if dialog.exec() == QDialog.DialogCode.Accepted else None

    def table_dialog(self):
        if not self.rich_ready(): return
        size = self.dimensions('Insert table')
        if size:
            try: self.editor.insert_table(*size)
            except ValueError as exc: self.error(exc)

    def table_action(self, op):
        e = self.editor
        table = e.formatted.textCursor().currentTable()
        try:
            if op == 'resize':
                if not table: raise ValueError('Place the cursor in a table first.')
                size = self.dimensions('Table size', table.rows(), table.columns())
                if not size: return
                if size[0] < table.rows() or size[1] < table.columns():
                    removed = 0
                    for row in range(table.rows()):
                        for col in range(table.columns()):
                            if row >= size[0] or col >= size[1]:
                                cell = table.cellAt(row,col)
                                cursor = cell.firstCursorPosition()
                                cursor.setPosition(cell.lastCursorPosition().position(), QTextCursor.MoveMode.KeepAnchor)
                                removed += bool(cursor.selectedText())
                    if QMessageBox.question(self, 'Remove table cells', f'{removed} nonempty cells will be removed. Apply the smaller dimensions? Undo can restore them.') != QMessageBox.StandardButton.Yes: return
                e.table_operation(op, size[0], size[1])
            elif op in ('column_width','row_height'):
                if not table: raise ValueError('Place the cursor in a table first.')
                from . import tabletools
                cell=table.cellAt(e.formatted.textCursor())
                if op=='column_width':
                    value=round(tabletools.widths(e.formatted.document(),table)[cell.column()])
                    chosen,ok=QInputDialog.getInt(self,'Column width','Width in pixels:',value,40,2000)
                    if ok: e.resize_column(chosen)
                else:
                    _,ys=tabletools.grid(e.formatted.document(),table)
                    chosen,ok=QInputDialog.getInt(self,'Row minimum height','Minimum height in pixels (content can grow):',round(ys[cell.row()+1]-ys[cell.row()]),24,2000)
                    if ok: e.resize_row(chosen)
            else: e.table_operation(op)
        except ValueError as exc: self.error(exc)

    def insert_image(self, data=None):
        if not self.rich_ready(): return
        if isinstance(data, bool): data = None
        if data is None:
            data, _ = QFileDialog.getOpenFileName(self, 'Insert image', '', 'Images (*.png *.jpg *.jpeg *.webp)')
            if not data: return
        try:
            raw = Path(data).read_bytes() if isinstance(data, str) else png_bytes(data)
            alt, ok = QInputDialog.getText(self, 'Image description', 'Alt text:', text=Path(data).stem if isinstance(data,str) else 'Image')
            if ok: self.editor.add_image(raw, alt)
        except (OSError, ValueError, TypeError) as exc: self.error(exc)

    def drawing(self, key=None):
        if isinstance(key, bool): key = None
        if self.editor.ink and key is None:
            self.editor.ink.finish()
            return
        if not self.rich_ready(): return
        e = self.editor
        if key is None:
            fmt=e.formatted.textCursor().charFormat()
            if fmt.isImageFormat() and fmt.toImageFormat().name() in e.note.drawings:
                key=fmt.toImageFormat().name()
        try: e.start_drawing(key)
        except ValueError as exc: self.error(exc)

    def update_drawing_tools(self):
        ink=bool(self.editor and self.editor.ink)
        self.normal_tools_action.setVisible(not ink)
        self.drawing_tools_action.setVisible(ink)
        self.rail_buttons['Draw'].setChecked(ink)
        self.drawing_tools.refresh()

    def edit_image(self, key):
        if key in self.editor.note.drawings:
            self.drawing(key); return
        e=self.editor
        position=e.image_position(key)
        if position is None: return
        cursor=QTextCursor(e.formatted.document()); cursor.setPosition(position)
        cursor.setPosition(position+1,QTextCursor.MoveMode.KeepAnchor)
        image_format=cursor.charFormat().toImageFormat()
        dialog=QDialog(self); dialog.setWindowTitle('Image properties')
        layout=QFormLayout(dialog)
        alt=QLineEdit(str(image_format.property(QTextFormat.Property.ImageAltText) or 'Image'))
        width=QSpinBox(); width.setRange(24,4000); width.setValue(int(image_format.width()) or 400)
        layout.addRow('Description:',alt); layout.addRow('Width (aspect ratio preserved):',width)
        choice={'path':None,'remove':False}
        replace=QPushButton('Replace / locate image…')
        def locate():
            path,_=QFileDialog.getOpenFileName(dialog,'Replace image','','Images (*.png *.jpg *.jpeg *.webp)')
            if path: choice['path']=path; replace.setText(Path(path).name)
        replace.clicked.connect(locate); layout.addRow(replace)
        remove=QPushButton('Remove image')
        def remove_image(): choice['remove']=True; dialog.accept()
        remove.clicked.connect(remove_image); layout.addRow(remove)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addRow(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted: return
        try:
            if choice['remove']:
                with e.operation('Remove image'): cursor.removeSelectedText()
            else:
                raw=Path(choice['path']).read_bytes() if choice['path'] else e.note.assets.get(key)
                if raw is None: raise ValueError('Locate a replacement image first.')
                e.add_image(raw,alt.text(),replace=key,width=width.value())
        except (OSError,ValueError) as exc: self.error(exc)

    def link(self):
        if not self.rich_ready(): return
        url, ok = QInputDialog.getText(self, 'Insert link', 'Web or email address:')
        if not ok: return
        if QUrl(url).scheme() not in ('https','http','mailto'):
            self.error(ValueError('Use an https://, http:// or mailto: link.'))
            return
        e = self.editor
        with e.operation('Insert link'):
            c = e.formatted.textCursor()
            label = c.selectedText() or url
            fmt = QTextCharFormat()
            fmt.setAnchor(True); fmt.setAnchorHref(url)
            fmt.setForeground(QColor('#447ed2')); fmt.setFontUnderline(True)
            c.insertText(label, fmt)

    def insert_text(self, text):
        e = self.editor
        if e.active.isReadOnly(): return
        with e.operation('Insert text'): e.active.textCursor().insertText(text)

    def show_search(self,replace=False):
        self.replace_toggle.setChecked(replace)
        self.search.show()
        self.query.setFocus(); self.query.selectAll()
        selected = self.editor.active.textCursor().selectedText()
        if selected and '\u2029' not in selected: self.query.setText(selected)

    def search_pattern(self):
        flags = QTextDocument.FindFlag(0)
        if self.case.isChecked(): flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.words.isChecked(): flags |= QTextDocument.FindFlag.FindWholeWords
        pattern = self.query.text()
        if self.regex.isChecked():
            pattern = QRegularExpression(pattern)
            if not pattern.isValid(): raise ValueError(pattern.errorString())
            if not self.case.isChecked(): pattern.setPatternOptions(QRegularExpression.PatternOption.CaseInsensitiveOption)
        return pattern, flags

    def find(self, backward=False):
        if not self.query.text(): self.show_search(); return False
        try:
            pattern, flags = self.search_pattern()
            if backward: flags |= QTextDocument.FindFlag.FindBackward
            active = self.editor.active
            result = active.document().find(pattern, active.textCursor(), flags)
            if result.isNull():
                start = active.document().characterCount()-1 if backward else 0
                result = active.document().find(pattern, start, flags)
            self.search_result.setText('No matches' if result.isNull() else 'Match found')
            if not result.isNull(): active.setTextCursor(result); active.ensureCursorVisible(); return True
            return False
        except ValueError as exc: self.search_result.setText(str(exc)); return False

    def replace_one(self):
        e=self.editor
        if e.active.isReadOnly() or not self.query.text(): return
        try:
            pattern,flags=self.search_pattern()
            current=e.active.textCursor()
            match=e.active.document().find(pattern,current.selectionStart(),flags)
            if (match.isNull() or not current.hasSelection() or
                    match.selectionStart()!=current.selectionStart() or match.selectionEnd()!=current.selectionEnd()):
                if not self.find(): return
            self.insert_text(self.replacement.text()); self.find()
        except ValueError as exc: self.search_result.setText(str(exc))

    def replace_all(self):
        e = self.editor
        if e.active.isReadOnly() or not self.query.text(): return
        try:
            pattern, flags = self.search_pattern()
            matches, pos, doc = [], 0, e.active.document()
            while pos < doc.characterCount():
                c = doc.find(pattern, pos, flags)
                if c.isNull(): break
                a,b = c.selectionStart(),c.selectionEnd()
                if a == b: pos=b+1; continue
                matches.append((a,b)); pos=b
            with e.operation('Replace all'):
                for a,b in reversed(matches):
                    c = QTextCursor(doc); c.setPosition(a); c.setPosition(b,QTextCursor.MoveMode.KeepAnchor)
                    c.insertText(self.replacement.text())
            self.search_result.setText(f'{len(matches)} replacements')
        except ValueError as exc: self.search_result.setText(str(exc))

    def goto(self):
        e = self.editor
        if e.note.rich: self.set_view('source')
        number, ok = QInputDialog.getInt(self, 'Go to line', 'Line:', 1, 1, e.source.blockCount())
        if ok:
            c = QTextCursor(e.source.document().findBlockByNumber(number-1))
            e.source.setTextCursor(c); e.source.ensureCursorVisible(); e.source.setFocus()

    def zoom(self, amount):
        self.editor.set_zoom(self.editor.note.zoom+amount if amount else 100)
        self.refresh()

    def word_wrap(self, enabled):
        from PySide6.QtWidgets import QPlainTextEdit
        for i in range(self.tabs.count()):
            e = self.tabs.widget(i)
            e.source.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap)
            e.formatted.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if enabled else QTextEdit.LineWrapMode.NoWrap)

    def choose_font(self):
        ok, font = QFontDialog.getFont(self.editor.active.font(), self)
        if ok:
            for e in (self.editor.source,self.editor.formatted,self.editor.preview): e.setFont(font)
            self.controller.settings.setValue('editor_font',font.toString())

    def ai_dialog(self):
        if self.editor.active.isReadOnly():
            self.message('Switch to an editable view first.'); return
        from .ai import AiDialog
        dialog=AiDialog(self.editor,self.controller.settings,self)
        dialog.exec()

    def spell_language(self):
        try:
            import enchant
            names = ['Disabled']+enchant.list_languages()
        except ImportError: names = ['Disabled']
        name, ok = QInputDialog.getItem(self, 'Spellcheck language', 'Available dictionary:', names, 0, False)
        if ok:
            self.editor.spelling.language('' if name=='Disabled' else name)
            self.editor.source_spelling.language('' if name=='Disabled' else name)

    def spell_suggestions(self):
        e = self.editor
        spelling = e.spelling if e.editable else e.source_spelling
        dictionary = spelling.dictionary
        if not dictionary:
            self.spell_language(); return
        c = e.active.textCursor()
        c.select(QTextCursor.SelectionType.WordUnderCursor)
        word = c.selectedText()
        options = dictionary.suggest(word)[:8]+['Ignore for this note','Add to dictionary']
        choice, ok = QInputDialog.getItem(self, 'Spelling', word, options, 0, False)
        if ok:
            if choice == 'Ignore for this note': spelling.ignored.add(word); spelling.rehighlight()
            elif choice == 'Add to dictionary': dictionary.add(word); spelling.rehighlight()
            else:
                with e.operation('Correct spelling'): c.insertText(choice)

    def update_theme_controls(self,name):
        if not hasattr(self,'theme_actions'): return
        self.theme_actions[name].setChecked(True)
        self.theme_button.setText('Theme: '+name)
        from .workspace import apply_style
        apply_style(self)

    def preferences(self):
        dialog = QDialog(self); dialog.setWindowTitle('Preferences')
        layout = QFormLayout(dialog)
        keep = QCheckBox('Keep drafts and restore on next launch')
        keep.setChecked(self.controller.settings.value('keep_drafts', True, bool))
        recent = QCheckBox('Remember recently opened files')
        recent.setChecked(self.controller.settings.value('remember_recents', True, bool))
        theme = QComboBox(); theme.addItems(['System','Light','Dark'])
        theme.setCurrentText(self.controller.settings.value('theme','System'))
        layout.addRow(keep); layout.addRow(recent); layout.addRow('Theme:',theme)
        layout.addRow(QLabel('Drafts are stored locally, without encryption. No note is uploaded automatically.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.settings.setValue('keep_drafts',keep.isChecked())
            self.controller.settings.setValue('remember_recents',recent.isChecked())
            if not recent.isChecked(): self.controller.settings.setValue('recents',[])
            self.controller.settings.setValue('theme',theme.currentText())
            self.controller.theme(theme.currentText())

    def tab_menu(self, pos):
        index = self.tabs.tabBar().tabAt(pos)
        if index < 0: return
        self.tabs.setCurrentIndex(index)
        menu = QMenu(self)
        menu.addAction('Rename draft…', self.rename)
        menu.addAction('Duplicate note', self.duplicate)
        menu.addAction('Move to new window', self.move_window)
        menu.addAction('Close other tabs', lambda: self.close_others(index,False))
        menu.addAction('Close tabs to the right', lambda: self.close_others(index,True))
        menu.exec(self.tabs.tabBar().mapToGlobal(pos))

    def rename(self):
        if self.editor.note.path:
            self.save_current(True); return
        title, ok = QInputDialog.getText(self,'Rename draft','Title:',text=self.editor.note.title)
        if ok and title.strip(): self.editor.note.title=title.strip(); self.refresh(); self.controller.schedule()

    def duplicate(self):
        note = Note.from_dict(self.editor.note.to_dict())
        from uuid import uuid4
        note.id, note.path, note.baseline, note.dirty = str(uuid4()), '', None, True
        note.title += ' — copy'
        self.add_note(note); self.controller.schedule()

    def move_window(self):
        e=self.editor
        for signal in (e.changed,e.position_changed,e.image_requested,e.image_edit,e.table_requested,e.operation_error,e.history_changed):
            signal.disconnect()
        self.tabs.removeTab(self.tabs.currentIndex())
        window=self.controller.new_window(empty=True)
        e.note.window=window.window_id
        e.changed.connect(lambda:(window.refresh(),self.controller.schedule()))
        e.position_changed.connect(window.refresh)
        e.history_changed.connect(window.refresh)
        e.image_requested.connect(window.insert_image)
        e.image_edit.connect(window.edit_image)
        e.table_requested.connect(window.table_action)
        e.operation_error.connect(window.message)
        index=window.tabs.addTab(e,e.note.title)
        window.tab_close_button(index,e)
        window.tabs.setCurrentWidget(e)
        window.refresh()
        if not self.tabs.count(): self.add_note()
        self.controller.schedule()

    def close_others(self, keep, right_only):
        for index in reversed(range(self.tabs.count())):
            if index != keep and (not right_only or index > keep):
                if not self.close_tab(index): break

    def close_tab(self, index, create=True):
        e = self.tabs.widget(index)
        if not e: return True
        if not self.controller.prepare_close(e,self): return False
        if e.ink: e.ink.finish()
        note = e.note
        self.tabs.removeTab(index)
        try:
            self.controller.protect_sync(
                closed=[note] if self.controller.settings.value('keep_drafts',True,bool) else [],
                discard_ids=[note.id] if getattr(note,'discard_requested',False) else [])
        except Exception as exc:
            note.discard_requested=False
            self.tabs.insertTab(index,e,note.title); self.error(exc); return False
        e.deleteLater()
        if not self.tabs.count() and create: self.add_note()
        self.refresh()
        return True

    def reopen(self):
        try:
            active_ids = {e.note.id for e in self.controller.editors()}
            notes = [n for n in self.controller.recoverable() if n.id not in active_ids]
            if not notes:
                QMessageBox.information(self,'Draft recovery','No closed drafts are available.'); return
            labels = [f'{n.title} — {n.path or "unnamed draft"} — {n.id[:8]}' for n in notes]
            choice, ok = QInputDialog.getItem(self,'Draft recovery','Restore a draft:',labels,0,False)
            if ok: self.add_note(notes[labels.index(choice)]); self.controller.schedule()
        except (OSError, ValueError) as exc: self.error(exc)

    def shortcuts(self):
        lines = [f'{a.shortcut().toString():18} {name}' for name,a in self.actions.items() if not a.shortcut().isEmpty()]
        QMessageBox.information(self,'Keyboard shortcuts','\n'.join(lines))

    def about(self):
        QMessageBox.about(self,'Folio Notepad',f'<h2>Folio Notepad {__version__}</h2><p>A native, offline-first editor for Fedora KDE.</p><p>Text · Markdown · Tables · Images · Drawings</p><p>PySide6 / Qt 6. No account required.</p><p>This is a development release. See docs/status.md for remaining plan items.</p>')

    def closeEvent(self, event):
        if self.controller.closing:
            event.accept(); return
        original_windows=list(self.controller.windows)
        for index in range(self.tabs.count()):
            if not self.controller.prepare_close(self.tabs.widget(index), self):
                for e in self.controller.editors(): e.note.discard_requested=False
                event.ignore(); return
        try:
            self.controller.protect_sync(discard_pending=True)
            self.controller.settings.setValue('geometry',self.saveGeometry())
            # Last window remains active in the saved session for next launch.
            if len(self.controller.windows) > 1:
                notes = [self.tabs.widget(i).note for i in range(self.tabs.count())]
                self.controller.windows.remove(self)
                self.controller.protect_sync(closed=notes, discard_ids=[n.id for n in notes if getattr(n,'discard_requested',False)])
            self.controller.windows = [w for w in self.controller.windows if w is not self]
            event.accept()
        except Exception as exc:
            self.controller.windows=original_windows
            for e in self.controller.editors(): e.note.discard_requested=False
            self.error(exc); event.ignore()
