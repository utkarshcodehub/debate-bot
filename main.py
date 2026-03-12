# main.py
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import matcher
import debate_engine as engine
import chat_engine as chat
from ai_judge import evaluate_round, summarize_debate
from elo import calculate_new_elos, elo_change_str
from database import init_db, get_or_create_user, update_after_debate, get_leaderboard, get_user_rank
from config import TELEGRAM_TOKEN, TOTAL_ROUNDS, ROUND_TIME_LIMIT, TOPIC_CATEGORIES, BOT_USERNAME

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Keyboards ──────────────────────────────────────────────────────────────────

def main_menu_keyboard():
    """The main 4-button menu shown on /start."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎤 Debate", callback_data="menu_debate"),
            InlineKeyboardButton("💬 Talk",   callback_data="menu_talk"),
        ],
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_leaderboard"),
            InlineKeyboardButton("❓ Help",         callback_data="menu_help"),
        ],
    ])


def category_keyboard():
    """One button per debate topic category."""
    buttons = [
        [InlineKeyboardButton(cat, callback_data=f"category_{cat}")]
        for cat in TOPIC_CATEGORIES.keys()
    ]
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_back")])
    return InlineKeyboardMarkup(buttons)


def post_debate_keyboard(user_id: int):
    """Shown after a debate ends — rematch or share invite link."""
    invite_url = f"https://t.me/{BOT_USERNAME}?start=challenge_{user_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎤 Debate Again",       callback_data="menu_debate")],
        [InlineKeyboardButton("🔗 Challenge a Friend", url=invite_url)],
        [InlineKeyboardButton("🏠 Main Menu",          callback_data="menu_back")],
    ])


# ── /start ─────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name or "Anonymous"

    # Register user in DB silently
    await get_or_create_user(user_id, username)

    # Handle challenge invite: /start challenge_12345
    args = context.args
    if args and args[0].startswith("challenge_"):
        try:
            challenger_id = int(args[0].split("_")[1])
            await handle_challenge_invite(update, context, user_id, challenger_id)
            return
        except (ValueError, IndexError):
            pass

    # Normal start — show main menu
    await update.message.reply_text(
        f"👋 *Welcome, {user.first_name}!*\n\n"
        "This bot lets you:\n"
        "🎤 *Debate* — argue a topic against a stranger, judged by AI\n"
        "💬 *Talk* — anonymous free chat with a random person\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def handle_challenge_invite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    challenger_id: int,
):
    """Someone clicked a challenge invite link."""
    if user_id == challenger_id:
        await update.message.reply_text(
            "😄 You can't challenge yourself! Share your link with someone else.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if matcher.is_in_debate(user_id) or matcher.is_waiting(user_id):
        await update.message.reply_text(
            "⚠️ You're already in a debate or queue. Finish it first!",
            reply_markup=main_menu_keyboard(),
        )
        return

    await update.message.reply_text(
        "🔗 *Challenge accepted!*\n\n"
        "Pick a category for this challenge:",
        parse_mode="Markdown",
        reply_markup=category_keyboard(),
    )
    # Store challenger_id so we can try to match them specifically
    context.user_data["challenge_from"] = challenger_id


# ── Callback Handler (all button presses) ─────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # remove loading spinner on button

    user_id = query.from_user.id
    data = query.data

    # ── Main menu buttons ──
    if data == "menu_back":
        await query.edit_message_text(
            "What would you like to do?",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "menu_debate":
        # Check if already busy
        if matcher.is_in_debate(user_id):
            await query.edit_message_text(
                "⚠️ You're already in a debate! Use /stop to end it first."
            )
            return
        if matcher.is_waiting(user_id):
            await query.edit_message_text(
                "⏳ You're already in the queue! Hang tight."
            )
            return
        if chat.is_in_chat(user_id) or chat.is_in_chat_queue(user_id):
            await query.edit_message_text(
                "⚠️ You're currently in a chat session. Use /stop to end it first."
            )
            return
        # Show category selection
        await query.edit_message_text(
            "🎯 *Choose a debate category:*\n\n"
            "The bot will pick a random topic within your category.",
            parse_mode="Markdown",
            reply_markup=category_keyboard(),
        )

    elif data == "menu_talk":
        await handle_talk(query, context, user_id)

    elif data == "menu_leaderboard":
        await handle_leaderboard(query)

    elif data == "menu_help":
        await query.edit_message_text(
            "❓ *How it works*\n\n"
            "🎤 *Debate mode:*\n"
            "• Pick a topic category\n"
            "• Get matched with a stranger\n"
            "• Debate for 3 rounds\n"
            "• AI judges each round (scores 1–10)\n"
            "• Winner gets Elo points!\n\n"
            "💬 *Talk mode:*\n"
            "• Get matched with a random stranger\n"
            "• Chat anonymously\n"
            "• Use /next to find someone new\n"
            "• Use /stop to end the chat\n\n"
            "📊 *Elo rating:*\n"
            "• Everyone starts at 1000\n"
            "• Win debates to climb the leaderboard",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="menu_back")]
            ]),
        )

    # ── Category selection ──
    elif data.startswith("category_"):
        category = data[len("category_"):]
        await handle_category_selected(query, context, user_id, category)


# ── Category Selected → Join Queue ────────────────────────────────────────────

async def handle_category_selected(
    query, context: ContextTypes.DEFAULT_TYPE, user_id: int, category: str
):
    if category not in TOPIC_CATEGORIES:
        await query.edit_message_text("❌ Unknown category. Please try again.")
        return

    added = matcher.add_to_queue(user_id, category)
    if not added:
        await query.edit_message_text(
            "⚠️ You're already in a queue or debate."
        )
        return

    await query.edit_message_text(
        f"🔍 *Looking for a {category} opponent...*\n\n"
        f"You'll be debating in: *{category}*\n"
        "Type /stop to leave the queue.",
        parse_mode="Markdown",
    )

    # Try to match
    match = matcher.try_match(category)
    if match:
        user1, user2 = match
        # If this was a challenge, try to respect it (best effort)
        await start_debate(user1, user2, category, context)


# ── Start Debate ───────────────────────────────────────────────────────────────

async def start_debate(
    user1: int, user2: int, category: str, context: ContextTypes.DEFAULT_TYPE
):
    session = engine.create_debate(user1, user2, category)

    # Fetch Elo for display
    u1 = await get_or_create_user(user1)
    u2 = await get_or_create_user(user2)

    intro = (
        "🎉 *Match found! Let the debate begin!*\n\n"
        f"📂 *Category:* {category}\n"
        f"📋 *Topic:* _{session.topic}_\n\n"
        "📌 You are: *{{label}}*\n"
        f"⭐ Your Elo: *{{elo}}*\n\n"
        f"🔄 *{TOTAL_ROUNDS} rounds* — type your argument when ready\n"
        f"⏱️ *{ROUND_TIME_LIMIT} seconds* per argument\n\n"
        "Round 1 starts now! Type your argument 👇"
    )

    await context.bot.send_message(
        chat_id=user1,
        text=intro.format(
            label=engine.get_label(session, user1), elo=u1["elo"]
        ),
        parse_mode="Markdown",
    )
    await context.bot.send_message(
        chat_id=user2,
        text=intro.format(
            label=engine.get_label(session, user2), elo=u2["elo"]
        ),
        parse_mode="Markdown",
    )

    await start_round_timer(session, context)


# ── Round Timer ────────────────────────────────────────────────────────────────

async def start_round_timer(
    session: engine.DebateSession, context: ContextTypes.DEFAULT_TYPE
):
    async def timer_callback():
        await asyncio.sleep(ROUND_TIME_LIMIT)
        timed_out = []
        if not session.argument_a:
            session.argument_a = "[No argument — timed out]"
            timed_out.append(session.user_a)
        if not session.argument_b:
            session.argument_b = "[No argument — timed out]"
            timed_out.append(session.user_b)
        for uid in timed_out:
            await context.bot.send_message(
                chat_id=uid,
                text="⏰ *Time's up!* Your argument was auto-submitted as blank.",
                parse_mode="Markdown",
            )
        if timed_out:
            await process_round(session, context)

    if session.timer_task and not session.timer_task.done():
        session.timer_task.cancel()
    session.timer_task = asyncio.create_task(timer_callback())


# ── Message Handler ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # ── Debate message ──
    if matcher.is_in_debate(user_id):
        opponent_id = matcher.get_opponent(user_id)
        session = engine.get_debate(user_id, opponent_id)
        if not session:
            return

        accepted = engine.submit_argument(session, user_id, text)
        if not accepted:
            await update.message.reply_text(
                "✅ Already submitted this round. Waiting for opponent..."
            )
            return

        await update.message.reply_text(
            f"✅ *Argument received for Round {session.current_round}!*\n"
            "Waiting for your opponent...",
            parse_mode="Markdown",
        )

        sender_label = engine.get_label(session, user_id)
        await context.bot.send_message(
            chat_id=opponent_id,
            text=f"💬 *Opponent ({sender_label}):*\n{text}",
            parse_mode="Markdown",
        )

        if engine.both_argued(session):
            if session.timer_task and not session.timer_task.done():
                session.timer_task.cancel()
            await process_round(session, context)
        return

    # ── Chat message ──
    if chat.is_in_chat(user_id):
        opponent_id = chat.get_chat_opponent(user_id)
        if not opponent_id:
            return

        chat.increment_message(user_id, opponent_id)

        await context.bot.send_message(
            chat_id=opponent_id,
            text=f"👤 *Stranger:*\n{text}",
            parse_mode="Markdown",
        )
        return

    # ── Not in anything ──
    await update.message.reply_text(
        "Use the menu to get started!",
        reply_markup=main_menu_keyboard(),
    )


# ── Process Debate Round ───────────────────────────────────────────────────────

async def process_round(
    session: engine.DebateSession, context: ContextTypes.DEFAULT_TYPE
):
    round_num = session.current_round

    for uid in [session.user_a, session.user_b]:
        await context.bot.send_message(
            chat_id=uid,
            text=f"🤖 *Round {round_num} complete! AI is judging...*",
            parse_mode="Markdown",
        )

    try:
        result = evaluate_round(
            topic=session.topic,
            round_number=round_num,
            argument_a=session.argument_a,
            argument_b=session.argument_b,
        )
    except Exception as e:
        logger.error(f"AI evaluation error: {e}")
        result = {
            "score_a": 5, "score_b": 5,
            "reasoning": "AI evaluation unavailable — defaulted to 5.",
            "winner_of_round": "tie",
        }

    round_winner = (
        "Debater A 🅰️" if result["winner_of_round"] == "A"
        else "Debater B 🅱️" if result["winner_of_round"] == "B"
        else "Tie 🤝"
    )

    preview_a = session.score_a + result["score_a"]
    preview_b = session.score_b + result["score_b"]

    result_msg = (
        f"📊 *Round {round_num} Results*\n\n"
        f"🅰️ Debater A: *{result['score_a']}/10*\n"
        f"🅱️ Debater B: *{result['score_b']}/10*\n\n"
        f"🏅 Round winner: *{round_winner}*\n\n"
        f"💡 *Judge's note:*\n{result['reasoning']}\n\n"
        f"📈 *Running total — A: {preview_a} | B: {preview_b}*"
    )

    for uid in [session.user_a, session.user_b]:
        await context.bot.send_message(
            chat_id=uid, text=result_msg, parse_mode="Markdown"
        )

    engine.advance_round(session, result)

    if session.current_round > TOTAL_ROUNDS:
        await finalize_debate(session, context)
    else:
        next_msg = (
            f"⚔️ *Round {session.current_round} begins!*\n"
            f"📋 Topic: _{session.topic}_\n\n"
            f"⏱️ {ROUND_TIME_LIMIT}s — type your argument!"
        )
        for uid in [session.user_a, session.user_b]:
            await context.bot.send_message(
                chat_id=uid, text=next_msg, parse_mode="Markdown"
            )
        await start_round_timer(session, context)


# ── Finalize Debate + Elo Update ───────────────────────────────────────────────

async def finalize_debate(
    session: engine.DebateSession, context: ContextTypes.DEFAULT_TYPE
):
    # Determine winner from debate scores
    if session.score_a > session.score_b:
        debate_winner = "A"
    elif session.score_b > session.score_a:
        debate_winner = "B"
    else:
        debate_winner = "tie"

    # Fetch current Elo ratings
    u_a = await get_or_create_user(session.user_a)
    u_b = await get_or_create_user(session.user_b)
    old_elo_a = u_a["elo"]
    old_elo_b = u_b["elo"]

    # Calculate new Elo
    new_elo_a, new_elo_b = calculate_new_elos(old_elo_a, old_elo_b, debate_winner)

    # Save to DB
    result_a = "win" if debate_winner == "A" else "loss" if debate_winner == "B" else "tie"
    result_b = "win" if debate_winner == "B" else "loss" if debate_winner == "A" else "tie"
    await update_after_debate(session.user_a, new_elo_a, result_a)
    await update_after_debate(session.user_b, new_elo_b, result_b)

    # Get AI summary
    try:
        summary = summarize_debate(
            topic=session.topic,
            total_score_a=session.score_a,
            total_score_b=session.score_b,
            rounds_data=session.rounds_data,
        )
    except Exception as e:
        logger.error(f"Summary error: {e}")
        summary = "A great debate! Both sides argued well."

    winner_line = (
        "🏆 *Debater A wins!*" if debate_winner == "A"
        else "🏆 *Debater B wins!*" if debate_winner == "B"
        else "🤝 *It's a tie!*"
    )

    # Build the final result message (same for both, personal note added separately)
    final_base = (
        "🎬 *Debate Over!*\n\n"
        f"📂 Category: {session.category}\n"
        f"📋 Topic: _{session.topic}_\n\n"
        f"🅰️ Debater A: *{session.score_a} pts*\n"
        f"🅱️ Debater B: *{session.score_b} pts*\n\n"
        f"{winner_line}\n\n"
        f"🤖 *AI Verdict:*\n{summary}"
    )

    for uid in [session.user_a, session.user_b]:
        user_label = "A" if uid == session.user_a else "B"
        old_elo = old_elo_a if user_label == "A" else old_elo_b
        new_elo = new_elo_a if user_label == "A" else new_elo_b
        elo_diff = elo_change_str(old_elo, new_elo)
        res = result_a if user_label == "A" else result_b

        if res == "win":
            personal = f"\n\n🎉 *You won!*\n⭐ Elo: {old_elo} → *{new_elo}* ({elo_diff})"
        elif res == "loss":
            personal = f"\n\n💪 *You lost — keep practicing!*\n⭐ Elo: {old_elo} → *{new_elo}* ({elo_diff})"
        else:
            personal = f"\n\n🤝 *It's a tie!*\n⭐ Elo: {old_elo} → *{new_elo}* ({elo_diff})"

        rank = await get_user_rank(uid)
        personal += f"\n🏅 Your rank: *#{rank}*"

        await context.bot.send_message(
            chat_id=uid,
            text=final_base + personal,
            parse_mode="Markdown",
            reply_markup=post_debate_keyboard(uid),
        )

    # Clean up
    engine.end_debate(session)
    matcher.end_match(session.user_a)


# ── Talk (Anonymous Chat) ──────────────────────────────────────────────────────

async def handle_talk(query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if matcher.is_in_debate(user_id) or matcher.is_waiting(user_id):
        await query.edit_message_text(
            "⚠️ Finish your debate first before starting a chat!"
        )
        return

    if chat.is_in_chat(user_id):
        await query.edit_message_text(
            "💬 You're already in a chat! Type /stop to end it."
        )
        return

    if chat.is_in_chat_queue(user_id):
        await query.edit_message_text("⏳ Already looking for a chat partner!")
        return

    chat.add_to_chat_queue(user_id)
    await query.edit_message_text(
        "🔍 *Looking for someone to chat with...*\n\n"
        "You'll be connected anonymously.\n"
        "• /next — find a new person\n"
        "• /stop — end the chat",
        parse_mode="Markdown",
    )

    match = chat.try_chat_match()
    if match:
        user1, user2 = match
        connect_msg = (
            "✅ *Connected to a stranger!*\n\n"
            "Say hi 👋 Your identity is completely anonymous.\n"
            "• /next — skip to someone new\n"
            "• /stop — end this chat"
        )
        await context.bot.send_message(
            chat_id=user1, text=connect_msg, parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=user2, text=connect_msg, parse_mode="Markdown"
        )


# ── Leaderboard ────────────────────────────────────────────────────────────────

async def handle_leaderboard(query):
    rows = await get_leaderboard(10)

    if not rows:
        await query.edit_message_text(
            "🏆 No debates yet! Be the first to climb the leaderboard.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="menu_back")]
            ]),
        )
        return

    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    lines = ["🏆 *Top Debaters*\n"]
    for i, (username, elo, wins, losses, ties, debates) in enumerate(rows):
        name = f"@{username}" if username else "Anonymous"
        lines.append(
            f"{medals[i]} {name} — *{elo} Elo* "
            f"({wins}W/{losses}L/{ties}T)"
        )

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="menu_back")]
        ]),
    )


# ── /next ──────────────────────────────────────────────────────────────────────

async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Skip in debate
    if matcher.is_waiting(user_id):
        matcher.remove_from_queue(user_id)
        await update.message.reply_text(
            "👋 Left the debate queue.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if matcher.is_in_debate(user_id):
        opponent_id = matcher.get_opponent(user_id)
        session = engine.get_debate(user_id, opponent_id)
        if session and session.timer_task and not session.timer_task.done():
            session.timer_task.cancel()
        if opponent_id:
            await context.bot.send_message(
                chat_id=opponent_id,
                text="⚠️ Your opponent skipped. Returning you to the menu.",
                reply_markup=main_menu_keyboard(),
            )
        if session:
            engine.end_debate(session)
        matcher.end_match(user_id)
        await update.message.reply_text(
            "⏩ Debate skipped.", reply_markup=main_menu_keyboard()
        )
        return

    # Skip in chat
    if chat.is_in_chat_queue(user_id):
        chat.remove_from_chat_queue(user_id)
        await update.message.reply_text("👋 Left chat queue.", reply_markup=main_menu_keyboard())
        return

    if chat.is_in_chat(user_id):
        opponent_id = chat.end_chat(user_id)
        if opponent_id:
            await context.bot.send_message(
                chat_id=opponent_id,
                text=(
                    "👤 *Stranger disconnected.*\n\n"
                    "Looking for a new chat partner... or use /stop to exit."
                ),
                parse_mode="Markdown",
            )
            # Put the opponent back in chat queue
            chat.add_to_chat_queue(opponent_id)
            match = chat.try_chat_match()
            if match:
                u1, u2 = match
                reconnect_msg = (
                    "✅ *Connected to a new stranger!*\n\nSay hi 👋\n• /next — skip\n• /stop — exit"
                )
                await context.bot.send_message(chat_id=u1, text=reconnect_msg, parse_mode="Markdown")
                await context.bot.send_message(chat_id=u2, text=reconnect_msg, parse_mode="Markdown")

        # Put current user back in queue too
        chat.add_to_chat_queue(user_id)
        await update.message.reply_text(
            "🔍 *Looking for a new chat partner...*",
            parse_mode="Markdown",
        )
        match = chat.try_chat_match()
        if match:
            u1, u2 = match
            reconnect_msg = "✅ *Connected to a new stranger!*\n\nSay hi 👋\n• /next — skip\n• /stop — exit"
            await context.bot.send_message(chat_id=u1, text=reconnect_msg, parse_mode="Markdown")
            await context.bot.send_message(chat_id=u2, text=reconnect_msg, parse_mode="Markdown")
        return

    await update.message.reply_text(
        "You're not in a debate or chat.", reply_markup=main_menu_keyboard()
    )


# ── /stop ──────────────────────────────────────────────────────────────────────

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if matcher.remove_from_queue(user_id):
        await update.message.reply_text(
            "✅ Left the debate queue.", reply_markup=main_menu_keyboard()
        )
        return

    if matcher.is_in_debate(user_id):
        opponent_id = matcher.get_opponent(user_id)
        session = engine.get_debate(user_id, opponent_id)
        if session and session.timer_task and not session.timer_task.done():
            session.timer_task.cancel()
        if opponent_id:
            await context.bot.send_message(
                chat_id=opponent_id,
                text="⚠️ Your opponent left the debate.",
                reply_markup=main_menu_keyboard(),
            )
        if session:
            engine.end_debate(session)
        matcher.end_match(user_id)
        await update.message.reply_text(
            "👋 Debate ended.", reply_markup=main_menu_keyboard()
        )
        return

    if chat.is_in_chat_queue(user_id):
        chat.remove_from_chat_queue(user_id)
        await update.message.reply_text(
            "✅ Left the chat queue.", reply_markup=main_menu_keyboard()
        )
        return

    if chat.is_in_chat(user_id):
        opponent_id = chat.end_chat(user_id)
        if opponent_id:
            await context.bot.send_message(
                chat_id=opponent_id,
                text="👤 *Stranger disconnected.*",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        await update.message.reply_text(
            "👋 Chat ended.", reply_markup=main_menu_keyboard()
        )
        return

    await update.message.reply_text(
        "You're not in a debate or chat right now.",
        reply_markup=main_menu_keyboard(),
    )


# ── Boot ───────────────────────────────────────────────────────────────────────

async def post_init(application):
    """Runs once on startup — initialize the database."""
    await init_db()
    logger.info("✅ Database initialized")


def main():
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("debate", lambda u, c: handle_debate_cmd(u, c)))
    app.add_handler(CommandHandler("next",   next_cmd))
    app.add_handler(CommandHandler("stop",   stop))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot is running...")
    app.run_polling(drop_pending_updates=True)


async def handle_debate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Typing /debate directly shows the category menu."""
    user_id = update.effective_user.id
    if matcher.is_in_debate(user_id):
        await update.message.reply_text("⚠️ You're already in a debate! Use /stop first.")
        return
    await update.message.reply_text(
        "🎯 *Choose a debate category:*",
        parse_mode="Markdown",
        reply_markup=category_keyboard(),
    )


if __name__ == "__main__":
    main()