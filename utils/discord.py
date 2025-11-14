import logging
from typing import Optional

import requests

from config import setting_env


class DiscordCriticalHandler(logging.Handler):
    """로그의 치명적(CRITICAL) 수준을 Discord로 전송하는 핸들러."""

    def __init__(self) -> None:
        super().__init__(level=logging.CRITICAL)

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "skip_discord", False):
            return
        try:
            message = self.format(record)
            error_message(message)
        except Exception:
            # 이미 CRITICAL 상황인 만큼, 추가 예외는 조용히 무시하여 무한 루프를 방지.
            pass


def register_discord_critical_handler(logger: Optional[logging.Logger] = None) -> None:
    """Discord 치명적 오류 핸들러를 한 번만 등록한다."""

    target_logger = logger or logging.getLogger()
    if any(isinstance(handler, DiscordCriticalHandler) for handler in target_logger.handlers):
        return

    handler = DiscordCriticalHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s'))
    target_logger.addHandler(handler)


def send_message(content):
    '''중요한 메세지의 경우 discord로 전송'''
    try:
        response = requests.post(url=setting_env.DISCORD_MESSAGE_URL, data={'content': content}, timeout=10)
        response.raise_for_status()  # 요청이 성공적으로 완료되지 않으면 예외 발생
    except requests.exceptions.RequestException as e:
        logging.getLogger(__name__).error("Failed to send message: %s", e, extra={"skip_discord": True})


def error_message(content):
    '''중요한 error 메세지의 경우 discord로 전송'''
    try:
        response = requests.post(url=setting_env.DISCORD_ERROR_URL, data={'content': content}, timeout=10)
        response.raise_for_status()  # 요청이 성공적으로 완료되지 않으면 예외 발생
    except requests.exceptions.RequestException as e:
        logging.getLogger(__name__).error("Failed to send error message: %s", e, extra={"skip_discord": True})


register_discord_critical_handler()
