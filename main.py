import sys
import sqlite3
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem
)
from PyQt6.QtCore import Qt


class DBViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OBW - OpenBaseWriter")
        self.resize(1000, 700)

        self.conn = None
        self.cursor = None
        self.current_table_name = ""

        # UI
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Панель управления
        control_layout = QHBoxLayout()
        main_layout.addLayout(control_layout)

        self.open_button = QPushButton("Открыть файл .db")
        self.open_button.clicked.connect(self.open_db_file)
        control_layout.addWidget(self.open_button)

        self.table_selector = QComboBox()
        self.table_selector.currentIndexChanged.connect(self.on_table_selected)
        control_layout.addWidget(self.table_selector)

        # Таблица
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self.table.cellChanged.connect(self.on_cell_changed)
        main_layout.addWidget(self.table)

        # служебные переменные
        self._updating = False  # защита от рекурсии при cellChanged

    def open_db_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл базы данных",
            "",
            "Database files (*.db);;All files (*.*)"
        )
        if not file_path:
            return

        if self.conn:
            self.conn.close()

        try:
            self.conn = sqlite3.connect(file_path)
            self.cursor = self.conn.cursor()
            self.setWindowTitle(f"OBW - {file_path}")
            self.load_tables_list()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл базы данных:\n{e}")
            self.conn = None
            self.cursor = None
            self.table_selector.clear()
            self.table.clear()

    def load_tables_list(self):
        try:
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = self.cursor.fetchall()
            table_names = [table[0] for table in tables]
            self.table_selector.clear()
            self.table_selector.addItems(table_names)
            if table_names:
                self.current_table_name = table_names[0]
                self.load_table_data(self.current_table_name)
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить список таблиц:\n{e}")

    def on_table_selected(self):
        self.current_table_name = self.table_selector.currentText()
        if self.current_table_name:
            self.load_table_data(self.current_table_name)

    def load_table_data(self, table_name):
        try:
            self.cursor.execute(f"PRAGMA table_info('{table_name}');")
            columns = self.cursor.fetchall()
            column_names = [col[1] for col in columns]

            self.cursor.execute(f"SELECT * FROM '{table_name}';")
            rows = self.cursor.fetchall()

            self._updating = True
            self.table.clear()
            self.table.setRowCount(len(rows))
            self.table.setColumnCount(len(column_names))
            self.table.setHorizontalHeaderLabels(column_names)

            for row_idx, row in enumerate(rows):
                for col_idx, value in enumerate(row):
                    item = QTableWidgetItem(str(value))
                    if col_idx == 0:  # PK нельзя редактировать
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row_idx, col_idx, item)
            self._updating = False
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные из таблицы:\n{e}")
            self.table.clear()

    def on_cell_changed(self, row, col):
        if self._updating:
            return

        try:
            column_name = self.table.horizontalHeaderItem(col).text()
            new_value = self.table.item(row, col).text()
            pk_column = self.table.horizontalHeaderItem(0).text()
            row_id = self.table.item(row, 0).text()

            query = f"UPDATE '{self.current_table_name}' SET {column_name} = ? WHERE {pk_column} = ?;"
            self.cursor.execute(query, (new_value, row_id))
            self.conn.commit()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось обновить запись:\n{e}")
            self.conn.rollback()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = DBViewerApp()
    viewer.show()
    sys.exit(app.exec())
