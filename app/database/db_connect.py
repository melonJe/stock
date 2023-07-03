import config
from peewee import *


class DBHelper(object):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db = MySQLDatabase(host=config.DB_HOST, port=config.DB_PORT, database=config.DB_NAME, user=config.DB_USER, password=config.DB_PASS)
        return cls._instance


class BaseModel(Model):
    class Meta:
        database = DBHelper().db


class User(BaseModel):
    email = CharField(primary_key=True)
    pass_hash = BigBitField(null=False)
    pass_salt = BigBitField(null=False)


class Stock(BaseModel):
    symbol = CharField(primary_key=True)
    name = CharField(null=False)


class StockBuy(BaseModel):
    id = BigAutoField(primary_key=True)
    email = CharField(null=False)
    symbol = CharField(null=False)
    volume = IntegerField(null=False)

    class Meta:
        db_table = 'stock_buy'
        constraints = [SQL('UNIQUE (email, symbol)')]


class StockPrice(BaseModel):
    symbol = CharField(null=False)
    date = DateField(null=False)
    open = BigIntegerField(null=False)
    high = BigIntegerField(null=False)
    close = BigIntegerField(null=False)
    low = BigIntegerField(null=False)

    class Meta:
        db_table = 'stock_price'
        primary_key = CompositeKey('symbol', 'date')


class StockSubscription(BaseModel):
    id = BigAutoField(primary_key=True)
    email = CharField(null=False)
    symbol = CharField(null=False)

    class Meta:
        db_table = 'stock_subscription'
        constraints = [SQL('UNIQUE (email, symbol)')]
