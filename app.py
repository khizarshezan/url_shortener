# URL SHORTENER
from flask import Flask, render_template, request, jsonify, redirect
import mysql.connector
from mysql.connector import Error
import string
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'Khizar@Dev2024'

import os
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
        INSERT INTO short_urls (original_url, short_code, title, created_at)
        VALUES (%s, %s, %s, %s)
    """, (original_url, short_code, title, datetime.now()))
    conn.commit()
    conn.close()

    short_url = f"http://localhost:5000/{short_code}"
    return jsonify({'short_url': short_url, 'short_code': short_code})

@app.route('/<short_code>')
def redirect_url(short_code):
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
    cursor.execute("SELECT * FROM short_urls ORDER BY created_at DESC")
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
    cursor.execute("DELETE FROM short_urls WHERE id = %s", (id,))
    cursor.execute("DELETE FROM url_clicks WHERE short_code = (SELECT short_code FROM short_urls WHERE id = %s)", (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
