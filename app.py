from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from gtts import gTTS
import os
import random
import json

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

AUDIO_FOLDER = os.path.join("static", "audio")
IMAGE_FOLDER = os.path.join("static", "images")
os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, default=100)

class Mistake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    phrase = db.Column(db.String, nullable=False)
    correct_word = db.Column(db.String, nullable=False)
    user_answer = db.Column(db.String, nullable=False)

@app.context_processor
def inject_nav_links():
    logged_in = 'user_id' in session
    return dict(
        nav_links=[
            ("🏠 Home", url_for("index")),
            ("📚 Learn", url_for("learn")),
            ("🧠 Test", url_for("test")),
            ("👤 Profile", url_for("profile") if logged_in else url_for("login")),
            ("🚪 Logout", url_for("logout") if logged_in else url_for("register"))
        ]
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        user = User(email=email, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('profile'))
        else:
            return "Invalid credentials"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    mistakes = Mistake.query.filter_by(user_id=user.id).all()
    return render_template('profile.html', user=user, mistakes=mistakes)

@app.route('/learn')
def learn():
    mode = request.args.get('mode', 'manual')
    timer = request.args.get('timer', '5')

    if not os.path.exists("data/phrases.json"):
        return "Phrases file not found."

    with open("data/phrases.json", "r", encoding="utf-8") as f:
        phrases = json.load(f)

    if not phrases:
        return "No phrases found."

    phrase = random.choice(phrases)
    text_nl = phrase['nl']

    audio_filename = f"{text_nl.replace(' ', '_')}.mp3"
    audio_path = os.path.join(AUDIO_FOLDER, audio_filename)
    if not os.path.exists(audio_path):
        tts = gTTS(text=text_nl, lang='nl')
        tts.save(audio_path)

    audio_url = url_for('static', filename=f"audio/{audio_filename}")

    image_url = None
    if 'image' in phrase:
        image_path = os.path.join(IMAGE_FOLDER, phrase['image'])
        if os.path.exists(image_path):
            image_url = url_for('static', filename=f"images/{phrase['image']}")

    return render_template("learn.html", phrase=phrase, mode=mode, timer=timer, audio_url=audio_url, image_url=image_url)

@app.route('/test', methods=['GET', 'POST'])
def test():
    if not os.path.exists("data/phrases.json"):
        return "Phrases file not found."

    with open("data/phrases.json", "r", encoding="utf-8") as f:
        all_phrases = json.load(f)

    if not all_phrases:
        return "No phrases found."

    # Сбросить тест, если нажата кнопка "Try Again"
    if request.method == 'POST' and request.form.get('restart') == '1':
        session.pop('test_phrases', None)
        session.pop('test_index', None)
        session.pop('score', None)
        session.pop('mistakes', None)
        return redirect(url_for('test'))

    if 'test_phrases' not in session or 'test_index' not in session:
        session['test_phrases'] = random.sample(all_phrases, min(10, len(all_phrases)))
        session['test_index'] = 0
        session['score'] = 0
        session['mistakes'] = []

    test_index = session['test_index']
    test_phrases = session['test_phrases']

    if test_index >= len(test_phrases):
        return render_template("test_result.html", score=session['score'], mistakes=session['mistakes'])

    score = session.get('score', 0)
    phrase = test_phrases[test_index]

    if 'current_phrase' not in session or session.get('current_phrase') != phrase['nl']:
        words = phrase['nl'].split()
        missing_index = random.randint(0, len(words) - 1)
        session['missing_word'] = words[missing_index]
        session['masked_phrase'] = ' '.join(["_____" if i == missing_index else w for i, w in enumerate(words)])
        session['current_phrase'] = phrase['nl']

    question = session['masked_phrase']
    correct_word = session['missing_word']
    hint = correct_word[0] if correct_word else ''

    if request.method == 'POST':
        user_answer = request.form.get('answer', '').strip()
        show_answer_requested = 'show_answer' in request.form

        if show_answer_requested:
            session['score'] -= 1
            return render_template("test.html", question=question, translation=phrase['en'], hint=hint, score=session['score'], number=test_index+1, show_answer=correct_word, correct_word=correct_word)

        user = User.query.get(session['user_id']) if 'user_id' in session else None

        is_correct = user_answer.lower() == correct_word.lower()
        if is_correct:
            session['score'] += 5
        else:
            session['score'] -= 5
            session['mistakes'].append({
                'phrase': phrase['nl'],
                'correct_word': correct_word,
                'user_answer': user_answer
            })
            if user:
                mistake = Mistake(user_id=user.id, phrase=phrase['nl'], correct_word=correct_word, user_answer=user_answer)
                db.session.add(mistake)

        if user:
            user.points += session['score']
            db.session.commit()

        session['test_index'] += 1
        session.pop('missing_word', None)
        session.pop('masked_phrase', None)
        session.pop('current_phrase', None)

        return render_template("test.html", question=question, translation=phrase['en'], hint=hint, score=session['score'], number=test_index+1, user_answer=user_answer, is_correct=is_correct, correct_word=correct_word)

    return render_template("test.html", question=question, translation=phrase['en'], hint=hint, score=score, number=test_index+1)

if __name__ == '__main__':
    if not os.path.exists('users.db'):
        with app.app_context():
            db.create_all()
    app.run(debug=True)
