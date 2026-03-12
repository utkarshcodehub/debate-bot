# config.py
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME")  # for invite links

TOTAL_ROUNDS = 3
ROUND_TIME_LIMIT = 90  # seconds per argument

# Categorized topics — users pick a category, bot picks a topic within it
TOPIC_CATEGORIES = {
    "💻 Technology": [
        "Should AI eventually replace human teachers, or will human mentorship always be necessary in education?",
        "Has social media improved global communication more than it has harmed mental health and relationships?",
        "Should coding and AI literacy be mandatory subjects in schools, just like mathematics and science?",
        "Is remote work the future of productivity, or does office culture still provide irreplaceable benefits?",
        "Will artificial intelligence create more jobs than it destroys over the next 20 years?",
    ],

    "🧠 Philosophy": [
        "Do humans truly have free will, or are our choices determined by biology and environment?",
        "Is morality universal across cultures, or does each society define its own moral rules?",
        "Is living a happy life more important than living a meaningful or impactful one?",
        "Do humans have a moral obligation to protect nature even if it slows economic growth?",
        "Is ignorance sometimes better for happiness, or is truth always worth knowing?",
    ],

    "🏛️ Politics": [
        "Should voting be mandatory in democratic countries, or should participation remain a personal choice?",
        "Does capitalism create more opportunity and innovation than socialism, or does it increase inequality?",
        "Should the death penalty exist as a form of justice, or should all countries abolish it permanently?",
        "Is democracy truly the best form of government, or could other systems be more effective?",
        "Should countries open their borders to more immigrants, or should they prioritize strict immigration control?",
    ],

    "❤️ Relationships": [
        "Is social media strengthening relationships by keeping people connected, or damaging them by creating unrealistic expectations?",
        "Should couples share passwords and digital privacy, or should personal boundaries remain respected?",
        "Are long-distance relationships sustainable with modern technology, or are they fundamentally unstable?",
        "Should couples live together before marriage to test compatibility, or does it weaken commitment?",
        "Is deep friendship ultimately more fulfilling than romantic relationships?",
    ],

    "💰 Economics": [
        "Should college education be free for everyone, or should students contribute financially to maintain quality?",
        "Is cryptocurrency a revolutionary financial system, or is it mostly speculation and instability?",
        "Should governments tax unhealthy foods like junk food to improve public health?",
        "Would universal basic income reduce poverty and inequality, or discourage people from working?",
        "Is extreme wealth accumulation acceptable in capitalism, or should billionaires be heavily regulated or taxed?",
    ],
}

LABEL_A = "Debater A"
LABEL_B = "Debater B"

# Elo settings
ELO_START = 1000
ELO_K_FACTOR = 32