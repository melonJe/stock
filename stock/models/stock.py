from django.db import models

from stock.models.user import User


class Stock(models.Model):
    class Meta:
        db_table = 'stock'
        app_label = 'users_db'

    objects = models.Manager()

    symbol = models.CharField(primary_key=True)
    name = models.CharField()


class StockBuy(models.Model):
    class Meta:
        db_table = 'stock_buy'
        app_label = 'users_db'
        unique_together = (('email', 'symbol'),)

    objects = models.Manager()

    email = models.ForeignKey(User, models.DO_NOTHING, db_column='email')
    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')
    volume = models.IntegerField()


class StockPrice(models.Model):
    class Meta:
        db_table = 'stock_price'
        app_label = 'users_db'
        unique_together = (('symbol', 'date'),)

    objects = models.Manager()

    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')
    date = models.DateField()
    open = models.IntegerField()
    high = models.IntegerField()
    close = models.IntegerField()
    low = models.IntegerField()


class StockSubscription(models.Model):
    class Meta:
        db_table = 'stock_subscription'
        app_label = 'users_db'
        unique_together = (('email', 'symbol'),)

    objects = models.Manager()

    email = models.ForeignKey(User, models.DO_NOTHING, db_column='email')
    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')
