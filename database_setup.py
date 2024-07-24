import sqlite3
def create_tables():
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS wallets (
        address TEXT PRIMARY KEY,
        name TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tokens (
        address TEXT PRIMARY KEY,
        ticker TEXT,
        name TEXT
    )
    ''')
    conn.commit()
    conn.close()

# Вызовите эту функцию при запуске бота
create_tables()