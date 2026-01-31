import datetime

from peewee import *
from playhouse.pool import PooledPostgresqlDatabase

from config import setting_env

db = PooledPostgresqlDatabase(
    database=setting_env.DB_NAME,
    user=setting_env.DB_USER,
    password=setting_env.DB_PASS,
    host=setting_env.DB_HOST,
    port=setting_env.DB_PORT,
    max_connections=20,
    stale_timeout=300,
    timeout=30,
)


class Blacklist(Model):
    symbol = CharField(primary_key=True)
    record_date = DateField(default=datetime.datetime.now)

    class Meta:
        database = db
        table_name = 'blacklist'


class Stock(Model):
    symbol = CharField(primary_key=True)
    company_name = CharField()
    country = CharField(null=True)

    class Meta:
        database = db
        table_name = 'stock'


class StopLoss(Model):
    symbol = CharField(primary_key=True)
    price = IntegerField()

    class Meta:
        database = db
        table_name = 'stop_loss'


class PriceHistory(Model):
    symbol = CharField()
    date = DateField()
    open = BigIntegerField(null=True)
    high = BigIntegerField(null=True)
    close = BigIntegerField(null=True)
    low = BigIntegerField(null=True)
    volume = BigIntegerField(null=True)

    class Meta:
        database = db
        table_name = 'price_history'
        primary_key = False
        indexes = (
            (('symbol', 'date'), True),
        )


class PriceHistoryUS(Model):
    symbol = CharField()
    date = DateField()
    open = DecimalField(max_digits=20, decimal_places=4, null=True)
    high = DecimalField(max_digits=20, decimal_places=4, null=True)
    close = DecimalField(max_digits=20, decimal_places=4, null=True)
    low = DecimalField(max_digits=20, decimal_places=4, null=True)
    volume = BigIntegerField(null=True)

    class Meta:
        database = db
        table_name = 'price_history_us'
        primary_key = False
        indexes = (
            (('symbol', 'date'), True),
        )


class SellQueue(Model):
    symbol = CharField()
    volume = IntegerField()
    id = BigAutoField(primary_key=True)
    price = DecimalField(max_digits=20, decimal_places=4, null=True)

    class Meta:
        database = db
        table_name = 'sell_queue'


class Subscription(Model):
    symbol = CharField()
    category = CharField()
    id = BigAutoField(primary_key=True)

    class Meta:
        database = db
        table_name = 'subscription'


if __name__ == '__main__':
    db.connect()
    print(type(Stock))
