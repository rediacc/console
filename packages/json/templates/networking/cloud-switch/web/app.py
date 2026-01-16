from flask import Flask, jsonify, render_template_string
import random
import string
import os
from datetime import datetime
import sqlite3

app = Flask(__name__)

def get_db_connection():
    try:
        conn = sqlite3.connect('/app/data/database.db')
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to SQLite: {e}")
        return None

@app.before_request
def initialize_database():
    conn = get_db_connection()
    if conn is not None:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                InsertTime DATETIME NOT NULL
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()

@app.route('/api', methods=['GET'])
def merge_records():
    name = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    insert_time = datetime.now()
    conn = get_db_connection()
    if conn is not None:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO records (Name, InsertTime) VALUES (?, ?)', (name, insert_time))
        conn.commit()
        cursor.execute('SELECT ID, Name, InsertTime FROM records ORDER BY ID DESC')
        records = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify([{'ID': x[0], 'Name': x[1], 'InsertTime': str(x[2])} for x in records])
    else:
        return jsonify(error="Database connection failed"), 500

@app.route('/')
def index():
    return render_template_string('''
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
            <title>Infinite Loop</title>
          </head>
          <body>
            <h1>API Results</h1>
            <div id="results"></div>
            <script>
              function fetchApi() {
                fetch('/api')
                  .then(response => response.json())
                  .then(data => {
                    const resultsDiv = document.getElementById('results');
                    resultsDiv.innerHTML = '';
                    data.forEach(record => {
                      const recordDiv = document.createElement('div');
                      recordDiv.textContent = `ID: ${record.ID}, Name: ${record.Name}, InsertTime: ${record.InsertTime}`;
                      resultsDiv.appendChild(recordDiv);
                    });
                  })
                  .catch(error => console.error('Error fetching API:', error));
              }
              setInterval(fetchApi, 1000);
              fetchApi(); // Initial call to populate immediately
            </script>
          </body>
        </html>
    ''')

if __name__ == '__main__':
    app.run(debug=True)