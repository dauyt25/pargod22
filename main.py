import os
import json
import subprocess
import requests
import base64
from datetime import datetime
import pytz
import asyncio
import re

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, TypeHandler
from google.cloud import texttospeech

# 🟡 כתיבת קובץ מפתח Google מ־BASE64
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

# 📌 מספרי צינתוק – תכניס כאן ערכים נכונים
YMOT_DID = os.getenv("YMOT_DID", "YOUR_DID")   # המספר שלך במערכת
YMOT_DST = os.getenv("YMOT_DST", "YOUR_DEST") # מספר היעד לצינתוק

# 🔢 המרת מספרים לעברית
def num_to_hebrew_words(hour, minute):
    hours_map = {
        1: "אחת", 2: "שתיים", 3: "שלוש", 4: "ארבע", 5: "חמש",
        6: "שש", 7: "שבע", 8: "שמונה", 9: "תשע", 10: "עשר",
        11: "אחת עשרה", 12: "שתים עשרה"
    }
    minutes_map = {0: "אפס", 1: "ודקה", 2: "ושתי דקות", 3: "ושלוש דקות", 4: "וארבע דקות",
        5: "וחמש דקות", 6: "ושש דקות", 7: "ושבע דקות", 8: "ושמונה דקות", 9: "ותשע דקות", 10: "ועשרה",
        15: "ורבע", 30: "וחצי", 45: "וארבעים וחמש"}
    hour_12 = hour % 12 or 12
    return f"{hours_map[hour_12]} {minutes_map.get(minute, str(minute))}"

def clean_text(text):
    BLOCKED_PHRASES = ["חדשות המוקד", "t.me/hamoked_il"]
    for phrase in BLOCKED_PHRASES:
        text = text.replace(phrase, '')
    text = re.sub(r'https?://\S+', '', text)
    return text.strip()

def create_full_text(text):
    tz = pytz.timezone('Asia/Jerusalem')
    now = datetime.now(tz)
    hebrew_time = num_to_hebrew_words(now.hour, now.minute)
    return f"{hebrew_time} בחדשות הפרגוד. {text}"

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
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )
    with open(filename, "wb") as out:
        out.write(response.audio_content)

def convert_to_wav(input_file, output_file='output.wav'):
    print(f"🎧 ממיר קובץ {input_file} ל־WAV…")
    subprocess.run([
        'ffmpeg', '-i', input_file, '-ar', '8000', '-ac', '1', '-f', 'wav',
        output_file, '-y'
    ])

def upload_to_ymot(wav_file_path):
    print(f"📤 מעלה לימות: {wav_file_path}")
    url = 'https://call2all.co.il/ym/api/UploadFile'
    with open(wav_file_path, 'rb') as f:
        files = {'file': (os.path.basename(wav_file_path), f, 'audio/wav')}
        data = {
            'token': YMOT_TOKEN,
            'path': YMOT_PATH,
            'convertAudio': '1',
            'autoNumbering': 'true'
        }
        response = requests.post(url, data=data, files=files)
    print("📞 תגובת ימות:", response.status_code, response.text)

# 📞 שליחת צינתוק ישיר עם דיבוג מלא
def _send_tzintuk_sync():
    url = "https://www.call2all.co.il/ym/api/Calls/MissCall"
    data = {
        "token": YMOT_TOKEN,
        "did": YMOT_DID,
        "dst": YMOT_DST
    }
    try:
        print("📡 שולח בקשת צינתוק:", data)
        response = requests.post(url, data=data, timeout=10)
        print("📡 סטטוס HTTP:", response.status_code)
        return response.text
    except Exception as e:
        print("❌ שגיאה בצינתוק:", e)
        return f"שגיאה בשליחת צינתוק: {str(e)}"

async def send_tzintuk():
    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(None, _send_tzintuk_sync)
    print("📢 תגובת צינתוק:", text)

# 📥 טיפול בהודעות
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.channel_post
    if not message:
        return

    text = message.text or message.caption
    has_video = message.video is not None
    has_audio = message.audio is not None or message.voice is not None

    if has_video:
        video_file = await message.video.get_file()
        await video_file.download_to_drive("video.mp4")
        convert_to_wav("video.mp4", "video.wav")
        upload_to_ymot("video.wav")
        print("➡️ מנסה לשלוח צינתוק אחרי וידאו")
        await send_tzintuk()
        print("✅ סיים צינתוק אחרי וידאו")
        os.remove("video.mp4")
        os.remove("video.wav")

    if has_audio:
        audio_file = await (message.audio or message.voice).get_file()
        await audio_file.download_to_drive("audio.ogg")
        convert_to_wav("audio.ogg", "audio.wav")
        upload_to_ymot("audio.wav")
        print("➡️ מנסה לשלוח צינתוק אחרי אודיו")
        await send_tzintuk()
        print("✅ סיים צינתוק אחרי אודיו")
        os.remove("audio.ogg")
        os.remove("audio.wav")

    if text:
        cleaned = clean_text(text)
        full_text = create_full_text(cleaned)
        text_to_mp3(full_text, "output.mp3")
        convert_to_wav("output.mp3", "output.wav")
        upload_to_ymot("output.wav")
        print("➡️ מנסה לשלוח צינתוק אחרי טקסט")
        await send_tzintuk()
        print("✅ סיים צינתוק אחרי טקסט")
        os.remove("output.mp3")
        os.remove("output.wav")

# ♻️ שמירה על חיים
from keep_alive import keep_alive
keep_alive()

# ▶️ הפעלת הבוט
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(TypeHandler(Update, handle_message))

print("🚀 הבוט מאזין להודעות! כל הודעה → שלוחה 🎧 + צינתוק 📞")

app.run_polling()
