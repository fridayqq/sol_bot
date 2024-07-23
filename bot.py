import telebot
import sqlite3
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts
import asyncio
from dotenv import load_dotenv
import os

load_dotenv()
# Telegram bot token
token = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(token)

# Solana RPC endpoint
SOLANA_RPC_ENDPOINT = 'https://api.mainnet-beta.solana.com'

# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 'Welcome! Use /check_balance <contract_address> to check token balances. Use /add_wallet <wallet_address> to add a new wallet.')

# Команда /check_balance
@bot.message_handler(commands=['check_balance'])
def check_balance(message):
    try:
        contract_address = message.text.split()[1]
    except IndexError:
        bot.reply_to(message, 'Usage: /check_balance <contract_address>')
        return
    
    balances = asyncio.run(get_balances(contract_address))
    
    if not balances:
        bot.reply_to(message, 'No balances found for the provided contract address.')
    else:
        response_lines = []
        for address, balance in balances.items():
            response_lines.append(f"Address: `{address}`\nBalance: `{balance:.6f} ==coin==`\n")
        response = '\n'.join(response_lines)
        bot.reply_to(message, response, parse_mode='Markdown')

# Команда /add_wallet
@bot.message_handler(commands=['add_wallet'])
def add_wallet(message):
    try:
        wallet_address = message.text.split()[1]
    except IndexError:
        bot.reply_to(message, 'Usage: /add_wallet <wallet_address>')
        return
    
    if not is_valid_wallet(wallet_address):
        bot.reply_to(message, 'Invalid wallet address.')
        return
    
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO wallets (address) VALUES (?)', (wallet_address,))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f'Wallet {wallet_address} added successfully.')

async def get_balances(contract_address: str) -> dict:
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT address FROM wallets')
    wallets = cursor.fetchall()
    conn.close()

    balances = {}
    for wallet in wallets:
        address = wallet[0]
        try:
            balance = await get_token_balance(address, contract_address)
            balances[address] = balance
        except Exception as e:
            print(f"Error processing wallet {address}: {str(e)}")

    return balances

async def get_token_balance(wallet_address: str, token_mint_address: str) -> float:
    async with AsyncClient(SOLANA_RPC_ENDPOINT) as client:
        wallet_pubkey = Pubkey.from_string(wallet_address)
        token_pubkey = Pubkey.from_string(token_mint_address)
        
        # Используем TokenAccountOpts для фильтрации по mint
        opts = TokenAccountOpts(mint=token_pubkey)
        
        # Получаем все аккаунты токенов для указанного кошелька
        response = await client.get_token_accounts_by_owner(wallet_pubkey, opts=opts)
        
        if response.value:
            for account_info in response.value:
                account_pubkey = account_info.pubkey
                balance_response = await client.get_token_account_balance(account_pubkey)
                balance = balance_response.value.amount
                # Преобразуем строку в число и затем в читаемый формат
                balance_coin = int(balance) / 1_000_000  # Преобразуем минимальные единицы в ==coin==
                return balance_coin
        else:
            print("No token accounts found for the given wallet and token mint.")
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
