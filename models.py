# models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any


@dataclass
class Transaction:
    """Модель транзакции"""
    id: Optional[int] = None
    type: str = "expense"  # income/expense
    category: str = ""
    amount: float = 0.0
    comment: str = ""
    date: str = ""
    updated_at: Optional[str] = None
    sync_status: str = "synced"
    status: str = "actual"  # actual (выполненная) / planned (запланированная)
    money_source: str = "cashless"  # cashless / cash
    
    @property
    def type_emoji(self) -> str:
        return "💰" if self.type == "income" else "💸"
    
    @property
    def type_ru(self) -> str:
        return "Доход" if self.type == "income" else "Расход"
    
    @property
    def formatted_amount(self) -> str:
        return f"{self.amount:,.2f} ₽".replace(",", " ")
    
    def get_summary(self) -> str:
        """Возвращает краткое описание транзакции"""
        return f"Транзакция: {self.formatted_amount} руб, категория: {self.category}, дата: {self.date}, описание: {self.comment}"
    
    @classmethod
    def from_row(cls, row: Any) -> Optional['Transaction']:
        """Создает объект из строки БД"""
        if row is None:
            return None
        return cls(
            id=row['id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'id', None),
            type=row['type'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'type', 'expense'),
            category=row['category'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'category', ''),
            amount=row['amount'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'amount', 0.0),
            comment=row.get('comment', '') if isinstance(row, dict) else getattr(row, 'comment', ''),
            date=row['date'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'date', ''),
            status=row.get('status', 'actual') if isinstance(row, dict) else getattr(row, 'status', 'actual'),
            money_source=row.get('money_source', 'cashless') if isinstance(row, dict) else getattr(row, 'money_source', 'cashless')
        )


@dataclass
class Budget:
    """Модель бюджета"""
    id: Optional[int] = None
    category_id: int = 0
    category: str = ""
    amount: float = 0.0
    period: str = "monthly"  # monthly/yearly
    
    @property
    def period_ru(self) -> str:
        return "в месяц" if self.period == "monthly" else "в год"
    
    @property
    def formatted_amount(self) -> str:
        return f"{self.amount:,.2f} ₽".replace(",", " ")
    
    @classmethod
    def from_row(cls, row: Any) -> Optional['Budget']:
        """Создает объект из строки БД"""
        if row is None:
            return None
        return cls(
            id=row.get('id') if isinstance(row, dict) else getattr(row, 'id', None),
            category_id=row.get('category_id') if isinstance(row, dict) else getattr(row, 'category_id', 0),
            category=row.get('category') if isinstance(row, dict) else getattr(row, 'category', ''),
            amount=row.get('amount') if isinstance(row, dict) else getattr(row, 'amount', 0.0),
            period=row.get('period') if isinstance(row, dict) else getattr(row, 'period', 'monthly')
        )


@dataclass
class Balance:
    """Модель баланса"""
    main_balance: float = 0.0  # основной счёт
    income: float = 0.0
    expense: float = 0.0
    
    @property
    def total(self) -> float:
        """Общая сумма (основной счёт)"""
        return self.main_balance
    
    @property
    def difference(self) -> float:
        """Разница доходов и расходов"""
        return self.income - self.expense
    
    @property
    def color(self) -> str:
        return "#4caf50" if self.total >= 0 else "#f44336"


@dataclass
class Category:
    """Модель категории"""
    id: Optional[int] = None
    name: str = ""
    type: str = ""  # 'income', 'expense', 'both'
    color: str = "#808080"
    icon: str = "📁"
    is_active: bool = True
    
    @classmethod
    def from_row(cls, row: Any) -> Optional['Category']:
        """Создает объект из строки БД"""
        if row is None:
            return None
        return cls(
            id=row['id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'id', None),
            name=row['name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'name', ''),
            type=row['type'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'type', ''),
            color=row.get('color', '#808080') if isinstance(row, dict) else getattr(row, 'color', '#808080'),
            icon=row.get('icon', '📁') if isinstance(row, dict) else getattr(row, 'icon', '📁'),
            is_active=bool(row.get('is_active', 1)) if isinstance(row, dict) else bool(getattr(row, 'is_active', 1))
        )


@dataclass
class Account:
    """Модель счёта"""
    id: Optional[int] = None
    name: str = ""
    type: str = ""  # 'main', 'capital', 'savings'
    balance: float = 0.0
    currency: str = "RUB"
    is_active: bool = True
    
    @property
    def formatted_balance(self) -> str:
        return f"{self.balance:,.2f} ₽".replace(",", " ")
    
    @classmethod
    def from_row(cls, row: Any) -> Optional['Account']:
        """Создает объект из строки БД"""
        if row is None:
            return None
        return cls(
            id=row['id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'id', None),
            name=row['name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'name', ''),
            type=row['type'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'type', ''),
            balance=row.get('balance', 0.0) if isinstance(row, dict) else getattr(row, 'balance', 0.0),
            currency=row.get('currency', 'RUB') if isinstance(row, dict) else getattr(row, 'currency', 'RUB'),
            is_active=bool(row.get('is_active', 1)) if isinstance(row, dict) else bool(getattr(row, 'is_active', 1))
        )


@dataclass
class CapitalAccount:
    """Модель счёта капитала"""
    id: Optional[int] = None
    name: str = ""
    balance: float = 0.0
    currency: str = "RUB"
    icon: str = "💰"
    color: str = "#ff9800"
    is_active: bool = True
    is_default: bool = False
    
    @property
    def formatted_balance(self) -> str:
        return f"{self.balance:,.2f} ₽".replace(",", " ")
    
    @classmethod
    def from_row(cls, row: Any) -> Optional['CapitalAccount']:
        """Создает объект из строки БД"""
        if row is None:
            return None
        return cls(
            id=row['id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'id', None),
            name=row['name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'name', ''),
            balance=row.get('balance', 0.0) if isinstance(row, dict) else getattr(row, 'balance', 0.0),
            currency=row.get('currency', 'RUB') if isinstance(row, dict) else getattr(row, 'currency', 'RUB'),
            icon=row.get('icon', '💰') if isinstance(row, dict) else getattr(row, 'icon', '💰'),
            color=row.get('color', '#ff9800') if isinstance(row, dict) else getattr(row, 'color', '#ff9800'),
            is_active=bool(row.get('is_active', 1)) if isinstance(row, dict) else bool(getattr(row, 'is_active', 1)),
            is_default=bool(row.get('is_default', 0)) if isinstance(row, dict) else bool(getattr(row, 'is_default', 0))
        )


@dataclass
class Transfer:
    """Модель перевода"""
    id: Optional[int] = None
    from_account_id: int = 0
    to_account_id: int = 0
    amount: float = 0.0
    date: str = ""
    comment: str = ""
    from_name: str = ""
    to_name: str = ""
    
    @property
    def formatted_amount(self) -> str:
        return f"{self.amount:,.2f} ₽".replace(",", " ")
    
    @classmethod
    def from_row(cls, row: Any) -> Optional['Transfer']:
        """Создает объект из строки БД"""
        if row is None:
            return None
        return cls(
            id=row['id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'id', None),
            from_account_id=row['from_account_id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'from_account_id', 0),
            to_account_id=row['to_account_id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'to_account_id', 0),
            amount=row['amount'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'amount', 0.0),
            date=row['date'] if isinstance(row, dict) or hasattr(row, '__getitem__') else getattr(row, 'date', ''),
            comment=row.get('comment', '') if isinstance(row, dict) else getattr(row, 'comment', ''),
            from_name=row.get('from_name', '') if isinstance(row, dict) else getattr(row, 'from_name', ''),
            to_name=row.get('to_name', '') if isinstance(row, dict) else getattr(row, 'to_name', '')
        )
