# debate_engine.py
import random
import asyncio
from dataclasses import dataclass, field
from config import TOPIC_CATEGORIES, LABEL_A, LABEL_B

active_debates: dict[frozenset, "DebateSession"] = {}


@dataclass
class DebateSession:
    user_a: int
    user_b: int
    category: str = ""
    topic: str = ""
    current_round: int = 1
    argument_a: str = ""
    argument_b: str = ""
    score_a: int = 0
    score_b: int = 0
    rounds_data: list[dict] = field(default_factory=list)
    timer_task: asyncio.Task | None = None


def create_debate(user1: int, user2: int, category: str) -> DebateSession:
    topic = random.choice(TOPIC_CATEGORIES[category])
    session = DebateSession(
        user_a=user1, user_b=user2, category=category, topic=topic
    )
    active_debates[frozenset({user1, user2})] = session
    return session


def get_debate(user_id: int, opponent_id: int) -> DebateSession | None:
    return active_debates.get(frozenset({user_id, opponent_id}))


def submit_argument(session: DebateSession, user_id: int, text: str) -> bool:
    if user_id == session.user_a:
        if session.argument_a:
            return False
        session.argument_a = text
    elif user_id == session.user_b:
        if session.argument_b:
            return False
        session.argument_b = text
    return True


def both_argued(session: DebateSession) -> bool:
    return bool(session.argument_a and session.argument_b)


def advance_round(session: DebateSession, round_result: dict):
    session.rounds_data.append(round_result)
    session.score_a += round_result["score_a"]
    session.score_b += round_result["score_b"]
    session.current_round += 1
    session.argument_a = ""
    session.argument_b = ""


def end_debate(session: DebateSession):
    active_debates.pop(frozenset({session.user_a, session.user_b}), None)


def get_label(session: DebateSession, user_id: int) -> str:
    return LABEL_A if user_id == session.user_a else LABEL_B