import os
import json
import subprocess
import requests
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import asyncio
import re
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, TypeHandler
from google.cloud import texttospeech
import logging
import google.generativeai as genai

# 🔧 הגדרת לוגים לקובץ וגם לקונסולה
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("log.txt"),
        logging.StreamHandler()
    ]
)

# 🔒 מנעול לעיבוד הודעות - מונע קריסה עקב עומס זיכרון ב-Render
processing_lock = asyncio.Lock()

# 🟡 כתיבת קובץ מפתח Google מ־BASE64 (עבור TTS)
key_b64 = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_B64")
if not key_b64:
    raise Exception("❌ משתנה GOOGLE_APPLICATION_CREDENTIALS_B64 לא מוגדר או ריק")
try:
    with open("google_key.json", "wb") as f:
        f.write(base64.b64decode(key_b64))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_key.json"
except Exception as e:
    raise Exception("❌ נכשל בכתיבת קובץ JSON מ־BASE64: " + str(e))

# 🛠 משתנים מ־Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
YMOT_TOKEN = os.getenv("YMOT_TOKEN")
YMOT_PATH = os.getenv("YMOT_PATH", "ivr2:95/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 

# 🧠 הגדרת ג'מיני (נטען פעם אחת בלבד כדי לחסוך זיכרון)
model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")
else:
    logging.warning("⚠️ לא הוגדר מפתח GEMINI_API_KEY! הסינון לא יעבוד.")

# 🤖 פונקציה לבדיקת תוכן מול ג'מיני
async def check_content_with_gemini(text):
    if not GEMINI_API_KEY or not model:
        return True 

    try:
        # 📂 קריאת ההוראות מקובץ חיצוני
        try:
            with open("gemini_prompt.txt", "r", encoding="utf-8") as f:
                prompt_instructions = f.read()
        except FileNotFoundError:
            logging.error("⚠️ קובץ ההוראות gemini_prompt.txt לא נמצא! משתמש בהוראות ברירת מחדל.")
            prompt_instructions = "סווג את ההודעה הבאה. השב APPROVE אם היא הולמת ו-BLOCK אם לא."

        # בניית ה-Prompt הסופי
        full_prompt = f"""
        {prompt_instructions}
        
        הטקסט לבדיקה: "{text}"
        
        הוראות מתן תשובה (קריטי):
        1. אם ההודעה תקינה ומותרת לשידור, השב רק במילה אחת: APPROVE
        2. אם ההודעה מכילה תוכן בעייתי, השב בפורמט הבא בדיוק: BLOCK: [כתוב כאן את המילה או המשפט הבעייתי]
           לדוגמה: BLOCK: המילה 'אינסטגרם' אסורה
        """
        
        response = await model.generate_content_async(full_prompt)
        answer = response.text.strip()
        
        logging.info(f"🤖 תשובת ג'מיני המלאה: {answer}")
        
        if answer.upper().startswith("BLOCK"):
            reason = "סיבה לא פורטה"
            if ":" in answer:
                reason = answer.split(":", 1)[1].strip()
            
            logging.info(f"❌ ג'מיני חסם את ההודעה. הסיבה שזוהתה: '{reason}'")
            return False
            
        return True

    except Exception as e:
        logging.error(f"❌ שגיאה בבדיקת ג'מיני: {e}")
        return True 

# 🔢 המרת מספרים לעברית
def num_to_hebrew_words(hour, minute):
    hours_map = {
        1: "אחת", 2: "שתיים", 3: "שלוש", 4: "ארבע", 5: "חמש", 6: "שש",
        7: "שבע", 8: "שמונה", 9: "תשע", 10: "עשר", 11: "אחת עשרה", 12: "שתים עשרה"
    }
    minutes_map = {
        0: "אפס", 1: "ודקה", 2: "ושתי דקות", 3: "ושלוש דקות", 4: "וארבע דקות",
        5: "וחמש דקות", 6: "ושש דקות", 7: "ושבע דקות", 8: "ושמונה דקות",
        9: "ותשע דקות", 10: "ועשרה", 11: "ואחת עשרה דקות", 12: "ושתים עשרה דקות",
        13: "ושלוש עשרה דקות", 14: "וארבע עשרה דקות", 15: "ורבע", 14: "וארבע עשרה דקות",
        16: "ושש עשרה דקות",
        17: "ושבע עשרה דקות", 18: "ושמונה עשרה דקות", 19: "ותשע עשרה דקות",
        20: "ועשרים", 21: "עשרים ואחת", 22: "עשרים ושתיים", 23: "עשרים ושלוש",
        24: "עשרים וארבע", 25: "עשרים וחמש", 26: "עשרים ושש", 27: "עשרים ושבע",
        28: "עשרים ושמונה", 29: "עשרים ותשע", 30: "וחצי", 31: "שלושים ואחת",
        32: "שלושים ושתיים", 33: "שלושים ושלוש", 34: "שלושים וארבע",
        35: "שלושים וחמש", 36: "שלושים ושש", 37: "שלושים ושבע",
        38: "שלושים ושמונה", 39: "שלושים ותשע", 40: "וארבעים דקות",
        41: "ארבעים ואחת", 42: "ארבעים ושתיים", 43: "ארבעים ושלוש",
        44: "ארבעים וארבע", 45: "ארבעים וחמש", 46: "ארבעים ושש",
        47: "ארבעים ושבע", 48: "ארבעים ושמונה", 49: "ארבעים ותשע",
        50: "וחמישים דקות", 51: "חמישים ואחת", 52: "חמישים ושתיים",
        53: "חמישים ושלוש", 54: "חמישים וארבע", 55: "חמישים וחמש",
        56: "חמישים ושש", 57: "חמישים ושבע", 58: "חמישים ושמונה", 59: "חמישים ותשע"
    }
    hour_12 = hour % 12 or 12
    return f"{hours_map[hour_12]} {minutes_map[minute]}"

def clean_text(text):
    BLOCKED_PHRASES = sorted([
        "לעדכוני",
        "בטלגרם",
        "בטלגרם",
        "'הכי חם ברשת - 'הערינג",
        "וואטצפ",
        "טלגרם",
        "לשליחת חומרים",
    ], key=len, reverse=True)
    for phrase in BLOCKED_PHRASES:
        text = text.replace(phrase, '')
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    text = re.sub(r'[^\w\s.,!?()\u0590-\u05FF]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# 🧠 יוצר טקסט מלא כולל שעה
def create_full_text(text):
    tz = ZoneInfo('Asia/Jerusalem')
    now = datetime.now(tz)
    hebrew_time = num_to_hebrew_words(now.hour, now.minute)
    return f"{hebrew_time} בחדשות המגזר. {text}"

# 🎤 יצירת MP3 עם Google TTS
def text_to_mp3(text, filename='output.mp3'):
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="he-IL",
        name="he-IL-Wavenet-B",
        ssml_gender=texttospeech.SsmlVoiceGender.MALE
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.2
    )
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )
    with open(filename, "wb") as out:
        out.write(response.audio_content)

# 🎧 המרה ל־WAV בפורמט ימות
def convert_to_wav(input_file, output_file='output.wav'):
    subprocess.run([
        'ffmpeg', '-i', input_file,
        '-ar', '8000', '-ac', '1', '-f', 'wav', output_file, '-y'
    ])

# 🔗 חיבור טקסט+וידאו
def concat_wav_files(file1, file2, output_file="merged.wav"):
    tmp1 = "tmp1.wav"
    tmp2 = "tmp2.wav"
    subprocess.run(["ffmpeg", "-y", "-i", file1, "-ar", "8000", "-ac", "1", tmp1])
    subprocess.run(["ffmpeg", "-y", "-i", file2, "-ar", "8000", "-ac", "1", tmp2])
    with open("list.txt", "w", encoding="utf-8") as f:
        f.write(f"file '{tmp1}'\n")
        f.write(f"file '{tmp2}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", "list.txt", "-c", "copy", output_file
    ])
    os.remove(tmp1)
    os.remove(tmp2)
    os.remove("list.txt")

# 📤 העלאה לשלוחה - מעודכן לקבל נתיב דינמי
def upload_to_ymot(wav_file_path, target_path=None):
    # אם לא סופק נתיב, השתמש בנתיב הראשי
    final_path = target_path if target_path else YMOT_PATH
    
    url = 'https://call2all.co.il/ym/api/UploadFile'
    with open(wav_file_path, 'rb') as f:
        files = {'file': (os.path.basename(wav_file_path), f, 'audio/wav')}
        data = {
            'token': YMOT_TOKEN,
            'path': final_path,
            'convertAudio': '1',
            'autoNumbering': 'true'
        }
        response = requests.post(url, data=data, files=files)
    logging.info(f"📞 תגובת ימות ({final_path}): {response.text}")

# 📥 טיפול בהודעות
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🛑 נעילת התהליך: רק הודעה אחת מעובדת בכל רגע נתון
    async with processing_lock:

        message = update.message or update.channel_post
        if not message:
            return

        text = message.text or message.caption
        has_video = message.video is not None
        has_audio = message.audio is not None or message.voice is not None

        # ברירת מחדל: לשלוחה הראשית
        upload_target_path = YMOT_PATH

        # ---------------------------------------------------------
        # שלב 1: בדיקות חסימה "קשות" (טלפונים, קישורים)
        # זה מתבצע תמיד אם יש טקסט, גם אם יש וידאו
        # ---------------------------------------------------------
        if text:
            WHITELISTED_PHONES = ["053-419-0216", "050-123-4567"] 
            PHONE_PATTERN = r'(0\d{1,2}[-.\s]?\d{3}[-.\s]?\d{4})'
            
            normalized_text = re.sub(r'[-.\s]', '', text) 
            found_phones = re.findall(PHONE_PATTERN, text)
            
            should_reject_phone = False
            for phone in found_phones:
                normalized_found_phone = re.sub(r'\D', '', phone)
                is_whitelisted = False
                for wl_phone in WHITELISTED_PHONES:
                    if normalized_found_phone == re.sub(r'\D', '', wl_phone):
                        is_whitelisted = True
                        break
                if not is_whitelisted:
                    should_reject_phone = True
                    break
            
            if should_reject_phone:
                logging.info(f"🚫 ההודעה לא תועלה כי מכילה מספר טלפון לא מורשה.")
                return

            if re.search(r'https?://', text):
                if "https://t.me/Moshepargod" not in text:
                    logging.info("🚫 ההודעה לא תועלה כי מכילה קישור לא מורשה.")
                    return

        # ---------------------------------------------------------
        # שלב 2: קביעת נתיב העלאה לפי סוג ההודעה
        # ---------------------------------------------------------

        # מקרה א': יש גם וידאו וגם טקסט -> תמיד ל-95 (לפי בקשה)
        if has_video and text:
            upload_target_path = "ivr2:95/"
            logging.info("📹 זוהתה הודעת וידאו+טקסט. מוגדרת אוטומטית לשלוחה 95.")

        # מקרה ב': רק טקסט -> בדיקת ג'מיני
        elif text and not has_video:
            is_content_safe = await check_content_with_gemini(text)
            if not is_content_safe:
                logging.info("🚫 ג'מיני סימן את ההודעה כבעייתית. היא תועלה לשלוחה 95.")
                upload_target_path = "ivr2:95/" 

        # מקרה ג': וידאו בלבד או אודיו בלבד -> נשאר בברירת מחדל (95)

        # ---------------------------------------------------------
        # שלב 3: עיבוד והעלאה
        # ---------------------------------------------------------

        # 🎥 וידאו עם טקסט
        if has_video and text:
            video_file = await message.video.get_file()
            await video_file.download_to_drive("video.mp4")
            convert_to_wav("video.mp4", "video.wav")
            
            cleaned = clean_text(text)
            full_text = create_full_text(cleaned)
            text_to_mp3(full_text, "text.mp3")
            convert_to_wav("text.mp3", "text.wav")
            
            concat_wav_files("text.wav", "video.wav", "final.wav")
            
            upload_to_ymot("final.wav", upload_target_path)

            for f in ["video.mp4", "video.wav", "text.mp3", "text.wav", "final.wav"]:
                if os.path.exists(f): os.remove(f)
            return

        # 🎥 וידאו ללא טקסט
        if has_video:
            video_file = await message.video.get_file()
            await video_file.download_to_drive("video.mp4")
            convert_to_wav("video.mp4", "video.wav")
            
            upload_to_ymot("video.wav", upload_target_path)

            os.remove("video.mp4")
            os.remove("video.wav")

        # 🎤 אודיו
        if has_audio:
            audio_file = await (message.audio or message.voice).get_file()
            await audio_file.download_to_drive("audio.ogg")
            convert_to_wav("audio.ogg", "audio.wav")
            
            upload_to_ymot("audio.wav", upload_target_path)

            os.remove("audio.ogg")
            os.remove("audio.wav")

        # 📝 טקסט בלבד
        if text:
            cleaned = clean_text(text)
            full_text = create_full_text(cleaned)
            text_to_mp3(full_text, "output.mp3")
            convert_to_wav("output.mp3", "output.wav")
            
            upload_to_ymot("output.wav", upload_target_path)

            os.remove("output.mp3")
            os.remove("output.wav")

# ♻️ שמירה על חיים
from keep_alive import keep_alive
keep_alive()

# ▶️ הפעלת הבוט
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(TypeHandler(Update, handle_message))
logging.info("🚀 הבוט מאזין להודעות מערוצים! 🎧")

while True:
    try:
        app.run_polling(
            poll_interval=10.0,
            timeout=30,
            allowed_updates=Update.ALL_TYPES
        )
    except Exception as e:
        logging.exception("❌ שגיאה כללית בהרצת הבוט:")
        time.sleep(10)
