import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3

class DBViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OBW - OpenBaseWriter")
        self.geometry("1000x700")

        self.conn = None
        self.cursor = None
        self.current_table_name = ""

        self.create_widgets()
        
        self.editor = None
        self.editing_item = None
        self.editing_column = None

    def create_widgets(self):
        control_frame = ttk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        open_button = ttk.Button(control_frame, text="Открыть файл .db", command=self.open_db_file)
        open_button.pack(side=tk.LEFT, padx=(0, 10))

        self.table_selector = ttk.Combobox(control_frame, state="readonly")
        self.table_selector.pack(side=tk.LEFT, padx=5)
        self.table_selector.bind("<<ComboboxSelected>>", self.on_table_selected)

        table_frame = ttk.Frame(self)
        table_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        vsb = ttk.Scrollbar(table_frame, orient="vertical")
        vsb.pack(side="right", fill="y")

        hsb = ttk.Scrollbar(table_frame, orient="horizontal")
        hsb.pack(side="bottom", fill="x")

        self.tree = ttk.Treeview(
            table_frame, 
            columns=(), 
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        self.tree.pack(expand=True, fill=tk.BOTH)

        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        self.tree.bind("<Double-1>", self.on_double_click)

    def open_db_file(self):
        file_path = filedialog.askopenfilename(
            title="Выберите файл базы данных",
            filetypes=[("Database files", "*.db"), ("All files", "*.*")]
        )

        if not file_path:
            return

        if self.conn:
            self.conn.close()

        try:
            self.conn = sqlite3.connect(file_path)
            self.cursor = self.conn.cursor()
            self.title(f"Просмотрщик и редактор SQLite DB - {file_path}")
            
            self.load_tables_list()

        except sqlite3.Error as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл базы данных: {e}")
            self.conn = None
            self.cursor = None
            self.table_selector['values'] = []
            self.tree.delete(*self.tree.get_children())
            self.tree["columns"] = []

    def load_tables_list(self):
        try:
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = self.cursor.fetchall()
            table_names = [table[0] for table in tables]
            
            self.table_selector['values'] = table_names
            if table_names:
                self.table_selector.current(0)
                self.on_table_selected(None)

        except sqlite3.Error as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить список таблиц: {e}")

    def on_table_selected(self, event):
        self.current_table_name = self.table_selector.get()
        if self.current_table_name:
            self.load_table_data(self.current_table_name)

    def load_table_data(self, table_name):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = ()

        try:
            self.cursor.execute(f"PRAGMA table_info('{table_name}');")
            columns = self.cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            self.tree["columns"] = column_names
            
            for col_name in column_names:
                self.tree.heading(col_name, text=col_name)
                self.tree.column(col_name, width=100, stretch=tk.YES)

            self.cursor.execute(f"SELECT * FROM '{table_name}';")
            rows = self.cursor.fetchall()
            
            for row in rows:
                self.tree.insert("", "end", values=row, iid=row[0])
        
        except sqlite3.Error as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить данные из таблицы '{table_name}': {e}")
            self.tree.delete(*self.tree.get_children())
            self.tree["columns"] = []

    def on_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        
        self.editing_item = self.tree.identify_row(event.y)
        self.editing_column = self.tree.identify_column(event.x)
        
        col_index = int(self.editing_column.replace("#", "")) - 1
        
        x, y, width, height = self.tree.bbox(self.editing_item, self.editing_column)
        
        current_value = self.tree.set(self.editing_item, self.editing_column)

        if self.editor:
            self.editor.destroy()

        self.editor = ttk.Entry(self.tree)
        self.editor.place(x=x, y=y, width=width, height=height)
        self.editor.insert(0, current_value)
        self.editor.focus()
        self.editor.select_range(0, 'end')

        self.editor.bind("<Return>", self.on_editor_enter)
        self.editor.bind("<Escape>", self.on_editor_escape)

    def on_editor_enter(self, event):
        new_value = self.editor.get()
        
        column_name = self.tree.heading(self.editing_column, "text")
        
        row_id = self.tree.item(self.editing_item, "values")[0]
        
        try:
            pk_column = self.tree.heading("#1", "text")
            query = f"UPDATE '{self.current_table_name}' SET {column_name} = ? WHERE {pk_column} = ?;"
            self.cursor.execute(query, (new_value, row_id))
            self.conn.commit()
            
            current_values = list(self.tree.item(self.editing_item, "values"))
            col_index = int(self.editing_column.replace("#", "")) - 1
            current_values[col_index] = new_value
            self.tree.item(self.editing_item, values=current_values)

        except sqlite3.Error as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось обновить запись: {e}")
            self.conn.rollback()

        self.editor.destroy()
        self.editor = None

    def on_editor_escape(self, event):
        self.editor.destroy()
        self.editor = None

if __name__ == "__main__":
    app = DBViewerApp()
    app.mainloop()

