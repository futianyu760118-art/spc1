"""通知文本长度裁剪：notification.title/content 为 varchar(256/512)，超长写入会 500。"""

NOTIFICATION_TITLE_MAX = 256
NOTIFICATION_CONTENT_MAX = 512
NOTIFICATION_REF_NO_MAX = 64


def clip_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)] + "…"
