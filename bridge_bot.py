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
STATE_AWAITING_CONFIRMATION = "STATE_AWAITING_CONFIRMATION"
STATE_AWAITING_APPROVAL = "STATE_AWAITING_APPROVAL"
STATE_AWAITING_TOKEN = "STATE_AWAITING_TOKEN"

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

# Initialize Clients
bot_client = TelegramClient("bot_session", TELEGRAM_API_ID, TELEGRAM_API_HASH)

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
        # Force terminate any zombie chromedriver or chrome processes holding file locks
        try:
            if os.name == 'nt':
                os.system("taskkill /f /im chromedriver.exe >nul 2>&1")
                os.system("taskkill /f /im chrome.exe >nul 2>&1")
            else:
                os.system("pkill -9 -f chromedriver >/dev/null 2>&1")
                os.system("pkill -9 -f chrome >/dev/null 2>&1")
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


def verify_stripe_payment(url: str) -> bool:
    # 1. Fast Path: try using tls_client (very fast, uses low memory)
    session = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
    proxy = get_proxy_url()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    try:
        r = session.get(url, timeout_seconds=10)
        if r.status_code == 200 and "Action Successful" in r.text:
            print(f"[System] Stripe verified via tls_client for {url}")
            return True
    except Exception as e:
        print(f"tls_client verification check failed/errored: {e}")

    # 2. Slow Path Fallback: use headless undetected-chromedriver (renders JS, handles Cloudflare)
    print(f"[System] tls_client did not verify. Falling back to headless Chrome for {url}...")
    driver = None
    try:
        driver = create_headless_driver(proxy)
        driver.get(url)
        # Wait up to 6 seconds for client-side JS rendering
        time.sleep(6)
        if "Action Successful" in driver.page_source:
            print(f"[System] Stripe verified via headless Chrome for {url}")
            return True
    except Exception as e:
        print(f"Headless Chrome verification check failed/errored: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
                
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
            
        # Check 2-minute total timeout
        if now - claimed_at >= 120:
            deduct = (action_taken == 0)
            await handle_panel_failure(panel_id, worker_id, channel_id, reason="Timeout (2 minutes exceeded)", deduct_penalty=deduct)
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
            f"⚠️ **Warning**: You have 2 minutes to complete this job. If you go offline or exceed 2 minutes, 20 coins will be deducted."
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

    status_msg = await interaction.channel.send(f"⌛ Waiting 12 seconds for the Stripe transaction status to propagate...")
    await asyncio.sleep(12)
    await status_msg.edit(content=f"Verifying payment status on Stripe for Job #{job_id}...")
    
    # Run Stripe verification
    is_success = await asyncio.to_thread(verify_stripe_payment, job["stripe_url"])
    await status_msg.delete()
    
    if is_success:
        # Credit worker 10 coins
        with sqlite3.connect("sparky.db") as db:
            db.execute(
                "INSERT INTO workers (user_id, username, balance) VALUES (?, ?, 10) ON CONFLICT(user_id) DO UPDATE SET balance = balance + 10",
                (interaction.user.id, str(interaction.user),)
            )
            db.execute("UPDATE jobs SET status = 'success' WHERE job_id = ?", (job_id,))
            
        # Reply Success on Telegram
        try:
            await bot_client.send_message(
                job["tg_chat_id"], 
                "Success", 
                reply_to=job["tg_msg_id"]
            )
        except Exception as e:
            print(f"Error replying success to TG seller: {e}")
            
        # Edit the message to show Verified status and remove/disable the button
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="Status", value="✅ Verified & Paid (10 coins credited)", inline=False)
        await interaction.message.edit(embed=embed, view=None)
        
        await interaction.channel.send(f"🎉 **Job #{job_id} Verified!** 10 coins added to your balance.")
        
        # Check if all jobs in this panel are now success
        with sqlite3.connect("sparky.db") as db:
            db.row_factory = sqlite3.Row
            total_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE panel_id = ?", (panel_id,)).fetchone()[0]
            success_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE panel_id = ? AND status = 'success'", (panel_id,)).fetchone()[0]
            
        if success_jobs >= total_jobs:
            # Mark panel as success
            with sqlite3.connect("sparky.db") as db:
                db.execute("UPDATE panels SET status = 'success' WHERE panel_id = ?", (panel_id,))
                
            # Send Log to Log Channel
            try:
                log_channel = await get_or_fetch_channel(DISCORD_LOG_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="Job Closed",
                        description=f"Panel ID: {panel_id}\nStatus: **Success**\nWorker: {interaction.user.mention}",
                        color=discord.Color.green()
                    )
                    await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"Error sending log message: {e}")
                
            await interaction.channel.send("🎉 **All payments verified successfully!** Channel will delete in 5 seconds...")
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
        await interaction.channel.send(f"❌ **Verification failed for Job #{job_id}.** The link did not show 'Action Successful'. Please ensure you paid before clicking Scanned.")

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
    await asyncio.sleep(30)
    
    states = load_states()
    session = states.get(chat_id, {})
    if not session or session.get("state") != STATE_AWAITING_TOKEN:
        return
        
    last_time = session.get("last_upload_time", 0)
    # Check if a newer upload has reset this timer
    if abs(last_time - target_time) < 0.01:
        # 30-second quiet period reached! Process all pending jobs
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
    chat_id = event.chat_id
    states = load_states()
    states[chat_id] = {"state": STATE_AWAITING_COUNT}
    save_states(states)
    
    await event.reply("How many QRs will you be providing?")

@bot_client.on(events.NewMessage(pattern="/support"))
async def tg_support_handler(event):
    await event.reply("For support, please contact the owner: @Onnnnmi")

@bot_client.on(events.NewMessage(pattern="/balance"))
async def tg_balance_handler(event):
    chat_id = event.chat_id
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
    
    bal = row["balance"] if row else 0.0
    await event.reply(f"Your current balance is: ${bal:.2f}")

@bot_client.on(events.NewMessage(pattern=r"^/(usebalance|submit)$"))
async def tg_use_balance_handler(event):
    chat_id = event.chat_id
    with sqlite3.connect("sparky.db") as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT balance FROM senders WHERE chat_id = ?", (chat_id,)).fetchone()
    
    bal = row["balance"] if row else 0.0
    if bal < 0.50:
        await event.reply("❌ You do not have enough balance to submit (Minimum: $0.50). Please use /start to request a deposit.")
        return
        
    states = load_states()
    states[chat_id] = {"state": STATE_AWAITING_TOKEN}
    save_states(states)
    
    await event.reply(
        f"Your current balance is: ${bal:.2f}\n\n"
        "Please send QRs with the Stripe payment link\n"
        "* DONT SEND ANY UNNECCESSARY THINGS *"
    )

@bot_client.on(events.NewMessage)
async def tg_message_handler(event):
    # Ignore commands (handled separately)
    if event.message.text and event.message.text.startswith("/"):
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
        
        session["state"] = STATE_AWAITING_CONFIRMATION
        session["count"] = count
        session["total"] = total
        states[chat_id] = session
        save_states(states)
        
        payment_msg = (
            f"Total Amount: ${total:.2f} ({count} QRs * $0.50 each)\n\n"
            f"Please pay using the following method:\n"
            f"- Binance ID: `{BINANCE_ID}`\n\n"
            f"Once you have sent the payment, please reply with 'Confirm' or 'Sent' to submit it for approval."
        )
        await event.reply(payment_msg)
        
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
