"""Единое SQLite-хранилище платформы.

Домены вынесены в отдельные модули пакета и композируются в единый
класс PlatformStore через миксины. Публичная точка входа — get_store();
для остального кода интерфейс не изменился:

    from services.store import get_store, ROLES, ROLE_PERMISSIONS
"""

from __future__ import annotations

from typing import Optional

from services.store.audit import AuditMixin
from services.store.base import StoreBase
from services.store.documents import DocumentsMixin
from services.store.facts import FactsMixin
from services.store.glossary import GlossaryMixin
from services.store.metrics import MetricsMixin
from services.store.notifications import NotificationsMixin
from services.store.users import ROLE_PERMISSIONS, ROLES, UsersMixin

__all__ = ["PlatformStore", "get_store", "ROLES", "ROLE_PERMISSIONS"]


class PlatformStore(
    AuditMixin,
    DocumentsMixin,
    FactsMixin,
    GlossaryMixin,
    MetricsMixin,
    NotificationsMixin,
    UsersMixin,
    StoreBase,
):
    """Фасад хранилища: собирает все доменные миксины поверх StoreBase.

    Инфраструктура (соединение, лок, инициализация схемы, метка времени)
    приходит из StoreBase; каждый домен — из своего модуля."""


_store: Optional[PlatformStore] = None


def get_store() -> PlatformStore:
    global _store
    if _store is None:
        _store = PlatformStore()
    return _store
