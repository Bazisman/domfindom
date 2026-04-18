# services/transaction_service.py
import core
from models import Transaction, Balance, Transfer
from typing import List, Optional, Callable, Any
from datetime import datetime, timedelta
import calendar
from utils.logger import app_logger


class TransactionService:
    """РЎРµСЂРІРёСЃ РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ С‚СЂР°РЅР·Р°РєС†РёСЏРјРё"""
    
    def __init__(self):
        self._listeners: List[Callable] = []
        self._auto_percent = 10
        self._auto_enabled = True
        app_logger.debug("TransactionService РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ")

    def sync_due_planned_transactions(self) -> int:
        """Автоматически исполняет просроченные плановые транзакции для web/API."""
        count = self.execute_planned_transactions()
        if count > 0:
            app_logger.info(f"Автосинхронизация исполнила {count} просроченных плановых транзакций")
        return count
    
    def set_auto_capital_settings(self, enabled: bool, percent: int):
        """Устанавливает настройки автоотчислений."""
        settings = core.set_auto_capital_settings(enabled, percent)
        self._auto_enabled = settings['enabled']
        self._auto_percent = settings['percent']
        app_logger.info(f"Настройки автоотчислений: enabled={enabled}, percent={percent}%")
    
    def add_listener(self, callback: Callable):
        """РџРѕРґРїРёСЃРєР° РЅР° РёР·РјРµРЅРµРЅРёСЏ РґР°РЅРЅС‹С…"""
        if callback not in self._listeners:
            self._listeners.append(callback)
            app_logger.debug(f"Р”РѕР±Р°РІР»РµРЅ СЃР»СѓС€Р°С‚РµР»СЊ: {getattr(callback, '__name__', 'lambda')}")
    
    def remove_listener(self, callback: Callable):
        """РћС‚РїРёСЃРєР° РѕС‚ РёР·РјРµРЅРµРЅРёР№"""
        if callback in self._listeners:
            self._listeners.remove(callback)
            app_logger.debug("РЎР»СѓС€Р°С‚РµР»СЊ СѓРґР°Р»С‘РЅ")
    
    def notify_listeners(self, update_all=False):
        """
        РЈРІРµРґРѕРјР»СЏРµС‚ РІСЃРµС… РїРѕРґРїРёСЃС‡РёРєРѕРІ РѕР± РёР·РјРµРЅРµРЅРёСЏС…
        
        Args:
            update_all: РµСЃР»Рё True - РѕР±РЅРѕРІР»СЏСЋС‚СЃСЏ РІСЃРµ РІРєР»Р°РґРєРё, РµСЃР»Рё False - С‚РѕР»СЊРєРѕ Р°РєС‚РёРІРЅР°СЏ
        """
        listeners = self._listeners.copy()
        
        # РџРѕР»СѓС‡Р°РµРј Р°РєС‚РёРІРЅСѓСЋ РІРєР»Р°РґРєСѓ РѕРґРёРЅ СЂР°Р·
        active_view = None
        root_ref = None
        
        for callback in listeners:
            try:
                if hasattr(callback, '__self__') and hasattr(callback.__self__, 'winfo_exists'):
                    if not callback.__self__.winfo_exists():
                        self.remove_listener(callback)
                        continue
                
                callback()
                
                # РЎРѕС…СЂР°РЅСЏРµРј root РґР»СЏ РґР°Р»СЊРЅРµР№С€РµРіРѕ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ
                if hasattr(callback, '__self__') and hasattr(callback.__self__, 'winfo_toplevel'):
                    if root_ref is None:
                        root_ref = callback.__self__.winfo_toplevel()
                        
                        # РћР±РЅРѕРІР»СЏРµРј Р±Р°Р»Р°РЅСЃ
                        if hasattr(root_ref, 'update_balance'):
                            root_ref.update_balance()
                        
                        # РџРѕР»СѓС‡Р°РµРј Р°РєС‚РёРІРЅСѓСЋ РІРєР»Р°РґРєСѓ
                        if hasattr(root_ref, 'current_view'):
                            active_view = root_ref.current_view
                
            except Exception as e:
                if "invalid command name" not in str(e) and "bad window path" not in str(e):
                    app_logger.error(f"РћС€РёР±РєР° РїСЂРё СѓРІРµРґРѕРјР»РµРЅРёРё СЃР»СѓС€Р°С‚РµР»СЏ: {e}", exc_info=True)
    
        # РћР±РЅРѕРІР»СЏРµРј С‚РѕР»СЊРєРѕ Р°РєС‚РёРІРЅСѓСЋ РІРєР»Р°РґРєСѓ (РґР»СЏ РѕРїС‚РёРјРёР·Р°С†РёРё)
        if root_ref and hasattr(root_ref, 'content_frame'):
            for child in root_ref.content_frame.winfo_children():
                if hasattr(child, 'refresh'):
                    # РћР±РЅРѕРІР»СЏРµРј С‚РѕР»СЊРєРѕ РµСЃР»Рё:
                    # 1. update_all=True (СЏРІРЅС‹Р№ Р·Р°РїСЂРѕСЃ РЅР° РѕР±РЅРѕРІР»РµРЅРёРµ РІСЃРµС…)
                    # 2. РР»Рё СЌС‚Рѕ Р°РєС‚РёРІРЅР°СЏ РІРєР»Р°РґРєР°
                    # 3. РР»Рё СЌС‚Рѕ РіР»Р°РІРЅРѕРµ РїСЂРµРґСЃС‚Р°РІР»РµРЅРёРµ (main_view)
                    should_refresh = update_all or (active_view is child) or (hasattr(child, '__class__') and 'MainView' in str(child.__class__))
                    
                    if should_refresh:
                        try:
                            child.refresh()
                        except Exception as ex:
                            app_logger.debug(f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ РІРєР»Р°РґРєРё: {ex}")
    
    def get_balance(self, force_update: bool = False) -> Balance:
        """Получает баланс основного счёта"""
        try:
            main_balance, income, expense = core.get_balance(force_update=force_update)
            return Balance(main_balance=main_balance or 0.0, income=income or 0.0, expense=expense or 0.0)
        except Exception as e:
            app_logger.error(f"Ошибка получения баланса: {e}", exc_info=True)
            return Balance()

    def get_transactions(self, limit: int = 100, period: str = "all", offset: int = 0) -> List[Transaction]:
        """РџРѕР»СѓС‡Р°РµС‚ СЃРїРёСЃРѕРє С‚СЂР°РЅР·Р°РєС†РёР№ СЃ РїРѕРґРґРµСЂР¶РєРѕР№ РїР°РіРёРЅР°С†РёРё"""
        try:
            # РћРіСЂР°РЅРёС‡РёРІР°РµРј РјР°РєСЃРёРјР°Р»СЊРЅРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ РґР»СЏ РїСЂРѕРёР·РІРѕРґРёС‚РµР»СЊРЅРѕСЃС‚Рё
            limit = min(limit, 500)
            
            today = datetime.now()
            
            if period == "month":
                start = today.replace(day=1).strftime("%Y-%m-%d")
                end = today.strftime("%Y-%m-%d")
                raw = core.get_transactions_by_period(start, end, limit)
            elif period == "last_month":
                if today.month == 1:
                    start = today.replace(year=today.year-1, month=12, day=1)
                    end = today.replace(year=today.year-1, month=12, day=31)
                else:
                    start = today.replace(month=today.month-1, day=1)
                    end = today.replace(day=1) - timedelta(days=1)
                raw = core.get_transactions_by_period(
                    start.strftime("%Y-%m-%d"), 
                    end.strftime("%Y-%m-%d"),
                    limit
                )
            elif period == "year":
                start = today.replace(month=1, day=1).strftime("%Y-%m-%d")
                end = today.strftime("%Y-%m-%d")
                raw = core.get_transactions_by_period(start, end, limit)
            else:  # all
                raw = core.get_last_transactions(limit, offset)
            
            result = []
            for row in raw:
                result.append(Transaction(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    amount=row['amount'],
                    comment=row['comment'],
                    date=row['date'],
                    status=row['status'] if 'status' in row.keys() else 'actual'
                ))
            
            app_logger.debug(f"РџРѕР»СѓС‡РµРЅРѕ {len(result)} С‚СЂР°РЅР·Р°РєС†РёР№")
            return result
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ С‚СЂР°РЅР·Р°РєС†РёР№: {e}", exc_info=True)
            return []

    def get_transactions_for_export(self) -> List[Transaction]:
        """РџРѕР»СѓС‡Р°РµС‚ РІСЃРµ С‚СЂР°РЅР·Р°РєС†РёРё Р±РµР· UI-Р»РёРјРёС‚Р° РґР»СЏ СЌРєСЃРїРѕСЂС‚Р°"""
        try:
            raw = core.get_all_transactions()
            result = []
            for row in raw:
                result.append(Transaction(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    amount=row['amount'],
                    comment=row['comment'],
                    date=row['date'],
                    status=row['status'] if 'status' in row.keys() else 'actual'
                ))
            app_logger.debug(f"РџРѕР»СѓС‡РµРЅРѕ {len(result)} С‚СЂР°РЅР·Р°РєС†РёР№ РґР»СЏ СЌРєСЃРїРѕСЂС‚Р°")
            return result
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ С‚СЂР°РЅР·Р°РєС†РёР№ РґР»СЏ СЌРєСЃРїРѕСЂС‚Р°: {e}", exc_info=True)
            return []
    
    def get_transaction_by_id(self, tid: int) -> Optional[Transaction]:
        """РџРѕР»СѓС‡Р°РµС‚ С‚СЂР°РЅР·Р°РєС†РёСЋ РїРѕ ID"""
        try:
            row = core.get_transaction_by_id(tid)
            if row:
                return Transaction(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    amount=row['amount'],
                    comment=row['comment'],
                    date=row['date']
                )
            return None
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ С‚СЂР°РЅР·Р°РєС†РёРё {tid}: {e}", exc_info=True)
            return None
    
    def add_transaction(self, transaction: Transaction) -> bool:
        """Р”РѕР±Р°РІР»СЏРµС‚ РЅРѕРІСѓСЋ С‚СЂР°РЅР·Р°РєС†РёСЋ"""
        try:
            app_logger.info(f"Р”РѕР±Р°РІР»РµРЅРёРµ С‚СЂР°РЅР·Р°РєС†РёРё: {transaction.type} - {transaction.amount}")
            
            if transaction.type == "income":
                # РџСЂРѕРІРµСЂСЏРµРј РєР°С‚РµРіРѕСЂРёСЋ - РґР»СЏ "РћСЃС‚Р°С‚РѕРє" РѕС‚С‡РёСЃР»РµРЅРёРµ РЅРµ РґРµР»Р°РµС‚СЃСЏ
                if "РћСЃС‚Р°С‚РѕРє" in transaction.category:
                    app_logger.info(f"РљР°С‚РµРіРѕСЂРёСЏ '{transaction.category}' - РѕС‚С‡РёСЃР»РµРЅРёРµ РЅРµ РґРµР»Р°РµС‚СЃСЏ")
                    core.add_income_with_capital(
                        transaction.amount, transaction.category, transaction.comment,
                        transaction.date, 0, None
                    )
                else:
                    # РџРѕР»СѓС‡Р°РµРј РѕСЃРЅРѕРІРЅРѕР№ СЃС‡С‘С‚ РєР°РїРёС‚Р°Р»Р°
                    capital_account = core.get_default_capital_account()
                    
                    if not capital_account:
                        app_logger.warning("РќРµС‚ РѕСЃРЅРѕРІРЅРѕРіРѕ СЃС‡С‘С‚Р° РєР°РїРёС‚Р°Р»Р°! РћС‚С‡РёСЃР»РµРЅРёРµ РЅРµ Р±СѓРґРµС‚ РІС‹РїРѕР»РЅРµРЅРѕ.")
                        # Р”РѕР±Р°РІР»СЏРµРј РґРѕС…РѕРґ Р±РµР· РѕС‚С‡РёСЃР»РµРЅРёСЏ
                        core.add_income_with_capital(
                            transaction.amount, transaction.category, transaction.comment,
                            transaction.date, 0, None
                        )
                    else:
                        # Р”РѕР±Р°РІР»СЏРµРј РґРѕС…РѕРґ СЃ РѕС‚С‡РёСЃР»РµРЅРёРµРј
                        core.add_income_with_capital(
                            transaction.amount, transaction.category, transaction.comment,
                            transaction.date, self._auto_percent if self._auto_enabled else 0,
                            capital_account['id']
                        )
            else:
                # Р Р°СЃС…РѕРґ
                core.add_expense(transaction.amount, transaction.category, transaction.comment, transaction.date)
            
            self.notify_listeners()
            app_logger.info(f"РўСЂР°РЅР·Р°РєС†РёСЏ РґРѕР±Р°РІР»РµРЅР° СѓСЃРїРµС€РЅРѕ")
            return True
            
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РґРѕР±Р°РІР»РµРЅРёСЏ С‚СЂР°РЅР·Р°РєС†РёРё: {e}", exc_info=True)
            return False
    
    def get_main_account(self):
        """РџРѕР»СѓС‡Р°РµС‚ РѕСЃРЅРѕРІРЅРѕР№ СЃС‡С‘С‚"""
        try:
            accounts = core.get_all_accounts()
            for acc in accounts:
                if acc['type'] == 'main':
                    return acc
            return None
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РѕСЃРЅРѕРІРЅРѕРіРѕ СЃС‡С‘С‚Р°: {e}", exc_info=True)
            return None

    def update_transaction(self, tid: int, field: str, value) -> bool:
        """РћР±РЅРѕРІР»СЏРµС‚ РїРѕР»Рµ С‚СЂР°РЅР·Р°РєС†РёРё"""
        try:
            core.update_transaction(tid, field, value)
            self.notify_listeners()
            app_logger.debug(f"РўСЂР°РЅР·Р°РєС†РёСЏ {tid} РѕР±РЅРѕРІР»РµРЅР°: {field}={value}")
            return True
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ С‚СЂР°РЅР·Р°РєС†РёРё {tid}: {e}", exc_info=True)
            return False
    
    def delete_transaction(self, tid: int) -> bool:
        """Удаляет транзакцию."""
        try:
            result = core.delete_transaction(tid)
            if result:
                self.notify_listeners()
                app_logger.info(f"Транзакция {tid} удалена")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления транзакции {tid}: {e}", exc_info=True)
            return False
    
    def get_categories(self, trans_type: str = None) -> List[str]:
        """РџРѕР»СѓС‡Р°РµС‚ СЃРїРёСЃРѕРє РІСЃРµС… РєР°С‚РµРіРѕСЂРёР№"""
        try:
            categories = core.get_all_categories(trans_type)
            return [cat['name'] for cat in categories]
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РєР°С‚РµРіРѕСЂРёР№: {e}", exc_info=True)
            return []
    
    def get_expenses_by_category(self, start_date=None, end_date=None):
        """РџРѕР»СѓС‡Р°РµС‚ СЂР°СЃС…РѕРґС‹ РїРѕ РєР°С‚РµРіРѕСЂРёСЏРј"""
        try:
            return core.get_expenses_by_category(start_date, end_date)
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ СЂР°СЃС…РѕРґРѕРІ: {e}", exc_info=True)
            return []
    
    def get_income_by_category(self, start_date=None, end_date=None):
        """РџРѕР»СѓС‡Р°РµС‚ РґРѕС…РѕРґС‹ РїРѕ РєР°С‚РµРіРѕСЂРёСЏРј"""
        try:
            return core.get_income_by_category(start_date, end_date)
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РґРѕС…РѕРґРѕРІ: {e}", exc_info=True)
            return []
        
    def get_monthly_stats(self, year: int, month: int) -> dict:
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃС‚Р°С‚РёСЃС‚РёРєСѓ Р·Р° РјРµСЃСЏС†: РґРѕС…РѕРґС‹, СЂР°СЃС…РѕРґС‹, РѕС‚С‡РёСЃР»РµРЅРёСЏ РІ РєР°РїРёС‚Р°Р»"""
        try:
            # Р¤РѕСЂРјРёСЂСѓРµРј РґР°С‚С‹
            start_date = f"{year}-{month:02d}-01"
            last_day = calendar.monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day:02d}"
            
            # РџРѕР»СѓС‡Р°РµРј РґР°РЅРЅС‹Рµ Р·Р° РїРµСЂРёРѕРґ
            income = core.get_income_by_category(start_date, end_date)
            expenses = core.get_expenses_by_category(start_date, end_date)
            capital = core.get_capital_contributions_for_period(start_date, end_date)
            
            # РЎСѓРјРјРёСЂСѓРµРј
            total_income = sum(item['total'] for item in income) if income else 0
            total_expense = sum(item['total'] for item in expenses) if expenses else 0
            
            return {
                'income': round(total_income, 2),
                'expense': round(total_expense, 2),
                'capital': round(capital, 2),
                'year': year,
                'month': month
            }
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РјРµСЃСЏС‡РЅРѕР№ СЃС‚Р°С‚РёСЃС‚РёРєРё: {e}", exc_info=True)
            return {'income': 0, 'expense': 0, 'capital': 0, 'year': year, 'month': month}
        
    def get_transactions_by_date_range(self, start_date, end_date):
        """РџРѕР»СѓС‡Р°РµС‚ С‚СЂР°РЅР·Р°РєС†РёРё Р·Р° РїСЂРѕРёР·РІРѕР»СЊРЅС‹Р№ РґРёР°РїР°Р·РѕРЅ РґР°С‚"""
        try:
            raw = core.get_transactions_by_period(start_date, end_date)
            result = []
            for row in raw:
                result.append(Transaction(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    amount=row['amount'],
                    comment=row['comment'],
                    date=row['date'],
                    status=row['status'] if 'status' in row.keys() else 'actual'
                ))
            return result
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ С‚СЂР°РЅР·Р°РєС†РёР№ Р·Р° РїРµСЂРёРѕРґ: {e}", exc_info=True)
            return []
    
    # ========== РњР•РўРћР”Р« Р”Р›РЇ Р РђР‘РћРўР« РЎРћ РЎР§Р•РўРђРњР ==========

    def get_all_accounts(self, include_inactive=False):
        """РџРѕР»СѓС‡Р°РµС‚ РІСЃРµ СЃС‡РµС‚Р°"""
        try:
            return core.get_all_accounts(include_inactive)
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ СЃС‡РµС‚РѕРІ: {e}", exc_info=True)
            return []

    def get_account_balance(self, account_id):
        """РџРѕР»СѓС‡Р°РµС‚ Р±Р°Р»Р°РЅСЃ СЃС‡С‘С‚Р° РїРѕ ID"""
        try:
            # РЎРЅР°С‡Р°Р»Р° РїСЂРѕРІРµСЂСЏРµРј РІ accounts
            accounts = self.get_all_accounts()
            for acc in accounts:
                if acc['id'] == account_id:
                    return acc['balance']
            
            # Р—Р°С‚РµРј РїСЂРѕРІРµСЂСЏРµРј РІ capital_accounts
            capital = self.get_capital_accounts()
            for acc in capital:
                if acc['id'] == account_id:
                    return acc['balance']
            
            app_logger.warning(f"РЎС‡С‘С‚ {account_id} РЅРµ РЅР°Р№РґРµРЅ")
            return 0
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ Р±Р°Р»Р°РЅСЃР°: {e}", exc_info=True)
            return 0
    
    # ========== РњР•РўРћР”Р« Р”Р›РЇ Р РђР‘РћРўР« РЎ РљРђРџРРўРђР›РћРњ ==========

    def get_capital_accounts(self):
        """РџРѕР»СѓС‡Р°РµС‚ РІСЃРµ СЃС‡РµС‚Р° РєР°РїРёС‚Р°Р»Р°"""
        try:
            return core.get_capital_accounts()
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ СЃС‡РµС‚РѕРІ РєР°РїРёС‚Р°Р»Р°: {e}", exc_info=True)
            return []

    def get_default_capital_account(self):
        """Возвращает основной счёт капитала для автоотчислений."""
        try:
            return core.get_default_capital_account()
        except Exception as e:
            app_logger.error(f"Ошибка получения основного счёта капитала: {e}", exc_info=True)
            return None

    def set_default_capital_account(self, account_id):
        """Устанавливает основной счёт капитала."""
        try:
            result = core.set_default_capital_account(account_id)
            if result:
                self.notify_listeners()
                app_logger.info(f"Основной счёт капитала изменён на ID={account_id}")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка установки основного счёта капитала: {e}", exc_info=True)
            return False

    def add_capital_account(self, name, balance=0, icon='💰', color='#ff9800'):
        """Добавляет новый счёт капитала."""
        try:
            result = core.add_capital_account(name, balance, icon, color)
            if result:
                app_logger.info(f"Добавлен счёт капитала: {name}")
                self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка добавления счёта капитала: {e}", exc_info=True)
            return None

    def update_capital_account(self, account_id, **kwargs):
        """РћР±РЅРѕРІР»СЏРµС‚ СЃС‡С‘С‚ РєР°РїРёС‚Р°Р»Р°"""
        try:
            result = core.update_capital_account(account_id, **kwargs)
            if result:
                self.notify_listeners()
                app_logger.debug(f"РћР±РЅРѕРІР»С‘РЅ СЃС‡С‘С‚ РєР°РїРёС‚Р°Р»Р° {account_id}: {kwargs}")
            return result
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ СЃС‡С‘С‚Р° РєР°РїРёС‚Р°Р»Р°: {e}", exc_info=True)
            return False

    def delete_capital_account(self, account_id):
        """Удаляет счёт капитала (деактивирует)."""
        try:
            result = core.delete_capital_account(account_id)
            if result:
                self.notify_listeners()
                app_logger.info(f"Счёт капитала {account_id} деактивирован")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления счёта капитала: {e}", exc_info=True)
            return False

    def get_total_capital(self):
        """РџРѕР»СѓС‡Р°РµС‚ РѕР±С‰СѓСЋ СЃСѓРјРјСѓ РІСЃРµС… СЃС‡РµС‚РѕРІ РєР°РїРёС‚Р°Р»Р°"""
        try:
            return core.get_total_capital()
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РѕР±С‰РµРіРѕ РєР°РїРёС‚Р°Р»Р°: {e}", exc_info=True)
            return 0
    
    def get_transfers_history(self, account_id=None, limit=100):
        """РџРѕР»СѓС‡Р°РµС‚ РёСЃС‚РѕСЂРёСЋ РїРµСЂРµРІРѕРґРѕРІ"""
        try:
            return core.get_transfers_history(account_id, limit)
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РёСЃС‚РѕСЂРёРё РїРµСЂРµРІРѕРґРѕРІ: {e}", exc_info=True)
            return []
    
    def check_budget(self, category: str, amount: float):
        """РџСЂРѕРІРµСЂСЏРµС‚ Р±СЋРґР¶РµС‚ РґР»СЏ РєР°С‚РµРіРѕСЂРёРё"""
        try:
            # РќР°С…РѕРґРёРј РєР°С‚РµРіРѕСЂРёСЋ РїРѕ РёРјРµРЅРё
            cat = core.get_category_by_name(category)
            if cat:
                return core.check_budget(cat['id'], amount)
            return None
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїСЂРѕРІРµСЂРєРё Р±СЋРґР¶РµС‚Р°: {e}", exc_info=True)
            return None
        
    def transfer_money(self, from_account_id, to_account_id, amount, date=None, comment=""):
        """Переводит деньги между счетами."""
        import core
        from utils.logger import app_logger
        
        app_logger.info(f"Перевод: {amount} со счёта {from_account_id} на {to_account_id}")
        
        try:
            if amount <= 0:
                app_logger.warning(f"Попытка перевода с суммой <= 0: {amount}")
                return False
            
            # Проверяем, достаточно ли средств
            from_balance = self.get_account_balance(from_account_id)
            if from_balance < amount:
                app_logger.warning(f"Недостаточно средств: {from_balance} < {amount}")
                return False
            
            # Обновляем балансы
            core.update_account_balance(from_account_id, -amount)
            core.update_account_balance(to_account_id, amount)
            
            # Добавляем запись о переводе
            core.add_transfer_record(from_account_id, to_account_id, amount, date, comment)
            
            self.notify_listeners()
            app_logger.info(f"Перевод {amount} выполнен успешно")
            return True
            
        except Exception as e:
            app_logger.error(f"Ошибка перевода: {e}", exc_info=True)
            return False
    
    # ========== Р Р•Р“РЈР›РЇР РќР«Р• РџР›РђРўР•Р–Р ==========
    
    def add_transaction_with_recurring(self, transaction: Transaction, months_ahead: int = 12) -> bool:
        """Р”РѕР±Р°РІР»СЏРµС‚ С‚СЂР°РЅР·Р°РєС†РёСЋ СЃ СЃРѕР·РґР°РЅРёРµРј С€Р°Р±Р»РѕРЅР° СЂРµРіСѓР»СЏСЂРЅРѕРіРѕ РїР»Р°С‚РµР¶Р°"""
        try:
            app_logger.info(f"Р”РѕР±Р°РІР»РµРЅРёРµ С‚СЂР°РЅР·Р°РєС†РёРё СЃ РїРѕРІС‚РѕСЂРµРЅРёРµРј: {transaction.type} - {transaction.amount} РЅР° {months_ahead} РјРµСЃСЏС†РµРІ")
            
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            is_future = transaction.date > today
            
            # 1. Р•СЃР»Рё РґР°С‚Р° РІ РїСЂРѕС€Р»РѕРј РёР»Рё СЃРµРіРѕРґРЅСЏ - РґРѕР±Р°РІР»СЏРµРј С„Р°РєС‚РёС‡РµСЃРєСѓСЋ С‚СЂР°РЅР·Р°РєС†РёСЋ
            # Р•СЃР»Рё РґР°С‚Р° РІ Р±СѓРґСѓС‰РµРј - РќР• РґРѕР±Р°РІР»СЏРµРј С‚СЂР°РЅР·Р°РєС†РёСЋ, С‚РѕР»СЊРєРѕ СЃРѕР·РґР°С‘Рј С€Р°Р±Р»РѕРЅ
            if not is_future:
                self.add_transaction(transaction)
                app_logger.info(f"Р¤Р°РєС‚РёС‡РµСЃРєР°СЏ С‚СЂР°РЅР·Р°РєС†РёСЏ РґРѕР±Р°РІР»РµРЅР° (РґР°С‚Р°: {transaction.date})")
            else:
                app_logger.info(f"Р”Р°С‚Р° РІ Р±СѓРґСѓС‰РµРј ({transaction.date}) - С‚СЂР°РЅР·Р°РєС†РёСЏ РЅРµ РґРѕР±Р°РІР»СЏРµС‚СЃСЏ, С‚РѕР»СЊРєРѕ РїР»Р°РЅРёСЂРѕРІР°РЅРёРµ")
            
            # 2. РџРѕР»СѓС‡Р°РµРј ID РєР°С‚РµРіРѕСЂРёРё
            category = core.get_category_by_name(transaction.category)
            category_id = category['id'] if category else None
            
            # 3. РћРїСЂРµРґРµР»СЏРµРј РЅР°Р·РІР°РЅРёРµ С€Р°Р±Р»РѕРЅР° (РёР· РєРѕРјРјРµРЅС‚Р°СЂРёСЏ РёР»Рё РєР°С‚РµРіРѕСЂРёРё)
            template_name = transaction.comment.strip() if transaction.comment else transaction.category
            
            # 4. РЎРѕР·РґР°С‘Рј С€Р°Р±Р»РѕРЅ
            template_id = core.create_recurring_template(
                template_type=transaction.type,
                name=template_name,
                amount=transaction.amount,
                day_of_month=int(transaction.date.split('-')[2]),
                category_id=category_id,
                comment_template=transaction.comment,
                months_ahead=months_ahead,
                working_days_only=True
            )

            # 5. РЈРІРµРґРѕРјР»СЏРµРј РІСЃРµС… СЃР»СѓС€Р°С‚РµР»РµР№ (РІРєР»СЋС‡Р°СЏ РїР»Р°РЅРёСЂРѕРІР°РЅРёРµ)
            self.notify_listeners()
            
            app_logger.info(f"РЎРѕР·РґР°РЅ С€Р°Р±Р»РѕРЅ ID={template_id} СЃ {months_ahead} РїР»Р°РЅРѕРІС‹РјРё С‚СЂР°РЅР·Р°РєС†РёСЏРјРё")
            return True
            
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РґРѕР±Р°РІР»РµРЅРёСЏ С‚СЂР°РЅР·Р°РєС†РёРё СЃ РїРѕРІС‚РѕСЂРµРЅРёРµРј: {e}", exc_info=True)
            return False
    
    def get_recurring_templates(self, template_type: str = None) -> list:
        """РџРѕР»СѓС‡Р°РµС‚ СЃРїРёСЃРѕРє С€Р°Р±Р»РѕРЅРѕРІ СЂРµРіСѓР»СЏСЂРЅС‹С… РїР»Р°С‚РµР¶РµР№"""
        try:
            return core.get_recurring_templates(template_type)
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ С€Р°Р±Р»РѕРЅРѕРІ: {e}", exc_info=True)
            return []
    
    def create_recurring_template(self, template_type: str, name: str, amount: float, 
                                   day_of_month: int, category_id: int = None,
                                   comment_template: str = None, months_ahead: int = 12,
                                   working_days_only: bool = True) -> int:
        """РЎРѕР·РґР°С‘С‚ С€Р°Р±Р»РѕРЅ СЂРµРіСѓР»СЏСЂРЅРѕРіРѕ РїР»Р°С‚РµР¶Р°"""
        try:
            template_id = core.create_recurring_template(
                template_type, name, amount, day_of_month, category_id,
                comment_template, months_ahead, working_days_only
            )
            self.notify_listeners()
            return template_id
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° СЃРѕР·РґР°РЅРёСЏ С€Р°Р±Р»РѕРЅР°: {e}", exc_info=True)
            return None
    
    def update_recurring_template(self, template_id: int, **kwargs) -> bool:
        """РћР±РЅРѕРІР»СЏРµС‚ С€Р°Р±Р»РѕРЅ Рё РїРµСЂРµРіРµРЅРµСЂРёСЂСѓРµС‚ РїР»Р°РЅРѕРІС‹Рµ С‚СЂР°РЅР·Р°РєС†РёРё"""
        try:
            result = core.update_recurring_template(template_id, **kwargs)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ С€Р°Р±Р»РѕРЅР°: {e}", exc_info=True)
            return False
    
    def delete_recurring_template(self, template_id: int) -> bool:
        """РЈРґР°Р»СЏРµС‚ С€Р°Р±Р»РѕРЅ Рё СЃРІСЏР·Р°РЅРЅС‹Рµ С‚СЂР°РЅР·Р°РєС†РёРё"""
        try:
            result = core.delete_recurring_template(template_id)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° СѓРґР°Р»РµРЅРёСЏ С€Р°Р±Р»РѕРЅР°: {e}", exc_info=True)
            return False
    
    def regenerate_template_transactions(self, template_id: int) -> int:
        """РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅРѕ РїРµСЂРµРіРµРЅРµСЂРёСЂСѓРµС‚ РїР»Р°РЅРѕРІС‹Рµ С‚СЂР°РЅР·Р°РєС†РёРё РґР»СЏ С€Р°Р±Р»РѕРЅР°"""
        try:
            # РЈРґР°Р»СЏРµРј СЃС‚Р°СЂС‹Рµ РїР»Р°РЅРѕРІС‹Рµ С‚СЂР°РЅР·Р°РєС†РёРё
            core.delete_planned_transactions(template_id)
            
            # РџРѕР»СѓС‡Р°РµРј С€Р°Р±Р»РѕРЅ
            template = core.get_recurring_template_by_id(template_id)
            if not template:
                return 0
            
            # Р“РµРЅРµСЂРёСЂСѓРµРј РЅРѕРІС‹Рµ
            count = core.generate_planned_transactions(template_id, months=template['months_ahead'])
            self.notify_listeners()
            return count
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРµСЂРµРіРµРЅРµСЂР°С†РёРё С‚СЂР°РЅР·Р°РєС†РёР№: {e}", exc_info=True)
            return 0
    
    def execute_planned_transactions(self) -> int:
        """Исполняет все просроченные плановые транзакции."""
        try:
            # Получаем настройки автоотчислений
            auto_percent = self._auto_percent if self._auto_enabled else 0
            capital_account = self.get_default_capital_account()
            capital_account_id = capital_account['id'] if capital_account else None
            
            # Исполняем
            count = core.execute_all_planned_transactions(auto_percent, capital_account_id)
            
            if count > 0:
                self.notify_listeners(update_all=True)
                app_logger.info(f"Исполнено {count} плановых транзакций")
            
            return count
        except Exception as e:
            app_logger.error(f"Ошибка исполнения плановых транзакций: {e}", exc_info=True)
            return 0
    
    def get_projected_balance(self, end_date: str = None) -> dict:
        """РџРѕР»СѓС‡Р°РµС‚ РїСЂРѕРіРЅРѕР·РёСЂСѓРµРјС‹Р№ Р±Р°Р»Р°РЅСЃ"""
        try:
            return core.get_projected_balance(end_date)
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РїСЂРѕРіРЅРѕР·Р°: {e}", exc_info=True)
            return {
                'current_balance': 0,
                'planned_income': 0,
                'planned_expense': 0,
                'budget_remaining': 0,
                'projected': 0,
                'end_date': end_date or ''
            }
    
    def get_auto_capital_settings(self) -> tuple:
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ РЅР°СЃС‚СЂРѕР№РєРё Р°РІС‚РѕРѕС‚С‡РёСЃР»РµРЅРёР№ (enabled, percent)"""
        settings = core.get_auto_capital_settings()
        self._auto_enabled = settings['enabled']
        self._auto_percent = settings['percent']
        return (self._auto_enabled, self._auto_percent)
    
    # ========== Р‘Р®Р”Р–Р•РўР« ==========
    
    def get_budgets(self) -> list:
        """РџРѕР»СѓС‡Р°РµС‚ РІСЃРµ Р±СЋРґР¶РµС‚С‹"""
        try:
            return core.get_budgets()
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ Р±СЋРґР¶РµС‚РѕРІ: {e}", exc_info=True)
            return []
    
    def set_budget(self, category_id: int, amount: float, period: str = 'monthly') -> bool:
        """РЈСЃС‚Р°РЅР°РІР»РёРІР°РµС‚ Р±СЋРґР¶РµС‚ РґР»СЏ РєР°С‚РµРіРѕСЂРёРё"""
        try:
            result = core.set_budget(category_id, amount, period)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° СѓСЃС‚Р°РЅРѕРІРєРё Р±СЋРґР¶РµС‚Р°: {e}", exc_info=True)
            return False
    
    def delete_budget(self, category_id: int) -> bool:
        """РЈРґР°Р»СЏРµС‚ Р±СЋРґР¶РµС‚ РґР»СЏ РєР°С‚РµРіРѕСЂРёРё"""
        try:
            result = core.delete_budget(category_id)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° СѓРґР°Р»РµРЅРёСЏ Р±СЋРґР¶РµС‚Р°: {e}", exc_info=True)
            return False
    
    def get_budget_status(self, category_id: int) -> dict:
        """РџРѕР»СѓС‡Р°РµС‚ СЃС‚Р°С‚СѓСЃ Р±СЋРґР¶РµС‚Р° РґР»СЏ РєР°С‚РµРіРѕСЂРёРё"""
        try:
            return core.get_budget_status(category_id)
        except Exception as e:
            app_logger.error(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ СЃС‚Р°С‚СѓСЃР° Р±СЋРґР¶РµС‚Р°: {e}", exc_info=True)
            return {'spent': 0, 'budget': 0, 'remaining': 0, 'percent': 0}

