import requests
import config


def send_message(content):
    requests.post(url=config.DISCORD_MESSAGE, data={
        'content': content
    })


def error_message(content):
    requests.post(url=config.DISCORD_ERROR, data={
        'content': content
    })
