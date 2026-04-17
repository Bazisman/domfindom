# 2026-04-17 - Mobile dock single-row scroll

## Что сделано
- Нижняя мобильная навигация переведена в одну горизонтальную линию.
- Добавлен горизонтальный скролл без видимого scrollbar.
- Убраны переносы вкладок на вторую строку.

## Технически
- `frontend/src/styles.css`
  - `.mobile-dock` переведен с grid на flex.
  - включен `overflow-x: auto` и touch scrolling.
  - ссылки получили `white-space: nowrap` и ширину по содержимому.

## Проверка
- `npm run build`
- `python tools/check_encoding.py --root .`
