# views/settings_view.py
import customtkinter as ctk
from tkinter import messagebox, filedialog
from utils.logger import app_logger
import core
import os
import json
import sqlite3
from datetime import datetime


class SettingsView(ctk.CTkFrame):
    """Вкладка настроек"""
    
    def __init__(self, parent, transaction_service, category_service):
        super().__init__(parent)
        
        self.transaction_service = transaction_service
        self.category_service = category_service
        
        self.setup_ui()
        self.load_info()
    
    def setup_ui(self):
        """Создаёт интерфейс настроек"""
        
        # Заголовок
        title_label = ctk.CTkLabel(
            self,
            text="⚙️ Настройки",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=20)
        
        # Создаём прокручиваемый контейнер
        scroll_frame = ctk.CTkScrollableFrame(self)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # === Настройки внешнего вида ===
        appearance_frame = ctk.CTkFrame(scroll_frame)
        appearance_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            appearance_frame,
            text="🎨 Внешний вид",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=10, pady=10)
        
        # Тема
        theme_frame = ctk.CTkFrame(appearance_frame, fg_color="transparent")
        theme_frame.pack(anchor="w", padx=20, pady=5)
        
        ctk.CTkLabel(theme_frame, text="Тема:").pack(side="left", padx=5)
        
        self.theme_var = ctk.StringVar(value="dark")
        theme_dark = ctk.CTkRadioButton(
            theme_frame,
            text="Тёмная",
            variable=self.theme_var,
            value="dark",
            command=self.change_theme
        )
        theme_dark.pack(side="left", padx=10)
        
        theme_light = ctk.CTkRadioButton(
            theme_frame,
            text="Светлая",
            variable=self.theme_var,
            value="light",
            command=self.change_theme
        )
        theme_light.pack(side="left", padx=10)
        
        # Цветовая схема
        color_frame = ctk.CTkFrame(appearance_frame, fg_color="transparent")
        color_frame.pack(anchor="w", padx=20, pady=5)
        
        ctk.CTkLabel(color_frame, text="Цвет:").pack(side="left", padx=5)
        
        self.color_var = ctk.StringVar(value="green")
        colors = [
            ("Зелёный", "green"),
            ("Синий", "blue"),
            ("Тёмно-синий", "dark-blue"),
            ("Оранжевый", "orange")
        ]
        
        for color_name, color_value in colors:
            radio = ctk.CTkRadioButton(
                color_frame,
                text=color_name,
                variable=self.color_var,
                value=color_value,
                command=self.change_color
            )
            radio.pack(side="left", padx=10)
        
        # === Информация о БД ===
        info_frame = ctk.CTkFrame(scroll_frame)
        info_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            info_frame,
            text="📊 Информация",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=10, pady=10)
        
        # Количество транзакций
        self.transactions_count_label = ctk.CTkLabel(
            info_frame,
            text="Транзакций: загрузка...",
            font=ctk.CTkFont(size=12)
        )
        self.transactions_count_label.pack(anchor="w", padx=20, pady=2)
        
        # Количество доходов
        self.income_count_label = ctk.CTkLabel(
            info_frame,
            text="Доходов: загрузка...",
            font=ctk.CTkFont(size=12)
        )
        self.income_count_label.pack(anchor="w", padx=20, pady=2)
        
        # Количество расходов
        self.expense_count_label = ctk.CTkLabel(
            info_frame,
            text="Расходов: загрузка...",
            font=ctk.CTkFont(size=12)
        )
        self.expense_count_label.pack(anchor="w", padx=20, pady=2)
        
        # Количество счетов капитала
        self.capital_count_label = ctk.CTkLabel(
            info_frame,
            text="Счетов капитала: загрузка...",
            font=ctk.CTkFont(size=12)
        )
        self.capital_count_label.pack(anchor="w", padx=20, pady=2)
        
        # Размер БД
        self.db_size_label = ctk.CTkLabel(
            info_frame,
            text="Размер БД: загрузка...",
            font=ctk.CTkFont(size=12)
        )
        self.db_size_label.pack(anchor="w", padx=20, pady=2)
        
        # === Резервное копирование ===
        backup_frame = ctk.CTkFrame(scroll_frame)
        backup_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            backup_frame,
            text="💾 Резервное копирование",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=10, pady=10)
        
        # Кнопка экспорта
        export_btn = ctk.CTkButton(
            backup_frame,
            text="📤 Экспорт всех данных",
            command=self.export_data,
            height=35,
            fg_color="#2e7d32",
            hover_color="#1e5a23"
        )
        export_btn.pack(padx=20, pady=10)
        
        # Кнопка импорта
        import_btn = ctk.CTkButton(
            backup_frame,
            text="📥 Импорт данных",
            command=self.import_data,
            height=35,
            fg_color="#ff9800",
            hover_color="#f57c00"
        )
        import_btn.pack(padx=20, pady=10)
        
        ctk.CTkLabel(
            backup_frame,
            text="Экспорт сохраняет все данные в JSON файл.\nИмпорт восстановит данные из ранее сохранённого файла.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack(pady=5)
        
        # === Разделитель ===
        separator = ctk.CTkFrame(scroll_frame, height=2, fg_color="gray")
        separator.pack(fill="x", padx=10, pady=20)
        
        # === Опасная зона ===
        danger_frame = ctk.CTkFrame(scroll_frame, fg_color="#330000")
        danger_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            danger_frame,
            text="⚠️ ОПАСНАЯ ЗОНА",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#ff4444"
        ).pack(anchor="w", padx=10, pady=10)
        
        # Кнопка сброса
        reset_btn = ctk.CTkButton(
            danger_frame,
            text="🚨 СБРОС ДО ЗАВОДСКИХ НАСТРОЕК",
            command=self.reset_to_factory,
            fg_color="#f44336",
            hover_color="#d32f2f",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        reset_btn.pack(padx=20, pady=20)
        
        ctk.CTkLabel(
            danger_frame,
            text="⚠️ ВНИМАНИЕ: Сначала сделайте ЭКСПОРТ данных!\n"
                 "Это действие удалит ВСЕ данные. После сброса вы сможете восстановить данные через ИМПОРТ.",
            font=ctk.CTkFont(size=12),
            text_color="#ff8888"
        ).pack(pady=10)
    
    def load_info(self):
        """Загружает информацию о базе данных"""
        try:
            conn = sqlite3.connect('finance.db')
            cursor = conn.cursor()
            
            # Количество транзакций
            cursor.execute("SELECT COUNT(*) FROM transactions")
            count = cursor.fetchone()[0]
            self.transactions_count_label.configure(text=f"Транзакций: {count}")
            
            # Количество доходов
            cursor.execute("SELECT COUNT(*) FROM transactions WHERE type = 'income'")
            income_count = cursor.fetchone()[0]
            self.income_count_label.configure(text=f"Доходов: {income_count}")
            
            # Количество расходов
            cursor.execute("SELECT COUNT(*) FROM transactions WHERE type = 'expense'")
            expense_count = cursor.fetchone()[0]
            self.expense_count_label.configure(text=f"Расходов: {expense_count}")
            
            # Количество счетов капитала
            cursor.execute("SELECT COUNT(*) FROM capital_accounts WHERE is_active = 1")
            capital_count = cursor.fetchone()[0]
            self.capital_count_label.configure(text=f"Счетов капитала: {capital_count}")
            
            conn.close()
            
            # Размер БД
            if os.path.exists('finance.db'):
                size = os.path.getsize('finance.db')
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                self.db_size_label.configure(text=f"Размер БД: {size_str}")
                
        except Exception as e:
            app_logger.error(f"Ошибка загрузки информации о БД: {e}")
    
    def change_theme(self):
        """Меняет тему приложения"""
        theme = self.theme_var.get()
        ctk.set_appearance_mode(theme)
        
        root = self.winfo_toplevel()
        if hasattr(root, 'set_status'):
            root.set_status(f"✅ Тема изменена на {theme}", True)
        
        app_logger.info(f"Тема изменена: {theme}")
    
    def change_color(self):
        """Меняет цветовую схему"""
        color = self.color_var.get()
        ctk.set_default_color_theme(color)
        
        root = self.winfo_toplevel()
        if hasattr(root, 'set_status'):
            root.set_status(f"✅ Цветовая схема изменена на {color}", True)
        
        app_logger.info(f"Цветовая схема изменена: {color}")
    
    def export_data(self):
        """Экспорт всех данных в JSON файл"""
        try:
            # Выбор места сохранения
            filename = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialfile=f"finance_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            if not filename:
                return
            
            root = self.winfo_toplevel()
            root.set_status("🔄 Экспорт данных...", True)
            
            # Собираем все данные
            conn = sqlite3.connect('finance.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            data = {
                "export_date": datetime.now().isoformat(),
                "version": "1.0",
                "transactions": [],
                "categories": [],
                "budgets": [],
                "capital_accounts": [],
                "transfers": []
            }
            
            # Транзакции
            cursor.execute("SELECT * FROM transactions")
            for row in cursor.fetchall():
                data["transactions"].append(dict(row))
            
            # Категории
            cursor.execute("SELECT * FROM categories")
            for row in cursor.fetchall():
                data["categories"].append(dict(row))
            
            # Бюджеты
            cursor.execute("SELECT * FROM budgets")
            for row in cursor.fetchall():
                data["budgets"].append(dict(row))
            
            # Счета капитала
            cursor.execute("SELECT * FROM capital_accounts")
            for row in cursor.fetchall():
                data["capital_accounts"].append(dict(row))
            
            # Переводы (только активные!)
            cursor.execute("SELECT * FROM transfers WHERE is_active = 1")
            for row in cursor.fetchall():
                data["transfers"].append(dict(row))
            
            conn.close()
            
            # Сохраняем в файл
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            
            size = os.path.getsize(filename)
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            
            root.set_status(f"✅ Данные экспортированы ({size_str})", True)
            messagebox.showinfo("Экспорт завершён", 
                f"Данные сохранены в:\n{filename}\n\n"
                f"Размер файла: {size_str}\n"
                f"Транзакций: {len(data['transactions'])}\n"
                f"Категорий: {len(data['categories'])}\n"
                f"Счетов капитала: {len(data['capital_accounts'])}")
            
            app_logger.info(f"Экспорт данных: {filename}, {len(data['transactions'])} транзакций")
            
        except Exception as e:
            app_logger.error(f"Ошибка экспорта: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось экспортировать данные:\n{e}")
    
    def import_data(self):
        """Импорт данных из JSON файла"""
        try:
            # Выбор файла
            filename = filedialog.askopenfilename(
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if not filename:
                return
            
            # Подтверждение
            result = messagebox.askyesno(
                "⚠️ ПОДТВЕРЖДЕНИЕ ИМПОРТА",
                "Импорт данных заменит ВСЕ текущие данные!\n\n"
                "Рекомендуется сначала сделать экспорт текущих данных.\n\n"
                "Перед импортом будет создана резервная копия.\n\n"
                "Продолжить?"
            )
            
            if not result:
                return
            
            root = self.winfo_toplevel()
            root.set_status("🔄 Импорт данных...", True)
            
            # Создаём резервную копию
            from utils.backup import DatabaseBackup
            backup = DatabaseBackup()
            backup.create_backup(reason="before_import")
            
            # Загружаем данные
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Очищаем текущие данные
            conn = sqlite3.connect('finance.db')
            cursor = conn.cursor()
            
            # ВАЖНО: отключаем проверку внешних ключей временно
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            cursor.execute("DELETE FROM transactions")
            cursor.execute("DELETE FROM categories")
            cursor.execute("DELETE FROM budgets")
            cursor.execute("DELETE FROM capital_accounts")
            cursor.execute("DELETE FROM transfers")
            
            # Сбрасываем автоинкремент
            cursor.execute("DELETE FROM sqlite_sequence")
            
            # Устанавливаем счётчик ID для capital_accounts на 100 (до вставки!)
            cursor.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('capital_accounts', 99)")
            
            # Восстанавливаем категории
            category_id_map = {}  # для маппинга старых ID на новые
            for cat in data.get('categories', []):
                old_id = cat.get('id')
                cursor.execute("""
                    INSERT INTO categories (name, type, color, icon, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    cat.get('name'), cat.get('type'),
                    cat.get('color', '#808080'), cat.get('icon', '📁'),
                    cat.get('is_active', 1), cat.get('created_at'), cat.get('updated_at')
                ))
                new_id = cursor.lastrowid
                if old_id:
                    category_id_map[old_id] = new_id
            
            # Восстанавливаем счета капитала (с сохранением ID >= 100)
            capital_id_map = {}
            for acc in data.get('capital_accounts', []):
                old_id = acc.get('id')
                # Сохраняем оригинальный ID (должен быть >= 100)
                new_id = old_id if old_id and old_id >= 100 else None
                
                cursor.execute("""
                    INSERT INTO capital_accounts (id, name, balance, currency, icon, color, is_active, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    new_id, acc.get('name'), acc.get('balance', 0),
                    acc.get('currency', 'RUB'), acc.get('icon', '💰'),
                    acc.get('color', '#ff9800'), acc.get('is_active', 1),
                    acc.get('is_default', 0), acc.get('created_at'), acc.get('updated_at')
                ))
                
                # new_id будет реально вставленным ID
                actual_id = cursor.lastrowid
                if old_id:
                    capital_id_map[old_id] = actual_id
            
            # Восстанавливаем бюджеты (используя новые ID категорий)
            for budget in data.get('budgets', []):
                old_category_id = budget.get('category_id')
                new_category_id = category_id_map.get(old_category_id, old_category_id)
                
                # Проверяем, существует ли категория
                if new_category_id:
                    cursor.execute("""
                        INSERT INTO budgets (category_id, amount, period)
                        VALUES (?, ?, ?)
                    """, (
                        new_category_id,
                        budget.get('amount', 0),
                        budget.get('period', 'monthly')
                    ))
            
            # Восстанавливаем транзакции
            for trans in data.get('transactions', []):
                cursor.execute("""
                    INSERT INTO transactions (type, category, amount, comment, date, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    trans.get('type'), trans.get('category'),
                    trans.get('amount'), trans.get('comment', ''),
                    trans.get('date'), trans.get('created_at')
                ))
            
            # Восстанавливаем переводы (используя новые ID счетов)
            for transfer in data.get('transfers', []):
                from_id = transfer.get('from_account_id')
                to_id = transfer.get('to_account_id')
                
                # Маппинг ID для счетов капитала
                if from_id in capital_id_map:
                    from_id = capital_id_map[from_id]
                if to_id in capital_id_map:
                    to_id = capital_id_map[to_id]
                
                cursor.execute("""
                    INSERT INTO transfers (from_account_id, to_account_id, amount, date, comment, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    from_id, to_id,
                    transfer.get('amount'), transfer.get('date'),
                    transfer.get('comment', ''), 1,  # is_active = 1
                    transfer.get('created_at')
                ))
            
            # Включаем проверку внешних ключей обратно
            cursor.execute("PRAGMA foreign_keys = ON")
            
            conn.commit()
            
            # Синхронизируем счета
            core.sync_accounts_with_transactions()
            
            conn.close()
            
            # Обновляем информацию
            self.load_info()
            
            # Уведомляем слушателей
            self.transaction_service.notify_listeners()
            
            # Обновляем главное окно
            if hasattr(root, 'update_balance'):
                root.update_balance()
            
            root.set_status(f"✅ Импорт завершён! Загружено {len(data.get('transactions', []))} транзакций", True)
            messagebox.showinfo("Импорт завершён", 
                f"Данные восстановлены из:\n{filename}\n\n"
                f"Загружено:\n"
                f"• Транзакций: {len(data.get('transactions', []))}\n"
                f"• Категорий: {len(data.get('categories', []))}\n"
                f"• Счетов капитала: {len(data.get('capital_accounts', []))}\n"
                f"• Бюджетов: {len(data.get('budgets', []))}")
            
            app_logger.info(f"Импорт данных: {filename}, {len(data.get('transactions', []))} транзакций")
            
        except Exception as e:
            app_logger.error(f"Ошибка импорта: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось импортировать данные:\n{e}")
    
    def reset_to_factory(self):
        """Сброс до заводских настроек"""
        import sys
        import subprocess
        
        # Подтверждение
        result = messagebox.askyesno(
            "⚠️ СБРОС ДО ЗАВОДСКИХ НАСТРОЕК",
            "ВНИМАНИЕ! Это действие удалит ВСЕ данные:\n"
            "• Все транзакции\n"
            "• Все категории (кроме стандартных)\n"
            "• Все бюджеты\n"
            "• Все счета капитала\n\n"
            "Перед сбросом будет создана резервная копия.\n\n"
            "После сброса у вас не будет счетов капитала.\n"
            "Вы сможете добавить их самостоятельно во вкладке 'Капитал'.\n\n"
            "Продолжить?"
        )
        
        if not result:
            return
        
        # Второе подтверждение
        result2 = messagebox.askyesno(
            "🔴 ПОСЛЕДНЕЕ ПРЕДУПРЕЖДЕНИЕ",
            "Это действие НЕОБРАТИМО!\n\n"
            "Все данные будут безвозвратно удалены.\n\n"
            "Вы действительно хотите сбросить всё до заводских настроек?",
            icon='warning'
        )
        
        if not result2:
            return
        
        root = self.winfo_toplevel()
        root.set_status("🔄 Создание резервной копии...", True)
        
        # Создаём резервную копию
        from utils.backup import DatabaseBackup
        try:
            backup = DatabaseBackup()
            backup.create_backup(reason="factory_reset")
            app_logger.info("Создана резервная копия перед сбросом")
        except Exception as e:
            app_logger.error(f"Ошибка создания бэкапа: {e}")
        
        root.set_status("🔄 Выполняется сброс...", True)
        
        try:
            # Выполняем сброс (удаляет БД и создаёт новую)
            core.reset_to_factory()
            
            root.set_status("✅ Сброс выполнен! Перезапуск приложения...", True)
            
            # Закрываем и перезапускаем
            root.quit()
            root.destroy()
            subprocess.Popen([sys.executable, "run.py"])
            sys.exit(0)
            
        except Exception as e:
            app_logger.error(f"Ошибка сброса: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось выполнить сброс:\n{e}")
            root.set_status("❌ Ошибка сброса", False)
    
    def refresh(self):
        """Обновляет данные на вкладке"""
        self.load_info()