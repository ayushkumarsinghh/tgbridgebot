import os
import sys
import subprocess
import json
import random
import string
import asyncio
import time
import re
import sqlite3
import datetime

# --- Auto-Installer for Dependencies ---
def install_and_import(package, import_name=None):
    if import_name is None:
        import_name = package
    try:
        __import__(import_name)
    except ImportError:
        print(f"\033[93m[!] Missing dependency '{package}'. Auto-installing now...\033[0m")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package, "--quiet"])
            print(f"\033[92m[+] Successfully installed '{package}'!\033[0m")
        except Exception as e:
            print(f"\033[91m[-] Failed to auto-install '{package}': {e}\033[0m")
            sys.exit(1)

# Check and install required packages
install_and_import("discord.py", "discord")
install_and_import("telethon")
install_and_import("undetected-chromedriver", "undetected_chromedriver")
install_and_import("selenium")
install_and_import("tls-client", "tls_client")
install_and_import("qrcode")
install_and_import("pillow", "PIL")

import discord
from discord.ext import commands, tasks
from telethon import TelegramClient, events
import tls_client

# Load standard .env file manually if it exists
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "244415954782519296"))
ADMIN_IDS = [170730211720167426]
DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "1520009752770379856"))
DISCORD_PANEL_CHANNEL_ID = int(os.getenv("DISCORD_PANEL_CHANNEL_ID", "1520009753386815620"))
DISCORD_CATEGORY_ID = int(os.getenv("DISCORD_CATEGORY_ID", "1520014399287590922"))
DISCORD_WORKER_ROLE_ID = int(os.getenv("DISCORD_WORKER_ROLE_ID", "1520014570876305569"))
DISCORD_APPROVAL_CHANNEL_ID = int(os.getenv("DISCORD_APPROVAL_CHANNEL_ID", "1520018012994932746"))
DISCORD_LOG_CHANNEL_ID = int(os.getenv("DISCORD_LOG_CHANNEL_ID", "1510245312801935473"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TARGET_TELEGRAM_BOT = os.getenv("TARGET_TELEGRAM_BOT", "@askaboutme_session_bot")

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID_1", "24901470"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH_1", "4cb5a2ff0dbfed004eff7c56ddee7253")

# Payment Methods Info
BINANCE_ID = os.getenv("PAYMENT_BINANCE_ID", "Not Configured")
UPI_ID = os.getenv("PAYMENT_UPI_ID", "Not Configured")
TRC20_ADDRESS = os.getenv("PAYMENT_TRC20_ADDRESS", "Not Configured")
LTC_ADDRESS = os.getenv("PAYMENT_LTC_ADDRESS", "Not Configured")
BSC_WALLET_ADDRESS = os.getenv("PAYMENT_BSC_WALLET_ADDRESS", "0xE9d2b69488DcFa424B535f765761b2da6ddE328f")
POLYGON_WALLET_ADDRESS = os.getenv("PAYMENT_POLYGON_WALLET_ADDRESS", "0xE9d2b69488DcFa424B535f765761b2da6ddE328f")

# Proxy configuration list
PROXIES = []


def get_proxy_url() -> str:
    if not PROXIES:
        return ""
    return random.choice(PROXIES)

# Database and State configuration
STATES_FILE = os.getenv("STATES_FILE_PATH", "tg_states.json")

# Override sqlite3.connect to redirect sparky.db to a configurable path (e.g. for persistence on Railway)
_original_connect = sqlite3.connect
def custom_connect(database, *args, **kwargs):
    if database == "sparky.db":
        database = os.getenv("DATABASE_PATH", "sparky.db")
    
    # Automatically create parent directories if they don't exist yet
    parent_dir = os.path.dirname(database)
    if parent_dir and not os.path.exists(parent_dir):
        try:
            os.makedirs(parent_dir, exist_ok=True)
            print(f"[System] Created database directory: {parent_dir}")
        except Exception as e:
            print(f"[Error] Failed to create database directory {parent_dir}: {e}")
            
    return _original_connect(database, *args, **kwargs)
sqlite3.connect = custom_connect


STATE_IDLE = "STATE_IDLE"
STATE_AWAITING_COUNT = "STATE_AWAITING_COUNT"
STATE_AWAITING_PAYMENT_METHOD = "STATE_AWAITING_PAYMENT_METHOD"
STATE_AWAITING_CONFIRMATION = "STATE_AWAITING_CONFIRMATION"
STATE_AWAITING_APPROVAL = "STATE_AWAITING_APPROVAL"
STATE_AWAITING_TXID = "STATE_AWAITING_TXID"
STATE_AWAITING_TOKEN = "STATE_AWAITING_TOKEN"
STATE_AWAITING_DEPOSIT_AMOUNT = "STATE_AWAITING_DEPOSIT_AMOUNT"
tg_service_active = True

def load_states():
    if os.path.exists(STATES_FILE):
        try:
            with open(STATES_FILE, "r") as f:
                d = json.load(f)
                return {int(k): v for k, v in d.items()}
        except:
            pass
    return {}

def save_states(states):
    try:
        # Automatically create parent directories if they don't exist yet
        parent_dir = os.path.dirname(STATES_FILE)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception as e:
                print(f"[Warning] Failed to create states directory {parent_dir}: {e}")
        with open(STATES_FILE, "w") as f:
            json.dump({str(k): v for k, v in states.items()}, f, indent=4)
    except Exception as e:
        print(f"Error saving states: {e}")

# Database Initialization
def init_db():
    conn = sqlite3.connect("sparky.db")
    with conn:
        # Auto-migrate: drop old schema tables if they exist
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT discord_msg_id FROM jobs LIMIT 1")
            cursor.execute("DROP TABLE IF EXISTS jobs")
            cursor.execute("DROP TABLE IF EXISTS panels")
            cursor.execute("DROP TABLE IF EXISTS workers")
        except sqlite3.OperationalError:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS allowed_admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS senders (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS panels (
                panel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_msg_id INTEGER,
                status TEXT NOT NULL DEFAULT 'available',
                worker_id INTEGER,
                claimed_at REAL,
                discord_channel_id INTEGER,
                action_taken INTEGER DEFAULT 0,
                created_at REAL
            );
        """)
        
        # Add action_taken column if database exists but doesn't have it
        try:
            conn.execute("ALTER TABLE panels ADD COLUMN action_taken INTEGER DEFAULT 0;")
        except sqlite3.OperationalError:
            pass
            
        # Add created_at column if database exists but doesn't have it
        try:
            conn.execute("ALTER TABLE panels ADD COLUMN created_at REAL;")
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                panel_id INTEGER,
                tg_chat_id INTEGER NOT NULL,
                tg_msg_id INTEGER NOT NULL,
                stripe_url TEXT NOT NULL,
                qr_file_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available',
                FOREIGN KEY(panel_id) REFERENCES panels(panel_id)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS used_txids (
                tx_hash TEXT PRIMARY KEY,
                used_at REAL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

def get_setting(key, default=None):
    with sqlite3.connect("sparky.db") as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row:
        val = row[0]
        if isinstance(default, int):
            try:
                return int(val)
            except ValueError:
                return default
        return val
    return default

def set_setting(key, value):
    with sqlite3.connect("sparky.db") as db:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

# Initialize Clients
SESSION_PATH = os.getenv("SESSION_FILE_PATH", "bot_session")
bot_client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH)

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True
discord_bot = commands.Bot(command_prefix="!", intents=intents)

# Helpers to resolve channel/guild caching issues
async def get_or_fetch_channel(channel_id):
    channel = discord_bot.get_channel(channel_id)
    if not channel:
        try:
            channel = await discord_bot.fetch_channel(channel_id)
        except Exception:
            pass
    return channel

async def get_or_fetch_guild(guild_id):
    guild = discord_bot.get_guild(guild_id)
    if not guild:
        try:
            guild = await discord_bot.fetch_guild(guild_id)
        except Exception:
            pass
    return guild


# --- STRIPE VERIFICATION SCRAPER ---
import base64
import threading
import shutil
chrome_launch_lock = threading.Lock()

def create_headless_driver(proxy=None):
    import undetected_chromedriver as uc
    
    # Helper to clear cached chromedrivers in AppData to fix file conflicts (WinError 183)
    def clear_uc_cache():
        # Force terminate any zombie chromedriver or chrome processes holding file locks (Windows only)
        try:
            if os.name == 'nt':
                os.system("taskkill /f /im chromedriver.exe >nul 2>&1")
                os.system("taskkill /f /im chrome.exe >nul 2>&1")
        except Exception:
            pass
            
        appdata = os.getenv("APPDATA")
        paths_to_check = []
        if appdata:
            paths_to_check.append(os.path.join(appdata, "undetected_chromedriver"))
        home = os.path.expanduser("~")
        if home:
            paths_to_check.append(os.path.join(home, ".local", "share", "undetected_chromedriver"))
            paths_to_check.append(os.path.join(home, ".config", "undetected_chromedriver"))
            
        for path in paths_to_check:
            if os.path.exists(path):
                try:
                    shutil.rmtree(path, ignore_errors=True)
                    print(f"[System] Cleared undetected_chromedriver cache at {path}")
                except Exception as cache_err:
                    print(f"[Warning] Failed to clear cache at {path}: {cache_err}")

    def build_fresh_options():
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        if proxy:
            clean_proxy = proxy.replace("http://", "").replace("https://", "")
            options.add_argument(f"--proxy-server={clean_proxy}")
        return options

    with chrome_launch_lock:
        fresh_opts = build_fresh_options()
        try:
            return uc.Chrome(options=fresh_opts, use_subprocess=True)
        except Exception as e:
            err_msg = str(e)
            print(f"[Warning] Headless Chrome launch failed: {err_msg}")
            
            # Parse correct Chrome version from error message
            detected_ver = None
            match1 = re.search(r"Current browser version is (\d+)", err_msg)
            match2 = re.search(r"only supports Chrome version (\d+)", err_msg)
            match3 = re.search(r"supports Chrome version (\d+)", err_msg)
            
            if match1:
                detected_ver = int(match1.group(1))
            elif match2:
                detected_ver = int(match2.group(1))
            elif match3:
                detected_ver = int(match3.group(1))
                
            # Clear cached conflicting chromedriver binaries
            clear_uc_cache()
            time.sleep(2)
            
            print(f"[System] Retrying Chrome launch after clearing cache...")
            try:
                retry_opts = build_fresh_options()
                if detected_ver:
                    print(f"[System] Specifying version_main={detected_ver}")
                    return uc.Chrome(options=retry_opts, version_main=detected_ver, use_subprocess=True)
                else:
                    return uc.Chrome(options=retry_opts, use_subprocess=True)
            except Exception as retry_err:
                print(f"[Error] Retry Chrome launch failed: {retry_err}")
            raise e


def verify_evm_transaction(chain: str, tx_hash: str, expected_to: str, expected_amount: float) -> bool:
    import urllib.request
    import urllib.parse
    import json

    if chain == "bsc":
        rpc_url = "https://bsc-dataseed.binance.org/"
        usdt_contract = "0x55d398326f99059ff775485246999027b3197955"  # BSC USDT
        decimals = 18
    elif chain == "polygon":
        rpc_url = "https://polygon-rpc.com/"
        usdt_contract = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"  # Polygon USDT
        decimals = 6
    else:
        print("[-] Invalid chain specified.")
        return False

    print(f"[+] Querying {chain.upper()} receipt for TX: {tx_hash}")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getTransactionReceipt",
        "params": [tx_hash],
        "id": 1
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        req = urllib.request.Request(
            rpc_url, 
            data=json.dumps(payload).encode("utf-8"), 
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            
        result = res_data.get("result")
        if not result:
            print("[-] Transaction receipt not found on chain yet.")
            return False
            
        # Check transaction execution status (0x1 = success)
        status = result.get("status")
        if status != "0x1":
            print(f"[-] Transaction failed or has status: {status}")
            return False
            
        logs = result.get("logs", [])
        transfer_signature = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        
        for idx, log in enumerate(logs):
            log_address = log.get("address", "").lower()
            if log_address != usdt_contract.lower():
                continue
                
            topics = log.get("topics", [])
            if not topics or topics[0].lower() != transfer_signature:
                continue
                
            # Topics[2] contains the padded 'to' address (recipient)
            if len(topics) < 3:
                continue
                
            recipient_topic = topics[2]
            # Convert 32-byte padded address to 20-byte address (take the last 40 hex characters)
            recipient_address = "0x" + recipient_topic[-40:].lower()
            
            # Extract data (transfer value)
            data_hex = log.get("data", "0x")
            val_int = int(data_hex, 16) if data_hex != "0x" else 0
            actual_amount = val_int / (10 ** decimals)
            
            print(f"[+] Found USDT transfer: To={recipient_address}, Amount={actual_amount}")
            
            # Verify recipient and amount
            if recipient_address == expected_to.lower():
                if actual_amount >= expected_amount - 0.001:
                    print("[+] Verification SUCCESS!")
                    return True
                else:
                    print(f"[-] Amount mismatch. Expected {expected_amount}, got {actual_amount}")
            else:
                print(f"[-] Recipient mismatch. Expected {expected_to.lower()}, got {recipient_address}")
                
        print("[-] No matching USDT transfer logs found in this transaction.")
        return False
        
    except Exception as e:
        print(f"[-] Error querying RPC: {e}")
        return False


def verify_stripe_payment(url: str) -> bool:
    import base64
    import urllib.parse
    import urllib.request
    import json
    
    # 1. First extract client_secret and publishable_key from the instruction page HTML
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # We use tls_client to fetch the page so we bypass any simple TLS blocking
    session = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
    proxy = get_proxy_url()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
        
    try:
        print(f"[Stripe Query] Fetching Stripe instructions page: {url}")
        r = session.get(url, headers=headers, timeout_seconds=10)
        if r.status_code != 200:
            print(f"[-] Stripe verification page request failed with status code {r.status_code}")
            return False
            
        html = r.text
        match = re.search(r'data-message="([^"]+)"', html)
        if not match:
            print("[-] data-message attribute not found in HTML.")
            # Fallback check
            if "Action Successful" in html:
                print("[+] Stripe page explicitly has 'Action Successful' in static text.")
                return True
            return False
            
        decoded = base64.b64decode(match.group(1)).decode("utf-8")
        payload = json.loads(decoded)
        
        client_secret = payload.get("client_secret")
        publishable_key = payload.get("publishable_key")
        
        if not client_secret or not publishable_key:
            print("[-] Missing client_secret or publishable_key in payload.")
            return False
            
        # Extract intent ID
        intent_id = client_secret.split("_secret_")[0]
        
        # Build Stripe API query URL
        if client_secret.startswith("seti_"):
            api_url = f"https://api.stripe.com/v1/setup_intents/{intent_id}"
        elif client_secret.startswith("pi_"):
            api_url = f"https://api.stripe.com/v1/payment_intents/{intent_id}"
        else:
            print(f"[-] Unknown intent type prefix: {client_secret}")
            return False
            
        params = {
            "key": publishable_key,
            "client_secret": client_secret,
            "is_stripe_sdk": "true"
        }
        api_url = f"{api_url}?{urllib.parse.urlencode(params)}"
        print(f"[Stripe Query] Querying public API endpoint: {api_url}")
        
        api_res = session.get(api_url, headers=headers, timeout_seconds=10)
        if api_res.status_code == 200:
            res_data = api_res.json()
            status = res_data.get("status")
            print(f"[Stripe Query] Intent status for {url}: {status}")
            return status == "succeeded"
        else:
            print(f"[-] Stripe API query returned status code {api_res.status_code}")
            
    except Exception as err:
        print(f"[-] Error verifying stripe payment status: {err}")
        
    return False

# --- DISCORD APPROVAL VIEW ---
class DiscordApprovalView(discord.ui.View):
    def __init__(self, tg_user_id: int, username: str, count: int, total: float):
        super().__init__(timeout=None)
        self.tg_user_id = tg_user_id
        self.username = username
        self.count = count
        self.total = total

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="approve_req")
    async def approve_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        states = load_states()
        states[self.tg_user_id] = {
            "state": STATE_AWAITING_TOKEN,
            "count": self.count
        }
        save_states(states)
        
        with sqlite3.connect("sparky.db") as db:
            db.execute(
                "INSERT INTO senders (chat_id, username, balance) VALUES (?, ?, ?) ON CONFLICT(chat_id) DO UPDATE SET balance = balance + ?",
                (self.tg_user_id, self.username, self.total, self.total)
            )
        
        try:
            # Notify user to upload QRs using the exact requested phrase
            await bot_client.send_message(
                self.tg_user_id, 
                "Please send QRs with the Stripe payment link\n* DONT SEND ANY UNNECCESSARY THINGS *"
            )
        except Exception as e:
            print(f"Error notifying TG user: {e}")
            
        await interaction.message.edit(
            content=f"✅ Approved Request from @{self.username} ({self.count} QRs, Total: ${self.total:.2f})", 
            view=None
        )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="decline_req")
    async def decline_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        states = load_states()
        states[self.tg_user_id] = {
            "state": STATE_IDLE
        }
        save_states(states)
        
        try:
            await bot_client.send_message(self.tg_user_id, "Your request was declined.")
        except Exception as e:
            print(f"Error notifying TG user: {e}")
            
        await interaction.message.edit(
            content=f"❌ Declined Request from @{self.username} ({self.count} QRs, Total: ${self.total:.2f})", 
            view=None
        )

# --- PENALTY & TIMEOUT ENGINE ---
async def handle_panel_failure(panel_id: int, worker_id: int, channel_id: int, reason: str, deduct_penalty: bool = True):
    # Fetch panel info
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        panel = db.execute("SELECT * FROM panels WHERE panel_id = ?", (panel_id,)).fetchone()
        
    if not panel or panel["status"] != "claimed":
        return

    # Deduct 20 coins if penalty applies
    if deduct_penalty:
        with sqlite3.connect("sparky.db") as db:
            db.execute(
                "INSERT INTO workers (user_id, balance) VALUES (?, 0) ON CONFLICT(user_id) DO UPDATE SET balance = MAX(0, balance - 20)",
                (worker_id,)
            )
            # Retrieve new balance
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT balance FROM workers WHERE user_id = ?", (worker_id,)).fetchone()
            new_bal = row["balance"] if row else 0

        # Log to hardcoded channel 1520019495626735718
        try:
            coin_log_channel = await get_or_fetch_channel(1520019495626735718)
            if coin_log_channel:
                coin_embed = discord.Embed(
                    title="⚠️ Panel Failure Penalty",
                    description=(
                        f"**Worker**: <@{worker_id}> (ID: `{worker_id}`)\n"
                        f"**Panel ID**: `{panel_id}`\n"
                        f"**Reason**: {reason}\n"
                        f"**Amount**: `-20 coins`\n"
                        f"**New Balance**: `{new_bal} coins`"
                    ),
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                await coin_log_channel.send(embed=coin_embed)
        except Exception as e:
            print(f"Error logging panel failure coin deduction: {e}")
            
    with sqlite3.connect("sparky.db") as db:
        db.execute("UPDATE panels SET status = 'failed' WHERE panel_id = ?", (panel_id,))

    # Fetch all jobs in this panel to reply Failed to Telegram for any that are not 'success'
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        jobs = db.execute("SELECT * FROM jobs WHERE panel_id = ?", (panel_id,)).fetchall()

    for job in jobs:
        if job["status"] != "success":
            with sqlite3.connect("sparky.db") as db:
                db.execute("UPDATE jobs SET status = 'failed' WHERE job_id = ?", (job["job_id"],))
            try:
                await bot_client.send_message(
                    job["tg_chat_id"], 
                    "Failed", 
                    reply_to=job["tg_msg_id"]
                )
            except Exception as e:
                print(f"Failed to reply to Telegram user: {e}")

    # Send Log to Log Channel
    try:
        log_channel = await get_or_fetch_channel(DISCORD_LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="Job Closed",
                description=f"Panel ID: {panel_id}\nStatus: **Failed** ({reason})\nWorker: <@{worker_id}>",
                color=discord.Color.red()
            )
            await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error sending log message: {e}")

    # Delete the Discord private channel
    guild = await get_or_fetch_guild(DISCORD_GUILD_ID)
    if guild:
        channel = await get_or_fetch_channel(channel_id)
        if channel:
            try:
                await channel.delete(reason=f"Panel failed: {reason}")
            except Exception as e:
                print(f"Error deleting private channel: {e}")

    # Alert worker in DMs
    try:
        worker = await discord_bot.fetch_user(worker_id)
        if worker:
            penalty_str = " 20 coins have been deducted from your balance." if deduct_penalty else ""
            await worker.send(f"⚠️ Your active Job Panel #{panel_id} has failed due to: **{reason}**.{penalty_str}")
    except Exception as e:
        print(f"Error DMing worker: {e}")

# --- TIMEOUT MONITOR LOOP ---
# Tracks when a worker was first detected offline for a panel
# Key: panel_id, Value: timestamp when first detected offline
offline_tracker = {}

@tasks.loop(seconds=10)
async def monitor_claimed_panels():
    guild = await get_or_fetch_guild(DISCORD_GUILD_ID)
    if not guild:
        return
    now = time.time()
    
    # 1. Process Unclaimed/Available Panels that exceed 60 seconds (remove button and show Expired)
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        unclaimed_panels = db.execute("SELECT * FROM panels WHERE status = 'available'").fetchall()
        
    for panel in unclaimed_panels:
        panel_id = panel["panel_id"]
        created_at = panel["created_at"]
        if created_at and (now - created_at >= 60):
            # Mark panel as expired
            with sqlite3.connect("sparky.db") as db:
                db.execute("UPDATE panels SET status = 'expired' WHERE panel_id = ?", (panel_id,))
                # Retrieve all jobs in this panel to update their status and notify their TG senders
                db.row_factory = sqlite3.Row
                jobs = db.execute("SELECT * FROM jobs WHERE panel_id = ?", (panel_id,)).fetchall()
                
            # Update jobs status to failed/expired
            for job in jobs:
                with sqlite3.connect("sparky.db") as db:
                    db.execute("UPDATE jobs SET status = 'expired' WHERE job_id = ?", (job["job_id"],))
                # Send redirect message to Telegram sender
                try:
                    await bot_client.send_message(
                        job["tg_chat_id"],
                        "Not completed and Try Again Later"
                    )
                except Exception as e:
                    print(f"Error redirecting message to TG sender: {e}")
                    
            # Edit original message card to remove button and show Expired
            try:
                panel_channel = await get_or_fetch_channel(DISCORD_PANEL_CHANNEL_ID)
                if panel_channel and panel["discord_msg_id"]:
                    msg = await panel_channel.fetch_message(panel["discord_msg_id"])
                    if msg:
                        expired_embed = discord.Embed(
                            title="Job Expired",
                            description=f"Panel ID: {panel_id}\nThis job panel has expired (unclaimed for 1 minute).",
                            color=discord.Color.red()
                        )
                        await msg.edit(content=None, embed=expired_embed, view=None)
            except Exception as e:
                print(f"Error editing expired panel card message: {e}")

    # 2. Process Claimed Panels (existing timeout logic)
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        claimed_panels = db.execute("SELECT * FROM panels WHERE status = 'claimed'").fetchall()
        
    for panel in claimed_panels:
        panel_id = panel["panel_id"]
        worker_id = panel["worker_id"]
        channel_id = panel["discord_channel_id"]
        claimed_at = panel["claimed_at"]
        action_taken = panel.get("action_taken", 0)
        
        # Check 45-second inactivity timeout (no button clicked)
        if action_taken == 0 and (now - claimed_at >= 45):
            await handle_panel_failure(panel_id, worker_id, channel_id, reason="Inactivity (45 seconds without action)", deduct_penalty=True)
            offline_tracker.pop(panel_id, None)
            continue
            
        # Check 5-minute total timeout
        if now - claimed_at >= 300:
            deduct = (action_taken == 0)
            await handle_panel_failure(panel_id, worker_id, channel_id, reason="Timeout (5 minutes exceeded)", deduct_penalty=deduct)
            offline_tracker.pop(panel_id, None)
            continue
            
        # Check if worker went offline
        try:
            member = await guild.fetch_member(worker_id)
            if member:
                status_str = str(member.status)
                if status_str == "offline":
                    if panel_id not in offline_tracker:
                        offline_tracker[panel_id] = now
                    else:
                        if now - offline_tracker[panel_id] >= 60:
                            deduct = (action_taken == 0)
                            await handle_panel_failure(panel_id, worker_id, channel_id, reason="Worker went offline", deduct_penalty=deduct)
                            offline_tracker.pop(panel_id, None)
                            continue
                else:
                    # Clear tracking if online
                    offline_tracker.pop(panel_id, None)
        except Exception as e:
            print(f"Error checking status for worker {worker_id}: {e}")

# --- DISCORD BUTTON AND SLASH INTERACTION DISPATCHER ---
@discord_bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("claim_panel_"):
            panel_id = int(custom_id.split("_")[-1])
            await handle_panel_claim(interaction, panel_id)
        elif custom_id.startswith("scanned_job_"):
            job_id = int(custom_id.split("_")[-1])
            await handle_individual_scanned(interaction, job_id)
        elif custom_id.startswith("cancel_panel_"):
            panel_id = int(custom_id.split("_")[-1])
            await handle_panel_cancel(interaction, panel_id)
        elif custom_id.startswith("approve_payout_"):
            parts = custom_id.split("_")
            worker_id = int(parts[2])
            amount = int(parts[3])
            await handle_payout_approval(interaction, worker_id, amount)

async def handle_payout_approval(interaction: discord.Interaction, worker_id: int, amount: int):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can approve payouts.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    # Update interaction message embed
    embed = interaction.message.embeds[0]
    embed.color = discord.Color.green()
    embed.title = "Payout Approved"
    embed.add_field(name="Approved By", value=interaction.user.mention, inline=False)
    
    await interaction.message.edit(
        content=f"✅ Payout Approved for <@{worker_id}>! That your funds are on the way",
        embed=embed,
        view=None
    )
    await interaction.followup.send("✅ Payout approved successfully.", ephemeral=True)

async def handle_panel_claim(interaction: discord.Interaction, panel_id: int):
    await interaction.response.defer(ephemeral=True)
    
    # Check if worker already has an active claimed panel
    with sqlite3.connect("sparky.db") as db:
        active = db.execute("SELECT 1 FROM panels WHERE worker_id = ? AND status = 'claimed'", (interaction.user.id,)).fetchone()
        
    if active:
        await interaction.followup.send("You already have an active job panel. Cancel or complete it first!", ephemeral=True)
        return

    # Check panel status
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        panel = db.execute("SELECT * FROM panels WHERE panel_id = ?", (panel_id,)).fetchone()
        
    if not panel or panel["status"] != "available":
        await interaction.followup.send("This job panel has already been claimed by another worker.", ephemeral=True)
        return

    guild = interaction.guild
    category = guild.get_channel(DISCORD_CATEGORY_ID)
    
    # Create private channel
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    try:
        channel_name = f"panel-{panel_id}-{interaction.user.name}"
        private_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )
    except Exception as e:
        await interaction.followup.send(f"Failed to create private channel: {e}", ephemeral=True)
        return

    now = time.time()
    with sqlite3.connect("sparky.db") as db:
        cur = db.execute(
            "UPDATE panels SET status = 'claimed', worker_id = ?, claimed_at = ?, discord_channel_id = ? WHERE panel_id = ? AND status = 'available'",
            (interaction.user.id, now, private_channel.id, panel_id)
        )
        rows_affected = cur.rowcount

    if rows_affected == 0:
        try:
            await private_channel.delete()
        except:
            pass
        await interaction.followup.send("This job panel has already been claimed by another worker.", ephemeral=True)
        return

    # Fetch all jobs in this panel
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        jobs = db.execute("SELECT * FROM jobs WHERE panel_id = ?", (panel_id,)).fetchall()

    # Post details in private channel
    embed = discord.Embed(
        title=f"Active Job Panel #{panel_id}",
        description=(
            f"**Instructions**:\n"
            f"1. Open each Stripe payment link below or scan the QRs to complete the payments.\n"
            f"2. Once payment is completed, click **Scanned** below each QR code to verify it.\n\n"
            f"**Warning**: You have 5 minutes to complete this job. If you go offline or exceed 5 minutes, 20 coins will be deducted.\n"
            f"**Strict Warning**: If you click **Scanned** on a QR that is NOT scanned or completed, **35 coins will be deducted** from your balance."
        ),
        color=discord.Color.purple()
    )
    
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Cancel Panel", style=discord.ButtonStyle.secondary, custom_id=f"cancel_panel_{panel_id}"))
    
    await private_channel.send(embed=embed, view=view)

    # Send each QR image with its Stripe link and its own Scanned button
    for idx, job in enumerate(jobs):
        job_embed = discord.Embed(
            title=f"QR #{idx+1} (Job ID: {job['job_id']})",
            description=f"**Stripe Link**:\n{job['stripe_url']}",
            color=discord.Color.purple()
        )
        
        job_view = discord.ui.View(timeout=None)
        job_view.add_item(discord.ui.Button(label="Scanned", style=discord.ButtonStyle.success, custom_id=f"scanned_job_{job['job_id']}"))
        
        if job["qr_file_path"] and os.path.exists(job["qr_file_path"]) and os.path.getsize(job["qr_file_path"]) > 0:
            qr_file = discord.File(job["qr_file_path"], filename=f"qr_{idx+1}.png")
            job_embed.set_image(url=f"attachment://qr_{idx+1}.png")
            await private_channel.send(file=qr_file, embed=job_embed, view=job_view)
        else:
            await private_channel.send(embed=job_embed, view=job_view)

    # Edit original Job Panel Card to show claimed status (stays claimed, never marked success/fail on panel board)
    try:
        panel_channel = await get_or_fetch_channel(DISCORD_PANEL_CHANNEL_ID)
        if panel_channel:
            msg = await panel_channel.fetch_message(panel["discord_msg_id"])
            if msg:
                claimed_embed = discord.Embed(
                    title="Job Claimed",
                    description=f"Panel ID: {panel_id}\nClaimed by: {interaction.user.mention}",
                    color=discord.Color.orange()
                )
                await msg.edit(content=None, embed=claimed_embed, view=None)
    except Exception as e:
        print(f"Error editing job card: {e}")

    await interaction.followup.send(f"Job claimed! Please head to your private channel: {private_channel.mention}", ephemeral=True)

async def handle_individual_scanned(interaction: discord.Interaction, job_id: int):
    await interaction.response.defer()
    
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        job = db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        
    if not job or job["status"] != "available":
        await interaction.followup.send("This QR has already been completed or is not active.", ephemeral=True)
        return
        
    panel_id = job["panel_id"]
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        panel = db.execute("SELECT * FROM panels WHERE panel_id = ?", (panel_id,)).fetchone()
        
    if not panel or panel["status"] != "claimed" or panel["worker_id"] != interaction.user.id:
        await interaction.followup.send("This job panel is no longer active for you.", ephemeral=True)
        return

    # Set action_taken = 1 to prevent inactivity timeout penalty
    with sqlite3.connect("sparky.db") as db:
        db.execute("UPDATE panels SET action_taken = 1 WHERE panel_id = ?", (panel_id,))

    # Check Stripe verification using the public API endpoint query (polls for up to 1 minute)
    status_msg = await interaction.channel.send(f"⌛ Starting Stripe transaction verification for Job #{job_id}...")
    
    is_success = False
    start_time = time.time()
    max_duration = 60  # 1 minute
    poll_interval = 5   # check every 5 seconds
    
    while time.time() - start_time < max_duration:
        # Check if the panel was cancelled or failed by the monitor task in the background
        with sqlite3.connect("sparky.db") as db:
            db.row_factory = sqlite3.Row
            p_status = db.execute("SELECT status FROM panels WHERE panel_id = ?", (panel_id,)).fetchone()
            j_status = db.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            
        if not p_status or p_status["status"] != "claimed" or not j_status or j_status["status"] != "available":
            print(f"[System] Job #{job_id} or Panel #{panel_id} is no longer active. Exiting poll loop.")
            try:
                await status_msg.delete()
            except:
                pass
            return

        is_success = await asyncio.to_thread(verify_stripe_payment, job["stripe_url"])
        if is_success:
            break
            
        elapsed = int(time.time() - start_time)
        try:
            await status_msg.edit(content=f"⌛ Checking Stripe transaction status for Job #{job_id}... ({elapsed}s elapsed)")
        except Exception:
            pass
            
        await asyncio.sleep(poll_interval)
        
    try:
        await status_msg.delete()
    except Exception:
        pass
    
    if is_success:
        # Credit worker 10 coins
        with sqlite3.connect("sparky.db") as db:
            db.execute(
                "INSERT INTO workers (user_id, username, balance) VALUES (?, ?, 10) ON CONFLICT(user_id) DO UPDATE SET balance = balance + 10",
                (interaction.user.id, str(interaction.user),)
            )
            db.execute("UPDATE jobs SET status = 'success' WHERE job_id = ?", (job_id,))
            
            # Retrieve new balance
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT balance FROM workers WHERE user_id = ?", (interaction.user.id,)).fetchone()
            new_bal = row["balance"] if row else 10

        # Log to hardcoded channel 1520019495626735718
        try:
            coin_log_channel = await get_or_fetch_channel(1520019495626735718)
            if coin_log_channel:
                coin_embed = discord.Embed(
                    title="🪙 QR Scanned Coin Credit",
                    description=(
                        f"**Worker**: {interaction.user.mention} (ID: `{interaction.user.id}`)\n"
                        f"**Job ID**: `{job_id}`\n"
                        f"**Amount**: `+10 coins`\n"
                        f"**New Balance**: `{new_bal} coins`"
                    ),
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                await coin_log_channel.send(embed=coin_embed)
        except Exception as e:
            print(f"Error logging QR scanned coin credit: {e}")
            
        # Reply Success on Telegram, replying the stripe link / qr
        try:
            success_caption = f"Success\n{job['stripe_url']}"
            if job["qr_file_path"] and os.path.exists(job["qr_file_path"]) and os.path.getsize(job["qr_file_path"]) > 0:
                await bot_client.send_file(
                    job["tg_chat_id"],
                    job["qr_file_path"],
                    caption=success_caption,
                    reply_to=job["tg_msg_id"]
                )
            else:
                await bot_client.send_message(
                    job["tg_chat_id"], 
                    success_caption, 
                    reply_to=job["tg_msg_id"]
                )
        except Exception as e:
            print(f"Error replying success to TG seller: {e}")

        # Log every scanned QR / link with the person who clicked scanned button to channel 1520104064875237407
        try:
            log_channel_id = 1520104064875237407
            log_channel = await get_or_fetch_channel(log_channel_id)
            if log_channel:
                log_embed = discord.Embed(
                    title="QR / Stripe Link Verified",
                    description=f"**Worker**: {interaction.user.mention} (ID: {interaction.user.id})\n**Stripe Link**: {job['stripe_url']}",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                if job["qr_file_path"] and os.path.exists(job["qr_file_path"]) and os.path.getsize(job["qr_file_path"]) > 0:
                    file_to_send = discord.File(job["qr_file_path"], filename="qr.png")
                    log_embed.set_image(url="attachment://qr.png")
                    await log_channel.send(file=file_to_send, embed=log_embed)
                else:
                    await log_channel.send(embed=log_embed)
            else:
                print(f"[Error] Log channel {log_channel_id} not found or could not be fetched.")
        except Exception as log_err:
            print(f"Error logging scanned job to channel {log_channel_id}: {log_err}")
            
        # Edit the message to show Verified status and remove/disable the button
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="Status", value="✅ Verified & Paid (10 coins credited)", inline=False)
        await interaction.message.edit(embed=embed, view=None)
        
        await interaction.channel.send(f"🎉 **Job #{job_id} Verified!** 10 coins added to your balance.")
        
        # Check if all jobs in this panel are now completed (success or failed)
        with sqlite3.connect("sparky.db") as db:
            db.row_factory = sqlite3.Row
            total_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE panel_id = ?", (panel_id,)).fetchone()[0]
            completed_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE panel_id = ? AND status IN ('success', 'failed')", (panel_id,)).fetchone()[0]
            
        if completed_jobs >= total_jobs:
            # Mark panel as success
            with sqlite3.connect("sparky.db") as db:
                db.execute("UPDATE panels SET status = 'success' WHERE panel_id = ?", (panel_id,))
                
            # Send Log to Log Channel
            try:
                log_channel = await get_or_fetch_channel(DISCORD_LOG_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="Job Closed",
                        description=f"Panel ID: {panel_id}\nStatus: **Completed**\nWorker: {interaction.user.mention}",
                        color=discord.Color.green()
                    )
                    await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"Error sending log message: {e}")
                
            await interaction.channel.send("🎉 **All payments in this panel have been completed or failed!** Channel will delete in 5 seconds...")
            await asyncio.sleep(5)
            
            # Delete channel
            try:
                await interaction.channel.delete(reason="Panel completed successfully")
            except Exception as e:
                print(f"[Error] Failed to delete completed channel: {e}")
                
            # Cleanup QR files
            with sqlite3.connect("sparky.db") as db:
                db.row_factory = sqlite3.Row
                jobs_in_panel = db.execute("SELECT * FROM jobs WHERE panel_id = ?", (panel_id,)).fetchall()
            for j in jobs_in_panel:
                if os.path.exists(j["qr_file_path"]):
                    try:
                        os.remove(j["qr_file_path"])
                    except:
                        pass
    else:
        # Update job status to 'failed' in DB
        with sqlite3.connect("sparky.db") as db:
            db.execute("UPDATE jobs SET status = 'failed' WHERE job_id = ?", (job_id,))
            # Recredit the Telegram sender by adding $0.50 back to their balance
            db.execute("UPDATE senders SET balance = balance + 0.50 WHERE chat_id = ?", (job["tg_chat_id"],))
            
        # Reply "Failed" to Telegram user
        try:
            await bot_client.send_message(
                job["tg_chat_id"], 
                "Failed", 
                reply_to=job["tg_msg_id"]
            )
        except Exception as tg_err:
            print(f"Error sending Failed reply to Telegram sender: {tg_err}")
            
        # Edit the message on Discord to remove the button and show Failed status
        try:
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.add_field(name="Status", value="❌ Verification Failed (No coins credited)", inline=False)
            await interaction.message.edit(embed=embed, view=None)
        except Exception as edit_err:
            print(f"Error editing message to failed status: {edit_err}")
            
        # Send channel notification
        await interaction.channel.send(f"Verification failed for job number {job_id} . Stripe payment is not completed/succeeded yet . No bal is added")
        
        # Check if all jobs in this panel are now finished (success or failed)
        with sqlite3.connect("sparky.db") as db:
            db.row_factory = sqlite3.Row
            total_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE panel_id = ?", (panel_id,)).fetchone()[0]
            completed_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE panel_id = ? AND status IN ('success', 'failed')", (panel_id,)).fetchone()[0]
            
        if completed_jobs >= total_jobs:
            # Mark panel as success (or completed) since all jobs are finalized
            with sqlite3.connect("sparky.db") as db:
                db.execute("UPDATE panels SET status = 'success' WHERE panel_id = ?", (panel_id,))
                
            # Send Log to Log Channel
            try:
                log_channel = await get_or_fetch_channel(DISCORD_LOG_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="Job Closed",
                        description=f"Panel ID: {panel_id}\nStatus: **Closed** (All QRs processed)\nWorker: {interaction.user.mention}",
                        color=discord.Color.green()
                    )
                    await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"Error sending log message: {e}")
                
            await interaction.channel.send("🎉 **All jobs in this panel have been completed or failed!** Channel will delete in 5 seconds...")
            await asyncio.sleep(5)
            
            # Delete channel
            try:
                await interaction.channel.delete(reason="Panel completed successfully")
            except Exception as e:
                print(f"[Error] Failed to delete completed channel: {e}")
                
            # Cleanup QR files
            with sqlite3.connect("sparky.db") as db:
                db.row_factory = sqlite3.Row
                jobs_in_panel = db.execute("SELECT * FROM jobs WHERE panel_id = ?", (panel_id,)).fetchall()
            for j in jobs_in_panel:
                if os.path.exists(j["qr_file_path"]):
                    try:
                        os.remove(j["qr_file_path"])
                    except:
                        pass

async def handle_panel_cancel(interaction: discord.Interaction, panel_id: int):
    await interaction.response.defer()
    
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        panel = db.execute("SELECT * FROM panels WHERE panel_id = ?", (panel_id,)).fetchone()
        
    if not panel or panel["status"] != 'claimed' or panel["worker_id"] != interaction.user.id:
        await interaction.followup.send("This job panel cannot be cancelled.", ephemeral=True)
        return

    # Return panel and jobs to pool
    with sqlite3.connect("sparky.db") as db:
        db.execute(
            "UPDATE panels SET status = 'available', worker_id = NULL, claimed_at = NULL, discord_channel_id = NULL WHERE panel_id = ?",
            (panel_id,)
        )
        db.execute(
            "UPDATE jobs SET status = 'available' WHERE panel_id = ? AND status != 'success'",
            (panel_id,)
        )

    # Reset Card in Job Panel
    try:
        panel_channel = await get_or_fetch_channel(DISCORD_PANEL_CHANNEL_ID)
        if panel_channel:
            msg = await panel_channel.fetch_message(panel["discord_msg_id"])
            if msg:
                embed = discord.Embed(
                    title="New Job Panel Available!",
                    description=f"**Panel ID**: {panel_id}\nContains: **5 QRs**",
                    color=discord.Color.purple()
                )
                view = discord.ui.View(timeout=None)
                view.add_item(discord.ui.Button(label="Claim", style=discord.ButtonStyle.primary, custom_id=f"claim_panel_{panel_id}"))
                await msg.edit(content=f"<@&{DISCORD_WORKER_ROLE_ID}> New job posted!", embed=embed, view=view)
    except Exception as e:
        print(f"Error resetting job panel card: {e}")

    await interaction.channel.send("Job panel cancelled. Channel will delete in 3 seconds...")
    await asyncio.sleep(3)
    try:
        await interaction.channel.delete(reason="Cancelled by worker")
    except Exception as e:
        print(f"[Error] Failed to delete cancelled channel: {e}")

# --- DISCORD BALANCE CHECK COMMAND ---
@discord_bot.command(name="bal", aliases=["balance"])
async def balance_cmd(ctx):
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT balance FROM workers WHERE user_id = ?", (ctx.author.id,)).fetchone()
    
    bal = row["balance"] if row else 0
    await ctx.send(f"{ctx.author.mention}, your current balance is **{bal} coins**.")

# --- DISCORD ADMIN COINS COMMANDS ---
def is_admin_user(user_id, guild_perms=None):
    if user_id == OWNER_ID or user_id in ADMIN_IDS:
        return True
    if guild_perms and guild_perms.administrator:
        return True
    with sqlite3.connect("sparky.db") as db:
        row = db.execute("SELECT 1 FROM allowed_admins WHERE user_id = ?", (user_id,)).fetchone()
    return row is not None

@discord_bot.command(name="add")
async def add_coins_cmd(ctx, member: discord.Member, amount: int):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
        
    if amount <= 0:
        await ctx.send("❌ Amount must be greater than zero.")
        return
        
    with sqlite3.connect("sparky.db") as db:
        db.execute(
            "INSERT INTO workers (user_id, username, balance) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
            (member.id, str(member), amount, amount)
        )
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT balance FROM workers WHERE user_id = ?", (member.id,)).fetchone()
        
    new_bal = row["balance"] if row else amount
    await ctx.send(f"✅ Added **{amount} coins** to {member.mention}. New Balance: **{new_bal} coins**.")

    # Log to hardcoded channel 1520019495626735718
    try:
        log_channel = await get_or_fetch_channel(1520019495626735718)
        if log_channel:
            embed = discord.Embed(
                title="🪙 Coins Added",
                description=(
                    f"**Admin**: {ctx.author.mention} (ID: `{ctx.author.id}`)\n"
                    f"**Worker**: {member.mention} (ID: `{member.id}`)\n"
                    f"**Amount**: `+{amount} coins`\n"
                    f"**New Balance**: `{new_bal} coins`"
                ),
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging coin addition: {e}")

@discord_bot.command(name="deduct")
async def deduct_coins_cmd(ctx, member: discord.Member, amount: int):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
        
    if amount <= 0:
        await ctx.send("❌ Amount must be greater than zero.")
        return
        
    with sqlite3.connect("sparky.db") as db:
        db.execute(
            "INSERT INTO workers (user_id, username, balance) VALUES (?, ?, 0) ON CONFLICT(user_id) DO UPDATE SET balance = MAX(0, balance - ?)",
            (member.id, str(member), amount)
        )
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT balance FROM workers WHERE user_id = ?", (member.id,)).fetchone()
        
    new_bal = row["balance"] if row else 0
    await ctx.send(f"✅ Deducted **{amount} coins** from {member.mention}. New Balance: **{new_bal} coins**.")

    # Log to hardcoded channel 1520019495626735718
    try:
        log_channel = await get_or_fetch_channel(1520019495626735718)
        if log_channel:
            embed = discord.Embed(
                title="🪙 Coins Deducted",
                description=(
                    f"**Admin**: {ctx.author.mention} (ID: `{ctx.author.id}`)\n"
                    f"**Worker**: {member.mention} (ID: `{member.id}`)\n"
                    f"**Amount**: `-{amount} coins`\n"
                    f"**New Balance**: `{new_bal} coins`"
                ),
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging coin deduction: {e}")

@discord_bot.command(name="tgbaladd")
async def tgbaladd_cmd(ctx, tg_user: str, amount: float):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
        
    if amount <= 0:
        await ctx.send("❌ Amount must be greater than zero.")
        return
        
    tg_user = tg_user.strip()
    is_id = False
    try:
        chat_id = int(tg_user)
        is_id = True
    except ValueError:
        username = tg_user.lstrip("@").lower()
        
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        if is_id:
            row = db.execute("SELECT * FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
            if row:
                db.execute("UPDATE senders SET balance = balance + ? WHERE chat_id = ?", (amount, chat_id))
                username_val = row["username"] or "Unknown"
            else:
                db.execute("INSERT INTO senders (chat_id, username, balance) VALUES (?, ?, ?)", (chat_id, "Unknown", amount))
                username_val = "Unknown"
            new_row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
        else:
            row = db.execute("SELECT * FROM senders WHERE LOWER(username) = ?", (username,)).fetchone()
            if row:
                chat_id = row["chat_id"]
                username_val = row["username"]
                db.execute("UPDATE senders SET balance = balance + ? WHERE chat_id = ?", (amount, chat_id))
            else:
                # Attempt to resolve username via Telethon bot_client lookup
                try:
                    entity = await bot_client.get_entity(username)
                    if entity:
                        chat_id = entity.id
                        username_val = entity.username or username
                        db.execute(
                            "INSERT INTO senders (chat_id, username, balance) VALUES (?, ?, ?)",
                            (chat_id, username_val, amount)
                        )
                    else:
                        await ctx.send(f"❌ Could not find a Telegram user with username **@{username}** in the database or Telegram lookup.")
                        return
                except Exception as lookup_err:
                    print(f"Telethon lookup failed for {username}: {lookup_err}")
                    await ctx.send(f"❌ Could not find a Telegram user with username **@{username}** in the database, and Telegram lookup failed.")
                    return
            new_row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
            
    new_bal = new_row["balance"] if new_row else amount
    await ctx.send(f"✅ Added **${amount:.2f}** to Telegram user **@{username_val}** (ID: `{chat_id}`). New Balance: **${new_bal:.2f}**.")

    # Log to hardcoded channel 1520019495626735718
    try:
        log_channel = await get_or_fetch_channel(1520019495626735718)
        if log_channel:
            embed = discord.Embed(
                title="💰 TG User Balance Added",
                description=(
                    f"**Admin**: {ctx.author.mention} (ID: `{ctx.author.id}`)\n"
                    f"**Telegram User**: @{username_val} (ID: `{chat_id}`)\n"
                    f"**Amount**: `+${amount:.2f}`\n"
                    f"**New Balance**: `${new_bal:.2f}`"
                ),
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging TG balance addition: {e}")


@discord_bot.command(name="tgbaldeduct")
async def tgbaldeduct_cmd(ctx, tg_user: str, amount: float):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
        
    if amount <= 0:
        await ctx.send("❌ Amount must be greater than zero.")
        return
        
    tg_user = tg_user.strip()
    is_id = False
    try:
        chat_id = int(tg_user)
        is_id = True
    except ValueError:
        username = tg_user.lstrip("@").lower()
        
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        if is_id:
            row = db.execute("SELECT * FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
            if not row:
                await ctx.send(f"❌ Telegram user with ID `{chat_id}` not found in the database.")
                return
            username_val = row["username"] or "Unknown"
            db.execute("UPDATE senders SET balance = MAX(0.0, balance - ?) WHERE chat_id = ?", (amount, chat_id))
            new_row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
        else:
            row = db.execute("SELECT * FROM senders WHERE LOWER(username) = ?", (username,)).fetchone()
            if row:
                chat_id = row["chat_id"]
                username_val = row["username"]
                db.execute("UPDATE senders SET balance = MAX(0.0, balance - ?) WHERE chat_id = ?", (amount, chat_id))
            else:
                # Attempt to resolve username via Telethon bot_client lookup
                try:
                    entity = await bot_client.get_entity(username)
                    if entity:
                        chat_id = entity.id
                        username_val = entity.username or username
                        db.execute(
                            "INSERT INTO senders (chat_id, username, balance) VALUES (?, ?, 0.0)",
                            (chat_id, username_val)
                        )
                        db.execute("UPDATE senders SET balance = MAX(0.0, balance - ?) WHERE chat_id = ?", (amount, chat_id))
                    else:
                        await ctx.send(f"❌ Could not find a Telegram user with username **@{username}** in the database or Telegram lookup.")
                        return
                except Exception as lookup_err:
                    print(f"Telethon lookup failed for {username}: {lookup_err}")
                    await ctx.send(f"❌ Could not find a Telegram user with username **@{username}** in the database, and Telegram lookup failed.")
                    return
            new_row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
            
    new_bal = new_row["balance"] if new_row else 0.0
    await ctx.send(f"✅ Deducted **${amount:.2f}** from Telegram user **@{username_val}** (ID: `{chat_id}`). New Balance: **${new_bal:.2f}**.")

    # Log to hardcoded channel 1520019495626735718
    try:
        log_channel = await get_or_fetch_channel(1520019495626735718)
        if log_channel:
            embed = discord.Embed(
                title="💰 TG User Balance Deducted",
                description=(
                    f"**Admin**: {ctx.author.mention} (ID: `{ctx.author.id}`)\n"
                    f"**Telegram User**: @{username_val} (ID: `{chat_id}`)\n"
                    f"**Amount**: `-${amount:.2f}`\n"
                    f"**New Balance**: `${new_bal:.2f}`"
                ),
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging TG balance deduction: {e}")

# --- DISCORD USER MANAGEMENT COMMANDS ---
@discord_bot.command(name="adduser")
async def adduser_cmd(ctx, member: discord.Member):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
    with sqlite3.connect("sparky.db") as db:
        db.execute(
            "INSERT INTO allowed_admins (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO NOTHING",
            (member.id, str(member))
        )
    await ctx.send(f"✅ Authorized {member.mention} as a bot administrator.")

@discord_bot.command(name="removeuser")
async def removeuser_cmd(ctx, member: discord.Member):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
    with sqlite3.connect("sparky.db") as db:
        db.execute("DELETE FROM allowed_admins WHERE user_id = ?", (member.id,))
    await ctx.send(f"✅ Removed administrator permissions from {member.mention}.")

@discord_bot.command(name="listusers")
async def listusers_cmd(ctx):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        admins = db.execute("SELECT * FROM allowed_admins").fetchall()
    
    msg_lines = ["**Authorized Admins List:**", f"• Owner: <@{OWNER_ID}>"]
    for aid in ADMIN_IDS:
        msg_lines.append(f"• Config Admin: <@{aid}>")
    for row in admins:
        msg_lines.append(f"• <@{row['user_id']}> (ID: {row['user_id']})")
    await ctx.send("\n".join(msg_lines))

@discord_bot.command(name="tgstop")
async def tgstop_cmd(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Only the bot owner can run this command.")
        return
    global tg_service_active
    tg_service_active = False
    await ctx.send("✅ Telegram bot services have been **paused**.")

@discord_bot.command(name="tgstart")
async def tgstart_cmd(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Only the bot owner can run this command.")
        return
    global tg_service_active
    tg_service_active = True
    await ctx.send("✅ Telegram bot services have been **resumed**.")

@discord_bot.command(name="withdraw")
async def withdraw_cmd(ctx):
    # Check current balance of worker
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT balance FROM workers WHERE user_id = ?", (ctx.author.id,)).fetchone()
        
    bal = row["balance"] if row else 0
    min_withdraw = get_setting("withdraw_min", 100)
    
    if bal < min_withdraw:
        await ctx.send(f"❌ You do not have enough balance to withdraw. Minimum is **{min_withdraw} coins** (your balance: **{bal} coins**).")
        return
        
    prompt = await ctx.send(
        f"🪙 You have **{bal} coins**. Please reply to this message with your UPI ID / payout details, or upload your payment QR code image within 60 seconds."
    )
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
        
    try:
        msg = await discord_bot.wait_for('message', check=check, timeout=60.0)
    except asyncio.TimeoutError:
        await prompt.edit(content="❌ Payout request timed out. Please run `!withdraw` again when ready.")
        return
        
    payout_details = msg.content.strip() if msg.content else "No text details provided"
    qr_url = None
    if msg.attachments:
        qr_url = msg.attachments[0].url
        
    if not msg.content and not msg.attachments:
        await ctx.send("❌ Payout request cancelled: No details or QR attachment provided.")
        return
        
    # Deduct the balance from worker in DB immediately to prevent double spending
    with sqlite3.connect("sparky.db") as db:
        db.execute("UPDATE workers SET balance = balance - ? WHERE user_id = ?", (bal, ctx.author.id))
        
    # Log to hardcoded channel 1520019495626735718
    try:
        coin_log_channel = await get_or_fetch_channel(1520019495626735718)
        if coin_log_channel:
            coin_embed = discord.Embed(
                title="🪙 Payout Requested (Deduction)",
                description=(
                    f"**Worker**: {ctx.author.mention} (ID: `{ctx.author.id}`)\n"
                    f"**Amount**: `-{bal} coins`\n"
                    f"**New Balance**: `0 coins`"
                ),
                color=discord.Color.orange(),
                timestamp=datetime.datetime.utcnow()
            )
            await coin_log_channel.send(embed=coin_embed)
    except Exception as e:
        print(f"Error logging payout request deduction: {e}")
        
    # Create the embed
    embed = discord.Embed(
        title="Payout Request Submitted",
        description=(
            f"**Worker**: {ctx.author.mention} (ID: `{ctx.author.id}`)\n"
            f"**Amount**: **{bal} coins**\n"
            f"**Details**: {payout_details}"
        ),
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow()
    )
    if qr_url:
        embed.set_image(url=qr_url)
        
    # Add the approve button
    # Custom ID format: approve_payout_<worker_id>_<amount>
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label="Approved", 
            style=discord.ButtonStyle.success, 
            custom_id=f"approve_payout_{ctx.author.id}_{bal}"
        )
    )
    
    # Forward it to the payout channel 1520675082949890088
    try:
        payout_channel = await get_or_fetch_channel(1520675082949890088)
        if payout_channel:
            await payout_channel.send(
                content=f"🔔 New payout request from {ctx.author.mention}!",
                embed=embed,
                view=view
            )
            await ctx.send(f"✅ Your payout request for **{bal} coins** has been submitted for approval.")
        else:
            # If channel is not found, refund balance and raise error
            with sqlite3.connect("sparky.db") as db:
                db.execute("UPDATE workers SET balance = balance + ? WHERE user_id = ?", (bal, ctx.author.id))
            await ctx.send("❌ Error: Payout channel not found. Payout request cancelled and balance refunded.")
    except Exception as e:
        print(f"Error submitting payout: {e}")
        # Refund on failure
        with sqlite3.connect("sparky.db") as db:
            db.execute("UPDATE workers SET balance = balance + ? WHERE user_id = ?", (bal, ctx.author.id))
        await ctx.send(f"❌ Failed to submit payout request: {e}. Balance refunded.")


@discord_bot.command(name="withdrawminset")
async def withdrawminset_cmd(ctx, amount: int):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
        
    if amount <= 0:
        await ctx.send("❌ Minimum amount must be greater than zero.")
        return
        
    set_setting("withdraw_min", amount)
    await ctx.send(f"✅ Minimum withdrawal limit has been set to **{amount} coins**.")


@discord_bot.command(name="jobs", aliases=["active"])
async def active_jobs_cmd(ctx):
    if not is_admin_user(ctx.author.id, ctx.author.guild_permissions):
        await ctx.send("❌ You do not have permission to run this command.")
        return
        
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        claimed = db.execute("SELECT * FROM panels WHERE status = 'claimed'").fetchall()
        available = db.execute("SELECT * FROM panels WHERE status = 'available'").fetchall()
        
    msg_lines = []
    msg_lines.append(f"📊 **Current Job Panels Status:**")
    msg_lines.append(f"• **Available Panels (Unclaimed)**: {len(available)}")
    msg_lines.append(f"• **Active Panels (In Progress)**: {len(claimed)}")
    
    if claimed:
        msg_lines.append("\n**Active Worker Assignments:**")
        for panel in claimed:
            worker_mention = f"<@{panel['worker_id']}>"
            # Get job count in this panel
            with sqlite3.connect("sparky.db") as db:
                db.row_factory = sqlite3.Row
                jobs_count = db.execute("SELECT COUNT(*) FROM jobs WHERE panel_id = ?", (panel["panel_id"],)).fetchone()[0]
            claimed_duration = int(time.time() - panel["claimed_at"])
            msg_lines.append(f"• Panel #{panel['panel_id']} ({jobs_count} QRs) claimed by {worker_mention} ({claimed_duration}s ago)")
            
    await ctx.send("\n".join(msg_lines))

# --- UPLOAD TIMEOUT PROCESSOR ---
async def wait_and_process_uploads(chat_id: int, target_time: float):
    await asyncio.sleep(5)
    
    states = load_states()
    session = states.get(chat_id, {})
    if not session or session.get("state") != STATE_AWAITING_TOKEN:
        return
        
    last_time = session.get("last_upload_time", 0)
    # Check if a newer upload has reset this timer
    if abs(last_time - target_time) < 0.01:
        # 5-second quiet period reached! Process all pending jobs
        with sqlite3.connect("sparky.db") as db:
            db.row_factory = sqlite3.Row
            pending_jobs = db.execute(
                "SELECT * FROM jobs WHERE tg_chat_id = ? AND status = 'pending_panel' ORDER BY job_id ASC",
                (chat_id,)
            ).fetchall()
            
        if not pending_jobs:
            return
            
        received_count = len(pending_jobs)
        chunk_size = 5
        chunks = [pending_jobs[i:i + chunk_size] for i in range(0, len(pending_jobs), chunk_size)]
        
        now_ts = time.time()
        for chunk in chunks:
            panel_id = None
            with sqlite3.connect("sparky.db") as db:
                cur = db.execute("INSERT INTO panels (status, created_at) VALUES ('available', ?)", (now_ts,))
                panel_id = cur.lastrowid
                
                for job in chunk:
                    db.execute(
                        "UPDATE jobs SET panel_id = ?, status = 'available' WHERE job_id = ?",
                        (panel_id, job["job_id"])
                    )

            # Post the Job Panel Card on Discord
            panel_channel = await get_or_fetch_channel(DISCORD_PANEL_CHANNEL_ID)
            if panel_channel:
                embed = discord.Embed(
                    title="New Job Panel Available!",
                    description=f"**Panel ID**: {panel_id}\nContains: **{len(chunk)} QRs**\nPayout: **10 Coins per QR**",
                    color=discord.Color.purple()
                )
                view = discord.ui.View(timeout=None)
                view.add_item(discord.ui.Button(label="Claim", style=discord.ButtonStyle.primary, custom_id=f"claim_panel_{panel_id}"))
                
                msg = await panel_channel.send(
                    content=f"<@&{DISCORD_WORKER_ROLE_ID}> New job panel posted!",
                    embed=embed,
                    view=view
                )
                
                with sqlite3.connect("sparky.db") as db:
                    db.execute("UPDATE panels SET discord_msg_id = ? WHERE panel_id = ?", (msg.id, panel_id))
                    
        # Reset state to idle
        states = load_states()
        states[chat_id] = {"state": STATE_IDLE}
        save_states(states)
        
        try:
            await bot_client.send_message(
                chat_id,
                "Your QR confirmations will arrive shortly."
            )
        except Exception as e:
            print(f"Error sending final completion message: {e}")


# --- TELEGRAM BOT EVENT HANDLERS ---
@bot_client.on(events.NewMessage(pattern="/start"))
async def tg_start_handler(event):
    if not tg_service_active:
        sender = await event.get_sender()
        username = sender.username or ""
        if username.lower() != "sleepu69":
            await event.reply("⚠️ Bot services are currently paused by the administrator.")
            return

    briefing_msg = (
        "👋 **Welcome to the Bot!** Here is a list of available commands:\n\n"
        "💸 `/deposit` - Request a new deposit (USDT BEP20 / Polygon)\n"
        "🤖 `/startqr` - Start submitting QRs (requires balance)\n"
        "💰 `/balance` - Check your current balance\n"
        "📞 `/support` - Get support contact info"
    )
    await event.reply(briefing_msg)

@bot_client.on(events.NewMessage(pattern="/deposit"))
async def tg_deposit_handler(event):
    if not tg_service_active:
        sender = await event.get_sender()
        username = sender.username or ""
        if username.lower() != "sleepu69":
            await event.reply("⚠️ Bot services are currently paused by the administrator.")
            return

    chat_id = event.chat_id
    states = load_states()
    states[chat_id] = {"state": STATE_AWAITING_DEPOSIT_AMOUNT}
    save_states(states)
    
    await event.reply("How much would you like to deposit (in USD)?")

@bot_client.on(events.NewMessage(pattern="/support"))
async def tg_support_handler(event):
    if not tg_service_active:
        sender = await event.get_sender()
        username = sender.username or ""
        if username.lower() != "sleepu69":
            await event.reply("⚠️ Bot services are currently paused by the administrator.")
            return

    await event.reply("For support, please contact the owner: @SLEEPU69")

@bot_client.on(events.NewMessage(pattern="/balance"))
async def tg_balance_handler(event):
    if not tg_service_active:
        sender = await event.get_sender()
        username = sender.username or ""
        if username.lower() != "sleepu69":
            await event.reply("⚠️ Bot services are currently paused by the administrator.")
            return

    chat_id = event.chat_id
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
    
    bal = row["balance"] if row else 0.0
    await event.reply(f"Your current balance is: ${bal:.2f}")

@bot_client.on(events.NewMessage(pattern=r"^/tgstop$"))
async def tg_service_stop_handler(event):
    sender = await event.get_sender()
    username = sender.username or ""
    if username.lower() != "sleepu69":
        return
        
    global tg_service_active
    tg_service_active = False
    await event.reply("✅ Telegram bot services have been **paused**.")

@bot_client.on(events.NewMessage(pattern=r"^/tgstart$"))
async def tg_service_start_handler(event):
    sender = await event.get_sender()
    username = sender.username or ""
    if username.lower() != "sleepu69":
        return
        
    global tg_service_active
    tg_service_active = True
    await event.reply("✅ Telegram bot services have been **resumed**.")

@bot_client.on(events.NewMessage(pattern="/startqr"))
async def tg_start_qr_handler(event):
    if not tg_service_active:
        sender = await event.get_sender()
        username = sender.username or ""
        if username.lower() != "sleepu69":
            await event.reply("⚠️ Bot services are currently paused by the administrator.")
            return

    chat_id = event.chat_id
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
    
    bal = row["balance"] if row else 0.0
    if bal < 0.50:
        await event.reply("❌ You do not have enough balance to submit (Minimum: $0.50). Please use /deposit to request a deposit.")
        return
        
    states = load_states()
    states[chat_id] = {"state": STATE_AWAITING_COUNT}
    save_states(states)
    
    await event.reply("How many QRs will you be sending?")

@bot_client.on(events.NewMessage)
async def tg_message_handler(event):
    # Ignore commands (handled separately)
    if event.message.text and event.message.text.startswith("/"):
        return
        
    if not tg_service_active:
        sender = await event.get_sender()
        username = sender.username or ""
        if username.lower() != "sleepu69":
            await event.reply("⚠️ Bot services are currently paused by the administrator.")
            return
        
    chat_id = event.chat_id
    states = load_states()
    session = states.get(chat_id, {"state": STATE_IDLE})
    state = session.get("state", STATE_IDLE)
    
    sender = await event.get_sender()
    username = sender.username or str(chat_id)
    
    if state == STATE_AWAITING_COUNT:
        text = (event.message.text or "").strip()
        if not text.isdigit():
            await event.reply("Please send a valid number.")
            return
            
        count = int(text)
        if count < 1 or count > 100:
            await event.reply("Please enter a number between 1 and 100.")
            return
            
        total = count * 0.50
        
        # Get sender's balance
        with sqlite3.connect("sparky.db") as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
        bal = row["balance"] if row else 0.0
        
        if bal < total:
            await event.reply(
                f"❌ Insufficient balance for {count} QRs (requires ${total:.2f}, but you have ${bal:.2f}).\n\n"
                f"Please use /deposit to add more balance, or reply with a smaller number."
            )
            return
            
        session["state"] = STATE_AWAITING_TOKEN
        session["count"] = count
        session["total"] = total
        states[chat_id] = session
        save_states(states)
        
        await event.reply(
            f"Your current balance is: ${bal:.2f} (using ${total:.2f} for this batch of {count} QRs).\n\n"
            f"Please send QRs with the Stripe payment link\n"
            f"* DONT SEND ANY UNNECCESSARY THINGS *"
        )

    elif state == STATE_AWAITING_DEPOSIT_AMOUNT:
        text = (event.message.text or "").strip()
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            await event.reply("Please enter a valid positive decimal amount (e.g., 5 or 10.50).")
            return
            
        session["state"] = STATE_AWAITING_TXID
        session["total"] = amount
        states[chat_id] = session
        save_states(states)
        
        target_address = "0xE9d2b69488DcFa424B535f765761b2da6ddE328f"
        payment_msg = (
            f"Please send exactly **${amount:.2f} USDT** on this address: USDT - `{target_address}`\n\n"
            f"Once the transaction is sent, please drop your Transaction Hash (TXID) below to verify."
        )
        await event.reply(payment_msg)

    elif state == STATE_AWAITING_TXID:
        tx_hash = (event.message.text or "").strip().lower()
        
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
            
        if len(tx_hash) != 66 or not all(c in "0123456789abcdef" for c in tx_hash[2:]):
            await event.reply("❌ Invalid transaction hash format. Please ensure you copied the full TX Hash (66 characters starting with 0x).")
            return
            
        # Check if TXID was already used to prevent double-spending
        with sqlite3.connect("sparky.db") as db:
            db.row_factory = sqlite3.Row
            existing = db.execute("SELECT * FROM used_txids WHERE tx_hash = ?", (tx_hash,)).fetchone()
            
        if existing:
            await event.reply("❌ This transaction has already been used to deposit. Please provide a fresh TXID.")
            return
            
        total = session.get("total", 0.50)
        target_address = "0xE9d2b69488DcFa424B535f765761b2da6ddE328f"
        
        status_msg = await event.reply("⌛ Verifying transaction on the blockchain, please wait...")
        
        # Check BSC network first
        is_success = await asyncio.to_thread(
            verify_evm_transaction, 
            "bsc", 
            tx_hash, 
            target_address, 
            total
        )
        
        # If BSC fails, fall back to check Polygon network
        if not is_success:
            print("[System] BSC verification failed. Checking Polygon network...")
            is_success = await asyncio.to_thread(
                verify_evm_transaction, 
                "polygon", 
                tx_hash, 
                target_address, 
                total
            )
        
        try:
            await status_msg.delete()
        except:
            pass
            
        if is_success:
            # Prevent double spend by marking this TXID as used
            with sqlite3.connect("sparky.db") as db:
                db.execute("INSERT OR REPLACE INTO used_txids (tx_hash, used_at) VALUES (?, ?)", (tx_hash, time.time()))
                
                # Check if sender exists in DB
                row = db.execute("SELECT * FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
                if row:
                    db.execute("UPDATE senders SET balance = balance + ? WHERE chat_id = ?", (total, chat_id))
                else:
                    db.execute("INSERT INTO senders (chat_id, username, balance) VALUES (?, ?, ?)", (chat_id, username, total))
                    
            # Move to awaiting QRs
            session["state"] = STATE_AWAITING_TOKEN
            states[chat_id] = session
            save_states(states)
            
            await event.reply(
                f"✅ **Payment Verified!** ${total:.2f} has been added to your balance.\n\n"
                f"Please start sending your QR codes with the Stripe link in the same message."
            )

            # Log to Discord approval channel
            try:
                channel = await get_or_fetch_channel(DISCORD_APPROVAL_CHANNEL_ID)
                if channel:
                    embed = discord.Embed(
                        title="💰 Successful Crypto Deposit",
                        description=(
                            f"**Telegram User**: @{username} (ID: `{chat_id}`)\n"
                            f"**Amount**: **${total:.2f} USDT**\n"
                            f"**TXID**: `{tx_hash}`"
                        ),
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.utcnow()
                    )
                    await channel.send(embed=embed)
            except Exception as d_err:
                print(f"Error logging successful deposit to Discord: {d_err}")
        else:
            await event.reply(
                f"❌ **Verification Failed!**\n"
                f"Could not find a confirmed USDT transfer of **${total:.2f}** to USDT - `{target_address}` in this transaction on either the BSC (BEP20) or Polygon network.\n\n"
                f"Please verify that the transaction is fully confirmed on the blockchain and you sent the correct amount, then reply with the correct TXID again."
            )
        
    elif state == STATE_AWAITING_CONFIRMATION:
        text = (event.message.text or "").strip().lower()
        if text not in ["confirm", "sent"]:
            await event.reply("Please confirm by replying with 'Confirm' or 'Sent'.")
            return
            
        count = session.get("count", 1)
        total = session.get("total", 0.50)
        
        session["state"] = STATE_AWAITING_APPROVAL
        states[chat_id] = session
        save_states(states)
        
        await event.reply("Request sent to admin for approval. Please wait...")
        
        # Trigger Discord Bot notification in the approval channel
        try:
            channel = await get_or_fetch_channel(DISCORD_APPROVAL_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="New Payment Request",
                    description=f"Telegram user @{username} has confirmed sending payment.",
                    color=discord.Color.purple()
                )
                embed.add_field(name="Quantity", value=f"{count} QRs", inline=True)
                embed.add_field(name="Total Price", value=f"${total:.2f}", inline=True)
                
                view = DiscordApprovalView(chat_id, username, count, total)
                await channel.send(content=f"@everyone New payment request to approve!", embed=embed, view=view)
            else:
                print(f"Error: Approval channel {DISCORD_APPROVAL_CHANNEL_ID} not found.")
        except Exception as d_err:
            print(f"Error sending Discord approval notification: {d_err}")
            
    elif state == STATE_AWAITING_TOKEN:
        # Expecting QR images with Stripe link in caption/text
        stripe_url = None
        text = event.message.text or ""
        
        # Match Stripe or OpenAI URLs
        url_match = re.search(r'(https://[a-zA-Z0-9\-\.]*(?:stripe\.com|openai\.com)/[^\s"\'<>]+)', text)
        if url_match:
            stripe_url = url_match.group(1).strip()
            
        if not stripe_url and event.message.file:
            caption = event.message.message or ""
            url_match = re.search(r'(https://[a-zA-Z0-9\-\.]*(?:stripe\.com|openai\.com)/[^\s"\'<>]+)', caption)
            if url_match:
                stripe_url = url_match.group(1).strip()
                
        if not stripe_url:
            await event.reply("Please send the QR image with the Stripe payment link in the same message.")
            return
            
        temp_qr_path = ""
        if event.message.file:
            os.makedirs("qrs", exist_ok=True)
            temp_qr_path = f"qrs/qr_{chat_id}_{event.message.id}.png"
            try:
                await event.message.download_media(file=temp_qr_path)
            except Exception as e:
                await event.reply(f"Failed to download QR image: {e}")
                return
                
        # Check if we have a valid stripe_url at this point
        if not stripe_url:
            await event.reply("Please send the Stripe payment link in your message.")
            return
            

            
        # Check if sender has enough balance
        with sqlite3.connect("sparky.db") as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
            
        balance = row["balance"] if row else 0.0
        if balance < 0.50:
            await event.reply("❌ Submission failed: Insufficient balance. Please check /balance or request a new deposit.")
            return

        # Save job record (initially has status = 'pending_panel', panel_id = None)
        job_id = None
        new_balance = 0.0
        with sqlite3.connect("sparky.db") as db:
            cur = db.execute(
                "INSERT INTO jobs (tg_chat_id, tg_msg_id, stripe_url, qr_file_path, status) VALUES (?, ?, ?, ?, 'pending_panel')",
                (chat_id, event.message.id, stripe_url, temp_qr_path)
            )
            job_id = cur.lastrowid
            
            # Deduct 0.50 from sender's balance
            db.execute("UPDATE senders SET balance = balance - 0.50 WHERE chat_id = ?", (chat_id,))
            
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
            if row:
                new_balance = row["balance"]

        # Alert sender if balance drops below $1.00
        if new_balance < 1.00:
            try:
                await bot_client.send_message(
                    chat_id,
                    f"⚠️ Warning: Your balance is low (${new_balance:.2f}). Please top up soon."
                )
            except Exception as e:
                print(f"Error notifying low balance: {e}")


        # Reset 30-second quiet period timer
        now = time.time()
        session["last_upload_time"] = now
        states[chat_id] = session
        save_states(states)
        
        asyncio.create_task(wait_and_process_uploads(chat_id, now))

# --- DATABASE BACKUP AND RESTORE ON DISCORD CHANNELS ---
DB_WORKERS_CHANNEL_ID = 1521090428554842172
DB_TG_BAL_CHANNEL_ID = 1521090483529584764

db_restored = False
db_sync_lock = asyncio.Lock()
last_workers_json = ""
last_senders_json = ""

async def restore_db_from_discord():
    global db_restored, last_workers_json, last_senders_json
    if db_restored:
        return
    print("[DB Restore] Attempting to restore database tables from Discord channels...")
    
    # 1. Restore workers table
    try:
        workers_chan = await get_or_fetch_channel(DB_WORKERS_CHANNEL_ID)
        if workers_chan:
            async for message in workers_chan.history(limit=10):
                if message.attachments:
                    attachment = message.attachments[0]
                    if attachment.filename.endswith(".json"):
                        print(f"[DB Restore] Found workers backup file: {attachment.filename}")
                        content_bytes = await attachment.read()
                        data = json.loads(content_bytes.decode("utf-8"))
                        with sqlite3.connect("sparky.db") as db:
                            for row in data:
                                db.execute(
                                    "INSERT OR REPLACE INTO workers (user_id, username, balance) VALUES (?, ?, ?)",
                                    (row["user_id"], row["username"], row["balance"])
                                )
                        last_workers_json = json.dumps(data, sort_keys=True)
                        print(f"[DB Restore] Restored {len(data)} workers from Discord.")
                        break
    except Exception as e:
        print(f"[DB Restore Error] Failed to restore workers: {e}")
        
    # 2. Restore senders table
    try:
        senders_chan = await get_or_fetch_channel(DB_TG_BAL_CHANNEL_ID)
        if senders_chan:
            async for message in senders_chan.history(limit=10):
                if message.attachments:
                    attachment = message.attachments[0]
                    if attachment.filename.endswith(".json"):
                        print(f"[DB Restore] Found senders backup file: {attachment.filename}")
                        content_bytes = await attachment.read()
                        data = json.loads(content_bytes.decode("utf-8"))
                        with sqlite3.connect("sparky.db") as db:
                            for row in data:
                                db.execute(
                                    "INSERT OR REPLACE INTO senders (chat_id, username, balance) VALUES (?, ?, ?)",
                                    (row["chat_id"], row["username"], row["balance"])
                                )
                        last_senders_json = json.dumps(data, sort_keys=True)
                        print(f"[DB Restore] Restored {len(data)} senders from Discord.")
                        break
    except Exception as e:
        print(f"[DB Restore Error] Failed to restore senders: {e}")
        
    db_restored = True
    print("[DB Restore] Database restoration process completed.")

@tasks.loop(seconds=5)
async def sync_db_to_discord():
    global last_workers_json, last_senders_json, db_restored
    if not db_restored:
        return
        
    async with db_sync_lock:
        # Sync workers
        try:
            with sqlite3.connect("sparky.db") as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("SELECT user_id, username, balance FROM workers").fetchall()
            workers_list = [{"user_id": r["user_id"], "username": r["username"], "balance": r["balance"]} for r in rows]
            workers_json = json.dumps(workers_list, sort_keys=True)
            
            if workers_json != last_workers_json:
                print("[DB Sync] Workers balance changed. Uploading backup to Discord...")
                workers_chan = await get_or_fetch_channel(DB_WORKERS_CHANNEL_ID)
                if workers_chan:
                    temp_file = "workers_backup.json"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(workers_json)
                    
                    file = discord.File(temp_file)
                    await workers_chan.send(content=f"📦 **Workers Database Backup** | Synced at `{datetime.datetime.utcnow().isoformat()}`", file=file)
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                    last_workers_json = workers_json
                    print("[DB Sync] Workers backup uploaded successfully.")
        except Exception as e:
            print(f"[DB Sync Error] Failed to sync workers: {e}")
            
        # Sync senders
        try:
            with sqlite3.connect("sparky.db") as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("SELECT chat_id, username, balance FROM senders").fetchall()
            senders_list = [{"chat_id": r["chat_id"], "username": r["username"], "balance": r["balance"]} for r in rows]
            senders_json = json.dumps(senders_list, sort_keys=True)
            
            if senders_json != last_senders_json:
                print("[DB Sync] Senders balance changed. Uploading backup to Discord...")
                senders_chan = await get_or_fetch_channel(DB_TG_BAL_CHANNEL_ID)
                if senders_chan:
                    temp_file = "senders_backup.json"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(senders_json)
                    
                    file = discord.File(temp_file)
                    await senders_chan.send(content=f"📦 **Senders Database Backup** | Synced at `{datetime.datetime.utcnow().isoformat()}`", file=file)
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                    last_senders_json = senders_json
                    print("[DB Sync] Senders backup uploaded successfully.")
        except Exception as e:
            print(f"[DB Sync Error] Failed to sync senders: {e}")

@discord_bot.event
async def on_ready():
    print(f"[Discord Bot] Logged in and ready as: {discord_bot.user}")
    
    # Restore DB on boot
    await restore_db_from_discord()
    
    # Start the sync loop if not already running
    if not sync_db_to_discord.is_running():
        sync_db_to_discord.start()

# --- SERVICE RUNNER ---
async def start_services():
    init_db()

    print("[Telegram Bot] Connecting...")
    await bot_client.start(bot_token=TELEGRAM_BOT_TOKEN)
    print("[Telegram Bot] Connected and listening.")

    print("[Discord Bot] Starting background task...")
    asyncio.create_task(discord_bot.start(DISCORD_TOKEN))
    
    # Start Discord presence monitor loop
    monitor_claimed_panels.start()

    # Keep bot telegram loop alive
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    if DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN" or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("[-] Configuration Error: Please check your environment variables.")
        sys.exit(1)
        
    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        print("\n[System] Services stopped by user.")
