import pandas as pd
from app.database.db_connect import StockPrice


def get_bollinger_band_adx(data, window=20, num_std=2):
    data['ewm20'] = data['close'].ewm(span=window).mean()
    data['rolling_std'] = data['close'].rolling(window=window).std()
    data['upper_band'] = data['ewm20'] + (data['rolling_std'] * num_std)
    data['lower_band'] = data['ewm20'] - (data['rolling_std'] * num_std)
    data['up_move'] = data['high'] - data['high'].shift(1)
    data['down_move'] = data['low'].shift(1) - data['low']
    data['pdm'] = 0
    data['mdm'] = 0
    data.loc[(data['up_move'] > data['down_move']) & (data['up_move'] > 0), 'pdm'] = data['up_move']
    data.loc[(data['up_move'] < data['down_move']) & (data['down_move'] > 0), 'mdm'] = data['down_move']
    data['h-l'] = data['high'] - data['low']
    data['h-c'] = data['high'] - data['close'].shift(1)
    data['l-c'] = data['low'] - data['close'].shift(1)
    data['tr'] = data[['h-l', 'h-c', 'l-c']].max(axis=1)
    data['smoothed_pdm'] = data['pdm'].rolling(window=14).sum() - data['pdm'].rolling(window=14).mean() + data['pdm']
    data['smoothed_mdm'] = data['mdm'].rolling(window=14).sum() - data['mdm'].rolling(window=14).mean() + data['mdm']
    data['smoothed_tr'] = data['tr'].rolling(window=14).sum() - data['tr'].rolling(window=14).mean() + data['tr']
    data['pdi'] = data['smoothed_pdm'] / data['smoothed_tr']
    data['mdi'] = data['smoothed_mdm'] / data['smoothed_tr']
    data['dx'] = (data['pdi'] - data['mdi']) / (data['pdi'] + data['mdi']) * 100
    data['adx'] = data['dx'].rolling(window=14).mean()
    del data['ewm20'], data['rolling_std'], data['tr'], data['up_move'], data['down_move'], data['pdm'], data['mdm'], data['h-l'], data['h-c'], data['l-c'], data['smoothed_pdm'], \
        data['smoothed_mdm'], data['smoothed_tr'], data['pdi'], data['mdi'], data['dx']
    return data


query = StockPrice.select().limit(100).where(StockPrice.symbol == '005930').order_by(StockPrice.date.desc())
data = pd.DataFrame(list(query.dicts())).sort_values(by='date', ascending=True)
get_bollinger_band_adx(data)

# data['signal'] = 0
# data.loc[data['close'] < data['lower_band'], 'signal'] = 1
# data.loc[data['close'] > data['upper_band'], 'signal'] = -1

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
print(data)
# trading_decisions = []

# for i in range(1, len(data)):
#     if data['Signal'][i] == 1 and data['Signal'][i-1] != 1:
#         trading_decisions.append('Buy')
#     elif data['Signal'][i] == -1 and data['Signal'][i-1] != -1:
#         trading_decisions.append('Sell')
#     else:
#         trading_decisions.append('Hold')

# data['Decision'] = trading_decisions

# print(data['Decision'])
