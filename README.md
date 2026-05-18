Бот для поиска вакансий в Telegram.

## Команды
- `/search` - найти работу (город → профессия)
- `/favorites` - избранное
- `/last` - повторить поиск
## .env файл

Создайте файл `.env` и вставьте:

BOT_TOKEN=ваш_токен_бота
RAPIDAPI_KEY=ваш_ключ_api

## Запуск
```bash
pip install -r requirements.txt
python bot.py 