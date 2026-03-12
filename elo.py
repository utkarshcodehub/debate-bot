# elo.py
# Standard Elo rating calculation.
# Same system used in chess — winner gains points, loser loses them.

from config import ELO_K_FACTOR


def expected_score(rating_a: int, rating_b: int) -> float:
    """
    Probability that player A wins against player B.
    e.g. if A=1200, B=1000 → A has ~76% chance
    """
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def calculate_new_elos(
    elo_a: int, elo_b: int, winner: str
) -> tuple[int, int]:
    """
    Calculate new Elo ratings after a debate.
    winner: 'A', 'B', or 'tie'
    Returns: (new_elo_a, new_elo_b)
    """
    exp_a = expected_score(elo_a, elo_b)
    exp_b = expected_score(elo_b, elo_a)

    if winner == "A":
        score_a, score_b = 1.0, 0.0
    elif winner == "B":
        score_a, score_b = 0.0, 1.0
    else:  # tie
        score_a, score_b = 0.5, 0.5

    new_elo_a = round(elo_a + ELO_K_FACTOR * (score_a - exp_a))
    new_elo_b = round(elo_b + ELO_K_FACTOR * (score_b - exp_b))

    # Never let Elo drop below 100
    return max(100, new_elo_a), max(100, new_elo_b)


def elo_change_str(old: int, new: int) -> str:
    """Returns a display string like '+18' or '-12'."""
    diff = new - old
    return f"+{diff}" if diff >= 0 else str(diff)