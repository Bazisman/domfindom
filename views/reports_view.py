# views/reports_view.py
import customtkinter as ctk
from services.transaction_service import TransactionService
from services.category_service import CategoryService
from datetime import datetime, timedelta

class ReportsView(ctk.CTkFrame):
    """Вкладка с отчётами"""
    
    def __init__(self, master, transaction_service, category_service):
        super().__init__(master)
        
        self.transaction_service = transaction_service
        self.category_service = category_service
        
        self.setup_ui()
        self.refresh()
    
    def setup_ui(self):
        """Создаёт интерфейс вкладки"""
        
        # Заголовок
        title_label = ctk.CTkLabel(
            self,
            text="📊 Отчёты по категориям",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=20)
        
        # Панель выбора периода
        period_frame = ctk.CTkFrame(self)
        period_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(period_frame, text="Период:").pack(side="left", padx=10)
        
        self.period_var = ctk.StringVar(value="Текущий месяц")
        self.period_combo = ctk.CTkComboBox(
            period_frame,
            values=["Текущий месяц", "Прошлый месяц", "Текущий год", "Всё время"],
            variable=self.period_var,
            width=150,
            command=self.on_period_change
        )
        self.period_combo.pack(side="left", padx=10)
        
        # Контейнер для отчёта
        self.report_frame = ctk.CTkFrame(self)
        self.report_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Текстовое поле для отчёта
        self.report_text = ctk.CTkTextbox(self.report_frame, font=ctk.CTkFont(size=12))
        self.report_text.pack(fill="both", expand=True, padx=10, pady=10)
    
    def on_period_change(self, choice):
        """При смене периода - сразу генерируем отчёт"""
        self.generate_report()
    
    def generate_report(self):
        """Генерирует отчёт"""
        self.report_text.delete("0.0", "end")
        self.report_text.insert("0.0", "⏳ Загрузка...")
        self.update()
        
        # Получаем даты периода
        start_date, end_date = self.get_period_dates()
        
        # Получаем расходы по категориям
        expenses = self.transaction_service.get_expenses_by_category(start_date, end_date)
        
        self.report_text.delete("0.0", "end")
        
        if not expenses:
            self.report_text.insert("0.0", "📭 Нет данных за выбранный период")
            return
        
        period_name = self.period_var.get()
        
        text = f"📊 ОТЧЁТ ПО РАСХОДАМ\n"
        text += f"Период: {period_name}\n"
        text += "=" * 50 + "\n\n"
        
        total = 0
        for cat in expenses:
            amount = cat['total']
            total += amount
            text += f"{cat['category']:<30} {amount:>12.2f} ₽\n"
        
        text += "=" * 50 + "\n"
        text += f"{'ИТОГО':<30} {total:>12.2f} ₽\n"
        
        self.report_text.insert("0.0", text)
    
    def get_period_dates(self):
        """Возвращает даты начала и конца периода"""
        today = datetime.now()
        period = self.period_var.get()
        
        if period == "Текущий месяц":
            start = today.replace(day=1).strftime("%Y-%m-%d")
            end = today.strftime("%Y-%m-%d")
            return start, end
        
        elif period == "Прошлый месяц":
            if today.month == 1:
                start = today.replace(year=today.year-1, month=12, day=1)
                end = today.replace(year=today.year-1, month=12, day=31)
            else:
                start = today.replace(month=today.month-1, day=1)
                end = today.replace(day=1) - timedelta(days=1)
            return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        
        elif period == "Текущий год":
            start = today.replace(month=1, day=1).strftime("%Y-%m-%d")
            end = today.strftime("%Y-%m-%d")
            return start, end
        
        else:  # Всё время
            return None, None
    
    def refresh(self):
        """Обновляет данные"""
        self.generate_report()