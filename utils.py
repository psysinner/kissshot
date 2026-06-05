import asyncio
import time
import math
import logging
import aiohttp
from shortzy import Shortzy  # Ensure pip install shortzy
import os, uuid, subprocess
import random, string
# --- FIX: Added AUTH_CHANNEL, AUTH_PICS to imports ---
from info import SHORTLINK_API, SHORTLINK_URL, POST_SHORTLINK_API, POST_SHORTLINK_URL, AUTH_CHANNEL, AUTH_PICS
from database.users_db import db
from pyrogram.enums import ParseMode
from Script import script

# --- FIX: Added missing Pyrogram Types & Errors ---
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import (
    FloodWait, 
    InputUserDeactivated, 
    UserIsBlocked, 
    PeerIdInvalid, 
    UserNotParticipant,  # Required for Force Sub
    ChatAdminRequired    # Required for Force Sub
)

# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# -------------------------- TEMPORARY DATA STORAGE -------------------------- #
class temp(object):
    ME = None
    U_NAME = None
    B_NAME = None
    B_LINK = None
    BOT = None
    USERS_CANCEL = False
    CANCEL = False  
    START_TIME = 0  
    CURRENT = 0    

# =================================================
# 📢 FORCE SUBSCRIBE CHECK (Updated)
# =================================================
async def is_user_joined(bot, message: Message) -> bool:
    # Agar AUTH_CHANNEL khali hai to check skip karo
    if not AUTH_CHANNEL:
        return True

    user_id = message.from_user.id    
    not_joined_channels = []
    
    for channel_id in AUTH_CHANNEL:
        try:
            await bot.get_chat_member(channel_id, user_id)
        except UserNotParticipant:
            try:
                chat = await bot.get_chat(channel_id)
                try:
                    invite_link = await bot.export_chat_invite_link(channel_id)
                except ChatAdminRequired:
                    # Agar bot admin nahi hai to user ko batao
                    await message.reply_text(
                        text = (
                            "<i>🔒 Bᴏᴛ ɪs ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪs ᴄʜᴀɴɴᴇʟ.\n"
                            "Pʟᴇᴀsᴇ ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴅᴇᴠᴇʟᴏᴘᴇʀ:</i> "
                            "<b><a href='https://t.me/AV_SUPPORT_GROUP'>[ ᴄʟɪᴄᴋ ʜᴇʀᴇ ]</a></b>"
                        ),
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    return False
                except Exception as e:
                    logger.error(f"Failed to export link: {e}")
                    continue

                not_joined_channels.append((chat.title, invite_link))
            except Exception as e:
                logger.error(f"[ERROR] Chat fetch failed: {e}")
                continue
        except Exception as e:
            # Agar koi aur error aaye (jaise bot kicked), to ignore karo ya log karo
            # logger.error(f"[ERROR] get_chat_member failed: {e}")
            continue

    if not_joined_channels:
        buttons = [
            [InlineKeyboardButton(f"Join {title}", url=link)]
            for title, link in not_joined_channels
        ]
        # Try Again button
        try_again_link = f"https://t.me/{temp.U_NAME}?start=start" if temp.U_NAME else f"https://t.me/{temp.BOT.username}?start=start"
        
        buttons.append([
            InlineKeyboardButton("🔄 Try Again", url=try_again_link)
        ])
        
        try:
            if AUTH_PICS:
                await message.reply_photo(
                    photo=AUTH_PICS,
                    caption=script.AUTH_TXT.format(message.from_user.mention),
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    text=script.AUTH_TXT.format(message.from_user.mention),
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Error sending force sub message: {e}")
            
        return False

    return True

async def generate_thumbnail(video_path):
    thumb_path = f"/tmp/thumb_{uuid.uuid4().hex}.jpg"

    cmd = [
        "ffmpeg", "-i", video_path,
        "-ss", "00:00:01",
        "-vframes", "1",
        thumb_path
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await process.wait()
    return thumb_path if os.path.exists(thumb_path) else None

def generate_weird_name(length=8):
    chars = string.ascii_letters + string.digits + "@$#%&()-_"
    return "".join(random.choice(chars) for _ in range(length))
    
# =================================================
# ⏰ TIME FORMATTER (Seconds -> Readable)
# =================================================
def get_readable_time(seconds: int) -> str:
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    
    if len(time_list) == 4:
        ping_time += time_list.pop() + ", "

    time_list.reverse()
    ping_time += ":".join(time_list)
    return ping_time

# =================================================
# 💾 FILE SIZE FORMATTER (Bytes -> MB/GB)
# =================================================
def get_size(bytes, suffix="B"):
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

# =================================================
# ⏳ STRING TO SECONDS (For Auto-Delete etc.)
# =================================================
async def get_seconds(time_string):
    def extract_value_and_unit(ts):
        value = ""
        unit = ""
        index = 0
        while index < len(ts) and ts[index].isdigit():
            value += ts[index]
            index += 1
        unit = ts[index:].strip().lower()
        if value:
            value = int(value)
        else:
            value = 0
        return value, unit
        
    value, unit = extract_value_and_unit(time_string)
    
    unit_mapping = {
        's': 1, 'sec': 1, 'second': 1, 'seconds': 1,
        'min': 60, 'minute': 60, 'minutes': 60, 'm': 60,
        'hour': 3600, 'hours': 3600, 'h': 3600,
        'day': 86400, 'days': 86400, 'd': 86400,
        'month': 86400 * 30, 'months': 86400 * 30,
        'year': 86400 * 365, 'years': 86400 * 365
    }
    
    return value * unit_mapping.get(unit, 0)

# =================================================
# 📊 PROGRESS BAR GENERATOR
# =================================================
def get_progress_bar(percent, length=10):
    try:
        filled = int(length * percent / 100)
        unfilled = length - filled
        return '🟩' * filled + '⬜️' * unfilled
    except:
        return '🟩' * 0 + '⬜️' * length

# =================================================
# 📢 BROADCAST FUNCTION
# =================================================
async def users_broadcast(user_id, message, is_pin):
    try:
        m = await message.copy(chat_id=user_id)
        if is_pin:
            try:
                await m.pin(both_sides=True)
            except Exception:
                pass 
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await users_broadcast(user_id, message, is_pin)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - Removed from Database, since deleted account.")
        return False, "Deleted"
    except UserIsBlocked:
        logging.info(f"{user_id} - Blocked the bot.")
        await db.delete_user(user_id)
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - PeerIdInvalid")
        return False, "Error"
    except Exception as e:
        logging.error(f"Error broadcasting to {user_id}: {e}")
        return False, "Error"
        
# -------------------------- SHORT LINK GENERATOR (Manual) -------------------------- #
async def get_shortlink(link):
    API = POST_SHORTLINK_API
    URL_DOMAIN = POST_SHORTLINK_URL
    
    if not link.startswith("https"):
        link = link.replace("http", "https", 1)

    if "shareus.in" in URL_DOMAIN:
        req_url = f"https://{URL_DOMAIN}/shortLink"
        params = {"token": API, "format": "json", "link": link}
    else:
        req_url = f"https://{URL_DOMAIN}/api"
        params = {"api": API, "url": link}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(req_url, params=params, ssl=False) as response:
                data = await response.json(content_type=None)
                
                if data.get("status") == "success" or "shortenedUrl" in data:
                    return data.get("shortlink") or data.get("shortenedUrl")
                elif "short_url" in data: 
                    return data["short_url"]
                else:
                    logger.error(f"Manual Shorten Error: {data}")
                    
    except Exception as e:
        logger.error(f"Manual Shorten Exception: {e}")

    return f"https://{URL_DOMAIN}/api?api={API}&url={link}"

# -------------------------- SHORTENER HELPER (Shortzy Lib) -------------------------- #
async def get_shortlink_av(url):
    api = SHORTLINK_API
    site = SHORTLINK_URL

    try:
        shortzy = Shortzy(api, site)
        url = await shortzy.convert(url)
    except Exception as e:
        logger.error(f"Shortzy Error: {e}")
        try:
            shortzy = Shortzy(api, site)
            url = await shortzy.get_quick_link(url)
        except Exception:
            logger.error("Failed to generate shortlink via Shortzy")
            
    return url

# --- BACKGROUND DELETE HELPER ---
async def auto_delete_message(message, dlt_msg):
    await asyncio.sleep(600)
    try:
        await dlt_msg.delete()
        await message.delete()
    except Exception:
        pass
        
