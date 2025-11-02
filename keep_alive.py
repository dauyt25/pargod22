from flask import Flask, make_response
from threading import Thread

app = Flask('')

# המשתנה הזה יהיה נכון רק כשהשרת בדיוק נטען (מתעורר)
server_just_woke_up = True

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
        text_to_say = "id_list_message=t-השרת התעורר בהצלחה"
        # משנים את המשתנה כדי שבפעמים הבאות נדע שהוא כבר ער
        server_just_woke_up = False
    else:
        # השרת כבר היה ער
        text_to_say = "id_list_message=t-השרת כבר היה ער"

    # --- 🔽 התיקון המרכזי (קידוד) 🔽 ---
    
    # 1. נקודד את המחרוזת העברית לקידוד הספציפי (windows-1255)
    #    זה הקידוד הנפוץ ביותר במערכות ישראליות ישנות.
    try:
        response_bytes = text_to_say.encode('windows-1255')
        charset_to_use = 'windows-1255'
    except Exception as e:
        # גיבוי: אם מסיבה כלשהי השרת לא תומך בקידוד הזה, נחזור ל-utf-8
        print(f"Warning: Could not encode in windows-1255 ({e}). Falling back to utf-8.")
        response_bytes = text_to_say.encode('utf-8')
        charset_to_use = 'utf-8'

    # 2. ניצור אובייקט תגובה מה-bytes המקודדים
    response = make_response(response_bytes)
    
    # 3. נגדיר את הכותרת (header) שתתאים במדויק לקידוד שבו השתמשנו
    response.headers['Content-Type'] = f'text/plain; charset={charset_to_use}'
    
    # 4. נחזיר את התגובה המקודדת
    return response
    # --- 🔼 סוף התיקון 🔼 ---

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
