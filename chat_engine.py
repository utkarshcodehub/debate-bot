# chat_engine.py
# Anonymous free-form chat between two random users.
# No rounds, no scoring — just relay messages until someone types /stop or /next.

from dataclasses import dataclass

# Users waiting for a chat partner
chat_queue: list[int] = []

# Active chat pairs: user_id → opponent_id
active_chats: dict[int, int] = {}


@dataclass
class ChatSession:
    user_a: int
    user_b: int
    message_count: int = 0


# Active sessions keyed by frozenset of both user IDs
active_chat_sessions: dict[frozenset, ChatSession] = {}


def add_to_chat_queue(user_id: int) -> bool:
    if user_id in chat_queue or user_id in active_chats:
        return False
    chat_queue.append(user_id)
    return True


def try_chat_match() -> tuple[int, int] | None:
    if len(chat_queue) >= 2:
        user1 = chat_queue.pop(0)
        user2 = chat_queue.pop(0)
        active_chats[user1] = user2
        active_chats[user2] = user1
        active_chat_sessions[frozenset({user1, user2})] = ChatSession(
            user_a=user1, user_b=user2
        )
        return user1, user2
    return None


def remove_from_chat_queue(user_id: int) -> bool:
    if user_id in chat_queue:
        chat_queue.remove(user_id)
        return True
    return False


def get_chat_opponent(user_id: int) -> int | None:
    return active_chats.get(user_id)


def is_in_chat(user_id: int) -> bool:
    return user_id in active_chats


def is_in_chat_queue(user_id: int) -> bool:
    return user_id in chat_queue


def end_chat(user_id: int) -> int | None:
    opponent_id = active_chats.pop(user_id, None)
    if opponent_id:
        active_chats.pop(opponent_id, None)
        active_chat_sessions.pop(frozenset({user_id, opponent_id}), None)
    return opponent_id


def increment_message(user_id: int, opponent_id: int):
    session = active_chat_sessions.get(frozenset({user_id, opponent_id}))
    if session:
        session.message_count += 1


def get_message_count(user_id: int, opponent_id: int) -> int:
    session = active_chat_sessions.get(frozenset({user_id, opponent_id}))
    return session.message_count if session else 0