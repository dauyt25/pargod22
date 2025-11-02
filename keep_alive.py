from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "הבוט חי!"

# 🔽 --- הוסף את הקטע הבא --- 🔽
@app.route('/wakeup')
def wakeup_from_yemot():
    """
    נתיב זה מיועד לקריאה ממערכת ימות המשיח.
    הוא מחזיר פקודת טקסט פשוטה שימות המשיח מבין.
    """
    #
    # פקודה זו גורמת לימות להשמיע "השרת התעורר בהצלחה"
    # באמצעות מנוע הקראת טקסט (TTS).
    response_text = "id_list_message=t-השרת התעורר בהצלחה"
    
    # מחזירים את הטקסט הפשוט, שימות המשיח יקרא
    return response_text
# 🔼 --- סוף הקטע להוספה --- 🔼

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
