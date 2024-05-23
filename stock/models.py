from django.db import models


class Account(models.Model):
    class Meta:
        managed = True
        db_table = 'account'
        app_label = 'stock_db'

    objects = models.Manager()

    email = models.CharField(primary_key=True)
    pass_hash = models.BinaryField()
    pass_salt = models.BinaryField()


class Stock(models.Model):
    class Meta:
        managed = True
        db_table = 'stock'
        app_label = 'stock_db'

    objects = models.Manager()

    symbol = models.CharField(primary_key=True)
    company_name = models.CharField()


class BuyQueue(models.Model):
    class Meta:
        managed = True
        db_table = 'buy_queue'
        app_label = 'stock_db'
        unique_together = (('email', 'symbol'),)

    objects = models.Manager()

    email = models.ForeignKey(Account, models.DO_NOTHING, db_column='email')
    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')
    volume = models.IntegerField()


class PriceHistory(models.Model):
    class Meta:
        managed = True
        db_table = 'price_history'
        app_label = 'stock_db'
        unique_together = (('symbol', 'date'),)

    objects = models.Manager()

    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')
    date = models.DateField()
    open = models.IntegerField()
    high = models.IntegerField()
    close = models.IntegerField()
    low = models.IntegerField()
    volume = models.IntegerField()


class Subscription(models.Model):
    class Meta:
        managed = True
        db_table = 'subscription'
        app_label = 'stock_db'
        unique_together = (('email', 'symbol'),)

    objects = models.Manager()

    email = models.ForeignKey(Account, models.DO_NOTHING, db_column='email')
    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')


class Blacklist(models.Model):
    class Meta:
        managed = True
        db_table = 'blacklist'
        app_label = 'stock_db'

    objects = models.Manager()

    symbol = models.CharField(primary_key=True)
    date = models.DateField(db_column='record_date')


class StopLoss(models.Model):
    class Meta:
        managed = True
        db_table = 'stop_loss'
        app_label = 'stock_db'

    objects = models.Manager()

    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol', primary_key=True)
    price = models.IntegerField()


class StockUs(models.Model):
    class Meta:
        managed = True
        db_table = 'stock_us'
        app_label = 'stock_db'

    objects = models.Manager()

    symbol = models.CharField(primary_key=True)
    company_name = models.CharField()


class PriceHistoryUs(models.Model):
    class Meta:
        managed = True
        db_table = 'price_history_us'
        app_label = 'stock_db'
        unique_together = (('symbol', 'date'),)

    objects = models.Manager()

    symbol = models.ForeignKey(StockUs, models.DO_NOTHING, db_column='symbol')
    date = models.DateField()
    open = models.DecimalField(max_digits=10, decimal_places=4)
    high = models.DecimalField(max_digits=10, decimal_places=4)
    close = models.DecimalField(max_digits=10, decimal_places=4)
    low = models.DecimalField(max_digits=10, decimal_places=4)
    volume = models.IntegerField()


class SellQueue(models.Model):
    class Meta:
        managed = True
        db_table = 'sell_queue'
        app_label = 'stock_db'
        unique_together = (('symbol', 'email', 'price'),)
        
    email = models.ForeignKey(Account, on_delete=models.DO_NOTHING, db_column='email')
    symbol = models.ForeignKey(Stock, on_delete=models.DO_NOTHING, db_column='symbol')
    volume = models.IntegerField()
    id = models.BigAutoField(primary_key=True)
    price = models.IntegerField()