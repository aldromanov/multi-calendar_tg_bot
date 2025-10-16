import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from app.config import SCOPES, logger


def create_token(creds_path: str, token_path: str) -> None:
    """
    Создаёт или обновляет pickle-токен для доступа к Google Calendar API.

    Если файл токена уже существует — выполняется попытка обновить его.
    Если токен недействителен или отсутствует, создаётся новый через OAuth-авторизацию.

    :param creds_path: путь к credentials.json, выданному Google Cloud Console
    :param token_path: путь для сохранения итогового token.pickle
    """
    logger.info("▶️ Запуск генерации токена Google Calendar...")
    creds = None
    if os.path.exists(token_path):
        logger.info(f"✅ Найден существующий токен: {token_path}")
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("🔄 Обновление устаревшего токена...")
            creds.refresh(Request())
        else:
            logger.info("🌐 Создание нового токена через OAuth...")
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as token:
            pickle.dump(creds, token)
            logger.info(f"✅ Токен успешно сохранён: {token_path}")
    else:
        logger.info("✅ Существующий токен действителен — обновление не требуется.")

    logger.info("🏁 Генерация токена завершена.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Создание token.pickle для Google Calendar API")
    parser.add_argument("--creds", required=True, help="Путь до credentials.json")
    parser.add_argument("--token", default="token.pickle", help="Путь, куда сохранить token.pickle")

    args = parser.parse_args()
    create_token(args.creds, args.token)
