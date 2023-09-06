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
