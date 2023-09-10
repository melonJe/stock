from django.db import models


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
        unique_together = (('email', 'symbol'),)
        app_label = 'users_db'

    objects = models.Manager()

    email = models.CharField()
    symbol = models.CharField()
    volume = models.IntegerField()


class StockPrice(models.Model):
    class Meta:
        db_table = 'stock_price'
        unique_together = (('symbol', 'date'),)
        app_label = 'users_db'

    objects = models.Manager()

    symbol = models.CharField()
    date = models.DateField()
    open = models.BigIntegerField()
    high = models.BigIntegerField()
    close = models.BigIntegerField()
    low = models.BigIntegerField()


class StockSubscription(models.Model):
    class Meta:
        db_table = 'stock_subscription'
        unique_together = (('email', 'symbol'),)
        app_label = 'users_db'

    objects = models.Manager()

    email = models.CharField()
    symbol = models.CharField()
