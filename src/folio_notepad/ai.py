"""Optional Ollama-compatible generation. No requests happen before Generate."""
import json
from PySide6.QtCore import QByteArray,QTimer,QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkReply,QNetworkRequest
from PySide6.QtWidgets import (QComboBox,QDialog,QDialogButtonBox,QFormLayout,
    QLabel,QLineEdit,QMessageBox,QPlainTextEdit,QPushButton,QVBoxLayout)


class StreamDecoder:
    def __init__(self):
        self.buffer=b''
        self.size=0
        self.done=False

    def feed(self,raw,final=False):
        self.size += len(raw)
        if self.size>4*1024*1024: raise ValueError('Response exceeds the 4 MiB limit.')
        self.buffer+=raw
        parts=self.buffer.split(b'\n')
        self.buffer=parts.pop()
        if final and self.buffer: parts.append(self.buffer); self.buffer=b''
        result=[]
        for line in parts:
            if not line.strip(): continue
            entry=json.loads(line)
            if not isinstance(entry,dict): raise ValueError('Invalid response object.')
            if entry.get('error'): raise ValueError(str(entry['error']))
            text=entry.get('response','')
            if not isinstance(text,str): raise ValueError('Invalid response text.')
            result.append(text)
            self.done |= bool(entry.get('done'))
        return ''.join(result)


class AiDialog(QDialog):
    def __init__(self,editor,settings,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Writing assistant — optional local model')
        self.resize(760,720)
        self.editor,self.settings=editor,settings
        self.revision=editor.note.revision
        self.cursor=QTextCursor(editor.active.textCursor())
        self.original_selection=self.cursor.hasSelection()
        self.reply=None
        self.decoder=StreamDecoder()
        self.network=QNetworkAccessManager(self)
        layout=QVBoxLayout(self)
        info=QLabel('Requires a running Ollama-compatible server and an installed model. Nothing is sent until Generate. The exact prompt is shown below. Credentials are session-only.')
        info.setWordWrap(True); layout.addWidget(info)
        form=QFormLayout()
        self.endpoint=QLineEdit(settings.value('ai_endpoint','http://127.0.0.1:11434/api/generate'))
        self.model=QLineEdit(settings.value('ai_model',''))
        self.model.setPlaceholderText('Name of a model already installed on your server')
        self.token=QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.operation=QComboBox(); self.operation.addItems(['Write','Rewrite','Summarize'])
        form.addRow('Endpoint:',self.endpoint); form.addRow('Model:',self.model)
        form.addRow('Bearer token (optional):',self.token); form.addRow('Action:',self.operation)
        layout.addLayout(form)
        self.prompt=QPlainTextEdit(); self.prompt.setAccessibleName('Exact prompt sent to model')
        text=self.cursor.selectedText().replace('\u2029','\n') if self.original_selection else editor.plain_text()
        self.input_text=text
        self.operation.currentTextChanged.connect(self.set_prompt)
        self.set_prompt('Write')
        layout.addWidget(QLabel('Exact prompt / instructions (editable):')); layout.addWidget(self.prompt)
        self.generate_button=QPushButton('Generate')
        self.generate_button.clicked.connect(self.generate); layout.addWidget(self.generate_button)
        self.result=QPlainTextEdit(); self.result.setReadOnly(True)
        self.result.setAccessibleName('Generated text preview')
        layout.addWidget(self.result)
        self.status=QLabel('Offline editor remains available without configuring a model.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.accept_button=buttons.button(QDialogButtonBox.StandardButton.Save)
        self.accept_button.setText('Accept text'); self.accept_button.setEnabled(False)
        buttons.accepted.connect(self.accept_result); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timer=QTimer(self); self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)

    def set_prompt(self,action):
        instruction={'Write':'Write a clear passage based on these notes or instructions:',
                     'Rewrite':'Rewrite the following text for clarity. Return only the rewritten text:',
                     'Summarize':'Summarize the following text. Return only the summary:'}[action]
        self.prompt.setPlainText(instruction+'\n\n'+self.input_text)

    def generate(self):
        url=QUrl(self.endpoint.text())
        if url.scheme() not in ('http','https') or not url.host() or url.userInfo():
            self.status.setText('Choose an http(s) endpoint without embedded credentials.'); return
        if not self.model.text().strip(): self.status.setText('Enter an installed model name.'); return
        if url.host() not in ('127.0.0.1','localhost','::1'):
            if QMessageBox.question(self,'Send prompt to another computer',f'The displayed prompt will be sent to {url.host()}. Continue?') != QMessageBox.StandardButton.Yes: return
        self.settings.setValue('ai_endpoint',self.endpoint.text())
        self.settings.setValue('ai_model',self.model.text())
        self.revision=self.editor.note.revision
        self.result.clear(); self.decoder=StreamDecoder()
        request=QNetworkRequest(url)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,'application/json')
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        if self.token.text(): request.setRawHeader(b'Authorization',('Bearer '+self.token.text()).encode())
        data=json.dumps({'model':self.model.text().strip(),'prompt':self.prompt.toPlainText(),'stream':True}).encode()
        if len(data)>1024*1024: self.status.setText('Prompt exceeds 1 MiB. Select less text.'); return
        self.reply=self.network.post(request,QByteArray(data))
        self.reply.readyRead.connect(self.consume)
        self.reply.finished.connect(self.finished)
        self.generate_button.setEnabled(False); self.accept_button.setEnabled(False)
        self.timer.start(120000)
        self.status.setText('Generating… Cancel closes this dialog and aborts the request.')

    def consume(self,final=False):
        if not self.reply: return
        try:
            text=self.decoder.feed(bytes(self.reply.readAll()),final)
            c=self.result.textCursor(); c.movePosition(QTextCursor.MoveOperation.End); c.insertText(text)
        except (ValueError,UnicodeError) as exc:
            self.status.setText(str(exc)); self.reply.abort()

    def finished(self):
        self.timer.stop()
        reply=self.reply
        self.consume(True)
        good=(reply.error()==QNetworkReply.NetworkError.NoError and self.decoder.done)
        if good: self.status.setText('Review the preview. Accept changes the note; Cancel leaves it unchanged.')
        else: self.status.setText('Generation failed or ended early: '+reply.errorString())
        self.generate_button.setEnabled(True)
        self.accept_button.setEnabled(good and bool(self.result.toPlainText()))
        reply.deleteLater(); self.reply=None

    def timeout(self):
        if self.reply: self.reply.abort()
        self.status.setText('Generation timed out. The note is unchanged.')

    def accept_result(self):
        if self.editor.note.revision != self.revision:
            self.status.setText('The note changed while generating. Copy the preview manually or generate again; new edits were not overwritten.'); return
        with self.editor.operation('Accept generated text'):
            if not self.original_selection:
                self.cursor.movePosition(QTextCursor.MoveOperation.End)
                self.cursor.insertText('\n\n')
            self.cursor.insertText(self.result.toPlainText())
        self.accept()

    def reject(self):
        if self.reply: self.reply.abort()
        super().reject()

    def closeEvent(self,event):
        if self.reply: self.reply.abort()
        super().closeEvent(event)
