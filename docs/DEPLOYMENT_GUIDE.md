# Публикация web-версии

## Что уже подготовлено

- backend берёт `host`, `port`, `reload`, `CORS` и путь к БД из переменных окружения
- frontend по умолчанию ходит в API через относительный путь `/api/v1`
- для локальной разработки в `Vite` включён proxy на backend

## Минимальная схема продакшена

1. VPS или другой Linux-сервер
2. backend `FastAPI` на `127.0.0.1:8000`
3. frontend как собранная статика из `frontend/dist`
4. `Nginx`:
   - раздаёт frontend
   - проксирует `/api/` на backend
5. домен + HTTPS

## Переменные окружения backend

Пример:

```env
FINANCE_APP_DB_NAME=/opt/finance-app/data/finance.db
FINANCE_APP_BACKEND_HOST=127.0.0.1
FINANCE_APP_BACKEND_PORT=8000
FINANCE_APP_BACKEND_RELOAD=false
FINANCE_APP_CORS_ORIGINS=https://your-domain.example,https://www.your-domain.example
```

## Сборка frontend

```powershell
cd frontend
npm install
npm run build
```

Результат будет в `frontend/dist`.

## Запуск backend

```powershell
python run_web_backend.py
```

Для продакшена лучше запускать как сервис без `reload`.

## Рекомендуемая Nginx-схема

```nginx
server {
    listen 80;
    server_name your-domain.example www.your-domain.example;

    root /opt/finance-app/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

После этого можно выпустить HTTPS через Let's Encrypt.

## Что тебе нужно сделать вручную

1. Купить и настроить домен
2. Поднять сервер
3. Установить Python, Node.js и Nginx
4. Скопировать проект на сервер
5. Заполнить `.env`
6. Собрать frontend
7. Настроить systemd или другой менеджер процессов для backend
8. Настроить HTTPS

## Что ещё желательно сделать до публичного запуска

- добавить авторизацию
- подумать о переходе с `SQLite` на `PostgreSQL`
- настроить регулярные бэкапы базы
- добавить отдельный production-лог
