from flask import Flask, make_response
from threading import Thread

app = Flask('')

# 🔽 --- הוספנו משתנה גלובלי --- 🔽
# המשתנה הזה יהיה נכון רק כשהשרת בדיוק נטען (מתעורר)
server_just_woke_up = True
# 🔼 --- --- --- 🔼


@app.route('/')
def home():
    return "הבוט חי!"

@app.route('/wakeup')
def wakeup_from_yemot():
    # ניגש למשתנה הגלובלי
    global server_just_woke_up
    
    # בודקים את מצב השרת
    if server_just_woke_up:
        # זו הפעם הראשונה, השרת בדיוק התעורר
        response_text = "id_list_message=t-השרת התעורר בהצלחה"
        # משנים את המשתנה כדי שבפעמים הבאות נדע שהוא כבר ער
        server_just_woke_up = False
    else:
        # השרת כבר היה ער
        response_text = "id_list_message=t-השרת כבר היה ער"

    # 🔽 --- זה התיקון לבעיית ה"שגיאה" --- 🔽
    # 1. יוצרים אובייקט תגובה מלא
    response = make_response(response_text)
    
    # 2. מגדירים במפורש את הכותרת לטקסט פשוט (כפי שימות דורשים)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    
    # 3. מחזירים את התגובה המתוקנת
    return response
    # 🔼 --- --- --- 🔼

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
