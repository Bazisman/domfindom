# widgets/category_selector.py
import customtkinter as ctk
from typing import List, Optional, Callable

class CategorySelector(ctk.CTkFrame):
    """Выбор категории с автодополнением"""
    
    def __init__(self, master, categories: List[str] = None, on_select: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.categories = categories or []
        self.on_select = on_select
        self.suggestions_window = None
        self._ignore_next = False
        
        self.setup_ui()
        self.setup_bindings()
        
        # Получаем главное окно приложения
        self.root = self.winfo_toplevel()
        
        # Глобальный обработчик кликов
        self.root.bind("<Button-1>", self.on_global_click, add=True)
        
        # Привязываемся к событиям главного окна
        self.root.bind("<FocusOut>", self.on_root_focus_out, add=True)
        self.root.bind("<Configure>", self.on_root_configure, add=True)
    
    def setup_ui(self):
        """Создаёт интерфейс"""
        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="Категория",
            width=150,
            height=35
        )
        self.entry.pack(fill="x", expand=True)
        
        self.dropdown_btn = ctk.CTkButton(
            self,
            text="▼",
            width=30,
            height=35,
            command=self.show_all_categories
        )
        self.dropdown_btn.place(relx=1.0, rely=0.5, anchor="e")
    
    def setup_bindings(self):
        """Настройка событий"""
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Return>", self._select_first)
        self.entry.bind("<Escape>", lambda e: self.hide_suggestions())
    
    def on_root_focus_out(self, event):
        """Когда главное окно теряет фокус - скрываем подсказки"""
        self.hide_suggestions()
    
    def on_root_configure(self, event):
        """Когда главное окно двигают или меняют размер - скрываем подсказки"""
        self.hide_suggestions()
    
    def on_global_click(self, event):
        """Обработчик кликов в любом месте"""
        if not self.suggestions_window:
            return
        
        widget = event.widget
        
        # Проверяем, кликнули ли внутри поля ввода
        if widget == self.entry or self._is_child_of(self.entry, widget):
            return
        
        # Проверяем, кликнули ли внутри окна подсказок
        if self._is_child_of(self.suggestions_window, widget):
            return
        
        # Проверяем, кликнули ли внутри самого селектора
        if self._is_child_of(self, widget):
            return
        
        # Если кликнули где-то ещё - закрываем список
        self.hide_suggestions()
    
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
    
    def set_categories(self, categories: List[str]):
        """Обновляет список доступных категорий"""
        self.categories = sorted(set(categories))
    
    def _on_key_release(self, event):
        """При вводе текста - показываем подсказки"""
        if self._ignore_next:
            return
        
        text = self.entry.get().strip().lower()
        
        if len(text) < 1:
            self.hide_suggestions()
            return
        
        matches = [cat for cat in self.categories if text in cat.lower()]
        
        if matches:
            self.show_suggestions(matches[:15])  # Показываем не больше 15
        else:
            self.hide_suggestions()
    
    def show_suggestions(self, suggestions: List[str]):
        """Показывает список подсказок с прокруткой"""
        self.hide_suggestions()
        
        if not suggestions:
            return
        
        width = self.entry.winfo_width()
        x = self.winfo_rootx() + self.entry.winfo_x()
        y = self.winfo_rooty() + self.entry.winfo_y() + self.entry.winfo_height()
        
        # Ограничиваем высоту окна (макс 200px)
        height = min(200, len(suggestions) * 35)
        
        self.suggestions_window = ctk.CTkToplevel(self.master)
        self.suggestions_window.overrideredirect(True)
        
        # Привязываем окно к главному окну (но не захватываем фокус)
        self.suggestions_window.transient(self.root)
        
        self.suggestions_window.geometry(f"{width}x{height}+{x}+{y}")
        
        # Используем CTkScrollableFrame для прокрутки
        scrollable_frame = ctk.CTkScrollableFrame(
            self.suggestions_window, 
            corner_radius=5,
            width=width,
            height=height
        )
        scrollable_frame.pack(fill="both", expand=True)
        
        # Добавляем подсказки
        for sugg in suggestions:
            btn = ctk.CTkButton(
                scrollable_frame,
                text=sugg,
                anchor="w",
                fg_color="transparent",
                hover_color=("gray70", "gray30"),
                command=lambda s=sugg: self.select_suggestion(s)
            )
            btn.pack(fill="x", padx=2, pady=1)
    
    def hide_suggestions(self):
        """Скрывает список подсказок"""
        if self.suggestions_window:
            self.suggestions_window.destroy()
            self.suggestions_window = None
    
    def select_suggestion(self, category: str):
        """Выбирает категорию из подсказок"""
        self._ignore_next = True
        self.entry.delete(0, "end")
        self.entry.insert(0, category)
        self._ignore_next = False
        self.hide_suggestions()
        self.entry.focus_set()
        
        if self.on_select:
            self.on_select(category)
    
    def _select_first(self, event):
        """Выбирает первую подсказку по Enter"""
        if self.suggestions_window:
            # Ищем кнопки внутри scrollable_frame
            for child in self.suggestions_window.winfo_children():
                if isinstance(child, ctk.CTkScrollableFrame):
                    for btn in child.winfo_children():
                        if isinstance(btn, ctk.CTkButton):
                            btn.invoke()
                            return
    
    def _on_focus_out(self, event):
        """При потере фокуса - скрываем подсказки"""
        self.after(200, self.hide_suggestions)
    
    def show_all_categories(self):
        """Показывает все категории с прокруткой"""
        if self.categories:
            self.show_suggestions(self.categories[:50])  # Показываем до 50 категорий
    
    def get(self) -> str:
        """Возвращает введённую категорию"""
        return self.entry.get().strip()
    
    def set(self, category: str):
        """Устанавливает категорию"""
        self.entry.delete(0, "end")
        self.entry.insert(0, category)