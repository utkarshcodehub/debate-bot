# ai_judge.py
# Sends debate arguments to Groq (free AI) and gets back scores + verdict.

import json
from groq import Groq
from config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)


def evaluate_round(
    topic: str,
    round_number: int,
    argument_a: str,
    argument_b: str,
) -> dict:
    """
    Ask Groq to score both arguments.
    Returns dict with score_a, score_b, reasoning, winner_of_round.
    """

    prompt = f"""You are an expert debate judge. Evaluate this debate round fairly and objectively.

DEBATE TOPIC: {topic}
ROUND: {round_number}

DEBATER A's ARGUMENT:
\"\"\"{argument_a}\"\"\"

DEBATER B's ARGUMENT:
\"\"\"{argument_b}\"\"\"

Evaluate each argument on:
1. Logic and reasoning
2. Clarity
3. Strength and conviction
4. Relevance to the topic

Respond ONLY with a valid JSON object. No extra text, no markdown, just raw JSON:
{{
  "score_a": <integer 1-10>,
  "score_b": <integer 1-10>,
  "reasoning": "<2-3 sentence explanation of your scoring>",
  "winner_of_round": "<'A', 'B', or 'tie'>"
}}"""

    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if the model added them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


def summarize_debate(
    topic: str,
    total_score_a: int,
    total_score_b: int,
    rounds_data: list[dict],
) -> str:
    """
    After all rounds, ask Groq to write an engaging final verdict.
    """
    rounds_summary = ""
    for i, r in enumerate(rounds_data, 1):
        rounds_summary += (
            f"\nRound {i}: A scored {r['score_a']}, "
            f"B scored {r['score_b']}. {r['reasoning']}"
        )

    winner = (
        "Debater A" if total_score_a > total_score_b
        else "Debater B" if total_score_b > total_score_a
        else "a tie"
    )

    prompt = f"""You are a debate judge writing a final verdict.

TOPIC: {topic}
FINAL SCORES — Debater A: {total_score_a} | Debater B: {total_score_b}
WINNER: {winner}

ROUND SUMMARIES:
{rounds_summary}

Write a 3-4 sentence engaging final verdict. 
- Name the winner clearly
- Highlight what the winner did well
- Give constructive feedback to the losing debater
- Be fair, encouraging, and specific"""

    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.5,
    )

    return response.choices[0].message.content.strip()