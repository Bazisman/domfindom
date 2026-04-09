# views/categories_view.py
import customtkinter as ctk
from tkinter import messagebox, colorchooser
from services.category_service import CategoryService

class CategoriesView(ctk.CTkFrame):
    """Вкладка управления категориями"""
    
    def __init__(self, master, transaction_service, category_service):
        super().__init__(master)
        
        self.transaction_service = transaction_service
        self.category_service = category_service
        self.category_service.add_listener(self.request_refresh_data)

        # Параметры пагинации
        self.current_page = 0
        self.page_size = 20
        self.has_more = True
        self.all_categories = []
        self.filtered_categories = []
        self.current_filter = "active"
        self._loading = False
        self._last_render_signature = None
        self._refresh_job = None
        self._row_widgets = []
        self._empty_label = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Создаёт интерфейс"""
        
        # Заголовок
        title_label = ctk.CTkLabel(
            self,
            text="📁 Управление категориями",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=20)
        
        # Панель добавления
        add_frame = ctk.CTkFrame(self)
        add_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(add_frame, text="Название:").grid(row=0, column=0, padx=5, pady=10)
        self.name_entry = ctk.CTkEntry(add_frame, width=200)
        self.name_entry.grid(row=0, column=1, padx=5, pady=10)
        
        ctk.CTkLabel(add_frame, text="Тип:").grid(row=0, column=2, padx=5, pady=10)
        self.type_combo = ctk.CTkComboBox(
            add_frame,
            values=["Доход", "Расход", "И то и другое"],
            width=150
        )
        self.type_combo.set("И то и другое")
        self.type_combo.grid(row=0, column=3, padx=5, pady=10)
        
        ctk.CTkLabel(add_frame, text="Иконка:").grid(row=0, column=4, padx=5, pady=10)
        self.icon_entry = ctk.CTkEntry(add_frame, width=50)
        self.icon_entry.insert(0, "📁")
        self.icon_entry.grid(row=0, column=5, padx=5, pady=10)
        
        self.color_btn = ctk.CTkButton(
            add_frame,
            text="🎨 Цвет",
            width=80,
            command=self.choose_color
        )
        self.color_btn.grid(row=0, column=6, padx=5, pady=10)
        self.selected_color = "#808080"
        
        add_btn = ctk.CTkButton(
            add_frame,
            text="➕ Добавить",
            command=self.add_category,
            width=100,
            fg_color="#2e7d32"
        )
        add_btn.grid(row=0, column=7, padx=20, pady=10)

        # Enter для добавления категории
        self.name_entry.bind("<Return>", lambda e: self.add_category())
        self.icon_entry.bind("<Return>", lambda e: self.add_category())

        # Панель фильтрации
        filter_frame = ctk.CTkFrame(self)
        filter_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(filter_frame, text="Показать:").pack(side="left", padx=5)

        self.filter_var = ctk.StringVar(value="✅ Активные")
        self.filter_combo = ctk.CTkComboBox(
            filter_frame,
            values=["✅ Активные", "❌ Неактивные", "📋 Все"],
            variable=self.filter_var,
            width=150,
            command=self.on_filter_change
        )
        self.filter_combo.pack(side="left", padx=5)
        
        # Счётчик категорий
        self.count_label = ctk.CTkLabel(
            filter_frame,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.count_label.pack(side="right", padx=10)
        
        # Таблица категорий
        list_frame = ctk.CTkFrame(self)
        list_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Заголовки
        headers_frame = ctk.CTkFrame(list_frame)
        headers_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(headers_frame, text="Иконка", width=60).pack(side="left", padx=5)
        ctk.CTkLabel(headers_frame, text="Название", width=150).pack(side="left", padx=5)
        ctk.CTkLabel(headers_frame, text="Тип", width=120).pack(side="left", padx=5)
        ctk.CTkLabel(headers_frame, text="Цвет", width=60).pack(side="left", padx=5)
        ctk.CTkLabel(headers_frame, text="Статус", width=80).pack(side="left", padx=5)
        ctk.CTkLabel(headers_frame, text="Действия", width=150).pack(side="left", padx=5)
        
        # Контейнер для списка категорий
        self.categories_frame = ctk.CTkScrollableFrame(list_frame)
        self.categories_frame.pack(fill="both", expand=True, padx=10, pady=5)
        # Привязываем событие прокрутки для ленивой загрузки
        self.categories_frame._parent_canvas.bind("<MouseWheel>", self.on_scroll)
    
        # Загружаем данные
        self.refresh_data()
    
    def choose_color(self):
        """Выбор цвета"""
        color = colorchooser.askcolor(title="Выберите цвет", initialcolor=self.selected_color)
        if color and color[1]:
            self.selected_color = color[1]
            self.color_btn.configure(fg_color=self.selected_color)
    
    def on_filter_change(self, choice):
        """При изменении фильтра"""
        filter_map = {
            "✅ Активные": "active",
            "❌ Неактивные": "inactive",
            "📋 Все": "all"
        }
        self.current_filter = filter_map.get(choice, "active")
        self._rebuild_categories_list(reset_page=True)
    
    def on_scroll(self, event):
        """При прокрутке - подгружаем новые категории"""
        # Проверяем, не доскроллили ли до конца
        canvas = self.categories_frame._parent_canvas
        if canvas.yview()[1] == 1.0 and self.has_more and not self._loading:
            self.load_more()
    
    def load_more(self):
        """Подгружает следующую страницу категорий"""
        if self._loading:
            return
        self._loading = True
        self.current_page += 1
        self.display_categories()
        self._loading = False
        
    def add_category(self):
        """Добавляет новую категорию"""
        name = self.name_entry.get().strip()
        if not name:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("❌ Введите название категории", False)
            return
        
        # Проверяем, существует ли уже такая категория (включая неактивные)
        existing = self.category_service.get_category_by_name(name)
        
        if existing:
            if not existing.is_active:
                # Категория существует, но неактивна - предлагаем восстановить
                if messagebox.askyesno(
                    "Категория существует",
                    f"Категория '{name}' уже существует, но деактивирована.\nВосстановить её?"
                ):
                    self.category_service.update_category(existing.id, is_active=1)
                    root = self.winfo_toplevel()
                    if hasattr(root, 'set_status'):
                        root.set_status(f"✅ Категория '{name}' восстановлена", True)
            else:
                # Категория активна - просто сообщаем
                root = self.winfo_toplevel()
                if hasattr(root, 'set_status'):
                    root.set_status(f"❌ Категория '{name}' уже существует", False)
            return
        
        # Если категории нет - создаём новую
        type_map = {
            "Доход": "income",
            "Расход": "expense",
            "И то и другое": "both"
        }
        category_type = type_map.get(self.type_combo.get(), "both")
        icon = self.icon_entry.get().strip() or "📁"
        
        category_id = self.category_service.add_category(
            name,
            category_type,
            color=self.selected_color,
            icon=icon
        )
        if category_id:
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status(f"✅ Категория '{name}' добавлена", True)
            
            # Очищаем поля
            self.name_entry.delete(0, "end")
            self.icon_entry.delete(0, "end")
            self.icon_entry.insert(0, "📁")
            self.selected_color = "#808080"
            self.color_btn.configure(fg_color="#808080")
    
    def refresh(self):
        """Совместимый alias для полного обновления данных"""
        self.request_refresh_data()

    def request_refresh_data(self):
        """Планирует обновление данных, склеивая быстрые уведомления сервиса"""
        if not self.winfo_exists():
            return

        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass

        self._refresh_job = self.after(60, self.refresh_data)

    def refresh_data(self):
        """Полностью обновляет данные категорий из сервиса"""
        self._refresh_job = None
        if not self.winfo_exists() or self._loading:
            return
        
        self._loading = True
        
        try:
            self.all_categories = self.category_service.get_all_categories()
            self._rebuild_categories_list(reset_page=True)
        finally:
            self._loading = False

    def _update_count_label(self):
        """Обновляет счётчик категорий над списком"""
        filter_names = {
            "active": "активных",
            "inactive": "неактивных",
            "all": "всех"
        }
        filter_name = filter_names.get(self.current_filter, "активных")
        self.count_label.configure(
            text=f"Всего: {len(self.filtered_categories)} {filter_name}"
        )

    def _hide_unused_rows(self, visible_count):
        """Скрывает лишние строки, которые сейчас не должны быть видны"""
        for row_data in self._row_widgets[visible_count:]:
            if row_data["row"].winfo_manager():
                row_data["row"].pack_forget()

    def _show_empty_state(self):
        """Показывает пустое состояние, не создавая его повторно"""
        self._hide_unused_rows(0)
        if self._empty_label is None or not self._empty_label.winfo_exists():
            self._empty_label = ctk.CTkLabel(
                self.categories_frame,
                text="📭 Нет категорий для отображения",
                font=ctk.CTkFont(size=14)
            )
        if not self._empty_label.winfo_manager():
            self._empty_label.pack(pady=50)

    def _hide_empty_state(self):
        """Скрывает пустое состояние, если список не пустой"""
        if self._empty_label is not None and self._empty_label.winfo_exists() and self._empty_label.winfo_manager():
            self._empty_label.pack_forget()

    def _create_category_row_widgets(self):
        """Создаёт набор виджетов строки категории для переиспользования"""
        row = ctk.CTkFrame(self.categories_frame)

        icon_label = ctk.CTkLabel(row, text="", width=60, font=ctk.CTkFont(size=16))
        icon_label.pack(side="left", padx=5)

        name_label = ctk.CTkLabel(row, text="", width=150, anchor="w")
        name_label.pack(side="left", padx=5)

        type_label = ctk.CTkLabel(row, text="", width=120)
        type_label.pack(side="left", padx=5)

        color_box = ctk.CTkFrame(row, width=20, height=20, corner_radius=3)
        color_box.pack(side="left", padx=5)
        color_box.pack_propagate(False)

        status_label = ctk.CTkLabel(row, text="", width=80)
        status_label.pack(side="left", padx=5)

        actions_frame = ctk.CTkFrame(row, fg_color="transparent")
        actions_frame.pack(side="left", padx=5)

        return {
            "row": row,
            "icon_label": icon_label,
            "name_label": name_label,
            "type_label": type_label,
            "color_box": color_box,
            "status_label": status_label,
            "actions_frame": actions_frame,
        }

    def _get_render_signature(self):
        """Возвращает сигнатуру текущего видимого списка для защиты от лишнего redraw"""
        visible_ids = tuple(
            category.id for category in self.filtered_categories[:self.page_size]
        )
        return (self.current_filter, len(self.filtered_categories), visible_ids)

    def _scroll_list_to_top(self):
        """Возвращает список категорий к началу после полного reset"""
        try:
            self.categories_frame._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    def _rebuild_categories_list(self, reset_page=True):
        """Перестраивает список из уже загруженных данных"""
        if not self.winfo_exists():
            return

        self.apply_filter()
        self._update_count_label()

        if reset_page:
            signature = self._get_render_signature()
            if signature == self._last_render_signature:
                self.current_page = 0
                self.has_more = len(self.filtered_categories) > self.page_size
                self._scroll_list_to_top()
                return
            self.current_page = 0
            self.has_more = True

        self.display_categories()
        if reset_page:
            self._scroll_list_to_top()
    
    def _render_category_row(self, index, category):
        """Обновляет или создаёт строку категории на нужной позиции"""
        while len(self._row_widgets) <= index:
            self._row_widgets.append(self._create_category_row_widgets())

        row_data = self._row_widgets[index]
        row = row_data["row"]
        if not row.winfo_manager():
            row.pack(fill="x", pady=2)

        row_data["icon_label"].configure(text=category.icon)
        row_data["name_label"].configure(text=category.name)

        type_map = {
            "income": "💰 Доход",
            "expense": "💸 Расход", 
            "both": "🔄 Оба"
        }
        row_data["type_label"].configure(text=type_map.get(category.type, category.type))
        row_data["color_box"].configure(fg_color=category.color)

        status_text = "✅ Активна" if category.is_active else "❌ Неактивна"
        row_data["status_label"].configure(text=status_text)

        actions_frame = row_data["actions_frame"]
        for widget in actions_frame.winfo_children():
            widget.destroy()
        
        if category.is_active:
            edit_btn = ctk.CTkButton(
                actions_frame,
                text="✏️",
                width=30,
                command=lambda c=category: self.edit_category(c)
            )
            edit_btn.pack(side="left", padx=2)
            
            delete_btn = ctk.CTkButton(
                actions_frame,
                text="🗑️",
                width=30,
                fg_color="#f44336",
                hover_color="#d32f2f",
                command=lambda c=category: self.delete_category(c)
            )
            delete_btn.pack(side="left", padx=2)
        else:
            restore_btn = ctk.CTkButton(
                actions_frame,
                text="↩️ Восстановить",
                width=80,
                fg_color="#4caf50",
                command=lambda c=category: self.restore_category(c)
            )
            restore_btn.pack(side="left", padx=2)
    
    def edit_category(self, category):
        """Редактирование категории"""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"✏️ Редактирование: {category.name}")
        dialog.geometry("450x400")
        dialog.grab_set()
        
        # Заголовок
        ctk.CTkLabel(
            dialog,
            text=f"Редактирование категории",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        
        # Форма
        frame = ctk.CTkFrame(dialog)
        frame.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Название
        ctk.CTkLabel(frame, text="Название:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        name_entry = ctk.CTkEntry(frame, width=200)
        name_entry.insert(0, category.name)
        name_entry.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        # Тип категории
        ctk.CTkLabel(frame, text="Тип:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        
        # Определяем текущий тип для отображения
        type_map_display = {
            "income": "💰 Доход",
            "expense": "💸 Расход",
            "both": "🔄 И то и другое"
        }
        
        type_combo = ctk.CTkComboBox(
            frame,
            values=["💰 Доход", "💸 Расход", "🔄 И то и другое"],
            width=200
        )
        type_combo.set(type_map_display.get(category.type, "🔄 И то и другое"))
        type_combo.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        
        # Иконка
        ctk.CTkLabel(frame, text="Иконка:").grid(row=2, column=0, padx=10, pady=10, sticky="e")
        icon_entry = ctk.CTkEntry(frame, width=50)
        icon_entry.insert(0, category.icon)
        icon_entry.grid(row=2, column=1, padx=10, pady=10, sticky="w")
        
        # Цвет
        ctk.CTkLabel(frame, text="Цвет:").grid(row=3, column=0, padx=10, pady=10, sticky="e")
        
        color_frame = ctk.CTkFrame(frame)
        color_frame.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        
        color_box = ctk.CTkFrame(color_frame, width=30, height=30, fg_color=category.color, corner_radius=5)
        color_box.pack(side="left", padx=5)
        color_box.pack_propagate(False)
        
        color_btn = ctk.CTkButton(
            color_frame,
            text="Выбрать цвет",
            width=100,
            command=lambda: self._choose_edit_color(color_box)
        )
        color_btn.pack(side="left", padx=5)
        
        # Сохраняем выбранный цвет
        self.edit_selected_color = category.color
        
        def save():
            new_name = name_entry.get().strip()
            new_icon = icon_entry.get().strip()
            
            # Преобразуем выбранный тип обратно в значение для БД
            type_map_reverse = {
                "💰 Доход": "income",
                "💸 Расход": "expense",
                "🔄 И то и другое": "both"
            }
            new_type = type_map_reverse.get(type_combo.get(), "both")
            
            updates = {}

            if new_name and new_name != category.name:
                updates["name"] = new_name

            if new_type != category.type:
                updates["type"] = new_type

            if new_icon and new_icon != category.icon:
                updates["icon"] = new_icon

            if hasattr(self, 'edit_selected_color') and self.edit_selected_color != category.color:
                updates["color"] = self.edit_selected_color

            if updates:
                self.category_service.update_category(category.id, **updates)
            
            dialog.destroy()
            
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status("✅ Категория обновлена", True)
        
        # Кнопки
        btn_frame = ctk.CTkFrame(dialog)
        btn_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkButton(
            btn_frame,
            text="💾 Сохранить",
            command=save,
            width=100,
            fg_color="#2e7d32"
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            btn_frame,
            text="❌ Отмена",
            command=dialog.destroy,
            width=100,
            fg_color="#f44336",
            hover_color="#d32f2f"
        ).pack(side="right", padx=10)
    
    def _choose_edit_color(self, color_box):
        """Выбор цвета в режиме редактирования"""
        color = colorchooser.askcolor(title="Выберите цвет", initialcolor=self.edit_selected_color)
        if color and color[1]:
            self.edit_selected_color = color[1]
            color_box.configure(fg_color=self.edit_selected_color)

    def apply_filter(self):
        """Применяет фильтр к списку категорий"""
        if self.current_filter == "active":
            self.filtered_categories = [c for c in self.all_categories if c.is_active]
        elif self.current_filter == "inactive":
            self.filtered_categories = [c for c in self.all_categories if not c.is_active]
        else:  # all
            self.filtered_categories = self.all_categories.copy()
    
    def display_categories(self):
        """Отображает текущую страницу категорий"""
        start = self.current_page * self.page_size
        end = start + self.page_size
        
        categories_to_show = self.filtered_categories[start:end]
        
        if not categories_to_show:
            self.has_more = False
            if start == 0:  # Если вообще нет категорий
                self._show_empty_state()
            return
        
        self._hide_empty_state()
        
        # Проверяем, есть ли ещё категории
        self.has_more = end < len(self.filtered_categories)
        if start == 0:
            self._last_render_signature = self._get_render_signature()
        
        # Добавляем категории
        for index, cat in enumerate(categories_to_show, start=start):
            self._render_category_row(index, cat)

        self._hide_unused_rows(min(end, len(self.filtered_categories)))

    def delete_category(self, category):
        """Удаляет категорию (деактивирует)"""
        if messagebox.askyesno("Подтверждение", f"Деактивировать категорию '{category.name}'?"):
            self.category_service.delete_category(category.id)
            
            root = self.winfo_toplevel()
            if hasattr(root, 'set_status'):
                root.set_status(f"✅ Категория '{category.name}' деактивирована", True)
    
    def restore_category(self, category):
        """Восстанавливает категорию"""
        self.category_service.update_category(category.id, is_active=1)
        
        root = self.winfo_toplevel()
        if hasattr(root, 'set_status'):
            root.set_status(f"✅ Категория '{category.name}' восстановлена", True)
