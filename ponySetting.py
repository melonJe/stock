from datetime import datetime
from dotenv import dotenv_values
import pony.orm as pony

config = dotenv_values(".env")
db = pony.Database()


class User(db.Entity):
    email = pony.PrimaryKey(str)
    pass_hash = pony.Required(bytes)
    pass_salt = pony.Required(bytes)


class Stock(db.Entity):
    symbol = pony.PrimaryKey(str)
    name = pony.Required(str)
    unit = pony.Required(str)


class StockBuy(db.Entity):
    _table_ = 'stock_buy'
    email = pony.Required(str)
    symbol = pony.Required(str)
    volume = pony.Required(int)
    pony.PrimaryKey(email, symbol)


class StockPrice(db.Entity):
    _table_ = 'stock_price'
    symbol = pony.PrimaryKey(str)
    date = pony.Required(datetime)
    open = pony.Required(str)
    high = pony.Required(str)
    close = pony.Required(str)
    low = pony.Required(str)


class StockSubscription(db.Entity):
    _table_ = 'stock_subscription'
    email = pony.Required(str)
    symbol = pony.Required(str)
    pony.PrimaryKey(email, symbol)


db.bind(provider='postgres',
        user=config['DB_USER'],
        password=config['DB_PASS'],
        host=config['DB_HOST'],
        port=config['DB_PORT'],
        database=config['DB_NAME'])
db.generate_mapping(create_tables=False)