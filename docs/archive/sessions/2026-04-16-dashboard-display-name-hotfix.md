# Протокол: имя вместо email в ленте транзакций
Дата: 2026-04-16

## Запрос
- В разделе транзакций/ленте операций у участников семьи показывался email, а нужно показывать имя пользователя.

## Причина
- В `DashboardPage` для семейной ленты подтягивалось поле `owner_display_name`, но в UI рендерился только `owner_email`.

## Что изменено
- Файл: `frontend/src/pages/DashboardPage.tsx`
1. В тип `RecentFeedItem` добавлено поле `owner_display_name`.
2. При маппинге семейных транзакций прокинут `owner_display_name`.
3. В отображении чипа автора установлен приоритет:
   - сначала `owner_display_name`
   - fallback: `owner_email`.

## Проверка
- `npm run build` (в `frontend`) — успешно.
- `python tools/check_encoding.py --root .` — `Encoding check passed`.

## Ожидаемый результат
- В ленте последних операций отображается имя профиля участника.
- Email показывается только если имя у пользователя не задано.
