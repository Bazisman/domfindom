# 2026-04-17 - Family balance cache fix

## Что исправлено
- Откатили ошибочное изменение главной страницы, которое решало не ту проблему.
- Исправили расчет `Текущий семейный баланс` во вкладке `Семья`.
- Причина была в общем cache key `balance`, который переиспользовался между БД разных участников семьи.
- Для семейной сводки баланс теперь читается с `force_update=True`, без перетекания значения от другого участника.

## Измененные файлы
- `services/transaction_service.py`
- `backend/api/routes/families.py`
- `tests/test_web_api.py`

## Проверка
- `python tools/check_encoding.py --root .`
- `python -m unittest tests.test_web_api.WebApiTestCase.test_family_dashboard_sums_each_member_balance_without_cache_bleed -v`
- `npm run build`

## Ожидаемое поведение
- Если у Максима `90000`, а у Насти `-20000`, то семейная сводка показывает `70000`.
