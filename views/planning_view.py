"""
Вкладка планирования бюджетов и регулярных операций
"""
import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from services.transaction_service import TransactionService
from services.category_service import CategoryService
from utils.logger import app_logger
import core


class PlanningView(ctk.CTkFrame):
    """Вкладка управления бюджетами и регулярными операциями"""
    
    def __init__(self, master, transaction_service: TransactionService, category_service: CategoryService):
        super().__init__(master)
        self.transaction_service = transaction_service
        self.category_service = category_service
        self._refresh_job = None
        self._last_templates_signature = None
        self._last_budgets_signature = None
        self._last_budget_categories_signature = None
        self._budget_card_widgets = []
        self._empty_budgets_label = None
        self._template_card_widgets = []
        self._empty_templates_label = None
        
        self.setup_ui()
        self.load_data()
        
        # Подписка на изменения
        self.transaction_service.add_listener(self.on_data_changed)
    
    def setup_ui(self):
        """Создаёт интерфейс"""
        # Заголовок
        ctk.CTkLabel(
            self,
            text="📅 Планирование бюджетов",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(15, 10))
        
        # Кнопка создания нового шаблона
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkButton(
            btn_frame,
            text="➕ Добавить регулярную операцию",
            command=self.add_template,
            fg_color="#2e7d32",
            hover_color="#1e5a23"
        ).pack(side="left")
        
        # Кнопка обновления
        ctk.CTkButton(
            btn_frame,
            text="🔄 Обновить",
            command=self.load_data,
            fg_color="transparent",
            border_width=1
        ).pack(side="right")
        
        # Кнопка исполнения просроченных
        self.execute_btn = ctk.CTkButton(
            btn_frame,
            text="⚡ Исполнить просроченные",
            command=self.execute_due,
            fg_color="#ff9800",
            hover_color="#f57c00"
        )
        self.execute_btn.pack(side="right", padx=10)
        
        # Список шаблонов
        self.templates_frame = ctk.CTkScrollableFrame(
            self,
            label_text="Регулярные операции"
        )
        self.templates_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Прогноз баланса
        self.forecast_frame = ctk.CTkFrame(self)
        self.forecast_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            self.forecast_frame,
            text="📊 Прогноз баланса",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(10, 5))
        
        self.forecast_labels = {}
        forecast_items = [
            ('current', 'Текущий баланс:'),
            ('planned_income', 'Ожидаемые доходы:'),
            ('planned_expense', 'Ожидаемые расходы:'),
            ('budgets', 'Плановые бюджеты:'),
            ('projected', 'Прогноз на конец месяца:'),
        ]
        
        for key, label_text in forecast_items:
            row = ctk.CTkFrame(self.forecast_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            
            ctk.CTkLabel(row, text=label_text, width=180).pack(side="left")
            value_label = ctk.CTkLabel(row, text="0 ₽", font=ctk.CTkFont(weight="bold"))
            value_label.pack(side="right")
            self.forecast_labels[key] = value_label
    
        # === СЕКЦИЯ БЮДЖЕТОВ ===
        self.budgets_frame = ctk.CTkFrame(self)
        self.budgets_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            self.budgets_frame,
            text="🎯 Бюджеты",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(10, 5))
        
        # Форма добавления бюджета
        budget_form = ctk.CTkFrame(self.budgets_frame, fg_color="transparent")
        budget_form.pack(fill="x", padx=10, pady=5)
        
        # Категория
        ctk.CTkLabel(budget_form, text="Категория:", width=80).pack(side="left", padx=5)
        
        # Получаем категории расходов
        expense_cats = [c.name for c in self.category_service.get_all_categories('expense')]
        self.budget_category_combo = ctk.CTkComboBox(budget_form, values=expense_cats, width=120)
        self.budget_category_combo.pack(side="left", padx=5)
        
        # Устанавливаем первую категорию по умолчанию если есть
        if expense_cats:
            self.budget_category_combo.set(expense_cats[0])
        
        # Сумма
        ctk.CTkLabel(budget_form, text="Сумма:", width=60).pack(side="left", padx=5)
        self.budget_amount_entry = ctk.CTkEntry(budget_form, width=100)
        self.budget_amount_entry.pack(side="left", padx=5)
        
        # Период (день/месяц/год)
        ctk.CTkLabel(budget_form, text="Период:", width=60).pack(side="left", padx=5)
        self.budget_period_combo = ctk.CTkComboBox(
            budget_form, 
            values=["В день", "В месяц", "В год"],
            width=100
        )
        self.budget_period_combo.set("В месяц")
        self.budget_period_combo.pack(side="left", padx=5)
        
        # Кнопка добавления
        ctk.CTkButton(
            budget_form,
            text="➕",
            command=self.add_budget,
            width=40,
            fg_color="#2e7d32"
        ).pack(side="left", padx=10)
        
        # Контейнер для карточек бюджетов
        self.budgets_container = ctk.CTkFrame(self.budgets_frame, fg_color="transparent")
        self.budgets_container.pack(fill="both", expand=True, padx=10, pady=10)
    
    def load_data(self):
        """Полностью обновляет все блоки экрана"""
        self.load_templates()
        self.update_forecast()
        self.load_budgets()
        self.refresh_budget_categories()

    def load_templates(self):
        """Загружает только блок регулярных операций"""
        templates = self.transaction_service.get_recurring_templates()
        signature = tuple(
            (
                template['id'],
                template['name'],
                template['type'],
                template['amount'],
                template['day_of_month'],
                template['months_ahead'],
                template['is_active'],
            )
            for template in templates
        )

        if signature == self._last_templates_signature and self.templates_frame.winfo_children():
            return
        
        if not templates:
            self._show_empty_templates_state()
            self._last_templates_signature = signature
            return

        self._hide_empty_templates_state()
        
        # Показываем шаблоны
        for index, template in enumerate(templates):
            self.create_template_card(index, template)
        self._hide_unused_template_cards(len(templates))
        self._last_templates_signature = signature
    
    def refresh_budget_categories(self):
        """Обновляет список категорий в форме бюджетов"""
        try:
            expense_cats = [c.name for c in self.category_service.get_all_categories('expense')]
            signature = tuple(expense_cats)
            if signature == self._last_budget_categories_signature:
                return
            self.budget_category_combo.configure(values=expense_cats)
            if expense_cats and not self.budget_category_combo.get():
                self.budget_category_combo.set(expense_cats[0])
            self._last_budget_categories_signature = signature
        except Exception as e:
            app_logger.error(f"Ошибка обновления категорий в PlanningView: {e}", exc_info=True)

    def _set_status(self, message, is_success=True):
        """Показывает короткий статус в главном окне, если оно доступно"""
        root = self.winfo_toplevel()
        if hasattr(root, 'set_status'):
            root.set_status(message, is_success)

    def _cancel_scheduled_refresh(self):
        """Отменяет отложенный полный refresh, если экран уже обновили локально"""
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
    
    def _show_empty_templates_state(self):
        """Показывает пустое состояние блока регулярных операций"""
        self._hide_unused_template_cards(0)
        if self._empty_templates_label is None or not self._empty_templates_label.winfo_exists():
            self._empty_templates_label = ctk.CTkLabel(
                self.templates_frame,
                text="Нет регулярных операций.\nНажмите 'Добавить регулярную операцию', чтобы создать первую.",
                text_color="gray"
            )
        if not self._empty_templates_label.winfo_manager():
            self._empty_templates_label.pack(pady=20)

    def _hide_empty_templates_state(self):
        """Скрывает пустое состояние блока регулярных операций"""
        if (
            self._empty_templates_label is not None
            and self._empty_templates_label.winfo_exists()
            and self._empty_templates_label.winfo_manager()
        ):
            self._empty_templates_label.pack_forget()

    def _hide_unused_template_cards(self, visible_count):
        """Скрывает неиспользуемые карточки шаблонов"""
        for card_data in self._template_card_widgets[visible_count:]:
            if card_data["card"].winfo_manager():
                card_data["card"].pack_forget()

    def _create_template_card_widgets(self):
        """Создаёт виджеты карточки шаблона для переиспользования"""
        card = ctk.CTkFrame(self.templates_frame)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=5)

        title_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title_label.pack(side="left")

        status_label = ctk.CTkLabel(header, text="")
        status_label.pack(side="right")

        details = ctk.CTkFrame(card, fg_color="transparent")
        details.pack(fill="x", padx=10, pady=(0, 5))

        amount_label = ctk.CTkLabel(details, text="")
        amount_label.pack(side="left", padx=10)

        day_label = ctk.CTkLabel(details, text="")
        day_label.pack(side="left", padx=10)

        months_label = ctk.CTkLabel(details, text="")
        months_label.pack(side="left", padx=10)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(0, 10))

        edit_btn = ctk.CTkButton(
            actions,
            text="✏️ Редактировать",
            fg_color="transparent",
            border_width=1,
            height=30
        )
        edit_btn.pack(side="left", padx=5)

        regenerate_btn = ctk.CTkButton(
            actions,
            text="🔄 Перегенерировать",
            fg_color="transparent",
            border_width=1,
            height=30
        )
        regenerate_btn.pack(side="left", padx=5)

        toggle_btn = ctk.CTkButton(
            actions,
            text="",
            fg_color="transparent",
            border_width=1,
            height=30
        )
        toggle_btn.pack(side="left", padx=5)

        delete_btn = ctk.CTkButton(
            actions,
            text="🗑️ Удалить",
            fg_color="#f44336",
            hover_color="#d32f2f",
            height=30
        )
        delete_btn.pack(side="right", padx=5)

        return {
            "card": card,
            "title_label": title_label,
            "status_label": status_label,
            "amount_label": amount_label,
            "day_label": day_label,
            "months_label": months_label,
            "edit_btn": edit_btn,
            "regenerate_btn": regenerate_btn,
            "toggle_btn": toggle_btn,
            "delete_btn": delete_btn,
        }

    def create_template_card(self, index, template):
        """Обновляет или создаёт карточку шаблона"""
        while len(self._template_card_widgets) <= index:
            self._template_card_widgets.append(self._create_template_card_widgets())

        card_data = self._template_card_widgets[index]
        card = card_data["card"]
        if not card.winfo_manager():
            card.pack(fill="x", pady=5)

        type_emoji = "💰" if template['type'] == 'income' else "💸"
        status_color = "#4caf50" if template['is_active'] else "#9e9e9e"
        status_text = "✅ Активен" if template['is_active'] else "❌ Неактивен"
        amount_str = f"{template['amount']:,.0f} ₽".replace(",", " ")
        day_str = f"{template['day_of_month']}-го числа"
        months_str = f"на {template['months_ahead']} мес."

        card_data["title_label"].configure(text=f"{type_emoji} {template['name']}")
        card_data["status_label"].configure(text=status_text, text_color=status_color)
        card_data["amount_label"].configure(text=f"Сумма: {amount_str}")
        card_data["day_label"].configure(text=f"Дата: {day_str}")
        card_data["months_label"].configure(text=f"Период: {months_str}")
        card_data["edit_btn"].configure(command=lambda t=template: self.edit_template(t))
        card_data["regenerate_btn"].configure(
            command=lambda template_id=template['id']: self.regenerate_template(template_id)
        )

        is_active = template['is_active']
        toggle_text = "⏸ Приостановить" if is_active else "▶️ Активировать"
        card_data["toggle_btn"].configure(
            text=toggle_text,
            command=lambda template_id=template['id'], new_state=not is_active: self.toggle_template(template_id, new_state)
        )
        card_data["delete_btn"].configure(
            command=lambda template_id=template['id'], name=template['name']: self.delete_template(template_id, name)
        )
    
    def update_forecast(self):
        """Обновляет прогноз баланса"""
        try:
            forecast = self.transaction_service.get_projected_balance()
            
            # Текущий баланс
            current = forecast.get('current_balance', 0)
            self.forecast_labels['current'].configure(
                text=f"{current:,.0f} ₽".replace(",", " "),
                text_color="#4caf50" if current >= 0 else "#f44336"
            )
            
            # Ожидаемые доходы
            planned_inc = forecast.get('planned_income', 0)
            self.forecast_labels['planned_income'].configure(
                text=f"+{planned_inc:,.0f} ₽".replace(",", " "),
                text_color="#4caf50"
            )
            
            # Ожидаемые расходы
            planned_exp = forecast.get('planned_expense', 0)
            self.forecast_labels['planned_expense'].configure(
                text=f"-{planned_exp:,.0f} ₽".replace(",", " "),
                text_color="#f44336"
            )
            
            # Плановые бюджеты
            total_budgets = forecast.get('total_budgets', 0)
            current_expenses = forecast.get('current_expenses', 0)
            budget_remaining = forecast.get('budget_remaining', 0)
            budget_color = "#4caf50" if budget_remaining > 0 else "#f44336"
            self.forecast_labels['budgets'].configure(
                text=f"-{total_budgets:,.0f} ₽ (осталось: {budget_remaining:,.0f})".replace(",", " "),
                text_color=budget_color
            )
            
            # Прогнозируемый баланс
            projected = forecast.get('projected', 0)
            self.forecast_labels['projected'].configure(
                text=f"{projected:,.0f} ₽".replace(",", " "),
                text_color="#4caf50" if projected >= 0 else "#f44336"
            )
            
        except Exception as e:
            app_logger.error(f"Ошибка обновления прогноза в PlanningView: {e}", exc_info=True)
    
    def add_template(self):
        """Добавляет новый шаблон"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("➕ Добавить регулярную операцию")
        dialog.geometry("450x500")
        dialog.grab_set()
        
        # Заголовок
        ctk.CTkLabel(
            dialog,
            text="Новый регулярный платёж",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        
        form = ctk.CTkFrame(dialog)
        form.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Тип
        ctk.CTkLabel(form, text="Тип:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        type_combo = ctk.CTkComboBox(form, values=["💰 Доход", "💸 Расход"], width=200)
        type_combo.set("💸 Расход")
        type_combo.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        # Название
        ctk.CTkLabel(form, text="Название:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        name_entry = ctk.CTkEntry(form, width=200)
        name_entry.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        
        # Сумма
        ctk.CTkLabel(form, text="Сумма:").grid(row=2, column=0, padx=10, pady=10, sticky="e")
        amount_entry = ctk.CTkEntry(form, width=200)
        amount_entry.grid(row=2, column=1, padx=10, pady=10, sticky="w")
        
        # День месяца
        ctk.CTkLabel(form, text="День месяца:").grid(row=3, column=0, padx=10, pady=10, sticky="e")
        day_entry = ctk.CTkEntry(form, width=200)
        day_entry.insert(0, "1")
        day_entry.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        
        # Категория
        ctk.CTkLabel(form, text="Категория:").grid(row=4, column=0, padx=10, pady=10, sticky="e")
        
        def get_categories_by_type(trans_type):
            """Возвращает список категорий для указанного типа"""
            return [c.name for c in self.category_service.get_all_categories(trans_type)]
        
        # Начальные категории для расхода
        category_combo = ctk.CTkComboBox(form, values=get_categories_by_type('expense'), width=200)
        category_combo.grid(row=4, column=1, padx=10, pady=10, sticky="w")
        
        # Обработчик изменения типа — обновляет список категорий
        def on_type_change(selection):
            """При смене типа обновляет список категорий"""
            new_type = "income" if "Доход" in selection else "expense"
            categories = get_categories_by_type(new_type)
            category_combo.configure(values=categories)
            if categories:
                category_combo.set(categories[0])
        
        type_combo.configure(command=on_type_change)
        
        # Комментарий
        ctk.CTkLabel(form, text="Комментарий:").grid(row=5, column=0, padx=10, pady=10, sticky="e")
        comment_entry = ctk.CTkEntry(form, width=200)
        comment_entry.grid(row=5, column=1, padx=10, pady=10, sticky="w")
        
        # Количество месяцев
        ctk.CTkLabel(form, text="На сколько месяцев:").grid(row=6, column=0, padx=10, pady=10, sticky="e")
        months_entry = ctk.CTkEntry(form, width=200)
        months_entry.insert(0, "12")
        months_entry.grid(row=6, column=1, padx=10, pady=10, sticky="w")
        
        # Только рабочие дни
        working_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            form,
            text="Переносить на рабочий день",
            variable=working_var
        ).grid(row=7, column=1, padx=10, pady=10, sticky="w")
        
        def save():
            try:
                template_type = "income" if "Доход" in type_combo.get() else "expense"
                name = name_entry.get().strip()
                amount = float(amount_entry.get().replace(" ", "").replace(",", "."))
                day = int(day_entry.get())
                category = category_combo.get()
                comment = comment_entry.get().strip()
                months = int(months_entry.get())
                working = working_var.get()
                
                if not name:
                    messagebox.showerror("Ошибка", "Введите название")
                    return
                
                if amount <= 0:
                    messagebox.showerror("Ошибка", "Сумма должна быть положительной")
                    return
                
                # Получаем ID категории
                cat = core.get_category_by_name(category)
                category_id = cat['id'] if cat else None
                
                # Создаём шаблон
                template_id = self.transaction_service.create_recurring_template(
                    template_type=template_type,
                    name=name,
                    amount=amount,
                    day_of_month=day,
                    category_id=category_id,
                    comment_template=comment,
                    months_ahead=months,
                    working_days_only=working
                )
                
                if template_id:
                    dialog.destroy()
                    self.load_templates()
                    self.update_forecast()
                    self._cancel_scheduled_refresh()
                    self._set_status(f"✅ Регулярная операция создана на {months} месяцев", True)
                else:
                    messagebox.showerror("Ошибка", "Не удалось создать шаблон")
                    
            except ValueError as e:
                messagebox.showerror("Ошибка", "Неверный формат данных")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
    
        # Кнопки
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkButton(btn_frame, text="💾 Создать", command=save).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", command=dialog.destroy, fg_color="transparent").pack(side="right", padx=5)
    
    def edit_template(self, template):
        """Редактирует шаблон"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("✏️ Редактировать регулярный платёж")
        dialog.geometry("450x500")
        dialog.grab_set()
        
        # Заголовок
        ctk.CTkLabel(
            dialog,
            text=f"Редактирование: {template['name']}",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        
        form = ctk.CTkFrame(dialog)
        form.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Тип
        ctk.CTkLabel(form, text="Тип:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        type_combo = ctk.CTkComboBox(form, values=["💰 Доход", "💸 Расход"], width=200)
        type_combo.set("💰 Доход" if template['type'] == 'income' else "💸 Расход")
        type_combo.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        # Название
        ctk.CTkLabel(form, text="Название:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        name_entry = ctk.CTkEntry(form, width=200)
        name_entry.insert(0, template['name'])
        name_entry.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        
        # Сумма
        ctk.CTkLabel(form, text="Сумма:").grid(row=2, column=0, padx=10, pady=10, sticky="e")
        amount_entry = ctk.CTkEntry(form, width=200)
        amount_entry.insert(0, str(template['amount']))
        amount_entry.grid(row=2, column=1, padx=10, pady=10, sticky="w")
        
        # День месяца
        ctk.CTkLabel(form, text="День месяца:").grid(row=3, column=0, padx=10, pady=10, sticky="e")
        day_entry = ctk.CTkEntry(form, width=200)
        day_entry.insert(0, str(template['day_of_month']))
        day_entry.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        
        # Категория
        ctk.CTkLabel(form, text="Категория:").grid(row=4, column=0, padx=10, pady=10, sticky="e")
        
        def get_categories_by_type(trans_type):
            return [c.name for c in self.category_service.get_all_categories(trans_type)]
        
        current_type = template['type']
        category_combo = ctk.CTkComboBox(form, values=get_categories_by_type(current_type), width=200)
        category_name = template['category_name'] if 'category_name' in template.keys() else ""
        available_categories = get_categories_by_type(current_type)
        if category_name:
            category_combo.set(category_name)
        elif available_categories:
            category_combo.set(available_categories[0])
        category_combo.grid(row=4, column=1, padx=10, pady=10, sticky="w")
        
        # Обработчик изменения типа
        def on_type_change(selection):
            new_type = "income" if "Доход" in selection else "expense"
            categories = get_categories_by_type(new_type)
            category_combo.configure(values=categories)
            if categories:
                category_combo.set(categories[0])
        
        type_combo.configure(command=on_type_change)
        
        # Комментарий
        ctk.CTkLabel(form, text="Комментарий:").grid(row=5, column=0, padx=10, pady=10, sticky="e")
        comment_entry = ctk.CTkEntry(form, width=200)
        comment_template_val = template['comment_template'] if 'comment_template' in template.keys() else ''
        comment_entry.insert(0, comment_template_val)
        comment_entry.grid(row=5, column=1, padx=10, pady=10, sticky="w")
        
        # Количество месяцев
        ctk.CTkLabel(form, text="На сколько месяцев:").grid(row=6, column=0, padx=10, pady=10, sticky="e")
        months_entry = ctk.CTkEntry(form, width=200)
        months_entry.insert(0, str(template['months_ahead']))
        months_entry.grid(row=6, column=1, padx=10, pady=10, sticky="w")
        
        # Только рабочие дни
        working_days_val = template['working_days_only'] if 'working_days_only' in template.keys() else 1
        working_var = ctk.BooleanVar(value=working_days_val == 1)
        ctk.CTkCheckBox(
            form,
            text="Переносить на рабочий день",
            variable=working_var
        ).grid(row=7, column=1, padx=10, pady=10, sticky="w")
        
        def save():
            try:
                template_type = "income" if "Доход" in type_combo.get() else "expense"
                name = name_entry.get().strip()
                amount = float(amount_entry.get().replace(" ", "").replace(",", "."))
                day = int(day_entry.get())
                category = category_combo.get()
                comment = comment_entry.get().strip()
                months = int(months_entry.get())
                working = working_var.get()
                
                if not name:
                    messagebox.showerror("Ошибка", "Введите название")
                    return
                
                if amount <= 0:
                    messagebox.showerror("Ошибка", "Сумма должна быть положительной")
                    return
                
                # Получаем ID категории
                cat = core.get_category_by_name(category)
                category_id = cat['id'] if cat else None
                
                # Обновляем шаблон
                self.transaction_service.update_recurring_template(
                    template['id'],
                    name=name,
                    template_type=template_type,
                    amount=amount,
                    day_of_month=day,
                    category_id=category_id,
                    comment_template=comment,
                    months_ahead=months,
                    working_days_only=working
                )
                
                dialog.destroy()
                self.load_templates()
                self.update_forecast()
                self._cancel_scheduled_refresh()
                self._set_status("✅ Регулярная операция обновлена", True)
                    
            except ValueError as e:
                messagebox.showerror("Ошибка", "Неверный формат данных")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        
        # Кнопки
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkButton(btn_frame, text="💾 Сохранить", command=save).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", command=dialog.destroy, fg_color="transparent").pack(side="right", padx=5)
    
    def toggle_template(self, template_id, is_active):
        """Переключает статус шаблона"""
        try:
            self.transaction_service.update_recurring_template(template_id, is_active=is_active)
            self.load_templates()
            self.update_forecast()
            self._cancel_scheduled_refresh()
            status_text = "активирована" if is_active else "приостановлена"
            self._set_status(f"✅ Регулярная операция {status_text}", True)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def regenerate_template(self, template_id):
        """Перегенерирует плановые транзакции"""
        try:
            count = self.transaction_service.regenerate_template_transactions(template_id)
            self.load_templates()
            self.update_forecast()
            self._cancel_scheduled_refresh()
            self._set_status(f"✅ Пересоздано {count} плановых транзакций", True)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    
    def delete_template(self, template_id, name):
        """Удаляет шаблон"""
        if messagebox.askyesno("Подтверждение", f"Удалить шаблон '{name}'?\nВсе связанные плановые транзакции будут удалены."):
            try:
                self.transaction_service.delete_recurring_template(template_id)
                self.load_templates()
                self.update_forecast()
                self._cancel_scheduled_refresh()
                self._set_status(f"✅ Регулярная операция '{name}' удалена", True)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
    
    def execute_due(self):
        """Исполняет просроченные плановые транзакции"""
        try:
            count = self.transaction_service.execute_planned_transactions()
            if count > 0:
                self.load_templates()
                self.update_forecast()
                self.load_budgets()
                self._cancel_scheduled_refresh()
                self._set_status(f"✅ Исполнено {count} просроченных транзакций", True)
            else:
                self._set_status("ℹ️ Нет просроченных транзакций", True)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    
    def on_data_changed(self):
        """Обработчик изменений данных"""
        if self.winfo_exists():
            if self._refresh_job is not None:
                try:
                    self.after_cancel(self._refresh_job)
                except Exception:
                    pass
            self._refresh_job = self.after(80, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self):
        """Выполняет отложенное полное обновление экрана"""
        self._refresh_job = None
        if self.winfo_exists():
            self.load_data()

    # ========== БЮДЖЕТЫ ==========
    
    def add_budget(self):
        """Добавляет новый бюджет"""
        try:
            from utils.logger import app_logger
            
            category = self.budget_category_combo.get()
            amount_str = self.budget_amount_entry.get().strip()
            period_text = self.budget_period_combo.get()
            
            app_logger.info(f"Добавление бюджета: category={category}, amount={amount_str}, period={period_text}")
            
            if not category:
                messagebox.showwarning("Ошибка", "Выберите категорию")
                return
            
            if not amount_str:
                messagebox.showwarning("Ошибка", "Введите сумму")
                return
            
            try:
                amount = float(amount_str.replace(" ", "").replace(",", "."))
            except ValueError:
                messagebox.showwarning("Ошибка", "Введите корректную сумму")
                return
            
            if amount <= 0:
                messagebox.showwarning("Ошибка", "Сумма должна быть положительной")
                return
            
            # Преобразуем период
            period_map = {"В день": "daily", "В месяц": "monthly", "В год": "yearly"}
            period = period_map.get(period_text, "monthly")
            
            # Получаем ID категории
            cat = core.get_category_by_name(category)
            if not cat:
                messagebox.showerror("Ошибка", "Категория не найдена")
                return
            
            app_logger.info(f"Category ID: {cat['id']}")
            
            # Устанавливаем бюджет
            result = self.transaction_service.set_budget(cat['id'], amount, period)
            app_logger.info(f"set_budget result: {result}")
            
            # Очищаем поле суммы
            self.budget_amount_entry.delete(0, "end")
            
            # Обновляем список бюджетов (там теперь будет отображаться информация)
            self.load_budgets()
            self.update_forecast()
            self._cancel_scheduled_refresh()
            
            self._set_status(f"✅ Бюджет для '{category}' установлен", True)
            
        except Exception as e:
            app_logger.error(f"Ошибка добавления бюджета в PlanningView: {e}", exc_info=True)
            messagebox.showerror("Ошибка", str(e))
    
    def load_budgets(self):
        """Загружает и отображает бюджеты как карточки"""
        try:
            budgets = self.transaction_service.get_budgets()
            signature = tuple(
                (
                    budget['id'],
                    budget['category'],
                    budget['amount'],
                    budget['period'] if 'period' in budget.keys() else 'monthly',
                )
                for budget in budgets
            )

            if signature == self._last_budgets_signature and self.budgets_container.winfo_children():
                return
            
            if not budgets:
                self._show_empty_budgets_state()
                self._last_budgets_signature = signature
                return

            self._hide_empty_budgets_state()
            
            # Показываем бюджеты карточками
            for index, budget in enumerate(budgets):
                self.create_budget_card(index, budget)
            self._hide_unused_budget_cards(len(budgets))
            self._last_budgets_signature = signature
            
        except Exception as e:
            self._hide_unused_budget_cards(0)
            ctk.CTkLabel(
                self.budgets_container,
                text=f"Ошибка загрузки: {e}",
                text_color="#f44336"
            ).pack(pady=20)
    
    def _show_empty_budgets_state(self):
        """Показывает пустое состояние блока бюджетов"""
        self._hide_unused_budget_cards(0)
        if self._empty_budgets_label is None or not self._empty_budgets_label.winfo_exists():
            self._empty_budgets_label = ctk.CTkLabel(
                self.budgets_container,
                text="📭 Бюджеты не установлены",
                text_color="gray"
            )
        if not self._empty_budgets_label.winfo_manager():
            self._empty_budgets_label.pack(pady=20)

    def _hide_empty_budgets_state(self):
        """Скрывает пустое состояние блока бюджетов"""
        if (
            self._empty_budgets_label is not None
            and self._empty_budgets_label.winfo_exists()
            and self._empty_budgets_label.winfo_manager()
        ):
            self._empty_budgets_label.pack_forget()

    def _hide_unused_budget_cards(self, visible_count):
        """Скрывает неиспользуемые карточки бюджета"""
        for card_data in self._budget_card_widgets[visible_count:]:
            if card_data["card"].winfo_manager():
                card_data["card"].pack_forget()

    def _create_budget_card_widgets(self):
        """Создаёт виджеты карточки бюджета для переиспользования"""
        card = ctk.CTkFrame(self.budgets_container)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=5)

        title_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title_label.pack(side="left")

        status_label = ctk.CTkLabel(header, text="")
        status_label.pack(side="right")

        details = ctk.CTkFrame(card, fg_color="transparent")
        details.pack(fill="x", padx=10, pady=(0, 5))

        input_label = ctk.CTkLabel(details, text="")
        input_label.pack(side="left", padx=10)

        monthly_label = ctk.CTkLabel(details, text="", text_color="gray")
        monthly_label.pack(side="left", padx=2)

        stats = ctk.CTkFrame(card, fg_color="transparent")
        stats.pack(fill="x", padx=10, pady=(0, 5))

        spent_label = ctk.CTkLabel(stats, text="")
        spent_label.pack(side="left", padx=10)

        remaining_label = ctk.CTkLabel(stats, text="")
        remaining_label.pack(side="left", padx=10)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(0, 10))

        edit_btn = ctk.CTkButton(
            actions,
            text="✏️ Редактировать",
            fg_color="transparent",
            border_width=1,
            height=30
        )
        edit_btn.pack(side="left", padx=5)

        delete_btn = ctk.CTkButton(
            actions,
            text="🗑️ Удалить",
            fg_color="#f44336",
            hover_color="#d32f2f",
            height=30
        )
        delete_btn.pack(side="right", padx=5)

        return {
            "card": card,
            "title_label": title_label,
            "status_label": status_label,
            "input_label": input_label,
            "monthly_label": monthly_label,
            "spent_label": spent_label,
            "remaining_label": remaining_label,
            "edit_btn": edit_btn,
            "delete_btn": delete_btn,
        }

    def create_budget_card(self, index, budget):
        """Обновляет или создаёт карточку бюджета"""
        while len(self._budget_card_widgets) <= index:
            self._budget_card_widgets.append(self._create_budget_card_widgets())

        card_data = self._budget_card_widgets[index]
        card = card_data["card"]
        if not card.winfo_manager():
            card.pack(fill="x", pady=5)
        
        # ID бюджета
        budget_id = budget['id']
        category = budget['category']
        amount = budget['amount']
        period = budget['period'] if 'period' in budget.keys() else 'monthly'
        
        # Переводим период в месячный эквивалент
        period_ru = {"daily": "в день", "monthly": "в месяц", "yearly": "в год"}.get(period, "в месяц")
        
        if period == 'daily':
            monthly_limit = amount * 30
        elif period == 'yearly':
            monthly_limit = amount / 12
        else:
            monthly_limit = amount
        
        # Получаем сколько потрачено в этом месяце
        from datetime import datetime
        today = datetime.now()
        start_month = today.replace(day=1).strftime('%Y-%m-%d')
        end_month = today.strftime('%Y-%m-%d')
        
        cat = core.get_category_by_name(category)
        spent = 0
        if cat:
            # Получаем расходы по категории за месяц
            expenses = core.get_expenses_by_category(start_month, end_month)
            for exp in expenses:
                if exp['category'] == category:
                    spent = exp['total'] or 0
                    break
        
        remaining = monthly_limit - spent
        percent = (spent / monthly_limit * 100) if monthly_limit > 0 else 0
        
        # Определяем статус
        if percent > 100:
            status_icon = "🔴"
            status_color = "#f44336"
            status_text = "ПРЕВЫШЕН!"
        elif percent > 80:
            status_icon = "🟠"
            status_color = "#ff9800"
            status_text = "Лимит близок"
        else:
            status_icon = "🟢"
            status_color = "#4caf50"
            status_text = "В норме"
        
        amount_str = f"{amount:,.0f} ₽".replace(",", " ")
        monthly_str = f"{monthly_limit:,.0f} ₽".replace(",", " ")
        spent_str = f"{spent:,.0f} ₽".replace(",", " ")
        remaining_str = f"{remaining:,.0f} ₽".replace(",", " ")

        card_data["title_label"].configure(text=f"🎯 {category}")
        card_data["status_label"].configure(
            text=f"{status_icon} {status_text}",
            text_color=status_color
        )
        card_data["input_label"].configure(text=f"Введено: {amount_str} {period_ru}")
        card_data["monthly_label"].configure(text=f"→ {monthly_str}/мес")
        card_data["spent_label"].configure(
            text=f"Потрачено: {spent_str} из {monthly_str} ({percent:.0f}%)"
        )
        card_data["remaining_label"].configure(
            text=f"Осталось: {remaining_str}",
            text_color=status_color
        )
        card_data["edit_btn"].configure(
            command=lambda b=budget_id, ci=cat['id'], c=category, a=amount, p=period: self.edit_budget(b, ci, c, a, p)
        )
        card_data["delete_btn"].configure(
            command=lambda: self.delete_budget(budget_id, category)
        )
    
    def edit_budget(self, budget_id, category_id, category, amount, period):
        """Редактирует бюджет"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("✏️ Редактировать бюджет")
        dialog.geometry("400x300")
        dialog.grab_set()
        
        # Заголовок
        ctk.CTkLabel(
            dialog,
            text=f"Редактирование: {category}",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        
        form = ctk.CTkFrame(dialog)
        form.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Сумма
        ctk.CTkLabel(form, text="Сумма:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        amount_entry = ctk.CTkEntry(form, width=200)
        amount_entry.insert(0, str(amount))
        amount_entry.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        # Период
        ctk.CTkLabel(form, text="Период:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        period_combo = ctk.CTkComboBox(
            form,
            values=["В день", "В месяц", "В год"],
            width=200
        )
        period_map = {"daily": "В день", "monthly": "В месяц", "yearly": "В год"}
        period_combo.set(period_map.get(period, "В месяц"))
        period_combo.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        
        def save():
            try:
                new_amount = float(amount_entry.get().replace(" ", "").replace(",", "."))
                if new_amount <= 0:
                    messagebox.showerror("Ошибка", "Сумма должна быть положительной")
                    return
                
                period_text = period_combo.get()
                period_map_inv = {"В день": "daily", "В месяц": "monthly", "В год": "yearly"}
                new_period = period_map_inv.get(period_text, "monthly")
                
                # Обновляем бюджет (передаём category_id, а не budget_id)
                self.transaction_service.set_budget(category_id, new_amount, new_period)
                
                dialog.destroy()
                self.load_budgets()
                self.update_forecast()
                self._cancel_scheduled_refresh()
                self._set_status(f"✅ Бюджет '{category}' обновлён", True)
                
            except ValueError:
                messagebox.showerror("Ошибка", "Неверный формат суммы")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        
        # Кнопки
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkButton(btn_frame, text="💾 Сохранить", command=save).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", command=dialog.destroy, fg_color="transparent").pack(side="right", padx=5)
    
    def delete_budget(self, budget_id, category):
        """Удаляет бюджет"""
        if messagebox.askyesno("Подтверждение", f"Удалить бюджет '{category}'?"):
            try:
                self.transaction_service.delete_budget(budget_id)
                self.load_budgets()
                self.update_forecast()
                self._cancel_scheduled_refresh()
                self._set_status(f"✅ Бюджет '{category}' удалён", True)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
