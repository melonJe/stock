import requests


def send_message(content):
    requests.post(url='https://discordapp.com/api/webhooks/1106978743756533841/fKloNp3oU5KXqcuTFCrAWrD41wgfq-Di1OLtbVkGqMgjFN99NM0aKHr1BxGF4-5gcxsD', data={
        'content': content
    })


def error_message(content):
    requests.post(url='https://discord.com/api/webhooks/1114793943977168936/Z54G25bTMemG_U9YPn1o7uv7L_JAOIzM1fKP3hq_-oer4ksokQwF7z65z4elJro2CeHd', data={
        'content': content
    })
