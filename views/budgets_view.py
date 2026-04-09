"""Устаревшее представление бюджетов.

Оставлено только для совместимости. Основная рабочая логика бюджетов
перенесена во вкладку PlanningView.
"""

import customtkinter as ctk
from widgets.amount_entry import AmountEntry
from widgets.category_selector import CategorySelector

class BudgetsView(ctk.CTkFrame):
    """Вкладка управления бюджетами"""
    
    def __init__(self, master, transaction_service, category_service):
        super().__init__(master)
        
        self.transaction_service = transaction_service
        self.category_service = category_service
        self.budgets = []
        
        # Подписываемся на обновления категорий
        self.category_service.add_listener(self.refresh)
        
        self.setup_ui()
        self.refresh()
    
    def setup_ui(self):
        """Создаёт интерфейс вкладки"""
        
        # Заголовок
        title_label = ctk.CTkLabel(
            self,
            text="🎯 Управление бюджетами",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=20)
        
        # Панель добавления бюджета
        add_frame = ctk.CTkFrame(self)
        add_frame.pack(fill="x", padx=20, pady=10)
        
        # Категория (используем CategorySelector вместо простого Entry)
        ctk.CTkLabel(add_frame, text="Категория:").grid(row=0, column=0, padx=5, pady=10)
        self.category_selector = CategorySelector(add_frame, width=150)
        self.category_selector.grid(row=0, column=1, padx=5, pady=10)
        
        # Сумма
        ctk.CTkLabel(add_frame, text="Сумма:").grid(row=0, column=2, padx=5, pady=10)
        self.amount_entry = AmountEntry(add_frame, initial_value=0.0)
        self.amount_entry.grid(row=0, column=3, padx=5, pady=10)
        
        # Период
        ctk.CTkLabel(add_frame, text="Период:").grid(row=0, column=4, padx=5, pady=10)
        self.period_combo = ctk.CTkComboBox(
            add_frame,
            values=["За месяц", "За год"],
            width=100
        )
        self.period_combo.set("За месяц")
        self.period_combo.grid(row=0, column=5, padx=5, pady=10)
        
        # Кнопка добавления
        add_btn = ctk.CTkButton(
            add_frame,
            text="➕ Добавить",
            command=self.add_budget,
            width=100,
            fg_color="#2e7d32"
        )
        add_btn.grid(row=0, column=6, padx=20, pady=10)
        
        # Enter для добавления бюджета
        self.amount_entry.entry.bind("<Return>", lambda e: self.add_budget())
        
        # Список бюджетов
        list_frame = ctk.CTkFrame(self)
        list_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(
            list_frame,
            text="Установленные бюджеты:",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=10)
        
        self.budgets_text = ctk.CTkTextbox(list_frame, font=ctk.CTkFont(size=12))
        self.budgets_text.pack(fill="both", expand=True, padx=10, pady=10)
    
    def add_budget(self):
        """Добавляет новый бюджет"""
        category = self.category_selector.get().strip()
        amount = self.amount_entry.get()
        period_value = self.period_combo.get()
        
        if not category:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Введите категорию", False)
            return
        
        if amount <= 0:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Сумма должна быть положительной", False)
            return
        
        # Преобразуем русский текст в значение для базы данных
        period = "monthly" if period_value == "За месяц" else "yearly"
        
        cat = self.category_service.get_category_by_name(category)
        if not cat:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Категория не найдена", False)
            return
        
        self.transaction_service.set_budget(cat.id, amount, period)
        
        root = self.winfo_toplevel()
        if hasattr(root, 'set_status'):
            root.set_status(f"✅ Бюджет для '{category}' добавлен", True)
        
        # Очищаем поля
        self.category_selector.set("")
        self.amount_entry.clear()
    
    def refresh_budgets_list(self):
        """Обновляет список бюджетов"""
        self.budgets_text.delete("0.0", "end")
        
        if not self.budgets:
            self.budgets_text.insert("0.0", "📭 Бюджеты не установлены")
            return
        
        text = "Установленные бюджеты:\n\n"
        for b in self.budgets:
            period_ru = "в месяц" if b.get('period') == 'monthly' else "в год"
            text += f"• {b['category']}: {b['amount']:.2f} ₽ {period_ru}\n"
        
        self.budgets_text.insert("0.0", text)
    
    def refresh(self):
        """Обновляет данные"""
        # Проверяем, существует ли ещё виджет
        if not self.winfo_exists():
            return
        
        # Загружаем категории для выпадающего списка
        categories = self.category_service.get_category_names('expense')
        if hasattr(self, 'category_selector'):
            self.category_selector.set_categories(categories)
        
        self.budgets = self.transaction_service.get_budgets()
        self.refresh_budgets_list()
