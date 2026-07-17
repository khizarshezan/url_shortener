# URL SHORTENER
from flask import Flask, render_template, request, jsonify, redirect, session
import mysql.connector
from mysql.connector import Error
import string
import random
import uuid
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'Khizar@Dev2024'

# ---- Set your admin password here ----
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Khizar@Admin2024')

DB_CONFIG = {
    'host': os.environ.get('MYSQL_HOST'),
    'user': os.environ.get('MYSQL_USER'),
    'password': os.environ.get('MYSQL_PASSWORD'),
    'database': os.environ.get('MYSQL_DATABASE'),
    'port': int(os.environ.get('MYSQL_PORT', 3306))
}

def get_db():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        print(f"DB Error: {e}")
        return None

def init_db():
    conn = get_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS short_urls (
                id INT AUTO_INCREMENT PRIMARY KEY,
                original_url TEXT,
                short_code VARCHAR(10) UNIQUE,
                title VARCHAR(255),
                session_id VARCHAR(100),
                click_count INT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_clicked DATETIME
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS url_clicks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                short_code VARCHAR(10),
                clicked_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        print("Database initialized.")

def generate_code(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

@app.before_request
def assign_session():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/shorten', methods=['POST'])
def shorten():
    data = request.json
    original_url = data.get('url', '').strip()
    title = data.get('title', 'Untitled').strip()

    if not original_url.startswith(('http://', 'https://')):
        original_url = 'https://' + original_url

    conn = get_db()
    if not conn:
        return jsonify({'error': 'DB connection failed'})

    short_code = generate_code()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO short_urls (original_url, short_code, title, session_id, created_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (original_url, short_code, title, session['user_id'], datetime.now()))
    conn.commit()
    conn.close()

    base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
    short_url = f"{base_url}/{short_code}"
    return jsonify({'short_url': short_url, 'short_code': short_code})

@app.route('/<short_code>')
def redirect_url(short_code):
    # Don't redirect admin routes
    if short_code in ['admin', 'api']:
        return "Not found", 404

    conn = get_db()
    if not conn:
        return "Error", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM short_urls WHERE short_code = %s", (short_code,))
    url_data = cursor.fetchone()

    if not url_data:
        conn.close()
        return "URL not found", 404

    cursor.execute("""
        UPDATE short_urls SET click_count = click_count + 1, last_clicked = %s 
        WHERE short_code = %s
    """, (datetime.now(), short_code))
    cursor.execute("INSERT INTO url_clicks (short_code, clicked_at) VALUES (%s, %s)",
                   (short_code, datetime.now()))
    conn.commit()
    conn.close()
    return redirect(url_data['original_url'])

@app.route('/api/urls', methods=['GET'])
def get_urls():
    conn = get_db()
    if not conn:
        return jsonify([])
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM short_urls WHERE session_id = %s ORDER BY created_at DESC",
                   (session.get('user_id'),))
    urls = cursor.fetchall()
    conn.close()
    for u in urls:
        u['created_at'] = str(u['created_at'])
        u['last_clicked'] = str(u['last_clicked']) if u['last_clicked'] else 'Never'
    return jsonify(urls)

@app.route('/api/urls/<int:id>', methods=['DELETE'])
def delete_url(id):
    conn = get_db()
    if not conn:
        return jsonify({'error': 'DB connection failed'})
    cursor = conn.cursor()
    cursor.execute("DELETE FROM short_urls WHERE id = %s AND session_id = %s",
                   (id, session.get('user_id')))
    cursor.execute("DELETE FROM url_clicks WHERE short_code = (SELECT short_code FROM short_urls WHERE id = %s)", (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ============== ADMIN ROUTES ==============

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect('/admin')
        else:
            return render_template('admin_login.html', error='Wrong password')

    if not session.get('is_admin'):
        return render_template('admin_login.html', error=None)

    return render_template('admin.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect('/')

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    if not conn:
        return jsonify({'error': 'DB connection failed'})

    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) as total_urls FROM short_urls")
    total_urls = cursor.fetchone()['total_urls']

    cursor.execute("SELECT COUNT(DISTINCT session_id) as total_users FROM short_urls")
    total_users = cursor.fetchone()['total_users']

    cursor.execute("SELECT SUM(click_count) as total_clicks FROM short_urls")
    result = cursor.fetchone()
    total_clicks = result['total_clicks'] or 0

    cursor.execute("SELECT COUNT(*) as today_urls FROM short_urls WHERE DATE(created_at) = CURDATE()")
    today_urls = cursor.fetchone()['today_urls']

    conn.close()

    return jsonify({
        'total_urls': total_urls,
        'total_users': total_users,
        'total_clicks': int(total_clicks),
        'today_urls': today_urls
    })

@app.route('/api/admin/urls', methods=['GET'])
def admin_get_all_urls():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    if not conn:
        return jsonify([])

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM short_urls ORDER BY created_at DESC")
    urls = cursor.fetchall()
    conn.close()

    for u in urls:
        u['created_at'] = str(u['created_at'])
        u['last_clicked'] = str(u['last_clicked']) if u['last_clicked'] else 'Never'
    return jsonify(urls)

@app.route('/api/admin/urls/<int:id>', methods=['DELETE'])
def admin_delete_url(id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    if not conn:
        return jsonify({'error': 'DB connection failed'})
    cursor = conn.cursor()
    cursor.execute("SELECT short_code FROM short_urls WHERE id = %s", (id,))
    result = cursor.fetchone()
    if result:
        cursor.execute("DELETE FROM url_clicks WHERE short_code = %s", (result[0],))
    cursor.execute("DELETE FROM short_urls WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/reset-db')
def reset_db():
    conn = get_db()
    if conn:
        cursor = conn.cursor()
        # Drop the old tables
        cursor.execute("DROP TABLE IF EXISTS url_clicks")
        cursor.execute("DROP TABLE IF EXISTS short_urls")
        conn.commit()
        conn.close()
        
        # Re-create them with the new session_id column
        init_db() 
        return "Database reset successful! You can now use the app."
    return "Failed to connect to database."
    
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
