import telebot
import sqlite3
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
from dotenv import load_dotenv
import os

load_dotenv()
# Telegram bot token
token = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(token)

# Solana RPC endpoint
SOLANA_RPC_ENDPOINT = 'https://api.mainnet-beta.solana.com'

# Whitelist of allowed user IDs
ALLOWED_USERS = [username.strip() for username in os.getenv('ALLOWED_USERS', '').split(',') if username.strip()]

# Decorator to check if user is in whitelist
def user_allowed(func):
    def wrapper(message):
        if not ALLOWED_USERS or (message.from_user.username and message.from_user.username.lower() in [u.lower() for u in ALLOWED_USERS]):
            return func(message)
        else:
            bot.reply_to(message, "Sorry, you are not authorized to use this bot.")
    return wrapper


def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    keyboard.row(KeyboardButton('Check Balance'), KeyboardButton('List Wallets'))
    keyboard.row(KeyboardButton('Add Wallet'), KeyboardButton('Remove Wallet'))
    keyboard.row(KeyboardButton('Rename Wallet'), KeyboardButton('Help'))
    return keyboard

@bot.message_handler(commands=['start', 'help'])
@user_allowed
def send_welcome(message):
    help_text = """
<b>Welcome! Here are the available commands:</b>
Check Balance - Check token balances
Add Wallet - Add a new wallet with an optional name
List Wallets - List all wallets in the database
Remove Wallet - Remove a wallet from the database
Rename Wallet - Rename a wallet
Help - Show this help message
    """
    bot.reply_to(message, help_text, parse_mode='HTML', reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: message.text == 'Check Balance')
@user_allowed
def check_balance_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the contract address and ticker (for example): \n\n<b>/check_balance EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm $WIF</b>\n\n<code>/check_balance </code>', parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == 'Add Wallet')
@user_allowed
def add_wallet_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the wallet address and optional name:\n\n<code>/add_wallet </code>', parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == 'Remove Wallet')
@user_allowed
def remove_wallet_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the wallet address to remove:\n\n<code>/remove_wallet </code>', parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == 'Rename Wallet')
@user_allowed
def rename_wallet_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the wallet address and new name:\n\n<code>/rename_wallet </code>', parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == 'List Wallets')
@user_allowed
def list_wallets_command(message):
    list_wallets(message)

@bot.message_handler(func=lambda message: message.text == 'Help')
@user_allowed
def help_command(message):
    send_welcome(message)

@bot.message_handler(commands=['check_balance'])
@user_allowed
def check_balance(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, 'Usage: /check_balance &lt;contract_address&gt; [ticker]', reply_markup=create_main_keyboard())
        return
    
    contract_address = parts[1]
    ticker = parts[2] if len(parts) > 2 else None
    
    # Проверяем, есть ли токен в базе данных
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ticker, name FROM tokens WHERE address = ?', (contract_address,))
    token_info = cursor.fetchone()
    
    if token_info:
        ticker, token_name = token_info
    elif ticker:
        # Если тикер указан вручную, сохраняем его в базу данных
        cursor.execute('INSERT OR REPLACE INTO tokens (address, ticker) VALUES (?, ?)', (contract_address, ticker))
        conn.commit()
    else:
        # Если тикер не указан и не найден в базе, запрашиваем его у пользователя
        bot.reply_to(message, 'Please provide the ticker for this token:')
        bot.register_next_step_handler(message, process_ticker, contract_address)
        conn.close()
        return
    
    conn.close()
    
    balances, total_wallets, wallets_with_balance = asyncio.run(get_balances(contract_address))
    
    if not balances:
        bot.reply_to(message, 'No balances found for the provided contract address.', reply_markup=create_main_keyboard())
    else:
        response_lines = []
        for address, (balance, name) in balances.items():
            name_str = f"Name: {name}\n" if name else ""
            response_lines.append(f"Address: <code>{address}</code>\n{name_str}Balance: <code>{balance:.6f} {ticker}</code>\n")
        
        percentage = (wallets_with_balance / total_wallets) * 100 if total_wallets > 0 else 0
        summary = f"\nThe token {ticker} is held by {wallets_with_balance} out of {total_wallets} checked wallets ({percentage:.2f}%)"
        
        response = '\n'.join(response_lines) + summary
        bot.reply_to(message, response, parse_mode='HTML', reply_markup=create_main_keyboard())

def process_ticker(message, contract_address):
    ticker = message.text.strip()
    if not ticker:
        bot.reply_to(message, 'Invalid ticker. Please try the check_balance command again.')
        return
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO tokens (address, ticker) VALUES (?, ?)', (contract_address, ticker))
    conn.commit()
    conn.close()
    
    # Повторно вызываем check_balance с сохраненным тикером
    bot.send_message(message.chat.id, f'/check_balance {contract_address} {ticker}')



@bot.message_handler(commands=['add_wallet'])
@user_allowed
def add_wallet(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(message, 'Usage: /add_wallet &lt;wallet_address&gt; [name]')
        return
    
    wallet_address = parts[1]
    name = parts[2] if len(parts) > 2 else None
    
    if not is_valid_wallet(wallet_address):
        bot.reply_to(message, 'Invalid wallet address.')
        return
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    
    # Check if wallet already exists
    cursor.execute('SELECT * FROM wallets WHERE address = ?', (wallet_address,))
    if cursor.fetchone():
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> already exists in the database.')
        conn.close()
        return
    
    cursor.execute('INSERT INTO wallets (address, name) VALUES (?, ?)', (wallet_address, name))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f'Wallet <code>{wallet_address}</code> added successfully.')

@bot.message_handler(commands=['list_wallets'])
@user_allowed
def list_wallets(message):
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT address, name FROM wallets')
    wallets = cursor.fetchall()
    conn.close()
    
    if not wallets:
        bot.reply_to(message, 'No wallets in the database.')
    else:
        response_lines = ['<b>List of wallets:</b>']
        for address, name in wallets:
            name_str = f"Name: {name}" if name else "Name: N/A"
            response_lines.append(f"Address: <code>{address}</code>\n{name_str}\n")
        response = '\n'.join(response_lines)
        bot.reply_to(message, response, parse_mode='HTML')

@bot.message_handler(commands=['remove_wallet'])
@user_allowed
def remove_wallet(message):
    try:
        wallet_address = message.text.split()[1]
    except IndexError:
        bot.reply_to(message, 'Usage: /remove_wallet &lt;wallet_address&gt;')
        return
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM wallets WHERE address = ?', (wallet_address,))
    if cursor.rowcount > 0:
        conn.commit()
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> removed successfully.')
    else:
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> not found in the database.')
    conn.close()

@bot.message_handler(commands=['rename_wallet'])
@user_allowed
def rename_wallet(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, 'Usage: /rename_wallet &lt;wallet_address&gt; &lt;new_name&gt;')
        return
    
    wallet_address = parts[1]
    new_name = parts[2]
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE wallets SET name = ? WHERE address = ?', (new_name, wallet_address))
    if cursor.rowcount > 0:
        conn.commit()
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> renamed to {new_name}.')
    else:
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> not found in the database.')
    conn.close()

async def get_balances(contract_address: str) -> tuple:
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT address, name FROM wallets')
    wallets = cursor.fetchall()
    conn.close()

    balances = {}
    total_wallets = len(wallets)
    wallets_with_balance = 0

    for wallet in wallets:
        address, name = wallet
        try:
            balance = await get_token_balance(address, contract_address)
            if balance > 0:
                balances[address] = (balance, name)
                wallets_with_balance += 1
        except Exception as e:
            print(f"Error processing wallet {address}: {str(e)}")

    return balances, total_wallets, wallets_with_balance

async def get_token_balance(wallet_address: str, token_mint_address: str) -> float:
    async with AsyncClient(SOLANA_RPC_ENDPOINT) as client:
        wallet_pubkey = Pubkey.from_string(wallet_address)
        token_pubkey = Pubkey.from_string(token_mint_address)
        
        opts = TokenAccountOpts(mint=token_pubkey)
        
        response = await client.get_token_accounts_by_owner(wallet_pubkey, opts=opts)
        
        if response.value:
            for account_info in response.value:
                account_pubkey = account_info.pubkey
                balance_response = await client.get_token_account_balance(account_pubkey)
                balance = balance_response.value.amount
                balance_coin = int(balance) / 1_000_000
                return balance_coin
        else:
            return 0.0

def is_valid_wallet(wallet_address: str) -> bool:
    try:
        Pubkey.from_string(wallet_address)
        return True
    except Exception:
        return False

if __name__ == '__main__':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    bot.polling()

