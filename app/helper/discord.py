import requests


def send_message(content):
    requests.post(url='https://discordapp.com/api/webhooks/1106978743756533841/fKloNp3oU5KXqcuTFCrAWrD41wgfq-Di1OLtbVkGqMgjFN99NM0aKHr1BxGF4-5gcxsD', data={
        'content': str(content)
    })
