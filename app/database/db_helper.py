import os
from dotenv import load_dotenv
from peewee import *

load_dotenv()


class DBHelper(object):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db = MySQLDatabase(
                host=os.getenv("DB_HOST"),
                port=int(os.getenv("DB_PORT")),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASS"),
            )
        return cls._instance


class BaseModel(Model):
    class Meta:
        database = DBHelper().db


class Commute(BaseModel):
    user_id = IntegerField(primary_key=True)
    date = DateField()
    come_at = TimeField()
    leave_at = TimeField()


class User(BaseModel):
    user_id = IntegerField(primary_key=True)
    username = CharField()
    manager = BooleanField()