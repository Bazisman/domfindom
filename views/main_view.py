# views/main_view.py
import customtkinter as ctk
from views.transactions_view import TransactionsView
from views.reports_view import ReportsView
from views.categories_view import CategoriesView
from services.transaction_service import TransactionService
from services.category_service import CategoryService
from typing import Optional, Type, Dict
from views.capital_view import CapitalView
from views.settings_view import SettingsView
from views.planning_view import PlanningView
from utils.logger import app_logger
import core
from datetime import datetime

class MainView(ctk.CTk):
    """Главное окно приложения с навигацией"""
    
    def __init__(self):
        super().__init__()
        
        # Настройки окна
        self.title("💰 Домашняя бухгалтерия")
        self.geometry("1300x800")
        self.minsize(1100, 600)
        
        # Сервисы
        self.transaction_service = TransactionService()
        self.category_service = CategoryService()
        
        # 🔥 Подписываемся на изменения транзакций
        self.transaction_service.add_listener(self.on_transactions_changed)
        
        # Настройка темы
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        
        # Текущая вкладка
        self.current_view: Optional[ctk.CTkFrame] = None
        
        # Кэш вкладок для быстрого переключения
        self._view_cache: Dict[str, ctk.CTkFrame] = {}
        
        # Создаём интерфейс
        self.setup_ui()
        
        # Загружаем данные
        self.after(100, self.load_initial_data)
    
    def setup_ui(self):
        """Создаёт интерфейс главного окна"""
        
        # === Верхняя панель с балансом ===
        self.setup_top_panel()
        
        # === Панель навигации (вкладки) ===
        self.setup_navigation()
        
        # === Контейнер для содержимого ===
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # === Строка статуса ===
        self.status_frame = ctk.CTkFrame(self, height=30, corner_radius=0)
        self.status_frame.pack(fill="x", side="bottom")
        self.status_frame.pack_propagate(False)
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="✅ Готов к работе",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.status_label.pack(side="left", padx=10, pady=5)
        
        # Debounce job для resize
        self._resize_job = None
        self._gradient_job = None
        self._last_gradient_width = 0
        self.bind("<Configure>", self._on_resize)
        
        # Показываем вкладку по умолчанию
        self.switch_tab(TransactionsView, "operations")
    
    def _on_resize(self, event):
        """Обработчик resize с debounce"""
        if event.widget is not self:
            return

        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self.draw_gradient)
    
    def setup_top_panel(self):
        """Создаёт верхнюю панель с балансом"""
        self.top_frame = ctk.CTkFrame(self, height=140, corner_radius=0)
        self.top_frame.pack(fill="x")
        self.top_frame.pack_propagate(False)
        
        # Градиентный фон через Canvas
        self.canvas = ctk.CTkCanvas(
            self.top_frame,
            height=140,
            highlightthickness=0,
            bg=ctk.ThemeManager.theme["CTkFrame"]["fg_color"][1]
        )
        self.canvas.pack(fill="both", expand=True)
        
        # Рисуем градиент
        self.draw_gradient()
        
        # Баланс по центру (реальный)
        self.balance_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.balance_frame.place(relx=0.35, rely=0.5, anchor="center")
        
        # Заголовок "Реальный баланс"
        ctk.CTkLabel(
            self.balance_frame,
            text="💵 Реальный баланс",
            font=ctk.CTkFont(size=12),
            text_color="#b0bec5"
        ).pack()
        
        # Индикатор загрузки
        self.loading_label = ctk.CTkLabel(
            self.balance_frame,
            text="⏳ Загрузка...",
            font=ctk.CTkFont(size=14),
            text_color="white"
        )
        self.loading_label.pack()
        
        # Баланс (изначально пустой)
        self.balance_label = ctk.CTkLabel(
            self.balance_frame,
            text="",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color="white"
        )
        self.balance_label.pack()
        
        self.balance_detail_label = ctk.CTkLabel(
            self.balance_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="white"
        )
        self.balance_detail_label.pack()
    
        # Месяц и год
        self.month_capital_label = ctk.CTkLabel(
            self.balance_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#b0bec5"
        )
        self.month_capital_label.pack(pady=(5, 0))
        
        # === БАЛАНС ПЛАНИРОВАНИЯ (справа) ===
        self.planning_balance_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.planning_balance_frame.place(relx=0.65, rely=0.5, anchor="center")
        
        # Заголовок "Баланс на конец месяца"
        ctk.CTkLabel(
            self.planning_balance_frame,
            text="📅 Баланс на конец месяца",
            font=ctk.CTkFont(size=12),
            text_color="#ff9800"
        ).pack()
        
        # Прогнозируемый баланс
        self.planning_balance_label = ctk.CTkLabel(
            self.planning_balance_frame,
            text="",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#ff9800"
        )
        self.planning_balance_label.pack()
        
    def update_last_reconciliation_label(self):
        """Обновляет метку последней сверки - для совместимости"""
        pass  # Метка теперь в transactions_view
    
    def draw_gradient(self):
        """Рисует градиент на Canvas (с debounce)"""
        try:
            width = self.top_frame.winfo_width()
            if width < 10:  # Если окно ещё не отрисовано
                self.after(100, self.draw_gradient)
                return

            if width == self._last_gradient_width:
                self._resize_job = None
                return
            
            # Debounce — не перерисовываем при каждом пикселе
            if self._gradient_job:
                self.after_cancel(self._gradient_job)
            
            self._gradient_job = self.after(80, lambda: self._do_draw_gradient(width))
            self._resize_job = None
        except Exception:
            pass
    
    def _do_draw_gradient(self, width):
        """Выполняет отрисовку градиента"""
        try:
            self.canvas.delete("gradient")
            
            # Цвета градиента
            colors = ["#2e7d32", "#1e5a23", "#0e3a17"]
            
            # Рисуем полосы градиента
            for i, color in enumerate(colors):
                y1 = i * 140 // len(colors)
                y2 = (i + 1) * 140 // len(colors)
                self.canvas.create_rectangle(
                    0, y1, width, y2,
                    fill=color,
                    outline="",
                    tags="gradient"
                )
            self._last_gradient_width = width
            self._gradient_job = None
        except Exception:
            pass
    
    def setup_navigation(self):
        """Создаёт панель навигации"""
        self.nav_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.nav_frame.pack(fill="x", pady=(0, 10))
        self.nav_frame.pack_propagate(False)
        
        # Определяем вкладки
        self.tabs = [
            {
                "id": "operations",
                "title": "📋 Операции",
                "view": TransactionsView,
            },
            {
                "id": "reports",
                "title": "📊 Отчёты",
                "view": ReportsView,
            },
            {
                "id": "planning",
                "title": "📅 Планирование бюджетов",
                "view": PlanningView,
            },
            {
                "id": "capital",
                "title": "💰 Капитал",
                "view": CapitalView,
            },
            {
                "id": "categories",
                "title": "📁 Категории",
                "view": CategoriesView,
            },
            {
                "id": "settings",
                "title": "⚙️ Настройки",
                "view": SettingsView,
            }
        ]
        
        # Создаём кнопки вкладок
        self.tab_buttons = []
        
        for i, tab in enumerate(self.tabs):
            btn = ctk.CTkButton(
                self.nav_frame,
                text=tab['title'],
                command=lambda t=tab: self.switch_tab(t['view'], t['id']),
                fg_color="transparent" if i != 0 else ("gray70", "gray30"),
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                anchor="center",
                width=140,
                height=40,
                corner_radius=20
            )
            btn.pack(side="left", padx=2, pady=5)
            self.tab_buttons.append(btn)
            
    def switch_tab(self, view_class: Optional[Type], tab_id: str):
        """Переключает вкладку с использованием кэша"""
        
        # Обновляем стиль кнопок
        for btn, tab in zip(self.tab_buttons, self.tabs):
            if tab['id'] == tab_id:
                btn.configure(fg_color=("gray70", "gray30"))
            else:
                btn.configure(fg_color="transparent")
        
        # Скрываем текущую вкладку (не уничтожаем!)
        if self.current_view:
            self.current_view.pack_forget()
        
        # Проверяем, есть ли вкладка в кэше
        if tab_id in self._view_cache:
            # Вкладка уже есть — показываем из кэша
            self.current_view = self._view_cache[tab_id]
            self.current_view.pack(fill="both", expand=True)
            
            # Обновляем данные при показе
            if hasattr(self.current_view, 'refresh'):
                try:
                    self.current_view.refresh()
                except Exception as e:
                    app_logger.debug(f"Ошибка обновления вкладки: {e}")
        else:
        # Создаём новую вкладку
            if view_class:
                try:
                    self.current_view = view_class(
                        self.content_frame, 
                        self.transaction_service,
                        self.category_service
                    )
                    self.current_view.pack(fill="both", expand=True)
                    
                    # Сохраняем в кэш
                    self._view_cache[tab_id] = self.current_view
                except Exception as e:
                    app_logger.error(f"Ошибка создания вкладки {tab_id}: {e}", exc_info=True)
                    self.show_placeholder(tab_id)
            else:
                self.show_placeholder(tab_id)
    
    def show_placeholder(self, tab_id: str):
        """Показывает заглушку для нереализованных вкладок"""
        placeholder = ctk.CTkFrame(self.content_frame)
        placeholder.pack(fill="both", expand=True)
        
        # Находим название вкладки
        tab_title = next((t['title'] for t in self.tabs if t['id'] == tab_id), "Вкладка")
        
        ctk.CTkLabel(
            placeholder,
            text=f"🚧 {tab_title}\n\nВ разработке",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(expand=True)
        
        self.current_view = placeholder
    
    def update_balance(self):
        """Обновляет отображение баланса"""
        try:
            from datetime import datetime
            
            balance = self.transaction_service.get_balance()
            
            # Получаем статистику за текущий месяц
            now = datetime.now()
            monthly = self.transaction_service.get_monthly_stats(now.year, now.month)
            
            # Название месяца
            month_names = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                          'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
            month_name = month_names[now.month - 1]
            
            # Скрываем индикатор загрузки
            if hasattr(self, 'loading_label') and self.loading_label.winfo_exists():
                self.loading_label.pack_forget()
            
            # Показываем месяц и год
            self.month_capital_label.configure(
                text=f"{month_name} {now.year}"
            )
            
            # Показываем баланс основного счёта
            self.balance_label.configure(
                text=f"{balance.main_balance:,.2f} ₽".replace(",", " "),
                text_color=balance.color
            )
            
            # Показываем статистику за месяц
            self.balance_detail_label.configure(
                text=f"Доход: {monthly['income']:,.0f} ₽ | Расход: {monthly['expense']:,.0f} ₽ | Вклад: {monthly['capital']:,.0f} ₽".replace(",", " ")
            )
            
            # === ОБНОВЛЯЕМ БАЛАНС ПЛАНИРОВАНИЯ ===
            try:
                forecast = self.transaction_service.get_projected_balance()
                current_balance = forecast.get('current_balance', balance.main_balance)
                projected = forecast.get('projected_balance', current_balance)
                
                # Показываем прогнозируемый баланс
                color = "#4caf50" if projected >= 0 else "#f44336"
                self.planning_balance_label.configure(
                    text=f"{projected:,.0f} ₽".replace(",", " "),
                    text_color=color
                )
                
            except Exception as e:
                app_logger.debug(f"Ошибка получения прогноза: {e}")
                self.planning_balance_label.configure(text="—")
                
        except Exception as e:
            app_logger.error(f"Ошибка обновления баланса: {e}")
    
    def load_initial_data(self):
        """Загружает начальные данные"""
        # Запускаем обновление баланса
        self.update_balance()
        
        # Обновляем текущую вкладку
        if hasattr(self.current_view, 'refresh'):
            try:
                self.current_view.refresh()
            except Exception as e:
                app_logger.error(f"Ошибка обновления текущей вкладки при старте: {e}", exc_info=True)
    
    def on_transactions_changed(self):
        """Вызывается при изменении транзакций"""
        # Обновляем баланс
        self.update_balance()
        
        # Обновляем только активную вкладку (оптимизация)
        if hasattr(self, 'current_view') and hasattr(self.current_view, 'refresh'):
            try:
                self.current_view.refresh()
            except Exception as e:
                app_logger.debug(f"Ошибка обновления активной вкладки: {e}")
    
    def set_status(self, message, is_success=True):
        """Устанавливает сообщение в строке статуса"""
        self.status_label.configure(text=message)
        
        # Если нужно, можно менять цвет
        if is_success:
            self.status_label.configure(text_color=("green", "#4caf50"))
        else:
            self.status_label.configure(text_color=("red", "#f44336"))
        
        # Через 3 секунды возвращаем стандартное сообщение
        self.after(3000, lambda: self.status_label.configure(
            text="✅ Готов к работе",
            text_color=("gray10", "gray90")
        ))

