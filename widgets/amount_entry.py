# widgets/amount_entry.py
import customtkinter as ctk
import re
from typing import Optional, Callable

class AmountEntry(ctk.CTkFrame):
    """Поле ввода суммы с поддержкой калькулятора"""
    
    def __init__(self, master, initial_value: float = 0.0, on_change: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.initial_value = initial_value
        self.on_change = on_change
        self._value = initial_value
        
        self.setup_ui()
        self.setup_bindings()
        
        # Устанавливаем начальное значение
        self._update_display()
    
    def setup_ui(self):
        """Создаёт интерфейс"""
        # Префикс (знак валюты)
        self.prefix_label = ctk.CTkLabel(
            self,
            text="₽",
            font=ctk.CTkFont(size=14),
            width=30
        )
        self.prefix_label.pack(side="left", padx=(5, 0))
        
        # Поле ввода
        self.entry = ctk.CTkEntry(
            self,
            width=120,
            height=35,
            justify="right",
            font=ctk.CTkFont(size=14)
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
    
    def setup_bindings(self):
        """Настройка событий"""
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Return>", self._on_focus_out)
        self.entry.bind("<KeyPress>", self._on_key_press)
        self._first_input_done = False
    
    def _calculate_expression(self, expr: str) -> float:
        """Вычисляет математическое выражение"""
        if not expr.strip():
            return 0.0
        
        # Убираем пробелы
        expr = expr.replace(' ', '')
        
        # Проверяем, является ли выражение простым числом
        try:
            return float(expr)
        except ValueError:
            pass
        
        # Разрешаем только цифры, точки и операторы + - * /
        if not re.match(r'^[0-9+\-*/().\s]+$', expr):
            return 0.0
        
        try:
            # Безопасно вычисляем выражение
            # Используем eval с ограниченным namespace для безопасности
            result = eval(expr, {"__builtins__": {}}, {})
            return float(result)
        except:
            return 0.0
    
    def _update_display(self):
        """Обновляет отображение"""
        # Форматируем значение
        if self._value == 0:
            display_text = "0"
        elif self._value.is_integer():
            display_text = str(int(self._value))
        else:
            display_text = f"{self._value:.2f}".rstrip('0').rstrip('.')
        
        self.entry.delete(0, "end")
        self.entry.insert(0, display_text)
    
    def _on_focus_in(self, event):
        """При получении фокуса - очищаем поле для ввода"""
        self.entry.delete(0, "end")
        self.entry.icursor("end")
        # Сбрасываем флаг "ожидания ввода"
        self._first_input_done = False
    
    def _on_key_press(self, event):
        """При первом нажатии клавиши - очищаем поле если там 0"""
        if not hasattr(self, '_first_input_done') or not self._first_input_done:
            # Если в поле только "0" - очищаем
            current = self.entry.get()
            if current == "0":
                self.entry.delete(0, "end")
                self._first_input_done = True
        return None
    
    def _on_key_release(self, event):
        """При вводе символов - показываем результат вычислений"""
        text = self.entry.get()
        
        # Вычисляем выражение
        result = self._calculate_expression(text)
        
        # Обновляем значение
        self._value = result
        
        # Вызываем колбэк
        if self.on_change:
            self.on_change(result)
    
    def _on_focus_out(self, event):
        """При потере фокуса - показываем результат"""
        text = self.entry.get()
        
        # Вычисляем выражение
        result = self._calculate_expression(text)
        self._value = round(result, 2)
        
        # Показываем результат
        self._update_display()
        
        if self.on_change:
            self.on_change(self._value)
    
    def get(self) -> float:
        """Возвращает числовое значение"""
        return self._value
    
    def set(self, value: float):
        """Устанавливает значение"""
        self._value = round(value, 2)
        self._update_display()
    
    def clear(self):
        """Очищает поле"""
        self._value = 0.0
        self._first_input_done = False
        # Показываем пустую строку вместо 0
        self.entry.delete(0, "end")