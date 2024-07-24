import sqlite3

conn = sqlite3.connect('wallets.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS wallets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address TEXT,
        name TEXT
    )
''')
conn.commit()
conn.close()
