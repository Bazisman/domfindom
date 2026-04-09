# widgets/date_picker.py
import customtkinter as ctk
from datetime import datetime
import calendar

class DatePicker(ctk.CTkFrame):
    """Виджет выбора даты с выпадающим календарём"""
    
    def __init__(self, master, initial_date=None, on_date_selected=None, **kwargs):
        super().__init__(master, **kwargs)
        
        # Текущая выбранная дата
        self.selected_date = initial_date or datetime.now()
        self.on_date_selected = on_date_selected
        self.calendar_window = None
        self._ignore_next = False
        
        # Получаем главное окно приложения
        self.root = self.winfo_toplevel()
        
        self.setup_ui()
        self.setup_bindings()
        
        # Глобальный обработчик кликов
        self.root.bind("<Button-1>", self.on_global_click, add=True)
        self.root.bind("<FocusOut>", self.on_root_focus_out, add=True)
        self.root.bind("<Configure>", self.on_root_configure, add=True)
    
    def setup_ui(self):
        """Создаёт интерфейс"""
        # Поле для отображения даты
        self.date_entry = ctk.CTkEntry(
            self,
            width=120,
            height=35,
            justify="center",
            font=ctk.CTkFont(size=12)
        )
        self.date_entry.pack(side="left", fill="x", expand=True)
        self.date_entry.bind("<Button-1>", self.toggle_calendar)
        self.date_entry.bind("<FocusIn>", self.toggle_calendar)
        self.date_entry.bind("<Key>", lambda e: "break")  # Запрещаем ввод с клавиатуры
        
        # Кнопка для открытия календаря
        self.calendar_btn = ctk.CTkButton(
            self,
            text="📅",
            width=30,
            height=35,
            command=self.toggle_calendar
        )
        self.calendar_btn.pack(side="right", padx=(2, 0))
        
        self.update_display()
    
    def setup_bindings(self):
        """Настройка событий"""
        self.date_entry.bind("<Escape>", lambda e: self.hide_calendar())
    
    def update_display(self):
        """Обновляет отображение даты в формате ДД.ММ.ГГГГ"""
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, self.selected_date.strftime("%d.%m.%Y"))
    
    def on_root_focus_out(self, event):
        """Когда главное окно теряет фокус - скрываем календарь"""
        self.hide_calendar()
    
    def on_root_configure(self, event):
        """Когда главное окно двигают или меняют размер - скрываем календарь"""
        self.hide_calendar()
    
    def on_global_click(self, event):
        """Обработчик кликов в любом месте"""
        if not self.calendar_window:
            return
        
        widget = event.widget
        
        # Проверяем, кликнули ли внутри поля ввода
        if widget == self.date_entry or self._is_child_of(self.date_entry, widget):
            return
        
        # Проверяем, кликнули ли внутри календаря
        if self._is_child_of(self.calendar_window, widget):
            return
        
        # Проверяем, кликнули ли внутри кнопки календаря
        if widget == self.calendar_btn or self._is_child_of(self.calendar_btn, widget):
            return
        
        # Если кликнули где-то ещё - закрываем календарь
        self.hide_calendar()
    
    def _is_child_of(self, parent, widget):
        """Проверяет, является ли widget дочерним для parent"""
        if not widget or not parent:
            return False
        
        if widget == parent:
            return True
        
        try:
            current = widget
            while current:
                if current == parent:
                    return True
                current = current.master
        except:
            pass
        
        return False
    
    def toggle_calendar(self, event=None):
        """Открывает или закрывает календарь"""
        if self.calendar_window:
            self.hide_calendar()
        else:
            self.show_calendar()
    
    def show_calendar(self):
        """Показывает календарь под полем ввода"""
        self.hide_calendar()
        
        # Получаем позицию для календаря
        width = 250  # Фиксированная ширина календаря
        x = self.winfo_rootx() + self.date_entry.winfo_x()
        y = self.winfo_rooty() + self.date_entry.winfo_y() + self.date_entry.winfo_height()
        
        # Создаём окно календаря
        self.calendar_window = ctk.CTkToplevel(self.master)
        self.calendar_window.overrideredirect(True)
        self.calendar_window.transient(self.root)
        self.calendar_window.geometry(f"{width}x280+{x}+{y}")
        
        # Основной контейнер календаря
        main_frame = ctk.CTkFrame(self.calendar_window, corner_radius=5)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Текущий месяц и год
        self.current_month = self.selected_date.month
        self.current_year = self.selected_date.year
        
        self.draw_calendar(main_frame)
    
    def draw_calendar(self, parent):
        """Рисует календарь"""
        # Заголовок с выбором месяца/года
        header_frame = ctk.CTkFrame(parent)
        header_frame.pack(fill="x", padx=5, pady=5)
        
        # Кнопки навигации
        prev_btn = ctk.CTkButton(
            header_frame,
            text="◀",
            width=30,
            command=self.prev_month
        )
        prev_btn.pack(side="left", padx=2)
        
        # Название месяца и год
        month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                      "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
        self.month_label = ctk.CTkLabel(
            header_frame,
            text=f"{month_names[self.current_month-1]} {self.current_year}",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.month_label.pack(side="left", expand=True)
        
        next_btn = ctk.CTkButton(
            header_frame,
            text="▶",
            width=30,
            command=self.next_month
        )
        next_btn.pack(side="right", padx=2)
        
        # Дни недели
        week_frame = ctk.CTkFrame(parent)
        week_frame.pack(fill="x", padx=5, pady=2)
        
        weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        for i, day in enumerate(weekdays):
            label = ctk.CTkLabel(
                week_frame,
                text=day,
                width=30,
                font=ctk.CTkFont(size=12, weight="bold")
            )
            label.grid(row=0, column=i, padx=1, pady=2)
        
        # Сетка дней
        self.days_frame = ctk.CTkFrame(parent)
        self.days_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.draw_days()
    
    def draw_days(self):
        """Рисует дни месяца"""
        # Очищаем предыдущие дни
        for widget in self.days_frame.winfo_children():
            widget.destroy()
        
        # Получаем первый день месяца и количество дней
        first_day = datetime(self.current_year, self.current_month, 1)
        first_weekday = first_day.weekday()  # 0 = понедельник, 6 = воскресенье
        days_in_month = calendar.monthrange(self.current_year, self.current_month)[1]
        
        # Смещение для первого дня
        row = 0
        col = 0
        
        # Пустые ячейки до первого дня месяца
        for _ in range(first_weekday):
            empty_label = ctk.CTkLabel(self.days_frame, text="", width=30, height=30)
            empty_label.grid(row=row, column=col, padx=1, pady=1)
            col += 1
        
        # Дни месяца
        for day in range(1, days_in_month + 1):
            day_date = datetime(self.current_year, self.current_month, day)
            
            # Определяем цвет кнопки
            if day_date.date() == self.selected_date.date():
                fg_color = "#2e7d32"  # зелёный для выбранной даты
                hover_color = "#1e5a23"
            elif day_date.date() == datetime.now().date():
                fg_color = "#1e5a23"  # тёмно-зелёный для сегодня
                hover_color = "#2e7d32"
            else:
                fg_color = "transparent"
                hover_color = ("gray70", "gray30")
            
            day_btn = ctk.CTkButton(
                self.days_frame,
                text=str(day),
                width=30,
                height=30,
                fg_color=fg_color,
                hover_color=hover_color,
                text_color=("black", "white") if fg_color == "transparent" else "white",
                command=lambda d=day_date: self.select_date(d)
            )
            day_btn.grid(row=row, column=col, padx=1, pady=1)
            
            col += 1
            if col > 6:
                col = 0
                row += 1
    
    def prev_month(self):
        """Предыдущий месяц"""
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        
        month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                      "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
        self.month_label.configure(
            text=f"{month_names[self.current_month-1]} {self.current_year}"
        )
        self.draw_days()
    
    def next_month(self):
        """Следующий месяц"""
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        
        month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                      "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
        self.month_label.configure(
            text=f"{month_names[self.current_month-1]} {self.current_year}"
        )
        self.draw_days()
    
    def select_date(self, date):
        """Выбирает дату"""
        self.selected_date = date
        self.update_display()
        self.hide_calendar()
        if self.on_date_selected:
            self.on_date_selected(date)
    
    def hide_calendar(self):
        """Скрывает календарь"""
        if self.calendar_window:
            self.calendar_window.destroy()
            self.calendar_window = None
    
    def get_date(self):
        """Возвращает выбранную дату"""
        return self.selected_date
    
    def get_date_str(self):
        """Возвращает дату в формате YYYY-MM-DD"""
        return self.selected_date.strftime("%Y-%m-%d")