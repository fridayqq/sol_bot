import sqlite3

conn = sqlite3.connect('wallets.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS wallets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address TEXT NOT NULL
    )
''')
conn.commit()
conn.close()
