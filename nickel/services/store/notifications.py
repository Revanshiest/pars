"""Домен уведомлений и подписок: notifications, subscriptions."""

from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional, Set


def _topic_tokens(text: str) -> Set[str]:
    return {t.lower() for t in text.replace(",", " ").split() if len(t) > 2}


def _subscription_match(sub_topic: str, keywords: List[str], filters: dict) -> bool:
    topic_l = sub_topic.lower()
    topic_tokens = _topic_tokens(sub_topic)

    try:
        from services.glossary import expand_query_with_glossary
        expanded = expand_query_with_glossary(sub_topic, use_bge=False)
        topic_tokens |= _topic_tokens(expanded.get("expanded", sub_topic))
        for syn in expanded.get("synonyms_added") or []:
            topic_tokens.add(syn.lower())
    except Exception:
        pass

    for kw in keywords:
        kl = kw.lower()
        if kl in topic_l or topic_l in kl:
            return True
        if kl in topic_tokens or any(kl in t or t in kl for t in topic_tokens if len(t) > 2):
            return True

    filter_geo = (filters or {}).get("geography")
    if filter_geo:
        return any(filter_geo.lower() in kw.lower() for kw in keywords)

    return False


class NotificationsMixin:
    """Уведомления и подписки. Композируется в PlatformStore
    (использует self._lock, self._connect(), self._now())."""

    def create_notification(self, user_id: str, title: str, body: str):
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO notifications (id, user_id, title, body, read, created_at) VALUES (?,?,?,?,0,?)",
                (str(uuid.uuid4()), user_id, title, body, self._now()),
            )

    def list_notifications(self, user_id: str, unread_only: bool = False) -> List[Dict]:
        sql = "SELECT * FROM notifications WHERE user_id=?"
        params: list = [user_id]
        if unread_only:
            sql += " AND read=0"
        sql += " ORDER BY created_at DESC LIMIT 50"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def mark_notification_read(self, notification_id: str, user_id: str):
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE notifications SET read=1 WHERE id=? AND user_id=?",
                (notification_id, user_id),
            )

    def add_subscription(self, user_id: str, topic: str, filters: Optional[dict] = None) -> str:
        sid = str(uuid.uuid4())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO subscriptions (id, user_id, topic, filters, active, created_at) VALUES (?,?,?,?,1,?)",
                (sid, user_id, topic, json.dumps(filters or {}), self._now()),
            )
        return sid

    def list_subscriptions(self, user_id: str) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM subscriptions WHERE user_id=? AND active=1", (user_id,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["filters"] = json.loads(d["filters"])
                result.append(d)
            return result

    def notify_subscribers(self, topic_keywords: List[str], title: str, body: str):
        with self._connect() as conn:
            subs = conn.execute("SELECT * FROM subscriptions WHERE active=1").fetchall()
            for sub in subs:
                filters = json.loads(sub["filters"] or "{}")
                if _subscription_match(sub["topic"], topic_keywords, filters):
                    self.create_notification(sub["user_id"], title, body)
