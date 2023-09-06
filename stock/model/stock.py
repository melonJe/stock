from django.db import models


class Stock(models.Model):
    class Meta:
        db_table = 'stock'

    symbol = models.CharField(primary_key=True)
    name = models.CharField()


class StockBuy(models.Model):
    class Meta:
        db_table = 'stock_buy'

    email = models.CharField(primary_key=True)
    symbol = models.CharField(primary_key=True)
    volume = models.IntegerField()


class StockPrice(models.Model):
    class Meta:
        db_table = 'stock_price'

    symbol = models.CharField(primary_key=True)
    date = models.DateField(primary_key=True)
    open = models.BigIntegerField()
    high = models.BigIntegerField()
    close = models.BigIntegerField()
    low = models.BigIntegerField()


class StockSubscription(models.Model):
    class Meta:
        db_table = 'stock_subscription'

    email = models.CharField(primary_key=True)
    symbol = models.CharField(primary_key=True)
