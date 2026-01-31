from typing import Type, Dict, List, Any, Optional

from peewee import Model, Field

from config.logging_config import get_logger
from data import models

logger = get_logger(__name__)


def upsert(model: Type[Model], data: Dict[str, Any], conflict_target: List[Field], preserve_fields: List[str]) -> None:
    """
    범용 UPSERT 함수 (다중 필드 고유 인덱스 처리 포함)
    :param model: Peewee 모델 클래스
    :param data: 삽입할 데이터 딕셔너리 (e.g., {'field1': value1, 'field2': value2, ...})
    :param conflict_target: 중복 확인 키 리스트 (e.g., [Model.field1, Model.field2])
    :param preserve_fields: 충돌 시 업데이트할 필드 리스트 (e.g., ['field3', 'field4'])
    """
    if not data:
        return

    try:
        with models.db.atomic():
            model.insert(**data).on_conflict(
                conflict_target=conflict_target,
                preserve=preserve_fields
            ).execute()
    except Exception as e:
        logger.error(f"Upsert failed for model {model.__name__}: {e}")


def upsert_many(model: Type[Model], data: List[Dict[str, Any]], conflict_target: Optional[List[Field]] = None, preserve_fields: Optional[List[str]] = None) -> None:
    """
    Peewee insert_many와 UPSERT를 결합하여 다중 데이터 처리
    :param model: Peewee 모델 클래스
    :param data: 삽입할 데이터의 리스트 (e.g., [{'field1': value1, ...}, ...])
    :param conflict_target: 중복 확인 키 리스트 (e.g., [Model.field1, Model.field2])
    :param preserve_fields: 충돌 시 업데이트할 필드 리스트 (e.g., ['field3', 'field4'])
    """
    if not data:
        return

    try:
        with models.db.atomic():
            if not conflict_target:
                model.insert_many(data).on_conflict().execute()
            elif not preserve_fields:
                model.insert_many(data).on_conflict(
                    conflict_target=conflict_target,
                    action='IGNORE'
                ).execute()
            else:
                model.insert_many(data).on_conflict(
                    conflict_target=conflict_target,
                    preserve=preserve_fields
                ).execute()
    except Exception as e:
        logger.error(f"Upsert many failed for model {model.__name__}: {e}")
