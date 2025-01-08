from tortoise import Tortoise

from config import setting_env


async def init():
    # Here we create a SQLite DB using file "db.sqlite3"
    #  also specify the app name of "models"
    #  which contain models from "app.models"
    await Tortoise.init(
        db_url=f'asyncpg://{setting_env.DB_USER}:{setting_env.DB_PASS}@{setting_env.DB_HOST}:{setting_env.DB_PORT}/{setting_env.DB_NAME}',
        modules={'models': ['stock.models']}
    )
