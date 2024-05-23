import requests
from stock import setting_env

def send_message(content):
    '''중요한 메세지의 경우 discord로 전송'''
    try:
        response = requests.post(url=setting_env.DISCORD_MESSAGE_URL, data={'content': content}, timeout=10)
        response.raise_for_status()  # 요청이 성공적으로 완료되지 않으면 예외 발생
        print(f"Message sent successfully: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send message: {e}")
        error_message(f"Failed to send message: {e}")

def error_message(content):
    '''중요한 error 메세지의 경우 discord로 전송'''
    try:
        response = requests.post(url=setting_env.DISCORD_ERROR_URL, data={'content': content}, timeout=10)
        response.raise_for_status()  # 요청이 성공적으로 완료되지 않으면 예외 발생
        print(f"Error message sent successfully: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send error message: {e}")