import os

from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DISCORD_MESSAGE = os.getenv("DISCORD_MESSAGE")
DISCORD_ERROR = os.getenv("DISCORD_ERROR")
DJANGO_SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
DEBUG_MODE = True if os.getenv("DEBUG_MODE") == 'True' else False
APP_KEY = os.getenv("APP_KEY")
APP_SECRET = os.getenv("APP_SECRET")
TR_ID = "T" if os.getenv("SIMULATE") == "False" else "V"
DOMAIN = "https://openapi.koreainvestment.com:9443" if os.getenv("SIMULATE") == "False" else "https://openapivts.koreainvestment.com:29443"
ACCOUNT_NUMBER = os.getenv("ACCOUNT_NUMBER")
ACCOUNT_CORD = os.getenv("ACCOUNT_CORD")
