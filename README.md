# Telegram Investitsiya va Referral Bot (Python)

Ushbu bot TypeScript'dan Python-ga to'liq o'tkazildi. Botni ishga tushirish uchun quyidagi ko'rsatmalarga amal qiling.

## Tizim talablari
- Python 3.10 yoki undan yuqori versiyasi
- SQLite3 (Python tarkibida o'rnatilgan bo'ladi)

## O'rnatish va Sozlash

1. **Virtual muhitni yaratish va faollashtirish:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # macOS/Linux
   # yoki Windows-da: venv\Scripts\activate
   ```

2. **Kutubxonalarni o'rnatish:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Muhit o'zgaruvchilari (`.env`):**
   Loyiha papkasidagi `.env` faylida quyidagi o'zgaruvchilar to'g'ri sozlanganligiga ishonch hosil qiling:
   ```env
   BOT_TOKEN="sizning_bot_tokeningiz"
   ADMIN_ID=sizning_telegram_idngiz
   CARD_DETAILS="karta_raqami (egasi)"
   MIN_DEPOSIT=20000
   MIN_WITHDRAWAL=30000
   REFERRAL_BONUS=1500
   ```

## Botni ishga tushirish

Botni ishga tushirish uchun quyidagi buyruqni bosing:
```bash
./venv/bin/python3 src/main.py
```

## Texnik Tafsilotlar
- **`src/config.py`**: Muhit sozlamalarini yuklaydi.
- **`src/database.py`**: Ma'lumotlar bazasi bilan ishlash (SQLite).
- **`src/main.py`**: Bot buyruqlari, tugmalar bilan ishlash, scheduler va Render keep-alive HTTP serveri.
