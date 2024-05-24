from django.db import models


class BaseModel(models.Model):
    objects = models.Manager()

    class Meta:
        abstract = True
        managed = True


class Account(BaseModel):
    email = models.CharField(primary_key=True)
    pass_hash = models.BinaryField()
    pass_salt = models.BinaryField()

    class Meta:
        db_table = 'account'
        app_label = 'stock_db'


class Stock(BaseModel):
    symbol = models.CharField(primary_key=True)
    company_name = models.CharField()

    class Meta:
        db_table = 'stock'
        app_label = 'stock_db'


class BuyQueue(BaseModel):
    email = models.ForeignKey(Account, models.DO_NOTHING, db_column='email')
    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')
    volume = models.IntegerField()

    class Meta:
        db_table = 'buy_queue'
        app_label = 'stock_db'
        unique_together = (('email', 'symbol'),)


class PriceHistory(BaseModel):
    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')
    date = models.DateField()
    open = models.IntegerField()
    high = models.IntegerField()
    close = models.IntegerField()
    low = models.IntegerField()
    volume = models.IntegerField()

    class Meta:
        db_table = 'price_history'
        app_label = 'stock_db'
        unique_together = (('symbol', 'date'),)


class Subscription(BaseModel):
    email = models.ForeignKey(Account, models.DO_NOTHING, db_column='email')
    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol')

    class Meta:
        db_table = 'subscription'
        app_label = 'stock_db'
        unique_together = (('email', 'symbol'),)


class Blacklist(BaseModel):
    symbol = models.CharField(primary_key=True)
    date = models.DateField(db_column='record_date')

    class Meta:
        db_table = 'blacklist'
        app_label = 'stock_db'


class StopLoss(BaseModel):
    symbol = models.ForeignKey(Stock, models.DO_NOTHING, db_column='symbol', primary_key=True)
    price = models.IntegerField()

    class Meta:
        db_table = 'stop_loss'
        app_label = 'stock_db'


class StockUs(BaseModel):
    symbol = models.CharField(primary_key=True)
    company_name = models.CharField()

    class Meta:
        db_table = 'stock_us'
        app_label = 'stock_db'


class PriceHistoryUs(BaseModel):
    symbol = models.ForeignKey(StockUs, models.DO_NOTHING, db_column='symbol')
    date = models.DateField()
    open = models.DecimalField(max_digits=10, decimal_places=4)
    high = models.DecimalField(max_digits=10, decimal_places=4)
    close = models.DecimalField(max_digits=10, decimal_places=4)
    low = models.DecimalField(max_digits=10, decimal_places=4)
    volume = models.IntegerField()

    class Meta:
        db_table = 'price_history_us'
        app_label = 'stock_db'
        unique_together = (('symbol', 'date'),)


class SellQueue(BaseModel):
    email = models.ForeignKey(Account, on_delete=models.DO_NOTHING, db_column='email')
    symbol = models.ForeignKey(Stock, on_delete=models.DO_NOTHING, db_column='symbol')
    volume = models.IntegerField()
    id = models.BigAutoField(primary_key=True)
    price = models.IntegerField()

    class Meta:
        db_table = 'sell_queue'
        app_label = 'stock_db'
        unique_together = (('symbol', 'email', 'price'),)
