import datetime

from peewee import *

from config import setting_env

db = PostgresqlDatabase(database=setting_env.DB_NAME, user=setting_env.DB_USER, password=setting_env.DB_PASS, host=setting_env.DB_HOST, port=setting_env.DB_PORT)


class Account(Model):
    email = CharField(max_length=320, primary_key=True)
    pass_hash = BlobField()
    pass_salt = BlobField()

    class Meta:
        database = db
        table_name = 'account'


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
    id = BigAutoField(primary_key=True)
    symbol = CharField()
    date = DateField()
    open = IntegerField()
    high = IntegerField()
    close = IntegerField()
    low = IntegerField()
    volume = IntegerField()

    class Meta:
        database = db
        table_name = 'price_history'
        indexes = (
            (('symbol', 'date'), True),
        )


class PriceHistoryUS(Model):
    id = BigAutoField(primary_key=True)
    symbol = CharField()
    date = DateField()
    open = DecimalField(max_digits=10, decimal_places=4, null=True)
    high = DecimalField(max_digits=10, decimal_places=4, null=True)
    close = DecimalField(max_digits=10, decimal_places=4, null=True)
    low = DecimalField(max_digits=10, decimal_places=4, null=True)
    volume = BigIntegerField(null=True)

    class Meta:
        database = db
        table_name = 'price_history_us'
        indexes = (
            (('symbol', 'date'), True),
        )


class SellQueue(Model):
    email = CharField(max_length=320)
    symbol = CharField()
    volume = IntegerField()
    id = BigAutoField(primary_key=True)
    price = IntegerField()

    class Meta:
        database = db
        table_name = 'sell_queue'


class Subscription(Model):
    email = CharField(max_length=320)
    symbol = CharField()
    id = BigAutoField(primary_key=True)

    class Meta:
        database = db
        table_name = 'subscription'
        indexes = (
            (('email', 'symbol'), True),
        )


if __name__ == '__main__':
    db.connect()
    print(type(Stock))
