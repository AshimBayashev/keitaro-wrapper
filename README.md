# Keitaro Campaign Studio

Небольшая обёртка над Keitaro Admin API: создание кампаний с двумя потоками и редактирование офферов в существующих кампаниях. Backend — FastAPI + SQLAlchemy + Alembic, frontend — Angular 22 с NG-ZORRO 22.

## Требования

- Python 3.13–3.15 и [uv](https://docs.astral.sh/uv/).
- Node.js 22.22.3+ или 24.15.0+ и npm.
- Доступный Keitaro Admin API и API-ключ с правами на кампании и потоки.

## Запуск

### 1. Backend

```powershell
cd backend
Copy-Item .env.example .env
# Укажите KEITARO_API_KEY в .env. Файл исключён из Git.
uv sync --python 3.13
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

На Linux/macOS замените `Copy-Item` на `cp`. Переменные в `backend/.env`:

| Переменная | Назначение |
|---|---|
| `KEITARO_BASE_URL` | Адрес трекера без `/admin` |
| `KEITARO_API_KEY` | Ключ Admin API; никогда не передаётся фронтенду |
| `DATABASE_URL` | SQLAlchemy URL; по умолчанию локальная SQLite |
| `CAMPAIGN_NAME_PREFIX` | Обязательный префикс новых кампаний, по умолчанию `test_bayashev_` |
| `FRONTEND_ORIGIN` | Разрешённый origin Angular при отдельном запуске |

Миграции обязательны до создания первой кампании. Структура БД хранит локальную историю созданных кампаний и ID потоков; актуальные кампании, офферы и доли всегда читаются из Keitaro. Новые миграции добавляются в `backend/alembic/versions/`; применяются командой `uv run alembic upgrade head`, текущая версия — `uv run alembic current`.

### 2. Frontend

В другом терминале:

```powershell
cd frontend
npm ci
npm start
```

Откройте [http://localhost:4200](http://localhost:4200). Angular проксирует `/api` на `127.0.0.1:8000`. Для проверки production-сборки: `npm run build`.

## Сценарии

**Создание.** В форме задаются окончание названия после `test_bayashev_`, страна из списка ISO 3166-1 с поиском по названию или коду, ID оффера с подсказкой из Keitaro, домен, группа кампаний и источник трафика. Backend повторно проверяет код страны и ссылки в Keitaro, создаёт отключённую кампанию, затем принудительный поток с фильтром `country` и редиректом на Google, затем поток по умолчанию с оффером. После успешного создания обоих потоков кампания включается. Если создание потока не удалось, новая кампания отправляется в архив. Alias генерируется автоматически. Список ISO исключает ошибочные двухбуквенные коды; доступность страны для фильтра зависит от установленной в Keitaro геобазы.

**Редактор.** Кампанию можно открыть из списка или по ID. Для активного потока с офферами доступны добавление и удаление. Существующие веса офферов сохраняются, новый получает вес `100`. В интерфейсе отображаются вес и приблизительная доля от суммы весов активных офферов. Удаление последнего оффера временно оставляет поток без назначения; интерфейс предупреждает об этом и позволяет добавить оффер обратно. После изменения экран повторно запрашивает данные у Keitaro; если состав офферов поменялся после открытия редактора, запрос получит HTTP 409. Проверка основана на отпечатке состава и не является атомарной блокировкой изменений из других приложений.

## Проверка

```powershell
cd backend
uv run pytest -q
cd ../frontend
npm run build
```

API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Основные маршруты: `GET /api/meta`, `GET /api/campaigns`, `GET /api/campaigns/{id}`, `POST /api/campaigns`, `POST /api/streams/{id}/offers`, `DELETE /api/streams/{id}/offers/{offer_id}`.

Документация API: [Keitaro Admin API](https://admin-api.docs.keitaro.io/), [руководство по авторизации](https://docs.keitaro.io/en/development/admin-api.html).
