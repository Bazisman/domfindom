# views/capital_view.py
import customtkinter as ctk
from tkinter import messagebox, colorchooser
from services.transaction_service import TransactionService
from services.category_service import CategoryService
from widgets.amount_entry import AmountEntry
from widgets.date_picker import DatePicker
from datetime import datetime
from utils.logger import app_logger

class CapitalView(ctk.CTkFrame):
    """Вкладка управления капиталом"""
    
    def __init__(self, master, transaction_service, category_service):
        super().__init__(master)
        
        self.transaction_service = transaction_service
        self.category_service = category_service
        self.capital_accounts = []
        self.main_account = None
        self._loading = False
        
        # Создаём прокручиваемый контейнер для всего содержимого
        self.main_container = ctk.CTkScrollableFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.setup_ui()
        self.load_auto_capital_settings()
        self.load_data()
    
    def setup_ui(self):
        """Создаёт интерфейс вкладки"""
        
        # Заголовок
        title_label = ctk.CTkLabel(
            self.main_container,
            text="💰 Управление капиталом",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=20)
        
        # === Общий баланс капитала ===
        total_frame = ctk.CTkFrame(self.main_container, height=100, corner_radius=10)
        total_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            total_frame,
            text="Общий капитал",
            font=ctk.CTkFont(size=16)
        ).pack(pady=(15, 5))
        
        self.total_capital_label = ctk.CTkLabel(
            total_frame,
            text="0.00 ₽",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color="#ff9800"
        )
        self.total_capital_label.pack(pady=(5, 15))
        
        # === Настройки автоотчислений ===
        settings_frame = ctk.CTkFrame(self.main_container)
        settings_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            settings_frame,
            text="⚙️ Настройки автоотчислений",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=10)

        auto_frame = ctk.CTkFrame(settings_frame)
        auto_frame.pack(pady=5)

        self.auto_capital_var = ctk.BooleanVar(value=True)
        self.auto_capital_check = ctk.CTkCheckBox(
            auto_frame,
            text="Автоматически отчислять в капитал",
            variable=self.auto_capital_var,
            command=self.save_auto_capital_setting
        )
        self.auto_capital_check.pack(side="left", padx=10)

        # Процент отчисления
        percent_frame = ctk.CTkFrame(settings_frame)
        percent_frame.pack(pady=5)

        ctk.CTkLabel(percent_frame, text="Процент отчисления:").pack(side="left", padx=5)

        self.capital_percent_var = ctk.StringVar(value="10")
        self.capital_percent_entry = ctk.CTkEntry(
            percent_frame,
            textvariable=self.capital_percent_var,
            width=60,
            justify="center"
        )
        self.capital_percent_entry.pack(side="left", padx=5)

        # Очищаем поле при фокусе
        self.capital_percent_entry.bind("<FocusIn>", lambda e: self.capital_percent_entry.delete(0, "end"))

        ctk.CTkLabel(percent_frame, text="%").pack(side="left", padx=5)

        self.save_percent_btn = ctk.CTkButton(
            percent_frame,
            text="💾 Сохранить",
            command=self.save_auto_capital_setting,
            width=80,
            height=30
        )
        self.save_percent_btn.pack(side="left", padx=20)
        
        # === Панель перевода между счетами ===
        transfer_section = ctk.CTkFrame(self.main_container)
        transfer_section.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            transfer_section,
            text="💸 Перевод между счетами",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=10)

        transfer_frame = ctk.CTkFrame(transfer_section)
        transfer_frame.pack(padx=20, pady=10)

        # Откуда
        ctk.CTkLabel(transfer_frame, text="Откуда:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.from_account_combo = ctk.CTkComboBox(
            transfer_frame,
            values=[],  # заполнится позже
            width=200
        )
        self.from_account_combo.grid(row=0, column=1, padx=10, pady=10)

        # Куда
        ctk.CTkLabel(transfer_frame, text="Куда:").grid(row=0, column=2, padx=10, pady=10, sticky="e")
        self.to_account_combo = ctk.CTkComboBox(
            transfer_frame,
            values=[],  # заполнится позже
            width=200
        )
        self.to_account_combo.grid(row=0, column=3, padx=10, pady=10)

        # Сумма
        ctk.CTkLabel(transfer_frame, text="Сумма:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        self.transfer_amount = AmountEntry(transfer_frame, initial_value=0.0)
        self.transfer_amount.grid(row=1, column=1, padx=10, pady=10)

        # Дата
        ctk.CTkLabel(transfer_frame, text="Дата:").grid(row=1, column=2, padx=10, pady=10, sticky="e")
        self.transfer_date = DatePicker(transfer_frame)
        self.transfer_date.grid(row=1, column=3, padx=10, pady=10)

        # Комментарий
        ctk.CTkLabel(transfer_frame, text="Комментарий:").grid(row=2, column=0, padx=10, pady=10, sticky="e")
        self.transfer_comment = ctk.CTkEntry(transfer_frame, width=250)
        self.transfer_comment.grid(row=2, column=1, padx=10, pady=10, columnspan=3, sticky="w")

        # Кнопка перевода
        transfer_btn = ctk.CTkButton(
            transfer_frame,
            text="💸 Выполнить перевод",
            command=self.execute_transfer,
            width=150,
            height=40,
            fg_color="#2e7d32",
            hover_color="#1e5a23"
        )
        transfer_btn.grid(row=3, column=0, columnspan=4, pady=20)
        
        # === Панель добавления нового счёта ===
        add_frame = ctk.CTkFrame(self.main_container)
        add_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            add_frame,
            text="➕ Добавить новый счёт",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        
        form_frame = ctk.CTkFrame(add_frame)
        form_frame.pack(padx=20, pady=10)
        
        # Название
        ctk.CTkLabel(form_frame, text="Название:").grid(row=0, column=0, padx=5, pady=10, sticky="e")
        self.new_name_entry = ctk.CTkEntry(form_frame, width=150)
        self.new_name_entry.grid(row=0, column=1, padx=5, pady=10)
        
        # Начальный баланс
        ctk.CTkLabel(form_frame, text="Начальный баланс:").grid(row=0, column=2, padx=5, pady=10, sticky="e")
        self.new_balance_entry = AmountEntry(form_frame, initial_value=0.0)
        self.new_balance_entry.grid(row=0, column=3, padx=5, pady=10)
        
        # Иконка
        ctk.CTkLabel(form_frame, text="Иконка:").grid(row=0, column=4, padx=5, pady=10, sticky="e")
        self.new_icon_entry = ctk.CTkEntry(form_frame, width=50)
        self.new_icon_entry.insert(0, "💰")
        self.new_icon_entry.grid(row=0, column=5, padx=5, pady=10)
        
        # Цвет
        self.new_color_btn = ctk.CTkButton(
            form_frame,
            text="🎨 Цвет",
            width=80,
            command=self.choose_new_color
        )
        self.new_color_btn.grid(row=0, column=6, padx=5, pady=10)
        self.new_selected_color = "#ff9800"
        
        # Кнопка добавления
        add_btn = ctk.CTkButton(
            form_frame,
            text="➕ Добавить",
            command=self.add_capital_account,
            width=100,
            fg_color="#2e7d32"
        )
        add_btn.grid(row=0, column=7, padx=20, pady=10)
        
        # Bind Enter для добавления по клавише
        self.new_name_entry.bind("<Return>", lambda e: self.add_capital_account())
        self.new_balance_entry.entry.bind("<Return>", lambda e: self.add_capital_account())
        self.new_icon_entry.bind("<Return>", lambda e: self.add_capital_account())
        
        # === Список счетов капитала ===
        list_frame = ctk.CTkFrame(self.main_container)
        list_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(
            list_frame,
            text="Мои счета",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=10, pady=10)
        
        # Контейнер для карточек счетов
        self.accounts_frame = ctk.CTkScrollableFrame(list_frame)
        self.accounts_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # === История переводов ===
        history_frame = ctk.CTkFrame(self.main_container)
        history_frame.pack(fill="both", expand=True, padx=20, pady=10)

        ctk.CTkLabel(
            history_frame,
            text="📋 История переводов",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=10, pady=10)

        # Создаём таблицу для истории
        history_table_frame = ctk.CTkFrame(history_frame)
        history_table_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Заголовки таблицы
        headers_frame = ctk.CTkFrame(history_table_frame)
        headers_frame.pack(fill="x", padx=5, pady=5)

        columns = ["Дата", "Откуда", "Куда", "Сумма", "Комментарий"]
        widths = [100, 150, 150, 100, 300]

        for i, (col, width) in enumerate(zip(columns, widths)):
            label = ctk.CTkLabel(
                headers_frame,
                text=col,
                font=ctk.CTkFont(size=12, weight="bold"),
                width=width
            )
            label.grid(row=0, column=i, padx=2, pady=2, sticky="w")

        # Контейнер для записей истории с прокруткой
        self.history_container = ctk.CTkScrollableFrame(history_table_frame, height=200)
        self.history_container.pack(fill="both", expand=True, padx=5, pady=5)
    
    def choose_new_color(self):
        """Выбор цвета для нового счёта"""
        color = colorchooser.askcolor(title="Выберите цвет", initialcolor=self.new_selected_color)
        if color and color[1]:
            self.new_selected_color = color[1]
            self.new_color_btn.configure(fg_color=self.new_selected_color)
    
    def load_auto_capital_settings(self):
        """Загружает настройки автоотчислений"""
        root = self.winfo_toplevel()
        
        # Устанавливаем значения по умолчанию
        if not hasattr(root, 'auto_capital_enabled'):
            root.auto_capital_enabled = True
        if not hasattr(root, 'auto_capital_percent'):
            root.auto_capital_percent = 10
        
        # Обновляем интерфейс
        self.auto_capital_var.set(root.auto_capital_enabled)
        self.capital_percent_var.set(str(root.auto_capital_percent))
    
    def save_auto_capital_setting(self):
        """Сохраняет настройки автоотчислений"""
        try:
            percent = float(self.capital_percent_var.get())
            if percent < 0 or percent > 100:
                root = self.winfo_toplevel()
                if hasattr(root, 'set_status'):
                    root.set_status("❌ Процент должен быть от 0 до 100", False)
                return
            
            # Сохраняем настройки в главном окне
            root = self.winfo_toplevel()
            root.auto_capital_enabled = self.auto_capital_var.get()
            root.auto_capital_percent = percent
            
            # 🔥 ПЕРЕДАЁМ НАСТРОЙКИ В СЕРВИС
            self.transaction_service.set_auto_capital_settings(
                root.auto_capital_enabled,
                root.auto_capital_percent
            )
            
            status = "включены" if self.auto_capital_var.get() else "отключены"
            root.set_status(f"✅ Автоотчисления {status}, {percent}%", True)
            
        except ValueError:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Введите корректное число", False)
    
    def load_data(self):
        """Загружает данные"""
        if self._loading:
            return
        self._loading = True
        
        # Получаем основной счёт
        self.main_account = self.transaction_service.get_main_account()
        
        # Получаем счета капитала
        self.capital_accounts = self.transaction_service.get_capital_accounts()
        
        # Обновляем отображение
        self.refresh_accounts_list()
        self.update_total_capital()
        self.update_transfer_accounts()
        self.load_transfers_history()
        
        self._loading = False
    
    def update_transfer_accounts(self):
        """Обновляет списки счетов для перевода"""
        # Получаем все доступные счета
        accounts = []
        
        # Добавляем основной счёт
        if self.main_account:
            accounts.append(f"🏦 {self.main_account['name']}")
        
        # Добавляем счета капитала (с пометкой основного)
        for acc in self.capital_accounts:
            if acc['is_default']:
                accounts.append(f"{acc['icon']} {acc['name']} (основной)")
            else:
                accounts.append(f"{acc['icon']} {acc['name']}")
        
        # Обновляем комбобоксы
        self.from_account_combo.configure(values=accounts)
        self.to_account_combo.configure(values=accounts)
        
        # Устанавливаем значения по умолчанию
        if accounts:
            if len(accounts) > 0:
                self.from_account_combo.set(accounts[0])
            if len(accounts) > 1:
                self.to_account_combo.set(accounts[1])
            elif len(accounts) == 1:
                self.to_account_combo.set(accounts[0])
    
    def get_account_id_from_display(self, display_text):
        """Получает ID счёта по отображаемому тексту"""
        # Убираем иконку и пробел в начале, а также пометку (основной)
        if ' ' in display_text:
            clean_name = display_text.split(' ', 1)[-1]
            # Убираем пометку (основной) если есть
            if ' (основной)' in clean_name:
                clean_name = clean_name.replace(' (основной)', '')
        else:
            clean_name = display_text
        
        # Проверяем основной счёт
        if self.main_account and clean_name == self.main_account['name']:
            return self.main_account['id'], 'main'
        
        # Проверяем счета капитала
        for acc in self.capital_accounts:
            if clean_name == acc['name']:
                return acc['id'], 'capital'
        
        return None, None
    
    def execute_transfer(self):
        """Выполняет перевод между счетами"""
        from_text = self.from_account_combo.get()
        to_text = self.to_account_combo.get()
        amount = self.transfer_amount.get()
        date = self.transfer_date.get_date_str()
        comment = self.transfer_comment.get()
        
        if not from_text or not to_text:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Выберите счета", False)
            return
        
        if from_text == to_text:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Счета должны быть разными", False)
            return
        
        if amount <= 0:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Сумма должна быть положительной", False)
            return
        
        # Получаем ID счетов
        from_id, from_type = self.get_account_id_from_display(from_text)
        to_id, to_type = self.get_account_id_from_display(to_text)
        
        if not from_id or not to_id:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Счета не найдены", False)
            return
        
        # Проверяем достаточно ли средств на счёте отправителя
        if from_type == 'main':
            if self.main_account['balance'] < amount:
                root = self.winfo_toplevel()
                if hasattr(root, 'set_status'):
                    root.set_status("❌ Недостаточно средств на основном счёте", False)
                return
        else:
            # Находим счёт капитала
            found = False
            for acc in self.capital_accounts:
                if acc['id'] == from_id:
                    found = True
                    if acc['balance'] < amount:
                        root = self.winfo_toplevel()
                        if hasattr(root, 'set_status'):
                            root.set_status(f"❌ Недостаточно средств на счёте {acc['name']}", False)
                        return
                    break
            if not found:
                root = self.winfo_toplevel()
                if hasattr(root, 'set_status'):
                    root.set_status("❌ Счёт отправителя не найден", False)
                return
        
        # Выполняем перевод через сервис
        success = self.transaction_service.transfer_money(
            from_id, to_id, amount, date, comment
        )
        
        if success:
            # Очищаем поля
            self.transfer_amount.clear()
            self.transfer_comment.delete(0, "end")
            
            # Обновляем данные
            self.load_data()
            
            # Обновляем баланс в главном окне
            root = self.winfo_toplevel()
            if hasattr(root, 'update_balance'):
                root.update_balance()
            
            root.set_status(f"✅ Перевод {amount:.2f} ₽ выполнен", True)
        else:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Ошибка при переводе", False)
    
    def refresh_accounts_list(self):
        """Обновляет список счетов"""
        # Очищаем контейнер
        for widget in self.accounts_frame.winfo_children():
            widget.destroy()
        
        if not self.capital_accounts:
            empty_label = ctk.CTkLabel(
                self.accounts_frame,
                text="📭 Нет счетов. Добавьте первый счёт!",
                font=ctk.CTkFont(size=14)
            )
            empty_label.pack(pady=50)
            return
        
        # Создаём карточки для каждого счёта
        for acc in self.capital_accounts:
            self.add_account_card(acc)
    
    def add_account_card(self, account):
        """Добавляет карточку счёта"""
        card = ctk.CTkFrame(self.accounts_frame, corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)
        
        # Иконка и название
        icon_label = ctk.CTkLabel(
            card,
            text=account['icon'],
            font=ctk.CTkFont(size=24),
            width=50
        )
        icon_label.pack(side="left", padx=10, pady=15)
        
        # Название с пометкой "основной"
        name_text = account['name']
        if account['is_default']:
            name_text += " ⭐"
        
        name_label = ctk.CTkLabel(
            card,
            text=name_text,
            font=ctk.CTkFont(size=16, weight="bold")
        )
        name_label.pack(side="left", padx=5, pady=15)
        
        # Баланс
        balance_label = ctk.CTkLabel(
            card,
            text=f"{account['balance']:,.2f} ₽".replace(",", " "),
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=account['color']
        )
        balance_label.pack(side="right", padx=20, pady=15)
        
        # Кнопки действий
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10, pady=15)
        
        # Кнопка "Основной" (только для неосновных счетов)
        if not account['is_default']:
            default_btn = ctk.CTkButton(
                btn_frame,
                text="⭐",
                width=30,
                fg_color="#6c757d",
                hover_color="#5a6268",
                command=lambda a=account: self.set_default_account(a)
            )
            default_btn.pack(side="left", padx=2)
        
        edit_btn = ctk.CTkButton(
            btn_frame,
            text="✏️",
            width=30,
            command=lambda a=account: self.edit_account(a)
        )
        edit_btn.pack(side="left", padx=2)
        
        delete_btn = ctk.CTkButton(
            btn_frame,
            text="🗑️",
            width=30,
            fg_color="#f44336",
            hover_color="#d32f2f",
            command=lambda a=account: self.delete_account(a)
        )
        delete_btn.pack(side="left", padx=2)
    
    def add_capital_account(self):
        """Добавляет новый счёт капитала"""
        name = self.new_name_entry.get().strip()
        balance = self.new_balance_entry.get()
        icon = self.new_icon_entry.get().strip() or "💰"
        
        if not name:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Введите название счёта", False)
            return
        
        account_id = self.transaction_service.add_capital_account(
            name, balance, icon, self.new_selected_color
        )
        
        if account_id:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status(f"✅ Счёт '{name}' добавлен", True)
            
            # Очищаем поля
            self.new_name_entry.delete(0, "end")
            self.new_balance_entry.clear()
            self.new_icon_entry.delete(0, "end")
            self.new_icon_entry.insert(0, "💰")
            self.new_selected_color = "#ff9800"
            self.new_color_btn.configure(fg_color="#ff9800")
            
            # Обновляем список
            self.load_data()
    
    def set_default_account(self, account):
        """Устанавливает счёт как основной для отчислений"""
        if messagebox.askyesno("Подтверждение", f"Сделать счёт '{account['name']}' основным для отчислений?"):
            self.transaction_service.set_default_capital_account(account['id'])
            self.load_data()
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status(f"✅ Счёт '{account['name']}' теперь основной", True)
    
    def edit_account(self, account):
        """Редактирование счёта"""
        # Преобразуем Row в словарь для редактирования
        account_dict = {
            'id': account['id'],
            'name': account['name'],
            'balance': account['balance'],
            'icon': account['icon'],
            'color': account['color']
        }
        
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"✏️ Редактирование: {account_dict['name']}")
        dialog.geometry("450x450")
        dialog.grab_set()
        
        ctk.CTkLabel(
            dialog,
            text="Редактирование счёта",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        
        frame = ctk.CTkFrame(dialog)
        frame.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Название
        ctk.CTkLabel(frame, text="Название:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        name_entry = ctk.CTkEntry(frame, width=150)
        name_entry.insert(0, account_dict['name'])
        name_entry.grid(row=0, column=1, padx=10, pady=10)
        
        # Баланс
        ctk.CTkLabel(frame, text="Баланс:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        
        # Показываем текущий баланс и поле для нового
        current_balance = account_dict['balance']
        balance_var = ctk.StringVar(value=str(current_balance))
        balance_entry = AmountEntry(frame, initial_value=current_balance)
        balance_entry.grid(row=1, column=1, padx=10, pady=10)
        
        # Добавляем пояснение
        ctk.CTkLabel(
            frame, 
            text="При изменении баланса будет создан корректировочный перевод",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        ).grid(row=2, column=0, columnspan=2, padx=10, pady=5)
        
        # Иконка
        ctk.CTkLabel(frame, text="Иконка:").grid(row=3, column=0, padx=10, pady=10, sticky="e")
        icon_entry = ctk.CTkEntry(frame, width=50)
        icon_entry.insert(0, account_dict['icon'])
        icon_entry.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        
        # Цвет
        ctk.CTkLabel(frame, text="Цвет:").grid(row=4, column=0, padx=10, pady=10, sticky="e")
        
        color_frame = ctk.CTkFrame(frame)
        color_frame.grid(row=4, column=1, padx=10, pady=10, sticky="w")
        
        current_color = account_dict['color']
        color_box = ctk.CTkFrame(color_frame, width=30, height=30, fg_color=current_color, corner_radius=5)
        color_box.pack(side="left", padx=5)
        color_box.pack_propagate(False)
        
        def choose_color():
            nonlocal current_color
            color = colorchooser.askcolor(title="Выберите цвет", initialcolor=current_color)
            if color and color[1]:
                current_color = color[1]
                color_box.configure(fg_color=current_color)
        
        color_btn = ctk.CTkButton(
            color_frame,
            text="Выбрать",
            width=80,
            command=choose_color
        )
        color_btn.pack(side="left", padx=5)
        
        # Фрейм для даты корректировки
        date_frame = ctk.CTkFrame(frame, fg_color="transparent")
        date_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        
        ctk.CTkLabel(date_frame, text="Дата корректировки:").pack(side="left", padx=5)
        
        from widgets.date_picker import DatePicker
        adjustment_date = DatePicker(date_frame)
        adjustment_date.pack(side="left", padx=5)
        
        # Комментарий для корректировки
        ctk.CTkLabel(frame, text="Комментарий:").grid(row=6, column=0, padx=10, pady=10, sticky="e")
        comment_entry = ctk.CTkEntry(frame, width=250)
        comment_entry.insert(0, "Корректировка баланса")
        comment_entry.grid(row=6, column=1, padx=10, pady=10, sticky="w")
        
        def save():
            new_name = name_entry.get().strip()
            new_balance = balance_entry.get()
            new_icon = icon_entry.get().strip()
            adjust_date = adjustment_date.get_date_str()
            adjust_comment = comment_entry.get().strip()
            
            if not new_name:
                messagebox.showerror("Ошибка", "Введите название")
                return
            
            # Получаем текущий баланс из БД (на случай, если он изменился)
            current = self.transaction_service.get_account_balance(account_dict['id'])
            balance_diff = new_balance - current
            
            # Если баланс изменился — создаём корректировочный перевод
            if abs(balance_diff) > 0.01:
                app_logger.info(f"Корректировка баланса счёта {new_name}: {current} → {new_balance} (разница: {balance_diff})")
                
                # Создаём перевод для корректировки
                if balance_diff > 0:
                    # Увеличиваем баланс — перевод из основного счёта
                    from_id = 1
                    to_id = account_dict['id']
                    comment = f"Корректировка баланса: +{balance_diff:.2f}. {adjust_comment}"
                else:
                    # Уменьшаем баланс — перевод на основной счёт
                    from_id = account_dict['id']
                    to_id = 1
                    comment = f"Корректировка баланса: {balance_diff:.2f}. {adjust_comment}"
                
                # Выполняем перевод
                success = self.transaction_service.transfer_money(
                    from_id, to_id, abs(balance_diff), adjust_date, comment
                )
                
                if not success:
                    messagebox.showerror("Ошибка", "Не удалось выполнить корректировку баланса")
                    return
            
            # Обновляем название, иконку, цвет
            self.transaction_service.update_capital_account(
                account_dict['id'],
                name=new_name,
                icon=new_icon or "💰",
                color=current_color
            )
            
            dialog.destroy()
            self.load_data()
            
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status(f"✅ Счёт '{new_name}' обновлён", True)
        
        # Кнопки
        btn_frame = ctk.CTkFrame(dialog)
        btn_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkButton(
            btn_frame,
            text="💾 Сохранить",
            command=save,
            fg_color="#2e7d32"
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            btn_frame,
            text="❌ Отмена",
            command=dialog.destroy,
            fg_color="#f44336",
            hover_color="#d32f2f"
        ).pack(side="right", padx=10)
    
    def delete_account(self, account):
        """Удаляет счёт (деактивирует)"""
        if messagebox.askyesno("Подтверждение", f"Удалить счёт '{account['name']}'?"):
            self.transaction_service.delete_capital_account(account['id'])
            self.load_data()
            
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status(f"✅ Счёт '{account['name']}' удалён", True)
    
    def update_total_capital(self):
        """Обновляет отображение общего капитала"""
        total = sum(acc['balance'] for acc in self.capital_accounts)
        self.total_capital_label.configure(
            text=f"{total:,.2f} ₽".replace(",", " ")
        )
    
    def load_transfers_history(self):
        """Загружает историю переводов"""
        # Проверяем, создан ли контейнер
        if not hasattr(self, 'history_container'):
            return
        
        # Очищаем контейнер
        for widget in self.history_container.winfo_children():
            widget.destroy()
        
        # Получаем историю переводов
        transfers = self.transaction_service.get_transfers_history(limit=100)
        
        if not transfers:
            empty_label = ctk.CTkLabel(
                self.history_container,
                text="📭 История переводов пуста",
                font=ctk.CTkFont(size=14)
            )
            empty_label.pack(pady=20)
            return
        
        # Создаём записи для каждого перевода
        for t in transfers:
            self.add_transfer_record(t)
        
    def add_transfer_record(self, transfer):
        """Добавляет запись о переводе в историю"""
        row = ctk.CTkFrame(self.history_container)
        row.pack(fill="x", pady=2, padx=5)
        
        # Форматируем дату
        date_parts = transfer['date'].split('-')
        display_date = f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]}"
        
        # Дата
        date_label = ctk.CTkLabel(row, text=display_date, width=100, anchor="w")
        date_label.pack(side="left", padx=5)
        
        # Откуда
        from_label = ctk.CTkLabel(row, text=transfer['from_name'], width=150, anchor="w")
        from_label.pack(side="left", padx=5)
        
        # Куда
        to_label = ctk.CTkLabel(row, text=transfer['to_name'], width=150, anchor="w")
        to_label.pack(side="left", padx=5)
        
        # Сумма с цветом
        amount_color = "#4caf50" if transfer['amount'] > 0 else "#f44336"
        amount_label = ctk.CTkLabel(
            row,
            text=f"{transfer['amount']:,.2f} ₽".replace(",", " "),
            width=100,
            anchor="e",
            text_color=amount_color
        )
        amount_label.pack(side="left", padx=5)
        
        # Комментарий
        comment_label = ctk.CTkLabel(
            row,
            text=transfer['comment'] or "",
            width=300,
            anchor="w"
        )
        comment_label.pack(side="left", padx=5)
    
    def refresh(self):
        """Обновляет данные"""
        self.load_data()