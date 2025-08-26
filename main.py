import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3

# This class creates the main application for the database viewer and editor.
# The user can open a .db file, view its tables, and edit data directly in the table view.
class DBViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Просмотрщик и редактор SQLite DB")  # Set the window title
        self.geometry("1000x700")  # Set the default window size

        # Initialize instance variables for the database connection and the current table.
        self.conn = None
        self.cursor = None
        self.current_table_name = ""

        # Create the main user interface.
        self.create_widgets()
        
        # Initialize the state of the in-place editor.
        self.editor = None
        self.editing_item = None
        self.editing_column = None

    def create_widgets(self):
        """Creates and organizes all the UI elements in the application."""

        # --- Frame for Controls (top part of the window) ---
        control_frame = ttk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        # Button to open a database file.
        open_button = ttk.Button(control_frame, text="Открыть файл .db", command=self.open_db_file)
        open_button.pack(side=tk.LEFT, padx=(0, 10))

        # Dropdown menu (Combobox) to select tables from the database.
        self.table_selector = ttk.Combobox(control_frame, state="readonly")
        self.table_selector.pack(side=tk.LEFT, padx=5)
        self.table_selector.bind("<<ComboboxSelected>>", self.on_table_selected)

        # --- Frame for the Table View (main part of the window) ---
        table_frame = ttk.Frame(self)
        table_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        # Scrollbar for the vertical movement in the table.
        vsb = ttk.Scrollbar(table_frame, orient="vertical")
        vsb.pack(side="right", fill="y")

        # Scrollbar for the horizontal movement in the table.
        hsb = ttk.Scrollbar(table_frame, orient="horizontal")
        hsb.pack(side="bottom", fill="x")

        # The Treeview widget is used to display the table data.
        self.tree = ttk.Treeview(
            table_frame, 
            columns=(), 
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        self.tree.pack(expand=True, fill=tk.BOTH)

        # Configure scrollbars to work with the Treeview.
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        # Bind events for in-place editing.
        # <Double-1> is the event for a double-click with the left mouse button.
        self.tree.bind("<Double-1>", self.on_double_click)

    def open_db_file(self):
        """
        Opens a file dialog to select a .db file.
        If a file is selected, it tries to connect to the database and load tables.
        """
        # Open a file dialog, filtering for .db files.
        file_path = filedialog.askopenfilename(
            title="Выберите файл базы данных",
            filetypes=[("Database files", "*.db"), ("All files", "*.*")]
        )

        if not file_path:
            return  # The user cancelled the dialog.

        # Close any previous connection to avoid resource leaks.
        if self.conn:
            self.conn.close()

        try:
            # Connect to the SQLite database.
            self.conn = sqlite3.connect(file_path)
            self.cursor = self.conn.cursor()
            self.title(f"Просмотрщик и редактор SQLite DB - {file_path}")
            
            # Load the list of tables from the database.
            self.load_tables_list()

        except sqlite3.Error as e:
            # Show an error message if the file is not a valid SQLite database.
            messagebox.showerror("Ошибка", f"Не удалось открыть файл базы данных: {e}")
            self.conn = None
            self.cursor = None
            self.table_selector['values'] = []
            self.tree.delete(*self.tree.get_children())
            self.tree["columns"] = []

    def load_tables_list(self):
        """Fetches the names of all tables in the database and populates the combobox."""
        try:
            # SQL query to get table names from the master table.
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = self.cursor.fetchall()
            table_names = [table[0] for table in tables]
            
            # Update the values in the table selector combobox.
            self.table_selector['values'] = table_names
            if table_names:
                # Select the first table by default and load its data.
                self.table_selector.current(0)
                self.on_table_selected(None)

        except sqlite3.Error as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить список таблиц: {e}")

    def on_table_selected(self, event):
        """Event handler for when a table is selected in the dropdown."""
        self.current_table_name = self.table_selector.get()
        if self.current_table_name:
            self.load_table_data(self.current_table_name)

    def load_table_data(self, table_name):
        """
        Loads all data from the selected table into the Treeview widget.
        """
        # Clear existing data from the Treeview.
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = ()

        try:
            # Get the column names from the table.
            self.cursor.execute(f"PRAGMA table_info('{table_name}');")
            columns = self.cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # Configure the Treeview to use these columns.
            self.tree["columns"] = column_names
            
            # Set the headings for each column.
            for col_name in column_names:
                self.tree.heading(col_name, text=col_name)
                # Set a default width for columns.
                self.tree.column(col_name, width=100, stretch=tk.YES)

            # Fetch all rows from the table.
            self.cursor.execute(f"SELECT * FROM '{table_name}';")
            rows = self.cursor.fetchall()
            
            # Insert each row into the Treeview.
            for row in rows:
                self.tree.insert("", "end", values=row, iid=row[0]) # Use first value as iid for updates
        
        except sqlite3.Error as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить данные из таблицы '{table_name}': {e}")
            self.tree.delete(*self.tree.get_children())
            self.tree["columns"] = []

    def on_double_click(self, event):
        """
        Handles the double-click event on a Treeview cell to initiate editing.
        """
        # Get the region of the click.
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        
        # Get the item (row) and column that was clicked.
        self.editing_item = self.tree.identify_row(event.y)
        self.editing_column = self.tree.identify_column(event.x)
        
        # Get the column index from the internal name (e.g., #1).
        col_index = int(self.editing_column.replace("#", "")) - 1
        
        # Get the bounding box of the selected cell.
        x, y, width, height = self.tree.bbox(self.editing_item, self.editing_column)
        
        # Get the current value of the cell.
        current_value = self.tree.set(self.editing_item, self.editing_column)

        # Destroy any existing editor widget to prevent multiple editors.
        if self.editor:
            self.editor.destroy()

        # Create a new Entry widget for editing.
        self.editor = ttk.Entry(self.tree)
        self.editor.place(x=x, y=y, width=width, height=height)
        self.editor.insert(0, current_value)
        self.editor.focus()
        self.editor.select_range(0, 'end')

        # Bind events to the editor.
        self.editor.bind("<Return>", self.on_editor_enter)
        self.editor.bind("<Escape>", self.on_editor_escape)

    def on_editor_enter(self, event):
        """
        Handles the Enter key press in the editor, saving the new value to the database.
        """
        new_value = self.editor.get()
        
        # Get the name of the column being edited.
        column_name = self.tree.heading(self.editing_column, "text")
        
        # Get the ID of the row being edited.
        row_id = self.tree.item(self.editing_item, "values")[0]
        
        try:
            # Construct the UPDATE SQL query.
            # IMPORTANT: This assumes the first column is the primary key (or a unique identifier).
            # If the first column is not unique, the update may affect multiple rows.
            # For a more robust solution, you would need to identify the primary key dynamically.
            pk_column = self.tree.heading("#1", "text")
            query = f"UPDATE '{self.current_table_name}' SET {column_name} = ? WHERE {pk_column} = ?;"
            self.cursor.execute(query, (new_value, row_id))
            self.conn.commit()
            
            # Update the Treeview display with the new value.
            current_values = list(self.tree.item(self.editing_item, "values"))
            col_index = int(self.editing_column.replace("#", "")) - 1
            current_values[col_index] = new_value
            self.tree.item(self.editing_item, values=current_values)

        except sqlite3.Error as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось обновить запись: {e}")
            self.conn.rollback() # Rollback the changes on error

        # Hide and destroy the editor.
        self.editor.destroy()
        self.editor = None

    def on_editor_escape(self, event):
        """
        Handles the Escape key press, canceling the edit and hiding the editor.
        """
        self.editor.destroy()
        self.editor = None

if __name__ == "__main__":
    app = DBViewerApp()
    app.mainloop()

