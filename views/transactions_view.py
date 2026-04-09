# views/transactions_view.py
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk
from services.transaction_service import TransactionService
from services.category_service import CategoryService
from models import Transaction
from widgets.amount_entry import AmountEntry
from widgets.category_selector import CategorySelector
from widgets.date_picker import DatePicker
from datetime import datetime
from views.capital_view import CapitalView
import core

class TransactionsView(ctk.CTkFrame):
    """Вкладка управления транзакциями"""
    
    def __init__(self, master, transaction_service, category_service):
        super().__init__(master)
        
        self.transaction_service = transaction_service
        self.category_service = category_service
        self.current_transaction_type = "expense"
        
        # Подписываемся на обновления категорий
        self.category_service.add_listener(self.load_categories)
        
        # Подписываемся на обновления транзакций
        self.transaction_service.add_listener(self.on_data_changed)
        
        self.setup_ui()
        
        # Загружаем данные
        self.refresh()
        self.load_categories()
    
    def setup_ui(self):
        """Создаёт интерфейс вкладки"""
        
        # === Панель сверки баланса (самая верхняя) ===
        self.reconcile_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.reconcile_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        # Кнопка сверки
        self.reconcile_btn = ctk.CTkButton(
            self.reconcile_frame,
            text="⚖️ Сверка",
            command=self.open_reconcile_window,
            width=80,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color="#4caf50",
            text_color=("gray10", "gray90")
        )
        self.reconcile_btn.pack(side="left", padx=2)
        
        # Метка баланса в программе
        self.prog_balance_label = ctk.CTkLabel(
            self.reconcile_frame,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.prog_balance_label.pack(side="left", padx=10)
        
        # Метка последней сверки
        self.last_recon_label = ctk.CTkLabel(
            self.reconcile_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#78909c"
        )
        self.last_recon_label.pack(side="left", padx=10)
        
        # Обновляем метки
        self.update_reconcile_labels()
        
        # === Верхняя панель с фильтрами ===
        self.filter_frame = ctk.CTkFrame(self)
        self.filter_frame.pack(fill="x", padx=10, pady=10)

        # Фильтр по дате
        date_filter_frame = ctk.CTkFrame(self.filter_frame, fg_color="transparent")
        date_filter_frame.pack(fill="x", pady=2)

        ctk.CTkLabel(date_filter_frame, text="Период:", width=60).pack(side="left", padx=5)

        self.period_var = ctk.StringVar(value="Всё время")
        self.period_combo = ctk.CTkComboBox(
            date_filter_frame,
            values=["Всё время", "Текущий месяц", "Прошлый месяц", "Текущий год", "Выбрать даты"],
            variable=self.period_var,
            width=150,
            command=self.on_period_change
        )
        self.period_combo.pack(side="left", padx=5)

        # Фрейм для выбора дат (изначально скрыт)
        self.date_range_frame = ctk.CTkFrame(date_filter_frame, fg_color="transparent")
        self.date_range_frame.pack(side="left", padx=10, fill="x", expand=True)

        # Дата "с"
        self.start_date_picker = DatePicker(
            self.date_range_frame,
            on_date_selected=self.on_start_date_selected
        )
        self.start_date_picker.pack(side="left", padx=2)

        ctk.CTkLabel(self.date_range_frame, text="—").pack(side="left", padx=2)

        # Дата "по"
        self.end_date_picker = DatePicker(
            self.date_range_frame,
            on_date_selected=self.on_end_date_selected
        )
        self.end_date_picker.pack(side="left", padx=2)
        
        # По умолчанию скрываем выбор дат
        self.date_range_frame.pack_forget()

        # 🔥 НОВОЕ: Фильтр по категориям
        category_filter_frame = ctk.CTkFrame(self.filter_frame, fg_color="transparent")
        category_filter_frame.pack(fill="x", pady=2)

        ctk.CTkLabel(category_filter_frame, text="Категория:", width=60).pack(side="left", padx=5)

        self.category_filter_var = ctk.StringVar(value="Все категории")
        self.category_filter_combo = ctk.CTkComboBox(
            category_filter_frame,
            values=["Все категории"],  # временно, обновится в load_categories
            variable=self.category_filter_var,
            width=200,
            command=self.on_category_filter_change
        )
        self.category_filter_combo.pack(side="left", padx=5)
        
        # Кнопка сброса фильтра
        self.reset_filter_btn = ctk.CTkButton(
            category_filter_frame,
            text="✖",
            width=30,
            command=self.reset_category_filter
        )
        self.reset_filter_btn.pack(side="left", padx=2)

        self.export_btn = ctk.CTkButton(
            self.filter_frame,
            text="📥 Экспорт CSV",
            command=self.export_csv,
            width=100,
            fg_color="#37474f"
        )
        self.export_btn.pack(side="right", padx=5)
        
        # === Панель добавления транзакции ===
        self.add_frame = ctk.CTkFrame(self)
        self.add_frame.pack(fill="x", padx=10, pady=10)
        
        # Переключатель типа
        self.type_switch = ctk.CTkSegmentedButton(
            self.add_frame, 
            values=["💰 Доход", "💸 Расход"],
            command=self.on_type_change
        )
        self.type_switch.set("💸 Расход")
        self.type_switch.grid(row=0, column=0, padx=5, pady=10)
        
        # Выбор даты
        self.date_picker = DatePicker(
            self.add_frame,
            on_date_selected=self.on_date_selected
        )
        self.date_picker.grid(row=0, column=1, padx=5, pady=10)
        
        # Категория
        self.category_selector = CategorySelector(
            self.add_frame,
            on_select=self.on_category_selected
        )
        self.category_selector.grid(row=0, column=2, padx=5, pady=10)
        
        # Сумма
        self.amount_entry = AmountEntry(
            self.add_frame, 
            initial_value=0.0,
            on_change=self.on_amount_change
        )
        self.amount_entry.grid(row=0, column=3, padx=5, pady=10)
        
        # Enter в поле суммы
        self.amount_entry.entry.bind("<Return>", self.on_enter_in_amount)
        
        # Комментарий
        self.comment_entry = ctk.CTkEntry(
            self.add_frame,
            placeholder_text="Комментарий",
            width=150,
            height=35
        )
        self.comment_entry.grid(row=0, column=4, padx=5, pady=10)
        
        # Enter в поле комментария
        self.comment_entry.bind("<Return>", self.on_enter_in_comment)
        
        # === Повторяющаяся транзакция ===
        self.recurring_var = ctk.BooleanVar(value=False)
        self.recurring_check = ctk.CTkCheckBox(
            self.add_frame,
            text="🔄 Повторяющаяся",
            variable=self.recurring_var,
            command=self.on_recurring_toggle
        )
        self.recurring_check.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        # Количество месяцев (появляется при включённой галочке)
        self.months_label = ctk.CTkLabel(self.add_frame, text="на")
        self.months_entry = ctk.CTkEntry(self.add_frame, width=50, justify="center")
        self.months_entry.insert(0, "12")
        self.months_label2 = ctk.CTkLabel(self.add_frame, text="месяцев")
        
        # Скрываем по умолчанию
        self.months_label.grid_forget()
        self.months_entry.grid_forget()
        self.months_label2.grid_forget()
        
        # Кнопка добавления
        self.add_btn = ctk.CTkButton(
            self.add_frame,
            text="➕ Добавить",
            command=self.add_transaction,
            width=100,
            height=35,
            fg_color="#2e7d32",
            hover_color="#1e5a23"
        )
        self.add_btn.grid(row=0, column=5, padx=10, pady=10)
        
        # === Таблица транзакций ===
        self.table_frame = ctk.CTkFrame(self)
        self.table_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Создаём Treeview для таблицы
        columns = ("id", "date", "type", "category", "amount", "comment")
        self.tree = ttk.Treeview(
            self.table_frame,
            columns=columns,
            show="headings",
            height=15
        )
        
        # Настройка заголовков
        self.tree.heading("id", text="ID")
        self.tree.heading("date", text="Дата")
        self.tree.heading("type", text="Тип")
        self.tree.heading("category", text="Категория")
        self.tree.heading("amount", text="Сумма")
        self.tree.heading("comment", text="Комментарий")
        
        # Настройка ширины колонок
        self.tree.column("id", width=0, stretch=False)  # Невидимая колонка
        self.tree.column("date", width=90, anchor="center")
        self.tree.column("type", width=90, anchor="center")
        self.tree.column("category", width=130)
        self.tree.column("amount", width=90, anchor="e")
        self.tree.column("comment", width=250)
        
        # Скроллбар
        scrollbar = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Контекстное меню
        self.setup_context_menu()
    
    def update_reconcile_labels(self):
        """Обновляет метки сверки"""
        try:
            balance = self.transaction_service.get_balance()
            self.prog_balance_label.configure(text=f"Баланс: {balance.main_balance:,.0f} ₽".replace(",", " "))
            
            last = core.get_last_reconciliation()
            if last:
                date_str = datetime.strptime(last['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                diff = last['difference']
                if diff > 0:
                    diff_text = f"+{abs(diff):,.0f}".replace(",", " ")
                elif diff < 0:
                    diff_text = f"{abs(diff):,.0f}".replace(",", " ")
                else:
                    diff_text = "0"
                self.last_recon_label.configure(text=f"Сверка: {date_str} ({diff_text} ₽)")
            else:
                self.last_recon_label.configure(text="Сверка не проводилась")
        except Exception as e:
            pass
    
    def open_reconcile_window(self):
        """Открывает окно сверки баланса"""
        ReconcileWindowCompact(self)
    
    def setup_context_menu(self):
        """Контекстное меню для таблицы"""
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="✏️ Редактировать", command=self.edit_selected)
        self.context_menu.add_command(label="🗑️ Удалить", command=self.delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📋 Копировать сумму", command=self.copy_amount)
        
        self.tree.bind("<Button-3>", self.show_context_menu)
    
    def show_context_menu(self, event):
        """Показывает контекстное меню"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    def on_type_change(self, value):
        """При смене типа транзакции"""
        self.current_transaction_type = "income" if "Доход" in value else "expense"
        self.load_categories()
    
    def on_category_selected(self, category):
        """При выборе категории"""
        pass
    
    def on_date_selected(self, date):
        """При выборе даты"""
        pass
    
    def on_amount_change(self, value):
        """При изменении суммы"""
        pass
    
    def on_enter_in_amount(self, event):
        """Enter в поле суммы - добавляем транзакцию"""
        self.add_transaction()
        return "break"
    
    def on_enter_in_comment(self, event):
        """Enter в поле комментария - добавляем транзакцию"""
        self.add_transaction()
        return "break"
    
    def on_recurring_toggle(self):
        """Показывает/скрывает поле выбора количества месяцев"""
        if self.recurring_var.get():
            self.months_label.grid(row=1, column=1, padx=2, pady=5, sticky="w")
            self.months_entry.grid(row=1, column=2, padx=2, pady=5, sticky="w")
            self.months_label2.grid(row=1, column=3, padx=2, pady=5, sticky="w")
        else:
            self.months_label.grid_forget()
            self.months_entry.grid_forget()
            self.months_label2.grid_forget()
    
    def on_period_change(self, choice):
        """При смене периода"""
        if choice == "Выбрать даты":
            # Показываем поля для выбора дат
            self.date_range_frame.pack(side="left", padx=10, fill="x", expand=True)
            # Устанавливаем даты по умолчанию (первые и последний день текущего месяца)
            today = datetime.now()
            first_day = today.replace(day=1)
            self.start_date_picker.selected_date = first_day
            self.start_date_picker.update_display()
            self.end_date_picker.selected_date = today
            self.end_date_picker.update_display()
        else:
            # Скрываем поля для выбора дат
            self.date_range_frame.pack_forget()
        
        self.refresh()
        
    def load_categories(self):
        """Загружает список категорий"""
        if not self.winfo_exists():
            return
        
        # Для выбора категории при добавлении
        add_categories = self.category_service.get_category_names(self.current_transaction_type)
        if hasattr(self, 'category_selector'):
            self.category_selector.set_categories(add_categories)
        
        # 🔥 Для фильтра - все категории (активные)
        all_categories = self.category_service.get_category_names()
        filter_categories = ["Все категории"] + all_categories
        if hasattr(self, 'category_filter_combo'):
            current = self.category_filter_var.get()
            self.category_filter_combo.configure(values=filter_categories)
            # Если текущее значение всё ещё в списке, оставляем, иначе ставим "Все категории"
            if current not in filter_categories:
                self.category_filter_var.set("Все категории")
    
    def on_category_filter_change(self, choice):
        """При изменении фильтра по категориям"""
        self.refresh()

    def reset_category_filter(self):
        """Сбрасывает фильтр по категориям"""
        self.category_filter_var.set("Все категории")
        self.refresh()

    def on_start_date_selected(self, date):
        """При выборе начальной даты"""
        self.refresh()

    def on_end_date_selected(self, date):
        """При выборе конечной даты"""
        self.refresh()

    def refresh(self):
        """Обновляет данные"""
        # Очищаем таблицу
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        period_choice = self.period_var.get()
        category_filter = self.category_filter_var.get()
        
        # Получаем все транзакции за период
        if period_choice == "Выбрать даты":
            start_date = self.start_date_picker.get_date_str()
            end_date = self.end_date_picker.get_date_str()
            all_transactions = self.transaction_service.get_transactions_by_date_range(
                start_date, end_date
            )
        else:
            period_map = {
                "Всё время": "all",
                "Текущий месяц": "month",
                "Прошлый месяц": "last_month",
                "Текущий год": "year"
            }
            period = period_map.get(period_choice, "all")
            # Ограничиваем количество для производительности
            all_transactions = self.transaction_service.get_transactions(limit=500, period=period)
        
        # 🔥 Фильтруем по категории, если выбрана
        if category_filter != "Все категории":
            transactions = [t for t in all_transactions if t.category == category_filter]
        else:
            transactions = all_transactions
        
        # Заполняем таблицу
        for t in transactions:
            type_ru = "💰 Доход" if t.type == "income" else "💸 Расход"
            date_parts = t.date.split('-')
            display_date = f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]}" if len(date_parts) == 3 else t.date
            
            # Проверяем статус транзакции (для запланированных - серый цвет)
            is_planned = getattr(t, 'status', None) == 'planned'
            
            # Добавляем маркер для запланированных
            if is_planned:
                display_date = f"📅 {display_date}"
            
            item_id = self.tree.insert("", "end", values=(
                t.id,
                display_date,
                type_ru,
                t.category,
                f"{t.amount:.2f}",
                t.comment
            ))
        
            # Раскрашиваем запланированные транзакции в серый
            if is_planned:
                self.tree.item(item_id, tags=('planned',))
        
        # Настраиваем теги для запланированных транзакций
        self.tree.tag_configure('planned', foreground='#888888')
        
        # Показываем количество записей в статусе
        root = self.winfo_toplevel()
        if hasattr(root, 'set_status'):
            filter_text = f" по категории '{category_filter}'" if category_filter != "Все категории" else ""
            root.set_status(f"📊 Найдено {len(transactions)} записей{filter_text}", True)
    
    def add_transaction(self):
        """Добавляет новую транзакцию"""
        category = self.category_selector.get()
        amount = self.amount_entry.get()
        comment = self.comment_entry.get()
        transaction_date = self.date_picker.get_date_str()
        
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
        
        # Проверка бюджета для расходов
        if self.current_transaction_type == "expense":
            result = self.transaction_service.check_budget(category, amount)
            if result:
                over, spent, budget = result
                if over:
                    if not messagebox.askyesno(
                        "⚠️ Превышение бюджета",
                        f"Эта трата превысит бюджет!\n"
                        f"Бюджет: {budget:.2f} ₽\n"
                        f"Уже потрачено: {spent:.2f} ₽\n\n"
                        f"Всё равно добавить?"
                    ):
                        return
        
        # Создаём транзакцию
        transaction = Transaction(
            type=self.current_transaction_type,
            category=category,
            amount=amount,
            comment=comment,
            date=transaction_date
        )
        
        # 🔥 Проверяем, нужно ли создавать повторяющуюся транзакцию
        if self.recurring_var.get():
            # Получаем количество месяцев
            try:
                months = int(self.months_entry.get()) if self.months_entry.get() else 12
            except ValueError:
                months = 12
            # Ограничим разумными пределами
            months = max(1, min(120, months))
            
            success = self.transaction_service.add_transaction_with_recurring(transaction, months)
            
            # Сбрасываем чекбокс
            self.recurring_var.set(False)
            self.on_recurring_toggle()
        else:
            # 🔥 ВАЖНО: add_transaction уже обрабатывает автоотчисления!
            success = self.transaction_service.add_transaction(transaction)
    
        if success:
            # 🔥 Убираем process_auto_capital — он уже внутри add_transaction
            # Очищаем поля
            self.amount_entry.clear()
            self.comment_entry.delete(0, "end")
            self.amount_entry.entry.focus_set()
            
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("✅ Транзакция добавлена", True)
            # 🔥 Сбрасываем кэш и обновляем баланс
            core._invalidate_cache('balance')
            if hasattr(root, 'update_balance'):
                root.update_balance()
        else:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Ошибка при добавлении", False)

    

    def edit_selected(self):
        """Редактирование выбранной транзакции"""
        selected = self.tree.selection()
        if not selected:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Выберите запись для редактирования", False)
            return
        
        item = self.tree.item(selected[0])
        values = item['values']
        if not values:
            return
        
        tid = values[0]
        
        # Проверяем, не запланированная ли это транзакция
        display_date = values[1]
        if display_date.startswith("📅"):
            messagebox.showwarning("Запланированная транзакция", 
                "Нельзя редактировать запланированные транзакции.\n"
                "Они будут созданы автоматически при наступлении даты.")
            return
        
        # Открываем диалог редактирования
        self.open_edit_dialog(tid, values)
    
    def open_edit_dialog(self, tid, values):
        """Открывает диалог редактирования"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("✏️ Редактирование записи")
        dialog.geometry("550x450")
        dialog.grab_set()
        
        # Заголовок
        ctk.CTkLabel(
            dialog,
            text="Редактирование транзакции",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        
        # Форма
        frame = ctk.CTkFrame(dialog)
        frame.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Дата (используем DatePicker)
        ctk.CTkLabel(frame, text="Дата:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        
        # Парсим дату из строки
        try:
            # Если дата в формате YYYY-MM-DD
            if '-' in values[1]:
                initial_date = datetime.strptime(values[1], "%Y-%m-%d")
            else:
                # Если в формате DD.MM.YYYY
                try:
                    initial_date = datetime.strptime(values[1], "%d.%m.%Y")
                except:
                    initial_date = datetime.now()
        except:
            initial_date = datetime.now()
        
        date_picker = DatePicker(frame, initial_date=initial_date)
        date_picker.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        # Получаем информацию о текущей категории
        current_category_name = values[3]
        current_category = None
        for cat in self.category_service.get_all_categories():
            if cat.name == current_category_name:
                current_category = cat
                break

        # Определяем текущий тип
        current_type = "income" if "Доход" in values[2] else "expense"

        # Тип
        ctk.CTkLabel(frame, text="Тип:").grid(row=1, column=0, padx=10, pady=10, sticky="e")

        # 🔥 Если категория "И то и другое" - показываем выбор типа
        if current_category and current_category.type == "both":
            type_combo = ctk.CTkComboBox(
                frame,
                values=["💰 Доход", "💸 Расход"],
                width=150
            )
            type_combo.set("💰 Доход" if current_type == "income" else "💸 Расход")
            type_combo.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        else:
            # Если категория строго определена - показываем только текст
            type_label = ctk.CTkLabel(
                frame, 
                text="💰 Доход" if current_type == "income" else "💸 Расход",
                font=ctk.CTkFont(size=14, weight="bold")
            )
            type_label.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        # Категория
        ctk.CTkLabel(frame, text="Категория:").grid(row=2, column=0, padx=10, pady=10, sticky="e")

        # Функция для получения категорий по типу
        def get_categories_by_type(trans_type):
            """Возвращает список категорий для указанного типа транзакции"""
            cats = self.category_service.get_all_categories(trans_type=trans_type)
            return [cat.name for cat in cats]

        # Начальные категории по текущему типу
        category_combo = ctk.CTkComboBox(
            frame,
            values=get_categories_by_type(current_type),
            width=200
        )
        category_combo.set(current_category_name)
        category_combo.grid(row=2, column=1, padx=10, pady=10, sticky="w")
        
        # Обработчик изменения типа — обновляет список категорий
        def on_type_change(selection):
            """При смене типа обновляет список категорий"""
            new_type = "income" if selection == "💰 Доход" else "expense"
            categories = get_categories_by_type(new_type)
            category_combo.configure(values=categories)
            # Выбираем первую категорию если текущая не подходит
            if categories and category_combo.get() not in categories:
                category_combo.set(categories[0])

        # Добавляем callback для type_combo если он существует
        if 'type_combo' in locals():
            type_combo.configure(command=on_type_change)
        
        # Сумма
        ctk.CTkLabel(frame, text="Сумма:").grid(row=3, column=0, padx=10, pady=10, sticky="e")
        amount_entry = AmountEntry(frame, initial_value=float(values[4]))
        amount_entry.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        
        # Комментарий
        ctk.CTkLabel(frame, text="Комментарий:").grid(row=4, column=0, padx=10, pady=10, sticky="e")
        comment_entry = ctk.CTkEntry(frame, width=250)
        comment_entry.insert(0, values[5])
        comment_entry.grid(row=4, column=1, padx=10, pady=10, columnspan=2, sticky="w")
        
        def save_changes():
            try:
                # Получаем дату из DatePicker
                new_date = date_picker.get_date_str()
                
                # Получаем новую категорию
                new_category_name = category_combo.get()
                
                # Находим информацию о новой категории
                new_category = None
                for cat in self.category_service.get_all_categories():
                    if cat.name == new_category_name:
                        new_category = cat
                        break
                
                if not new_category:
                    messagebox.showerror("Ошибка", "Категория не найдена")
                    return
                
                # 🔥 Определяем новый тип
                if new_category.type == "both":
                    # Если категория "И то и другое", используем выбранный тип
                    if 'type_combo' in locals():
                        new_type = "income" if type_combo.get() == "💰 Доход" else "expense"
                    else:
                        new_type = current_type
                else:
                    # Если категория строго определена, тип фиксирован
                    new_type = new_category.type
                
                self.transaction_service.update_transaction(tid, 'date', new_date)
                self.transaction_service.update_transaction(tid, 'type', new_type)
                self.transaction_service.update_transaction(tid, 'category', new_category_name)
                self.transaction_service.update_transaction(tid, 'amount', amount_entry.get())
                self.transaction_service.update_transaction(tid, 'comment', comment_entry.get())
                
                dialog.destroy()
                
                # Показываем статус
                root = self.winfo_toplevel()
                if hasattr(root, 'set_status'):
                    root.set_status("✅ Запись обновлена", True)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        
        # Кнопки
        btn_frame = ctk.CTkFrame(dialog)
        btn_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkButton(
            btn_frame,
            text="💾 Сохранить",
            command=save_changes
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            btn_frame,
            text="❌ Отмена",
            command=dialog.destroy,
            fg_color="#f44336",
            hover_color="#d32f2f"
        ).pack(side="right", padx=10)
    
    def delete_selected(self):
        """Удаление выбранной транзакции"""
        selected = self.tree.selection()
        if not selected:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Выберите запись для удаления", False)
            return
        
        item = self.tree.item(selected[0])
        tid = item['values'][0]
        trans_type = item['values'][2]
        amount = float(item['values'][4])
        date_display = item['values'][1]  # дата в формате DD.MM.YYYY или 📅 DD.MM.YYYY
        
        # Проверяем, не запланированная ли это транзакция (по иконке)
        if date_display.startswith("📅"):
            # Запланированная транзакция - можно удалить напрямую (без влияния на баланс)
            if messagebox.askyesno("Подтверждение", "Это запланированная транзакция.\nОна будет удалена без изменения баланса.\n\nУдалить?"):
                try:
                    # Удаляем напрямую из БД
                    import core
                    with core.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM transactions WHERE id = ?', (tid,))
                        conn.commit()
                    
                    root = self.winfo_toplevel()
                    if hasattr(root, 'set_status'):
                        root.set_status("✅ Запланированная транзакция удалена", True)
                    
                    # Обновляем данные
                    self.refresh()
                    if hasattr(root, 'update_balance'):
                        root.update_balance()
                    return
                except Exception as e:
                    messagebox.showerror("Ошибка", str(e))
                    return
        
        # Конвертируем дату обратно в YYYY-MM-DD для поиска
        date_parts = date_display.split('.')
        search_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
        
        if messagebox.askyesno("Подтверждение", "Точно удалить запись?"):
            # Удаляем транзакцию (delete_transaction в core.py уже обрабатывает возврат средств)
            success = self.transaction_service.delete_transaction(tid)
            
            if success:
                root = self.winfo_toplevel()
                if hasattr(root, 'set_status'):
                    root.set_status("✅ Запись удалена", True)
            else:
                root = self.winfo_toplevel()
                if hasattr(root, 'set_status'):
                    root.set_status("❌ Ошибка при удалении", False)
    
    def copy_amount(self):
        """Копирует сумму выбранной транзакции"""
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            amount = item['values'][4]
            self.clipboard_clear()
            self.clipboard_append(str(amount))
            
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("✅ Сумма скопирована", True)
    
    def export_csv(self):
        """Экспорт в CSV"""
        from tkinter import filedialog
        import csv
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        # Получаем все транзакции без лимита UI
        transactions = self.transaction_service.get_transactions_for_export()
        
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Дата', 'Тип', 'Категория', 'Сумма', 'Комментарий'])
            
            for t in transactions:
                type_ru = "Доход" if t.type == "income" else "Расход"
                writer.writerow([
                    t.id, t.date, type_ru,
                    t.category, t.amount, t.comment
                ])
        
        root = self.winfo_toplevel()
        if hasattr(root, 'set_status'):
            root.set_status(f"✅ Экспортировано {len(transactions)} записей", True)
    
    def on_data_changed(self):
        """Колбэк при изменении данных"""
        if not self.winfo_exists():
            return
        self.refresh()
        
        # 🔥 Дополнительно обновляем баланс в главном окне
        root = self.winfo_toplevel()
        if hasattr(root, 'update_balance'):
            root.update_balance()
        
        # Обновляем метки сверки
        self.update_reconcile_labels()


class ReconcileWindowCompact(ctk.CTkToplevel):
    """Компактное окно сверки баланса"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.parent_view = parent
        self.title("⚖️ Сверка баланса")
        self.geometry("450x600")
        self.resizable(True, True)
        
        self.transient(parent)
        self.grab_set()
        
        self.source_widgets = {}
        
        self.setup_ui()
        self.load_sources()
        
        # Центрируем
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
    
    def setup_ui(self):
        """Создаёт интерфейс"""
        # Заголовок
        ctk.CTkLabel(
            self,
            text="⚖️ Сверка баланса",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(15, 10))
        
        # Баланс в программе
        balance = self.parent_view.transaction_service.get_balance()
        self.program_balance = balance.main_balance
        
        prog_frame = ctk.CTkFrame(self)
        prog_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(prog_frame, text="Баланс в программе:").pack(side="left", padx=10)
        ctk.CTkLabel(
            prog_frame,
            text=f"{self.program_balance:,.0f} ₽".replace(",", " "),
            font=ctk.CTkFont(weight="bold"),
            text_color="#4caf50"
        ).pack(side="right", padx=10)
        
        # Источники
        ctk.CTkLabel(
            self,
            text="Источники:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=20, pady=(10, 5))
        
        # === Inline форма добавления источника ===
        add_source_frame = ctk.CTkFrame(self, fg_color="transparent")
        add_source_frame.pack(fill="x", padx=15, pady=2)
        
        # Поле названия
        self.new_source_name = ctk.CTkEntry(
            add_source_frame,
            placeholder_text="Название",
            width=150,
            height=30
        )
        self.new_source_name.pack(side="left", padx=2)
        
        # Поле суммы
        self.new_source_balance = ctk.CTkEntry(
            add_source_frame,
            placeholder_text="Сумма",
            width=100,
            height=30,
            justify="right"
        )
        self.new_source_balance.pack(side="left", padx=2)
        
        # Кнопка добавления
        ctk.CTkButton(
            add_source_frame,
            text="+",
            command=self.add_source_inline,
            width=30,
            height=30,
            fg_color="#2e7d32"
        ).pack(side="left", padx=2)
        
        # Enter на добавление
        self.new_source_name.bind("<Return>", lambda e: self.add_source_inline())
        self.new_source_balance.bind("<Return>", lambda e: self.add_source_inline())
        
        # Скроллируемый фрейм для источников
        self.sources_scroll = ctk.CTkScrollableFrame(
            self,
            height=120,
            label_text=""
        )
        self.sources_scroll.pack(fill="x", padx=15, pady=5)
        
        # Итого
        total_frame = ctk.CTkFrame(self)
        total_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(total_frame, text="Итого:", font=ctk.CTkFont(size=14)).pack(side="left", padx=10)
        self.total_label = ctk.CTkLabel(
            total_frame,
            text="0 ₽",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ff9800"
        )
        self.total_label.pack(side="right", padx=10)
        
        # Разница
        diff_frame = ctk.CTkFrame(self)
        diff_frame.pack(fill="x", padx=15, pady=5)
        
        self.diff_label = ctk.CTkLabel(
            diff_frame,
            text="",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.diff_label.pack(pady=5)
        
        # Кнопки
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkButton(
            btn_frame,
            text="Пересчитать",
            command=self.recalc_balance,
            fg_color="#4caf50",
            hover_color="#388e3c",
            height=35
        ).pack(side="left", padx=5, fill="x", expand=True)
        
        ctk.CTkButton(
            btn_frame,
            text="История",
            command=self.show_history,
            fg_color="transparent",
            border_width=1,
            height=35
        ).pack(side="right", padx=5)
        
        ctk.CTkButton(
            self,
            text="Закрыть",
            command=self.destroy,
            fg_color="transparent",
            border_width=1,
            height=30
        ).pack(pady=(0, 15))
    
    def load_sources(self):
        """Загружает источники (только активные)"""
        for widget in self.sources_scroll.winfo_children():
            widget.destroy()
        
        self.source_widgets = {}
        
        # Получаем только активные источники
        sources = core.get_reconciliation_sources()
        active_sources = [s for s in sources if s['is_active'] == 1]
        
        for source in active_sources:
            self.create_source_row(source['id'], source['name'], source['balance'], source['is_active'])
        
        self.update_total()
    
    def create_source_row(self, source_id, name, balance, is_active):
        """Создаёт строку источника"""
        row = ctk.CTkFrame(self.sources_scroll, fg_color="transparent")
        row.pack(fill="x", pady=2)
        
        # Чекбокс
        var = ctk.IntVar(value=1 if is_active else 0)
        checkbox = ctk.CTkCheckBox(row, text="", variable=var, width=25, command=self.update_total)
        checkbox.pack(side="left", padx=2)
        
        # Название (редактируемое)
        name_entry = ctk.CTkEntry(row, width=130, height=28)
        name_entry.insert(0, name)
        name_entry.pack(side="left", padx=2)
        name_entry.bind("<FocusOut>", lambda e, sid=source_id, ent=name_entry: self.save_source_name(sid, ent.get()))
        
        # Сумма (редактируемая, с сохранением в БД)
        entry = ctk.CTkEntry(row, width=100, justify="right", height=28)
        entry.insert(0, f"{balance:,.0f}".replace(",", " "))
        entry.pack(side="left", padx=2)
        
        # При потере фокуса - сохраняем в БД
        entry.bind("<FocusOut>", lambda e, sid=source_id, ent=entry: self.save_source_balance(sid, ent.get()))
        # Обновляем итог при изменении
        entry.bind("<KeyRelease>", lambda e: self.update_total())
        
        # Удалить
        ctk.CTkButton(
            row, text="✕", command=lambda: self.delete_source(source_id),
            width=25, height=25, fg_color="transparent", hover_color="#f44336"
        ).pack(side="right", padx=2)
        
        self.source_widgets[source_id] = {'checkbox': checkbox, 'entry': entry, 'name_entry': name_entry, 'var': var}
    
    def save_source_name(self, source_id, new_name):
        """Сохраняет название источника в БД"""
        new_name = new_name.strip()
        if new_name:
            core.update_reconciliation_source(source_id, name=new_name)
    
    def save_source_balance(self, source_id, balance_str):
        """Сохраняет баланс источника в БД"""
        try:
            # Убираем пробелы и запятые
            balance_str = balance_str.replace(" ", "").replace("₽", "")
            if balance_str:
                balance = float(balance_str)
                core.update_reconciliation_source(source_id, balance=balance)
        except ValueError:
            pass  # Игнорируем некорректный ввод
    
    def add_source_inline(self):
        """Добавляет источник inline (без диалога)"""
        name = self.new_source_name.get().strip()
        balance_str = self.new_source_balance.get().strip().replace(" ", "").replace("₽", "")
        
        if not name:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Введите название источника", False)
            return
        
        try:
            balance = float(balance_str) if balance_str else 0
        except ValueError:
            balance = 0
        
        # Добавляем источник в БД
        core.add_reconciliation_source(name, balance)
        
        # Очищаем поля
        self.new_source_name.delete(0, "end")
        self.new_source_balance.delete(0, "end")
        
        # Перезагружаем источники
        self.load_sources()
        
        root = self.winfo_toplevel()
        if hasattr(root, 'set_status'):
            root.set_status(f"✅ Источник '{name}' добавлен", True)
    
    def delete_source(self, source_id):
        """Удаляет источник (мягкое удаление - is_active=0)"""
        core.delete_reconciliation_source(source_id)
        self.load_sources()
    
    def update_total(self):
        """Пересчитывает итог"""
        total = 0
        for sid, w in self.source_widgets.items():
            if w['var'].get() == 1:
                try:
                    val = w['entry'].get().replace(" ", "").replace("₽", "")
                    total += float(val) if val else 0
                except ValueError:
                    pass
        
        self.total_label.configure(text=f"{total:,.0f} ₽".replace(",", " "))
        
        diff = total - self.program_balance
        if diff > 0:
            self.diff_label.configure(
                text=f"На {abs(diff):,.0f} ₽ больше чем в программе".replace(",", " "),
                text_color="#4caf50"
            )
        elif diff < 0:
            self.diff_label.configure(
                text=f"На {abs(diff):,.0f} ₽ меньше чем в программе".replace(",", " "),
                text_color="#f44336"
            )
        else:
            self.diff_label.configure(text="Балансы совпадают", text_color="#4caf50")
        
        return total
    
    def recalc_balance(self):
        """Пересчитывает баланс"""
        total = self.update_total()
        diff = total - self.program_balance
        
        if diff == 0:
            core.save_reconciliation(total, self.program_balance, diff, None)
            self.parent_view.update_reconcile_labels()
            self.parent_view.on_data_changed()
            return
        
        # Создаём транзакцию
        trans_type = "income" if diff > 0 else "expense"
        amount = abs(diff)
        
        # Категория Корректировка
        cat = core.get_category_by_name("Корректировка")
        if not cat:
            core.add_category("Корректировка", "both", "#9c27b0", "⚖️")
            cat = core.get_category_by_name("Корректировка")
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        if trans_type == "income":
            tid = core.add_income_with_capital(amount, "Корректировка", "Корректировка баланса", today, 0, None)
        else:
            tid = core.add_expense(amount, "Корректировка", "Корректировка баланса", today)
        
        core.save_reconciliation(total, self.program_balance, diff, tid)
        self.parent_view.update_reconcile_labels()
        self.parent_view.on_data_changed()
    
    def show_history(self):
        """Показывает историю"""
        ReconcileHistoryWindow(self)


class ReconcileHistoryWindow(ctk.CTkToplevel):
    """Окно истории сверок"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.title("История сверок")
        self.geometry("500x300")
        self.transient(parent)
        self.grab_set()
        
        ctk.CTkLabel(self, text="История сверок", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.load_history()
        
        ctk.CTkButton(self, text="Закрыть", command=self.destroy).pack(pady=10)
        
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
    
    def load_history(self):
        history = core.get_reconciliations_history()
        
        for w in self.scroll.winfo_children():
            w.destroy()
        
        # Заголовки
        header = ctk.CTkFrame(self.scroll, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text="Дата", width=120, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
        ctk.CTkLabel(header, text="Реальный", width=80, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
        ctk.CTkLabel(header, text="Программа", width=80, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
        ctk.CTkLabel(header, text="Разница", width=80, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
        
        for recon in history:
            row = ctk.CTkFrame(self.scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)
            
            date_str = datetime.strptime(recon['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            diff = recon['difference']
            diff_str = f"+{diff:,.0f}" if diff > 0 else f"{diff:,.0f}" if diff < 0 else "0"
            
            ctk.CTkLabel(row, text=date_str, width=120).pack(side="left", padx=5)
            ctk.CTkLabel(row, text=f"{recon['real_balance']:,.0f}".replace(",", " "), width=80).pack(side="left", padx=5)
            ctk.CTkLabel(row, text=f"{recon['program_balance']:,.0f}".replace(",", " "), width=80).pack(side="left", padx=5)
            ctk.CTkLabel(row, text=diff_str.replace(",", " "), width=80).pack(side="left", padx=5)
