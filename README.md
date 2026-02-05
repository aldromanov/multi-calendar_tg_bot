# 📅 Google Calendar Multi-Notifier Bot

Сервис-бот, который автоматически уведомляет о предстоящих событиях из **нескольких Google Calendar** и позволяет управлять событиями через Telegram.  
Поддерживается подтверждение событий, логирование, хранение истории в PostgreSQL и работа через Docker.

---

## 🚀 Основные возможности

- 🔔 Уведомления о событиях: автоматически за `AHEAD_HOUR` часов или вручную, выбирая интервал из `NOTIFY_INTERVALS` минут..  
- 📆 Получение списка событий на:
  - Сегодня  
  - Завтра  
  - Текущую неделю  
  - Следующую неделю  
- ✅ Подтверждение событий прямо в Telegram (чтобы больше не уведомляло о них).  
- 🗂️ Хранение информации о событиях и подтверждениях в базе PostgreSQL.  
- 🧠 Логирование всех действий и ошибок.  
- ⚙️ Полностью контейнеризировано через Docker Compose.

---

## 🧩 Стек технологий

- **Python 3.11+**
- **Google Calendar API**
- **Telegram Bot API**
- **SQLAlchemy + PostgreSQL**
- **Docker & Docker Compose**
- **Logging (стандартный модуль Python)**

---

## 📁 Структура проекта

```
project_root/
│
├── app/
│   ├── main.py                # Точка входа — бот и шедулер
│   ├── config.py              # Настройки и логирование
│   ├── notifier_worker.py     # Основная логика уведомлений (NotifierWorker)
│   ├── multicalendar.py       # Поддержка нескольких календарей
│   ├── google_calendar.py     # Работа с Google Calendar API
│   ├── telegram_bot.py        # Telegram-интерфейс (команды, кнопки)
│   ├── database.py            # SQLAlchemy модель SeenEvent и подключение к БД
│   ├── utils.py               # Вспомогательные функции
│   └── tokens/                # Хранилище OAuth-токенов пользователей
│       └── token_user1.pickle
│
├── get_token_pickle.py        # Скрипт для генерации токенов Google OAuth
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── license.md
└── README.md
```

---

## ⚙️ Переменные окружения (.env)

Пример файла `.env`:

```env
# Telegram
TELEGRAM_TOKEN=1234567890:ABCDEF...
NOTIFY_CHAT_ID=987654321

# Calendars as JSON-like mapping (use double quotes), keys are human names
TOKENS_PATH=/app/tokens
CALENDAR_TOKENS={
  "user1": {
    "token": "/app/tokens/token_user1.pickle", 
    "calendars": {"user1": "primary"}
  }, 
  "user2": {
    "token": "/app/tokens/token_user2.pickle", 
    "calendars": {"user2": "primary"}
  }
}

# Scheduler / timing settings
AHEAD_HOUR=2                        # hour ahead to notify
BUTTON_TTL=30                       # seconds button lifetime
NOTIFY_INTERVALS=60,30,15,10,5,0    # notify interval seconds

# Timezone
TIMEZONE=Europe/Moscow

# Database (Postgres service from docker-compose)
POSTGRES_DB=calendar_db
POSTGRES_USER=calendar_user
POSTGRES_PASSWORD=securepassword
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

---

## 🧰 Установка и запуск

### 1. Подготовить Google API
1. Создай проект в [Google Cloud Console](https://console.cloud.google.com/).  
2. Включи **Google Calendar API**.  
3. Создай **OAuth2 Client ID** → скачай JSON → сохрани как `credentials.json` в корне проекта.

### 2. Создать токен доступа
Сгенерируй `token_user1.pickle` (или для каждого пользователя свой):

```bash
python get_token_pickle.py --creds credentials.json --token app/tokens/token_user1.pickle
```

### 3. Настроить `.env`
Создай `.env` на основе `.env.example`.

### 4. Собрать и запустить контейнеры

```bash
docker-compose up --build -d
```

После запуска бот автоматически начнёт проверять календари и уведомлять в Telegram.

---

## 💬 Команды Telegram

| Команда        | Описание |
|----------------|-----------|
| `/start`       | Приветственное сообщение |
| `/today`       | Список событий на сегодня |
| `/tomorrow`    | Список событий на завтра |
| `/week`        | События на текущей неделе |
| `/nextweek`    | События на следующей неделе |

---

## 🧠 Архитектура

- **NotifierWorker** — управляет логикой уведомлений, повторных проверок и фильтрацией подтверждённых событий.  
- **TelegramBot** — обрабатывает команды и callback’и пользователей.  
- **GoogleCalendarClient** — взаимодействует с Google Calendar API и возвращает нормализованные события.  
- **SeenEvent (SQLAlchemy)** — модель для отслеживания уведомлённых и подтверждённых событий.  
- **Scheduler (main.py)** — периодически запускает проверку календарей и уведомления.  

---

## 🔐 Безопасность

- Не коммить `credentials.json`, `.env` и токены (`token_user*.pickle`) в репозиторий.  
- Для ограничения доступа можно фильтровать Telegram ID пользователей.  
- Каждый токен OAuth хранится в `app/tokens/`.

---

## 🧹 Очистка и перезапуск

```bash
docker-compose down -v
docker-compose up --build -d
```

---

## 🛠️ Настройка автозапуска через systemd

Чтобы бот запускался автоматически при старте системы, можно создать сервис `systemd`.  

### 1. Создать unit-файл

Сохрани файл `/etc/systemd/system/your_project.service`:

```ini
[Unit]
Description=Google Calendar Notifier Bot
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=/home/user/your_project
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down
Restart=always
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

> ⚠️ Замени `/home/user/your_project` на путь к твоему проекту.

### 2. Перезагрузить systemd и включить сервис

```bash
sudo systemctl daemon-reload
sudo systemctl enable your_project.service
sudo systemctl start your_project.service
```

### 3. Проверка статуса

```bash
sudo systemctl status your_project.service
```

### 4. Управление сервисом

```bash
# Перезапуск
sudo systemctl restart your_project.service

# Остановка
sudo systemctl stop your_project.service

# Просмотр логов
journalctl -u your_project.service -f
```

---

## 🪪 Автор

**Проект:** Google Calendar Multi-Notifier  
**Автор:** [GITHUB](https://github.com/aldromanov) Александр Р.  
**Назначение:** Автоматизация уведомлений и интеграция нескольких календарей с Telegram и PostgreSQL.

---

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. Подробности в файле [LICENSE](LICENSE).
