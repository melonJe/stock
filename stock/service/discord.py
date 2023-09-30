import requests
import setting_env


def send_message(content):
    requests.post(url=setting_env.DISCORD_MESSAGE, data={
        'content': content
    })


def error_message(content):
    requests.post(url=setting_env.DISCORD_ERROR, data={
        'content': content
    })
