# utils/formatters.py
from datetime import datetime
from typing import Optional

def format_money(amount: float) -> str:
    """Форматирует число как денежную сумму"""
    return f"{amount:,.2f} ₽".replace(",", " ")

def format_date(date_str: str, format: str = "short") -> str:
    """Форматирует дату в человекочитаемый вид"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if format == "short":
            return dt.strftime("%d.%m.%Y")
        elif format == "long":
            months = [
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]
            return f"{dt.day} {months[dt.month-1]} {dt.year}"
        elif format == "month":
            months = [
                "январь", "февраль", "март", "апрель", "май", "июнь",
                "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
            ]
            return f"{months[dt.month-1]} {dt.year}"
        return date_str
    except:
        return date_str

def truncate(text: str, length: int = 30) -> str:
    """Обрезает текст до указанной длины"""
    if len(text) <= length:
        return text
    return text[:length-3] + "..."

def type_to_emoji(trans_type: str) -> str:
    """Конвертирует тип транзакции в эмодзи"""
    return "💰" if trans_type == "income" else "💸"

def type_to_ru(trans_type: str) -> str:
    """Конвертирует тип транзакции в русский текст"""
    return "Доход" if trans_type == "income" else "Расход"