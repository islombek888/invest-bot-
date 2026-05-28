import os
from pathlib import Path
from dotenv import load_dotenv

# Find the workspace root (where .env lives)
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
    CARD_DETAILS = os.getenv('CARD_DETAILS', 'Karta raqami kiritilmagan')
    MIN_DEPOSIT = float(os.getenv('MIN_DEPOSIT', '20000'))
    MIN_WITHDRAWAL = float(os.getenv('MIN_WITHDRAWAL', '30000'))
    REFERRAL_BONUS = float(os.getenv('REFERRAL_BONUS', '1500'))
    MIN_REFERRALS = int(os.getenv('MIN_REFERRALS', '3'))
    DB_PATH = os.getenv('DB_PATH', str(ROOT_DIR / 'database.db'))

config = Config()
