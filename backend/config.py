import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── Discovery ─────────────────────────────────────────────────────────────────
DATA_SOURCE: str  = os.getenv("DATA_SOURCE", "mock")   # "mock" | "apify"
APIFY_TOKEN: str  = os.getenv("APIFY_TOKEN", "")

# ── Sending ───────────────────────────────────────────────────────────────────
SEND_MODE: str    = os.getenv("SEND_MODE", "simulate") # "simulate" | "smtp"
SMTP_HOST: str    = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str    = os.getenv("SMTP_USER", "")
SMTP_PASS: str    = os.getenv("SMTP_PASS", "")

# ── Notifications ─────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")

# ── App ───────────────────────────────────────────────────────────────────────
DB_PATH: str      = os.getenv("DB_PATH", "outreach.db")
BRAND_NAME: str   = os.getenv("BRAND_NAME", "GlowLab")
