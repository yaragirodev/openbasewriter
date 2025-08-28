import os
import sys
import json
import time
import threading
import logging
from ftplib import FTP, error_perm
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QFileDialog, QProgressBar, QPlainTextEdit, QGroupBox, QGridLayout, QMessageBox, QDialog,
    QDialogButtonBox, QFormLayout
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    PYFTPDLIB_AVAILABLE = True
except Exception:
    PYFTPDLIB_AVAILABLE = False


class Worker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    log = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn = fn
        self.args = args

    def start(self):
        def run():
            try:
                result = self.fn(*self.args, self)
                self.finished.emit(result)
            except Exception as e:
                self.error.emit(str(e))
        threading.Thread(target=run, daemon=True).start()


class AddUserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add User")
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.homedir = QLineEdit()
        self.perm = QLineEdit("elradfmw")
        form = QFormLayout()
        form.addRow("Username:", self.username)
        form.addRow("Password:", self.password)
        form.addRow("Home dir:", self.homedir)
        form.addRow("Permissions:", self.perm)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(btns)
        self.setLayout(layout)

    def get_data(self):
        return dict(
            username=self.username.text(),
            password=self.password.text(),
            homedir=self.homedir.text(),
            perm=self.perm.text()
        )


class OpenZilla(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenBaseWriter")
        self.resize(1000, 700)

        self.ftp = None
        self.server = None
        self.server_thread = None
        self.local_path = os.getcwd()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.client_tab = QWidget()
        self.server_tab = QWidget()
        self.tabs.addTab(self.client_tab, "Client")
        self.tabs.addTab(self.server_tab, "Server")

        self.setup_client()
        self.setup_server()

    def setup_client(self):
        layout = QVBoxLayout()
        top = QHBoxLayout()
        self.host = QLineEdit(); self.host.setPlaceholderText("Host")
        self.user = QLineEdit(); self.user.setPlaceholderText("User")
        self.pwd = QLineEdit(); self.pwd.setEchoMode(QLineEdit.EchoMode.Password); self.pwd.setPlaceholderText("Password")
        self.port = QLineEdit("21")
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connect)
        for w in [self.host, self.user, self.pwd, self.port, self.connect_btn]:
            top.addWidget(w)
        layout.addLayout(top)

        split = QHBoxLayout()
        self.local_tree = QTreeWidget(); self.local_tree.setHeaderLabels(["Name", "Size"])
        self.remote_tree = QTreeWidget(); self.remote_tree.setHeaderLabels(["Name", "Size"])
        split.addWidget(self.local_tree, 1)
        split.addWidget(self.remote_tree, 1)
        layout.addLayout(split)

        buttons = QHBoxLayout()
        self.download_btn = QPushButton("Download")
        self.upload_btn = QPushButton("Upload")
        self.download_btn.clicked.connect(self.download)
        self.upload_btn.clicked.connect(self.upload)
        self.download_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        buttons.addWidget(self.download_btn)
        buttons.addWidget(self.upload_btn)
        layout.addLayout(buttons)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.client_log = QPlainTextEdit(); self.client_log.setReadOnly(True)
        layout.addWidget(self.client_log, 1)

        self.client_tab.setLayout(layout)
        self.refresh_local()

    def setup_server(self):
        layout = QVBoxLayout()
        top = QHBoxLayout()
        self.s_ip = QLineEdit("0.0.0.0")
        self.s_port = QLineEdit("2121")
        self.start_btn = QPushButton("Start Server")
        self.stop_btn = QPushButton("Stop Server")
        self.start_btn.clicked.connect(self.start_server)
        self.stop_btn.clicked.connect(self.stop_server)
        self.stop_btn.setEnabled(False)
        for w in [QLabel("IP:"), self.s_ip, QLabel("Port:"), self.s_port, self.start_btn, self.stop_btn]:
            top.addWidget(w)
        layout.addLayout(top)

        self.users = QTreeWidget(); self.users.setHeaderLabels(["Username", "Home", "Perm"])
        layout.addWidget(self.users, 1)
        user_btns = QHBoxLayout()
        add = QPushButton("Add User"); add.clicked.connect(self.add_user)
        rm = QPushButton("Remove User"); rm.clicked.connect(self.remove_user)
        save = QPushButton("Save JSON"); save.clicked.connect(self.save_users)
        load = QPushButton("Load JSON"); load.clicked.connect(self.load_users)
        for w in [add, rm, save, load]: user_btns.addWidget(w)
        layout.addLayout(user_btns)

        self.server_log = QPlainTextEdit(); self.server_log.setReadOnly(True)
        layout.addWidget(self.server_log, 1)

        self.server_tab.setLayout(layout)

    def log_client(self, msg): self.client_log.appendPlainText(msg)
    def log_server(self, msg): self.server_log.appendPlainText(msg)

    def refresh_local(self):
        self.local_tree.clear()
        for f in os.listdir(self.local_path):
            path = os.path.join(self.local_path, f)
            size = str(os.path.getsize(path)) if os.path.isfile(path) else "<DIR>"
            self.local_tree.addTopLevelItem(QTreeWidgetItem([f, size]))

    def toggle_connect(self):
        if self.ftp:
            self.ftp.quit()
            self.ftp = None
            self.connect_btn.setText("Connect")
            self.download_btn.setEnabled(False)
            self.upload_btn.setEnabled(False)
            self.log_client("Disconnected.")
        else:
            try:
                self.ftp = FTP()
                self.ftp.connect(self.host.text(), int(self.port.text()))
                self.ftp.login(self.user.text(), self.pwd.text())
                self.connect_btn.setText("Disconnect")
                self.download_btn.setEnabled(True)
                self.upload_btn.setEnabled(True)
                self.log_client("Connected.")
                self.refresh_remote()
            except Exception as e:
                self.log_client(f"Error: {e}")
                self.ftp = None

    def refresh_remote(self):
        self.remote_tree.clear()
        try:
            for name in self.ftp.nlst():
                try:
                    size = self.ftp.size(name) or 0
                except Exception:
                    size = "<DIR>"
                self.remote_tree.addTopLevelItem(QTreeWidgetItem([name, str(size)]))
        except Exception as e:
            self.log_client(f"Remote list error: {e}")

    def upload(self):
        item = self.local_tree.currentItem()
        if not item: return
        name = item.text(0)
        path = os.path.join(self.local_path, name)
        with open(path, "rb") as f:
            self.ftp.storbinary(f"STOR {name}", f)
        self.log_client(f"Uploaded {name}")
        self.refresh_remote()

    def download(self):
        item = self.remote_tree.currentItem()
        if not item: return
        name = item.text(0)
        with open(os.path.join(self.local_path, name), "wb") as f:
            self.ftp.retrbinary(f"RETR {name}", f.write)
        self.log_client(f"Downloaded {name}")
        self.refresh_local()

    def add_user(self):
        dlg = AddUserDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.users.addTopLevelItem(QTreeWidgetItem([data["username"], data["homedir"], data["perm"]]))
            self.users.topLevelItem(self.users.topLevelItemCount()-1).setData(0, Qt.ItemDataRole.UserRole, data["password"])

    def remove_user(self):
        item = self.users.currentItem()
        if item: self.users.takeTopLevelItem(self.users.indexOfTopLevelItem(item))

    def save_users(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Save Users", filter="JSON Files (*.json)")
        if not fname: return
        data = []
        for i in range(self.users.topLevelItemCount()):
            it = self.users.topLevelItem(i)
            data.append(dict(
                username=it.text(0),
                password=it.data(0, Qt.ItemDataRole.UserRole),
                homedir=it.text(1),
                perm=it.text(2)
            ))
        with open(fname, "w") as f: json.dump(data, f, indent=2)
        self.log_server(f"Saved {len(data)} users.")

    def load_users(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Load Users", filter="JSON Files (*.json)")
        if not fname: return
        with open(fname) as f: data = json.load(f)
        self.users.clear()
        for u in data:
            it = QTreeWidgetItem([u["username"], u["homedir"], u["perm"]])
            it.setData(0, Qt.ItemDataRole.UserRole, u["password"])
            self.users.addTopLevelItem(it)
        self.log_server(f"Loaded {len(data)} users.")

    def start_server(self):
        if not PYFTPDLIB_AVAILABLE:
            QMessageBox.critical(self, "Error", "pyftpdlib not installed")
            return
        authorizer = DummyAuthorizer()
        for i in range(self.users.topLevelItemCount()):
            it = self.users.topLevelItem(i)
            authorizer.add_user(it.text(0), it.data(0, Qt.ItemDataRole.UserRole), it.text(1), perm=it.text(2))
        handler = FTPHandler; handler.authorizer = authorizer
        self.server = FTPServer((self.s_ip.text(), int(self.s_port.text())), handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.log_server("Server started.")
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)

    def stop_server(self):
        if self.server:
            self.server.close_all()
            self.server = None
            self.log_server("Server stopped.")
            self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = OpenZilla()
    w.show()
    sys.exit(app.exec())
