from dotenv import load_dotenv
import os


def get_bollinger_bands(data, window=20, num_std=2):
    rolling_mean = data['Close'].rolling(window=window).mean()
    rolling_std = data['Close'].rolling(window=window).std()
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    return rolling_mean, upper_band, lower_band

# ticker = 'AAPL'
# data = []

# rolling_mean, upper_band, lower_band = get_bollinger_bands(data)

# data['Signal'] = 0
# data.loc[data['Close'] < lower_band, 'Signal'] = 1
# data.loc[data['Close'] > upper_band, 'Signal'] = -1

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
