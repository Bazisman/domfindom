# widgets/modern_table.py
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Any, Optional, Callable
from utils import formatters

class ModernTable(ctk.CTkFrame):
    """Современная таблица с сортировкой и анимациями"""
    
    def __init__(self, master, columns: List[Dict], on_select: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.columns = columns
        self.on_select = on_select
        self.data = []
        self.sort_column = None
        self.sort_reverse = False
        self.rows = []
        self.selected_row = None
        
        self.setup_ui()
        self.setup_bindings()
    
    def setup_ui(self):
        """Создаёт интерфейс таблицы"""
        
        # Заголовок таблицы
        self.header_frame = ctk.CTkFrame(self, height=40, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=5, pady=(5, 0))
        
        # Создаём кнопки заголовков с сортировкой
        for i, col in enumerate(self.columns):
            btn = ctk.CTkButton(
                self.header_frame,
                text=col['title'],
                command=lambda c=col['field']: self.sort_by(c),
                width=col.get('width', 100),
                height=32,
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                anchor="w"
            )
            btn.grid(row=0, column=i, padx=1)
        
        # Контейнер для таблицы со скроллом
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Canvas для плавного скролла
        self.canvas = tk.Canvas(
            self.container,
            highlightthickness=0,
            bg=ctk.ThemeManager.theme["CTkFrame"]["fg_color"][1]
        )
        self.scrollbar = ttk.Scrollbar(self.container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        # Фрейм для строк
        self.table_frame = ctk.CTkFrame(self.canvas)
        self.canvas_window = self.canvas.create_window(
            (0, 0), 
            window=self.table_frame, 
            anchor="nw",
            width=800  # Фиксированная начальная ширина
        )
        
        # Debounce для resize — не обрабатываем каждый пиксель
        self._resize_job = None
        self.table_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
    
    def _on_frame_configure(self, event):
        """Обновляет область прокрутки (с debounce)"""
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(50, self._do_frame_configure)
    
    def _do_frame_configure(self):
        """Выполняет обновление области прокрутки"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._resize_job = None
    
    def _on_canvas_configure(self, event):
        """Обновляет ширину внутреннего фрейма (с debounce)"""
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(50, lambda: self._do_canvas_configure(event.width))
    
    def _do_canvas_configure(self, width):
        """Выполняет обновление ширины"""
        self.canvas.itemconfig(self.canvas_window, width=width)
        self._resize_job = None
    
    def setup_bindings(self):
        """Настройка событий"""
        # Используем bind вместо bind_all для избежания конфликтов
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
    
    def _on_mousewheel(self, event):
        """Обработка колесика мыши"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def set_data(self, data: List[Dict]):
        """Заполняет таблицу данными"""
        self.data = data
        self._render()
    
    def _render(self):
        """Отрисовывает строки таблицы"""
        # Очищаем старые строки
        for row in self.rows:
            row.destroy()
        self.rows.clear()
        
        # Создаём новые строки
        for i, item in enumerate(self.data):
            row = ModernTableRow(
                self.table_frame,
                item,
                self.columns,
                index=i,
                on_click=self._on_row_click,
                bg_color="transparent" if i % 2 == 0 else ("gray90", "gray20")
            )
            row.pack(fill="x", padx=2, pady=1)
            self.rows.append(row)
    
    def _on_row_click(self, row, item):
        """Обработчик клика по строке"""
        # Снимаем выделение с предыдущей строки
        if self.selected_row and self.selected_row != row:
            self.selected_row.deselect()
        
        # Выделяем текущую строку
        row.select()
        self.selected_row = row
        
        # Вызываем колбэк
        if self.on_select:
            self.on_select(item)
    
    def sort_by(self, field: str):
        """Сортирует таблицу по полю"""
        if self.sort_column == field:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = field
            self.sort_reverse = False
        
        # Анимируем сортировку (мигание)
        self._animate_sort()
        
        # Сортируем данные
        try:
            self.data.sort(
                key=lambda x: x.get(field, ""),
                reverse=self.sort_reverse
            )
        except:
            # Если сортировка не удалась, пробуем привести к строке
            self.data.sort(
                key=lambda x: str(x.get(field, "")),
                reverse=self.sort_reverse
            )
        
        self._render()
    
    def _animate_sort(self):
        """Анимация сортировки - мигание"""
        for row in self.rows:
            row.configure(fg_color=("gray70", "gray30"))
        self.after(200, lambda: [r.configure(fg_color=r.normal_bg) for r in self.rows])
    
    def get_selected_item(self) -> Optional[Dict]:
        """Возвращает выбранный элемент"""
        if self.selected_row:
            return self.selected_row.data
        return None
    
    def refresh(self):
        """Перерисовывает таблицу с текущими данными"""
        self._render()

class ModernTableRow(ctk.CTkFrame):
    """Строка таблицы с анимацией при наведении"""
    
    def __init__(self, master, data: Dict, columns: List, index: int, 
                 on_click: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.data = data
        self.columns = columns
        self.index = index
        self.on_click = on_click
        self.normal_bg = kwargs.get('bg_color', "transparent")
        self.is_selected = False
        
        self.setup_ui()
        self.setup_bindings()
    
    def setup_ui(self):
        """Создаёт ячейки строки"""
        for i, col in enumerate(self.columns):
            value = self.data.get(col['field'], "")
            
            # Форматирование значения
            if col.get('format') == 'money':
                try:
                    value = formatters.format_money(float(value))
                except:
                    value = str(value)
            elif col.get('format') == 'date':
                value = formatters.format_date(str(value))
            elif col.get('format') == 'type':
                value = f"{formatters.type_to_emoji(str(value))} {formatters.type_to_ru(str(value))}"
            
            label = ctk.CTkLabel(
                self,
                text=str(value),
                width=col.get('width', 100),
                anchor="w",
                justify="left"
            )
            label.grid(row=0, column=i, padx=5, pady=5, sticky="w")
            
            # Сохраняем ссылку на ячейку
            if not hasattr(self, 'cells'):
                self.cells = []
            self.cells.append(label)
    
    def setup_bindings(self):
        """Анимация при наведении и клик"""
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        
        # Для всех дочерних элементов тоже
        for child in self.winfo_children():
            child.bind("<Enter>", self._on_enter)
            child.bind("<Leave>", self._on_leave)
            child.bind("<Button-1>", self._on_click)
    
    def _on_enter(self, event):
        """При наведении мыши"""
        if not self.is_selected:
            self.configure(fg_color=("gray80", "gray25"))
            for cell in self.cells:
                cell.configure(fg_color=("gray80", "gray25"))
    
    def _on_leave(self, event):
        """При уходе мыши"""
        if not self.is_selected:
            self.configure(fg_color=self.normal_bg)
            for cell in self.cells:
                cell.configure(fg_color=self.normal_bg)
    
    def _on_click(self, event):
        """При клике на строку"""
        if self.on_click:
            self.on_click(self, self.data)
    
    def select(self):
        """Выделяет строку"""
        self.is_selected = True
        self.configure(fg_color=("gray60", "gray40"))
        for cell in self.cells:
            cell.configure(fg_color=("gray60", "gray40"))
    
    def deselect(self):
        """Снимает выделение"""
        self.is_selected = False
        self.configure(fg_color=self.normal_bg)
        for cell in self.cells:
            cell.configure(fg_color=self.normal_bg)