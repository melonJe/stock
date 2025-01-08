from tortoise import fields
from tortoise.models import Model


class Account(Model):
    email = fields.CharField(pk=True, max_length=255)
    pass_hash = fields.BinaryField()
    pass_salt = fields.BinaryField()

    class Meta:
        table = "account"


class Stock(Model):
    symbol = fields.CharField(pk=True, max_length=255)
    company_name = fields.CharField(max_length=255)
    country = fields.CharField(max_length=255)

    class Meta:
        table = "stock"


class BuyQueue(Model):
    email = fields.ForeignKeyField(
        "models.Account",
        related_name="buy_queues",
        to_field="email",
        on_delete=fields.NO_ACTION,  # Django의 NO_ACTION 대신
        source_field="email"
    )
    symbol = fields.ForeignKeyField(
        "models.Stock",
        related_name="buy_queues",
        to_field="symbol",
        on_delete=fields.NO_ACTION,
        source_field="symbol"
    )
    volume = fields.IntField()

    class Meta:
        table = "buy_queue"
        unique_together = (("email", "symbol"),)


class PriceHistory(Model):
    symbol = fields.ForeignKeyField(
        "models.Stock",
        related_name="price_histories",
        to_field="symbol",
        on_delete=fields.NO_ACTION,
        source_field="symbol"
    )
    date = fields.DateField()
    open = fields.IntField()
    high = fields.IntField()
    close = fields.IntField()
    low = fields.IntField()
    volume = fields.IntField()

    class Meta:
        table = "price_history"
        unique_together = (("symbol", "date"),)


class Subscription(Model):
    email = fields.ForeignKeyField(
        "models.Account",
        related_name="subscriptions",
        to_field="email",
        on_delete=fields.NO_ACTION,
        source_field="email"
    )
    symbol = fields.ForeignKeyField(
        "models.Stock",
        related_name="subscriptions",
        to_field="symbol",
        on_delete=fields.NO_ACTION,
        source_field="symbol"
    )

    class Meta:
        table = "subscription"
        unique_together = (("email", "symbol"),)


class Blacklist(Model):
    symbol = fields.CharField(pk=True, max_length=255)
    date = fields.DateField(source_field="record_date")

    class Meta:
        table = "blacklist"


class StopLoss(Model):
    # symbol을 PK로 지정
    symbol = fields.ForeignKeyField(
        "models.Stock",
        pk=True,
        to_field="symbol",
        on_delete=fields.NO_ACTION,
        source_field="symbol"
    )
    price = fields.IntField()

    class Meta:
        table = "stop_loss"


class PriceHistoryUs(Model):
    symbol = fields.ForeignKeyField(
        "models.Stock",
        related_name="price_histories_us",
        to_field="symbol",
        on_delete=fields.NO_ACTION,
        source_field="symbol"
    )
    date = fields.DateField()
    open = fields.DecimalField(max_digits=10, decimal_places=4)
    high = fields.DecimalField(max_digits=10, decimal_places=4)
    close = fields.DecimalField(max_digits=10, decimal_places=4)
    low = fields.DecimalField(max_digits=10, decimal_places=4)
    volume = fields.IntField()

    class Meta:
        table = "price_history_us"
        unique_together = (("symbol", "date"),)


class SellQueue(Model):
    id = fields.BigIntField(pk=True)
    email = fields.ForeignKeyField(
        "models.Account",
        related_name="sell_queues",
        to_field="email",
        on_delete=fields.NO_ACTION,
        source_field="email"
    )
    symbol = fields.ForeignKeyField(
        "models.Stock",
        related_name="sell_queues",
        to_field="symbol",
        on_delete=fields.NO_ACTION,
        source_field="symbol"
    )
    volume = fields.IntField()
    price = fields.IntField()

    class Meta:
        table = "sell_queue"
        unique_together = (("symbol", "email", "price"),)
