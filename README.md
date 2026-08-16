# Тестовое приложение для хранения заметок «Notes»

---

## Что нужно знать о приложении

### Запуск

```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Переменные окружения

Значений по умолчанию для параметров подключения к БД нет: без них приложение
завершится с ошибкой конфигурации.

| Переменная       | Обязательна | По умолчанию | Назначение                                                                                                 |
| -------------------------- | ---------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`           | см. ниже         | —                      | Строка подключения целиком, например`postgresql+psycopg2://user:pass@host:5432/db` |
| `POSTGRES_HOST`          | да¹                 | —                      | Хост БД                                                                                                        |
| `POSTGRES_PORT`          | нет                 | `5432`                | Порт БД                                                                                                        |
| `POSTGRES_DB`            | да¹                 | —                      | Имя базы                                                                                                      |
| `POSTGRES_USER`          | да¹                 | —                      | Пользователь                                                                                             |
| `POSTGRES_PASSWORD`      | да¹                 | —                      | Пароль                                                                                                         |
| `APP_NAME`               | нет                 | `notes`               | Имя приложения в логах                                                                            |
| `LOG_LEVEL`              | нет                 | `INFO`                | Уровень логирования                                                                                |
| `SHUTDOWN_DELAY_SECONDS` | нет                 | `3`                   | Пауза после SIGTERM перед закрытием пула соединений                            |
| `DB_CONNECT_TIMEOUT`     | нет                 | `5`                   | Таймаут одной попытки подключения к БД, сек                                      |

¹ Задайте либо `DATABASE_URL`, либо все четыре переменные `POSTGRES_*`.

### Endpoints

| Метод | Путь            | Описание                                                                                                 |
| ---------- | ------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `GET`    | `/`               | HTML-страница со списком заметок и формой добавления                    |
| `GET`    | `/api/notes`      | Список заметок (JSON)                                                                               |
| `POST`   | `/api/notes`      | Создать заметку:`{"title": "...", "body": "..."}`                                                |
| `DELETE` | `/api/notes/{id}` | Удалить заметку                                                                                    |
| `GET`    | `/healthz`        | Liveness: отвечает`200`, пока процесс жив; в БД не ходит                       |
| `GET`    | `/readyz`         | Readiness:`200`, если БД доступна, иначе `503`                                            |
| `GET`    | `/slow?seconds=N` | Запрос длительностью N секунд — удобно для проверки graceful shutdown |

### Особенности поведения, важные для задания

* **Приложение не ждёт базу самостоятельно.** Если на старте PostgreSQL
  недоступен, процесс пишет ошибку в лог и завершается с кодом `1`.
  Ожидание готовности БД — ответственность инфраструктуры.
* **Схема БД создаётся автоматически** при старте (`CREATE TABLE IF NOT EXISTS`),
  миграции запускать не нужно.
* **Graceful shutdown:** по `SIGTERM` приложение перестаёт принимать новые
  соединения, дорабатывает активные запросы, выдерживает паузу
  `SHUTDOWN_DELAY_SECONDS` и закрывает пул соединений с БД. В логах это видно по
  строкам `shutdown signal received` → `shutdown complete`. Если контейнер
  умирает по `SIGKILL` через 10 секунд после `docker compose stop` — сигнал не
  дошёл до процесса приложения.
* Все логи пишутся в `stdout`.

### Локальный запуск без Docker (если нужно посмотреть, как работает)

Потребуется запущенный PostgreSQL.

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_HOST=localhost POSTGRES_DB=notes POSTGRES_USER=notes POSTGRES_PASSWORD=secret
uvicorn app.main:app --reload
```

---

## Запуск через Docker (Блок 1 тестового задания)

В репозиторий добавлены:

- `Dockerfile` — многоступенчатая сборка образа приложения;
- `docker-compose.yml` — локальный стек app + PostgreSQL;
- `scripts/wait-for-db.py` — переносимое ожидание готовности БД;
- `scripts/docker-entrypoint.sh` — entrypoint контейнера (ждёт БД → `exec` uvicorn);
- `scripts/healthcheck.py` — HEALTHCHECK приложения;
- `.dockerignore`.

### Быстрый старт

```bash
cp .env.example .env            # задайте свой пароль POSTGRES_PASSWORD
docker compose up -d --build    # поднять стек с нуля одной командой
curl http://localhost:8000/readyz
docker compose logs -f app
docker compose down             # остановить (данные БД сохранятся)
docker compose down -v          # остановить и удалить том с данными
```

### Принятые решения и почему

**Образ.**
- База `python:3.12-slim` — официальный, легковеский, есть `linux/arm64` и `linux/amd64`.
- **Многоступенчатая сборка**: в `builder` ставятся `build-essential`/`libpq-dev` и
  зависимости в venv; в runtime-образ попадают только venv и код. Компиляторов и
  `-dev` пакетов в финальном образе нет.
- **Структура стадий**: в каждой стадии ровно один `COPY` и один `RUN`. Чтобы
  увести из builder и код, и venv одним `COPY`, venv создаётся внутри
  `/app/.venv` (а не в `/opt/venv`) и runtime забирает готовый `/app` целиком
  одной `COPY --from=builder`. Трейд-офф: единственный `COPY . .` перед установкой
  зависимостей означает, что любое изменение кода инвалидирует слой apt+pip —
  кэш requirements-only пожертвован ради заданной структуры.
- `psycopg2-binary` несёт собственный `libpq`, поэтому в runtime не нужен
  ни `postgresql-client`, ни `libpq5` — образ меньше.
- Запуск от непривилегированного пользователя `app` (`uid/gid 10001`), root
  нигде не используется.
- PID 1 — `tini` (минимальный init): корректно пересылает сигналы и реапит
  зомби. `docker-entrypoint.sh` делает `exec uvicorn …`, поэтому uvicorn сам
  оказывается непосредственным дочерним процессом tini и получает `SIGTERM`.
  `PYTHONUNBUFFERED=1` — логи остановки появляются сразу, без буферизации.

**Graceful shutdown.**
- `SIGTERM` → uvicorn прекращает принимать новые соединения, дорабатывает
  активные запросы, затем срабатывает `lifespan`: выдерживается пауза
  `SHUTDOWN_DELAY_SECONDS` и закрывается пул соединений. В логах видно
  `shutdown signal received → shutdown complete`.
- В `docker-compose.yml` у `app` задан `stop_grace_period: 30s` — больше, чем
  `SHUTDOWN_DELAY_SECONDS` + время доработки активных запросов, чтобы `docker
  compose stop` не убивал процесс `SIGKILL`'ом до завершения штатной остановки.

**Ожидание готовности БД (переносимо в K8s).**
- В compose `app` старtует только после `db: service_healthy` — это нативная
  гаранция compose.
- Дополнительно `docker-entrypoint.sh` вызывает `scripts/wait-for-db.py` —
  обычный процесс на `psycopg2` (зависимость уже есть в venv), который
  опрашивает БД и выходит `0` на `SELECT 1`, либо `1` по таймауту. Это
  решение **не зависит от оркестратора**: тот же самый скрипт можно
  использовать в K8s как `command` initContainer'а или в entrypoint основного
  контейнера. В compose он срабатывает мгновенно (БД уже healthy), но
  страхует нас при переносе и при локальном `docker run` без compose.

**Секреты.**
- Пароль БД и параметры подключения передаются только через переменные
  окружения из файла `.env` (через `env_file` в compose). `.env` внесён в
  `.gitignore`, в репозитории — только `.env.example` с placeholder-паролем.
- В образ секреты не попадают: `docker inspect notes:latest` показывает, что
  в `Env` есть только `PATH`, `PYTHONUNBUFFERED`, `APP_HOST/PORT` и т.п. —
  никаких `POSTGRES_PASSWORD`/`DATABASE_URL`.
- В URL для логов пароль маскируется (`app.config.Settings.safe_database_url`):
  в логах видно `postgresql+psycopg2://notes:***@db:5432/notes`.

**Healthcheck'и.**
- `db`: `pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"` (стандартная
  проверка postgres-образа, переменные разворачиваются внутри контейнера).
- `app`: `scripts/healthcheck.py` бьёт в `/readyz` (а не в `/healthz`), потому
  что `/readyz` проверяет и живость процесса, и доступность БД — это отражает
  реальную способность обслуживать трафик. Во время штатной остановки `/readyz`
  отвечает `503`, и контейнер корректно помечается `unhealthy`. Healthcheck
  описан и в `Dockerfile`, и в `docker-compose.yml` (второе — для наглядности
  стека).

### Проверка graceful shutdown

```bash
# запускаем долгий запрос (8 c) и тут же стопаем приложение
( curl -s http://localhost:8000/slow?seconds=8 > /tmp/slow.out ) &
sleep 1
docker compose stop app
cat /tmp/slow.out                 # ожидаем {"slept":8} — запрос доработал, а не был убит
docker compose logs app | tail    # строки "shutdown signal received" ... "shutdown complete"
```

### Проверка, что контейнер не root

```bash
docker exec notes-app id
# uid=10001(app) gid=10001(app) groups=10001(app)
```
