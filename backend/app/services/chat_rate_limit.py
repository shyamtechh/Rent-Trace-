import threading
import time
from collections import defaultdict, deque

from app.core.config import CHAT_RATE_LIMIT_PER_HOUR, CHAT_RATE_LIMIT_PER_MINUTE

_WINDOW_MINUTE_SECONDS = 60
_WINDOW_HOUR_SECONDS = 60 * 60


class ChatRateLimiter:
    def __init__(
        self,
        per_minute: int = CHAT_RATE_LIMIT_PER_MINUTE,
        per_hour: int = CHAT_RATE_LIMIT_PER_HOUR,
    ) -> None:
        if per_minute < 1 or per_hour < 1 or per_minute > per_hour:
            raise ValueError("Chat rate limits must be positive and minute limit cannot exceed hour limit.")
        self._per_minute = per_minute
        self._per_hour = per_hour
        self._events: dict[int, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def allow_request(self, user_id: int) -> bool:
        now = time.monotonic()
        minute_cutoff = now - _WINDOW_MINUTE_SECONDS
        hour_cutoff = now - _WINDOW_HOUR_SECONDS
        with self._lock:
            events = self._events[user_id]
            while events and events[0] <= hour_cutoff:
                events.popleft()
            minute_count = sum(timestamp > minute_cutoff for timestamp in events)
            if minute_count >= self._per_minute or len(events) >= self._per_hour:
                if not events:
                    self._events.pop(user_id, None)
                return False
            events.append(now)
            if not events:
                self._events.pop(user_id, None)
            return True


chat_rate_limiter = ChatRateLimiter()
