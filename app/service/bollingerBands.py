from datetime import datetime, timedelta

import FinanceDataReader
import pandas as pd
from app.database.db_connect import StockPrice, Stock
from app.service import stock

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)


def bollinger_band(data, window=20, num_std=2, adx_window=14):
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
    data['smoothed_pdm'] = data['pdm'].rolling(window=adx_window).sum() - data['pdm'].rolling(window=adx_window).mean() + data['pdm']
    data['smoothed_mdm'] = data['mdm'].rolling(window=adx_window).sum() - data['mdm'].rolling(window=adx_window).mean() + data['mdm']
    data['smoothed_tr'] = data['tr'].rolling(window=adx_window).sum() - data['tr'].rolling(window=adx_window).mean() + data['tr']
    data['pdi'] = data['smoothed_pdm'] / data['smoothed_tr']
    data['mdi'] = data['smoothed_mdm'] / data['smoothed_tr']
    data['dx'] = (data['pdi'] - data['mdi']) / (data['pdi'] + data['mdi']) * 100
    data['adx'] = data['dx'].rolling(window=adx_window).mean()

    data['signal'] = 0
    data.loc[data['close'] < data['lower_band'], 'signal'] = 1
    data.loc[data['close'] > data['upper_band'], 'signal'] = -1

    data.loc[(data['close'] < data['lower_band']) & (data['close'].shift(1) >= data['lower_band'].shift(1)), 'decision'] = 'buy'
    data.loc[(data['close'] > data['upper_band']) & (data['close'].shift(1) <= data['upper_band'].shift(1)), 'decision'] = 'sell'
    data.loc[(data['decision'] == 'buy') & (data['adx'] > 25), 'decision'] = 'sell'
    data.loc[(data['decision'] == 'sell') & (data['adx'] > 25), 'decision'] = 'buy'

    del data['ewm20'], data['rolling_std'], data['tr'], data['up_move'], data['down_move'], data['pdm'], data['mdm'], data['h-l'], data['h-c'], data['l-c'], data['smoothed_pdm'], \
        data['smoothed_mdm'], data['smoothed_tr'], data['pdi'], data['mdi'], data['dx']
    return data
