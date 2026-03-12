# matcher.py
# Category-based debate matchmaking.
# Each category has its own queue so users only match within the same topic category.

from collections import defaultdict

# Per-category waiting queues: {"💻 Technology": [user1, user2], ...}
category_queues: dict[str, list[int]] = defaultdict(list)

# Active debate pairs: user_id → opponent_id
active_pairs: dict[int, int] = {}

# Challenge tracking: challenger_id → category they challenged in
pending_challenges: dict[int, str] = {}


def add_to_queue(user_id: int, category: str) -> bool:
    """Add user to a category queue. Returns False if already queued/debating."""
    if user_id in active_pairs:
        return False
    for q in category_queues.values():
        if user_id in q:
            return False
    category_queues[category].append(user_id)
    return True


def try_match(category: str) -> tuple[int, int] | None:
    """Match first two users in a category queue."""
    queue = category_queues[category]
    if len(queue) >= 2:
        user1 = queue.pop(0)
        user2 = queue.pop(0)
        active_pairs[user1] = user2
        active_pairs[user2] = user1
        return user1, user2
    return None


def remove_from_queue(user_id: int) -> bool:
    """Remove user from whichever category queue they're in."""
    for q in category_queues.values():
        if user_id in q:
            q.remove(user_id)
            return True
    return False


def get_waiting_category(user_id: int) -> str | None:
    for cat, q in category_queues.items():
        if user_id in q:
            return cat
    return None


def get_opponent(user_id: int) -> int | None:
    return active_pairs.get(user_id)


def end_match(user_id: int) -> int | None:
    opponent_id = active_pairs.pop(user_id, None)
    if opponent_id:
        active_pairs.pop(opponent_id, None)
    return opponent_id


def is_in_debate(user_id: int) -> bool:
    return user_id in active_pairs


def is_waiting(user_id: int) -> bool:
    return any(user_id in q for q in category_queues.values())