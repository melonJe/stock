import pony.orm as pony

from ponySetting import *

with pony.db_session:
    stock = Stock.select()
    x = {x.symbol for x in stock}
    print(x)