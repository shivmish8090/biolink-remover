from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from pymongo import MongoClient
import re, os
api_id = os.getenv("API_ID", 0)
api_hash = os.getenv("API_HASH", "81719734c6a0af15e5d35006655c1f84")
bot_token = os.getenv("BOT_TOKEN", "8181075654:AAF_UqJxLYDp-odK8-SM-PK8WoTS_yX98cc")
mongodb_uri = os.getenv("MONGO_DB_URI", "mongodb+srv://Editguardian:Shiv@cluster0.bznqliz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

mongo_client = MongoClient(mongodb_uri)
db = mongo_client['bio_filter_bot']
settings_col = db['settings']
warnings_col = db['warnings']
approved_users_col = db['approved_users']  

url_pattern = re.compile(r'(https?://|www\.)[a-zA-Z0-9.\-]+(\.[a-zA-Z]{2,})+(/[a-zA-Z0-9._%+-]*)*')
mention_pattern = re.compile(r'@[ऀ-ॿa-zA-Z0-9_]{5,}')

def get_settings(chat_id):
    setting = settings_col.find_one({"chat_id": chat_id})
    return setting or {"chat_id": chat_id, "warn_limit": 3, "action": "mute"}

def set_settings(chat_id, warn_limit, action):
    settings_col.update_one({"chat_id": chat_id}, {"$set": {"warn_limit": warn_limit, "action": action}}, upsert=True)

def get_warnings(user_id):
    doc = warnings_col.find_one({"user_id": user_id})
    return doc["count"] if doc else 0

def add_warning(user_id):
    warnings_col.update_one({"user_id": user_id}, {"$inc": {"count": 1}}, upsert=True)

def clear_warning(user_id):
    warnings_col.delete_one({"user_id": user_id})

def is_approved(user_id, chat_id):
    return approved_users_col.find_one({"user_id": user_id, "chat_id": chat_id}) is not None

def approve_user(user_id, chat_id):
    approved_users_col.update_one({"user_id": user_id, "chat_id": chat_id}, {"$set": {"approved": True}}, upsert=True)

def unapprove_user(user_id, chat_id):
    approved_users_col.delete_one({"user_id": user_id, "chat_id": chat_id})

async def is_admin(client, chat_id, user_id):
    async for member in client.get_chat_members(chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
        if member.user.id == user_id:
            return True
    return False

@app.on_message(filters.group & filters.command("config"))
async def configure(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(client, chat_id, user_id):
        return await message.reply_text("<b>❌ You are not administrator</b>", parse_mode=enums.ParseMode.HTML)

    current = get_settings(chat_id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Warn", callback_data="warn")],
        [
            InlineKeyboardButton("Mute ✅" if current['action'] == "mute" else "Mute", callback_data="mute"),
            InlineKeyboardButton("Ban ✅" if current['action'] == "ban" else "Ban", callback_data="ban")
        ],
        [InlineKeyboardButton("Close", callback_data="close")]
    ])
    await message.reply_text("<b>Select punishment for users who have links or @username_remove?? in their bio:</b>",
                             reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

@app.on_callback_query()
async def callback_handler(client, cq):
    data = cq.data
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id

    if not await is_admin(client, chat_id, user_id):
        return await cq.answer("❌ You are not administrator", show_alert=True)

    current = get_settings(chat_id)

    if data == "close":
        return await cq.message.delete()

    elif data == "back":
        return await configure(client, cq.message)

    elif data == "warn":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("3 ✅" if current['warn_limit'] == 3 else "3", callback_data="warn_3"),
                InlineKeyboardButton("4 ✅" if current['warn_limit'] == 4 else "4", callback_data="warn_4"),
                InlineKeyboardButton("5 ✅" if current['warn_limit'] == 5 else "5", callback_data="warn_5")
            ],
            [InlineKeyboardButton("Back", callback_data="back"), InlineKeyboardButton("Close", callback_data="close")]
        ])
        return await cq.message.edit_text("<b>Select the number of warnings before punishment:</b>",
                                         reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    elif data in ["mute", "ban"]:
        set_settings(chat_id, current['warn_limit'], data)
        return await configure(client, cq.message)

    elif data.startswith("warn_"):
        limit = int(data.split("_")[1])
        set_settings(chat_id, limit, current['action'])
        return await configure(client, cq.message)

    elif data.startswith("unmute_"):
        uid = int(data.split("_")[1])
        try:
            await client.restrict_chat_member(chat_id, uid, ChatPermissions(can_send_messages=True))
            await cq.message.edit(f"<b>User <code>{uid}</code> has been unmuted</b>", parse_mode=enums.ParseMode.HTML)
        except:
            await cq.message.edit("I don't have permission to unmute users.")

    elif data.startswith("unban_"):
        uid = int(data.split("_")[1])
        try:
            await client.unban_chat_member(chat_id, uid)
            await cq.message.edit(f"<b>User <code>{uid}</code> has been unbanned</b>", parse_mode=enums.ParseMode.HTML)
        except:
            await cq.message.edit("I don't have permission to unban users.")

    await cq.answer()

@app.on_message(filters.group & filters.command("approve"))
async def approve_user_command(client, message):
    chat_id = message.chat.id
    from_user_id = message.from_user.id

    if not await is_admin(client, chat_id, from_user_id):
        return await message.reply_text("<b>❌ You are not an administrator</b>", parse_mode=enums.ParseMode.HTML)

    target_user = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        if arg.isdigit():
            try:
                target_user = await client.get_users(int(arg))
            except:
                return await message.reply_text("❌ Invalid user ID.")
        else:
            if arg.startswith("@"): arg = arg[1:]
            try:
                target_user = await client.get_users(arg)
            except:
                return await message.reply_text("❌ Invalid username.")
    else:
        return await message.reply_text("❌ Please reply to a message or provide a username/user ID.")

    if is_approved(target_user.id, chat_id):
        return await message.reply_text("❌ This user is already approved in this group.")

    approve_user(target_user.id, chat_id)
    await message.reply_text(f"✅ User {target_user.mention} has been approved for this group.")

@app.on_message(filters.group & filters.command("unapprove"))
async def unapprove_user_command(client, message):
    chat_id = message.chat.id
    from_user_id = message.from_user.id

    if not await is_admin(client, chat_id, from_user_id):
        return await message.reply_text("<b>❌ You are not an administrator</b>", parse_mode=enums.ParseMode.HTML)

    target_user = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        if arg.isdigit():
            try:
                target_user = await client.get_users(int(arg))
            except:
                return await message.reply_text("❌ Invalid user ID.")
        else:
            if arg.startswith("@"): arg = arg[1:]
            try:
                target_user = await client.get_users(arg)
            except:
                return await message.reply_text("❌ Invalid username.")
    else:
        return await message.reply_text("❌ Please reply to a message or provide a username/user ID.")

    if not is_approved(target_user.id, chat_id):
        return await message.reply_text("❌ This user is not approved in this group.")

    unapprove_user(target_user.id, chat_id)
    await message.reply_text(f"❌ User {target_user.mention} has been unapproved from this group.")

@app.on_message(filters.group & filters.command("approvelist"))
async def approvelist_command(client, message):
    chat_id = message.chat.id
    user_id_admin_check = message.from_user.id

    if not await is_admin(client, chat_id, user_id_admin_check):
        return await message.reply_text("<b>❌ You are not an administrator</b>", parse_mode=enums.ParseMode.HTML)

    approved_users = approved_users_col.find({"chat_id": chat_id})
    text = ""
    async for user_doc in approved_users:
        try:
            user = await client.get_users(user_doc['user_id'])
            text += f"• <code>{user.id}</code> | {user.first_name} (@{user.username or 'N/A'})\n"
        except:
            continue

    if not text:
        return await message.reply_text("❌ No users have been approved in this group.")

    await message.reply_text(f"✅ Approved Users in this group:\n\n{text}", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.group)
async def check_bio(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if is_approved(user_id, chat_id):
        return

    try:
        user_full = await client.get_chat(user_id)
    except:
        return

    bio = user_full.bio or ""
    username = f"@{user_full.username}" if user_full.username else user_full.first_name

    if re.search(url_pattern, bio) or re.search(mention_pattern, bio):
        try:
            await message.delete()
        except:
            return await message.reply_text("❌ Grant me delete message permissions.")

        current = get_settings(chat_id)
        warn_count = get_warnings(user_id) + 1
        add_warning(user_id)

        text = f"{username}, please remove <b>links or @username_remove??</b> from your bio.\nWarning {warn_count}/{current['warn_limit']}"
        reply = await message.reply_text(text, parse_mode=enums.ParseMode.HTML)

        if warn_count >= current['warn_limit']:
            if is_approved(user_id, chat_id):
                return await reply.edit(f"{username} is approved in this group, no action taken.")
            try:
                if current['action'] == "mute":
                    await client.restrict_chat_member(chat_id, user_id, ChatPermissions())
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unmute ✅", callback_data=f"unmute_{user_id}")]])
                    await reply.edit(f"{username} has been 🔇 muted.", reply_markup=kb)
                elif current['action'] == "ban":
                    await client.ban_chat_member(chat_id, user_id)
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unban ✅", callback_data=f"unban_{user_id}")]])
                    await reply.edit(f"{username} has been 🔨 banned.", reply_markup=kb)
            except:
                await reply.edit(f"I don't have permission to {current['action']} users.")
            clear_warning(user_id)

app.run()
