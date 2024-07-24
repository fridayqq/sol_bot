import telebot
import sqlite3
from loguru import logger
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio
from dotenv import load_dotenv
import os

# Настройка loguru
logger.add("bot.log", rotation="10 MB", retention="10 days")

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
            logger.warning(f"Unauthorized access attempt by user: {message.from_user.username}")
    return wrapper

def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    keyboard.row(KeyboardButton('Check Balance'), KeyboardButton('List Wallets'))
    keyboard.row(KeyboardButton('Add Wallet'), KeyboardButton('Remove Wallet'))
    keyboard.row(KeyboardButton('Rename Wallet'), KeyboardButton('Help'))
    keyboard.row(KeyboardButton('List Tokens'), KeyboardButton('Add Token'), KeyboardButton('Remove Token'))
    return keyboard

@bot.message_handler(commands=['start', 'help'])
@user_allowed
def send_welcome(message):
    help_text = """
<b>Welcome! Here are the available commands:</b>\n
<b>Check Balance</b> - Check token balances\n
<b>Add Wallet</b> - Add a new wallet with an optional name\n
<b>List Wallets</b> - List all wallets in the database\n
<b>Remove Wallet</b> - Remove a wallet from the database\n
<b>Rename Wallet</b> - Rename a wallet\n
<b>List Tokens</b> - List all tokens in the database\n
<b>Add Token</b> - Add a new token\n
<b>Remove Token</b> - Remove a token from the database\n
<b>Help</b> - Show this help message
    """
    bot.reply_to(message, help_text, parse_mode='HTML', reply_markup=create_main_keyboard())
    logger.info(f"Sent welcome message to user: {message.from_user.username}")

@bot.message_handler(func=lambda message: message.text == 'Check Balance')
@user_allowed
def check_balance_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the contract address and ticker (for example):\n\n<code>/check_balance EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm $WIF</code>\n\n<code>/check_balance </code>', parse_mode='HTML')
    logger.info(f"Check Balance command triggered by user: {message.from_user.username}")

@bot.message_handler(func=lambda message: message.text == 'Add Wallet')
@user_allowed
def add_wallet_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the wallet address and optional name:\n\n<code>/add_wallet </code>', parse_mode='HTML')
    logger.info(f"Add Wallet command triggered by user: {message.from_user.username}")

@bot.message_handler(func=lambda message: message.text == 'Remove Wallet')
@user_allowed
def remove_wallet_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the wallet address to remove:\n\n<code>/remove_wallet </code>', parse_mode='HTML')
    logger.info(f"Remove Wallet command triggered by user: {message.from_user.username}")

@bot.message_handler(func=lambda message: message.text == 'Rename Wallet')
@user_allowed
def rename_wallet_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the wallet address and new name:\n\n<code>/rename_wallet </code>', parse_mode='HTML')
    logger.info(f"Rename Wallet command triggered by user: {message.from_user.username}")

@bot.message_handler(func=lambda message: message.text == 'List Wallets')
@user_allowed
def list_wallets_command(message):
    list_wallets(message)

@bot.message_handler(func=lambda message: message.text == 'List Tokens')
@user_allowed
def list_tokens_command(message):
    list_tokens(message)

@bot.message_handler(func=lambda message: message.text == 'Add Token')
@user_allowed
def add_token_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the token address and ticker:\n\n<code>/add_token </code>', parse_mode='HTML')
    logger.info(f"Add Token command triggered by user: {message.from_user.username}")

@bot.message_handler(func=lambda message: message.text == 'Remove Token')
@user_allowed
def remove_token_command(message):
    bot.reply_to(message, 'Copy and paste the following command, then add the token address to remove:\n\n<code>/remove_token </code>', parse_mode='HTML')
    logger.info(f"Remove Token command triggered by user: {message.from_user.username}")

@bot.message_handler(func=lambda message: message.text == 'Help')
@user_allowed
def help_command(message):
    send_welcome(message)

@bot.message_handler(commands=['check_balance'])
@user_allowed
def check_balance(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, 'Usage: /check_balance <contract_address> [ticker]', reply_markup=create_main_keyboard())
        return
    
    contract_address = parts[1]
    ticker = parts[2] if len(parts) > 2 else None
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ticker FROM tokens WHERE address = ?', (contract_address,))
    token_info = cursor.fetchone()
    
    if token_info:
        ticker = token_info[0]
    elif ticker:
        cursor.execute('INSERT OR REPLACE INTO tokens (address, ticker) VALUES (?, ?)', (contract_address, ticker))
        conn.commit()
    else:
        bot.reply_to(message, 'Please provide the ticker for this token:')
        bot.register_next_step_handler(message, process_ticker, contract_address)
        conn.close()
        return
    
    conn.close()
    
    balances, total_wallets, wallets_with_balance = asyncio.run(get_balances(contract_address))
    
    if not balances:
        bot.reply_to(message, 'No balances found for the provided contract address.', reply_markup=create_main_keyboard())
        logger.info(f"No balances found for contract address: {contract_address}")
    else:
        response_lines = []
        for address, (balance, name) in balances.items():
            name_str = f"Name: {name}\n" if name else ""
            response_lines.append(f"Address: <code>{address}</code>\n{name_str}Balance: <code>{balance:.6f} {ticker}</code>\n")
        
        percentage = (wallets_with_balance / total_wallets) * 100 if total_wallets > 0 else 0
        summary = f"\nThe token {ticker} is held by {wallets_with_balance} out of {total_wallets} checked wallets ({percentage:.2f}%)"
        
        response = '\n'.join(response_lines) + summary
        bot.reply_to(message, response, parse_mode='HTML', reply_markup=create_main_keyboard())
        logger.info(f"Provided balances for contract address: {contract_address}")

def process_ticker(message, contract_address):
    ticker = message.text.strip()
    if not ticker:
        bot.reply_to(message, 'Invalid ticker. Please try the check_balance command again.')
        logger.warning(f"Invalid ticker provided by user: {message.from_user.username}")
        return
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO tokens (address, ticker) VALUES (?, ?)', (contract_address, ticker))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f'/check_balance {contract_address} {ticker}')
    logger.info(f"Ticker {ticker} for contract address {contract_address} added by user: {message.from_user.username}")

@bot.message_handler(commands=['add_wallet'])
@user_allowed
def add_wallet(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(message, 'Usage: /add_wallet <wallet_address> [name]')
        return
    
    wallet_address = parts[1]
    name = parts[2] if len(parts) > 2 else None
    
    if not is_valid_wallet(wallet_address):
        bot.reply_to(message, 'Invalid wallet address.')
        logger.warning(f"Invalid wallet address provided by user: {message.from_user.username}")
        return
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM wallets WHERE address = ?', (wallet_address,))
    if cursor.fetchone():
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> already exists in the database.', parse_mode='HTML')
        conn.close()
        logger.info(f"Wallet {wallet_address} already exists. Triggered by user: {message.from_user.username}")
        return
    
    cursor.execute('INSERT INTO wallets (address, name) VALUES (?, ?)', (wallet_address, name))
    conn.commit()
    conn.close()

    bot.reply_to(message, f'Wallet <code>{wallet_address}</code> added successfully.', parse_mode='HTML')
    logger.info(f"Wallet {wallet_address} added by user: {message.from_user.username}")

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
        logger.info(f"No wallets in the database. Requested by user: {message.from_user.username}")
    else:
        response_lines = ['<b>List of wallets:</b>']
        for address, name in wallets:
            name_str = f"Name: {name}" if name else "Name: N/A"
            response_lines.append(f"Address: <code>{address}</code>\n{name_str}\n")
        response = '\n'.join(response_lines)
        bot.reply_to(message, response, parse_mode='HTML')
        logger.info(f"Listed wallets for user: {message.from_user.username}")

@bot.message_handler(commands=['remove_wallet'])
@user_allowed
def remove_wallet(message):
    try:
        wallet_address = message.text.split()[1]
    except IndexError:
        bot.reply_to(message, 'Usage: /remove_wallet <wallet_address>')
        return
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM wallets WHERE address = ?', (wallet_address,))
    if cursor.rowcount > 0:
        conn.commit()
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> removed successfully.', parse_mode='HTML')
        logger.info(f"Wallet {wallet_address} removed by user: {message.from_user.username}")
    else:
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> not found in the database.', parse_mode='HTML')
        logger.warning(f"Wallet {wallet_address} not found in the database. Requested by user: {message.from_user.username}")
    conn.close()

@bot.message_handler(commands=['rename_wallet'])
@user_allowed
def rename_wallet(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, 'Usage: /rename_wallet <wallet_address> <new_name>')
        return
    
    wallet_address = parts[1]
    new_name = parts[2]
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE wallets SET name = ? WHERE address = ?', (new_name, wallet_address))
    if cursor.rowcount > 0:
        conn.commit()
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> renamed to {new_name}.', parse_mode='HTML')
        logger.info(f"Wallet {wallet_address} renamed to {new_name} by user: {message.from_user.username}")
    else:
        bot.reply_to(message, f'Wallet <code>{wallet_address}</code> not found in the database.', parse_mode='HTML')
        logger.warning(f"Wallet {wallet_address} not found in the database. Rename requested by user: {message.from_user.username}")
    conn.close()

@bot.message_handler(commands=['list_tokens'])
@user_allowed
def list_tokens(message):
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT address, ticker FROM tokens')
    tokens = cursor.fetchall()
    conn.close()
    
    if not tokens:
        bot.reply_to(message, 'No tokens in the database.')
        logger.info(f"No tokens in the database. Requested by user: {message.from_user.username}")
    else:
        response_lines = ['<b>List of tokens:</b>']
        for address, ticker in tokens:
            response_lines.append(f"Address: <code>{address}</code>\nTicker: {ticker}\n")
        response = '\n'.join(response_lines)
        bot.reply_to(message, response, parse_mode='HTML')
        logger.info(f"Listed tokens for user: {message.from_user.username}")

@bot.message_handler(commands=['add_token'])
@user_allowed
def add_token(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, 'Usage: /add_token <token_address> <ticker>')
        return
    
    token_address = parts[1]
    ticker = parts[2]
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    
    # Check if token already exists
    cursor.execute('SELECT * FROM tokens WHERE address = ?', (token_address,))
    if cursor.fetchone():
        bot.reply_to(message, f'Token <code>{token_address}</code> already exists in the database.', parse_mode='HTML')
        conn.close()
        logger.info(f"Token {token_address} already exists. Triggered by user: {message.from_user.username}")
        return

    cursor.execute('INSERT OR REPLACE INTO tokens (address, ticker) VALUES (?, ?)', (token_address, ticker))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f'Token <code>{token_address}</code> with ticker {ticker} added successfully.', parse_mode='HTML')
    logger.info(f"Token {token_address} with ticker {ticker} added by user: {message.from_user.username}")

@bot.message_handler(commands=['remove_token'])
@user_allowed
def remove_token(message):
    try:
        token_address = message.text.split()[1]
    except IndexError:
        bot.reply_to(message, 'Usage: /remove_token <token_address>')
        return
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ticker FROM tokens WHERE address = ?', (token_address,))
    token_info = cursor.fetchone()
    
    if token_info:
        ticker = token_info[0]
        cursor.execute('DELETE FROM tokens WHERE address = ?', (token_address,))
        if cursor.rowcount > 0:
            conn.commit()
            bot.reply_to(message, f'Token <code>{token_address}</code> with ticker {ticker} removed successfully.', parse_mode='HTML')
            logger.info(f"Token {token_address} with ticker {ticker} removed by user: {message.from_user.username}")
        else:
            bot.reply_to(message, f'Token <code>{token_address}</code> not found in the database.', parse_mode='HTML')
            logger.warning(f"Token {token_address} not found in the database. Requested by user: {message.from_user.username}")
    else:
        bot.reply_to(message, f'Token <code>{token_address}</code> not found in the database.', parse_mode='HTML')
        logger.warning(f"Token {token_address} not found in the database. Requested by user: {message.from_user.username}")
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
            logger.error(f"Error processing wallet {address}: {str(e)}")

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
