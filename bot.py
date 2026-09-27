import os
import json
import asyncio
import subprocess
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# --- SOZLAMALAR ---
BOT_TOKEN = "8745450390:AAHLfFSs3xeBzlcQBTqvHTTQupWE_9V2dLI"
ADMIN_ID = 6526744258
CHANNEL_ID = -1004491053728

# Mini App havolangiz (Vercel yoki GitHub Pages linkini bu yerga qo'yasiz)
MINI_APP_URL = "https://sizning-saytingiz.vercel.app" 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Vaqtinchalik fayllar uchun papka
os.makedirs("downloads", exist_ok=True)
os.makedirs("output", exist_ok=True)

# /start komandasi
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Kechirasiz, bu bot shaxsiy foydalanish uchun!")
    
    await message.answer(
        "👋 **VibeStudio Botiga xush kelibsiz!**\n\n"
        "Menga MP3 audio fayl yoki videoni yuboring. Men uni Mini App uchun tayyorlab beraman.",
        parse_mode="Markdown"
    )

# Audio yoki Video qabul qilish
@dp.message(F.audio | F.video | F.document)
async def handle_media(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    status_msg = await message.answer("⏳ Fayl yuklab olinmoqda...")
    
    file_id = None
    if message.audio:
        file_id = message.audio.file_id
        ext = "mp3"
    elif message.video:
        file_id = message.video.file_id
        ext = "mp4"
    elif message.document:
        file_id = message.document.file_id
        ext = "mp3"

    file = await bot.get_file(file_id)
    raw_path = f"downloads/raw_{message.from_user.id}.{ext}"
    audio_path = f"downloads/audio_{message.from_user.id}.mp3"
    
    await bot.download_file(file.file_path, raw_path)

    # Agar video yuborilgan bo'lsa, audiosini ajratib olamiz
    if ext == "mp4":
        await status_msg.edit_text("🎵 Videodan audio ajratib olinmoqda...")
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_path,
            "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", audio_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(raw_path)
    else:
        os.rename(raw_path, audio_path)

    # Mini App tugmasi
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎨 Studiyani ochish (Video yasash)",
                web_app=WebAppInfo(url=f"{MINI_APP_URL}?user={message.from_user.id}")
            )
        ]
    ])

    await status_msg.delete()
    await message.answer(
        "✅ **Audio tayyor!**\n\nQuyidagi tugmani bosing va satrlarni sinxronlang:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Mini App'dan yuborilgan ma'lumotni qabul qilish
@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    data = json.loads(message.web_app_data.data)
    user_id = message.from_user.id
    audio_path = f"downloads/audio_{user_id}.mp3"

    if not os.path.exists(audio_path):
        return await message.answer("❌ Audio fayl topilmadi. Avval audio yuboring!")

    notify_msg = await message.answer("⚙️ **60 FPS Video renderlash boshlandi...**\nIlovadan chiqavering, tayyor bo'lgach kanalga tashlayman!", parse_mode="Markdown")

    # Render jarayonini orqa fonda ishga tushirish (Non-blocking)
    asyncio.create_task(process_video_render(data, user_id, audio_path, notify_msg))

# --- RENDER QILISH VA KANALGA YUBORISH ---
async def process_video_render(data, user_id, audio_path, notify_msg):
    title = data.get("title", "Musiqa")
    artist = data.get("artist", "Ijrochi")
    lyrics = data.get("lyrics", [])
    bg_color = data.get("bgColor", "#071326")
    
    ass_path = f"output/sub_{user_id}.ass"
    output_video = f"output/final_{user_id}.mp4"

    # 1. ASS Subtitle faylini yaratish (Silliq Spotify Scroll bilan)
    create_ass_file(ass_path, lyrics, title, artist)

    # 2. FFmpeg orqali 1080x1920 60 FPS video renderlash
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={bg_color}:s=1080x1920:r=60",
        "-i", audio_path,
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", "60",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-pix_fmt", "yuv420p",
        output_video
    ]

    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await process.communicate()

    # 3. Tayyor videoni maxfiy kanalga yuklash
    if os.path.exists(output_video):
        video_file = FSInputFile(output_video)
        caption = f"🎵 **{title}** — {artist}\n\n✨ @ms.music uslubida tayyorlandi (60 FPS 9:16)"
        
        # Maxfiy kanalga yuborish
        await bot.send_video(chat_id=CHANNEL_ID, video=video_file, caption=caption, parse_mode="Markdown")
        
        # Adminga xabar berish
        await notify_msg.edit_text("✅ **Video tayyor!** Maxfiy kanalga muvaffaqiyatli yuklandi.")

        # Vaqtinchalik fayllarni tozalash
        try:
            os.remove(ass_path)
            os.remove(output_video)
            os.remove(audio_path)
        except:
            pass
    else:
        await notify_msg.edit_text("❌ Render jarayonida xatolik yuz berdi.")

# --- SPOTIFY DILIK SCROLL VA TINIQ SHIFT UCHUN ASS GENERATORI ---
def create_ass_file(filepath, lyrics, title, artist):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HeaderTitle,Montserrat,64,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,80,80,180,1
Style: HeaderArtist,Montserrat,40,&H00A0A0A0,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,80,80,270,1
Style: LyricActive,Montserrat,58,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1
Style: LyricInactive,Montserrat,50,&H80A0A0A0,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header)
        
        # Qo'shiq va ijrochi nomi (yuqori chap burchakda proporsional turadi)
        f.write(f"Dialogue: 0,0:00:00.00,10:00:00.00,HeaderTitle,,0,0,0,,{title}\n")
        f.write(f"Dialogue: 0,0:00:00.00,10:00:00.00,HeaderArtist,,0,0,0,,{artist}\n")

        # Satrlar sinxroni (Har bir satr markazda yonadi va yuqoriga siljiydi)
        for i, item in enumerate(lyrics):
            start_sec = item["time"]
            end_sec = lyrics[i+1]["time"] if i+1 < len(lyrics) else start_sec + 4.0
            
            s_time = format_ass_time(start_sec)
            e_time = format_ass_time(end_sec)

            text = item["text"]
            # Faol satr (Oq, katta va markazda)
            f.write(f"Dialogue: 1,{s_time},{e_time},LyricActive,,0,0,0,,{{\\pos(540,960)}}{text}\n")
            
            # Keyingi keladigan satr (Pastda xira kutib turadi)
            if i + 1 < len(lyrics):
                next_text = lyrics[i+1]["text"]
                f.write(f"Dialogue: 0,{s_time},{e_time},LyricInactive,,0,0,0,,{{\\pos(540,1100)}}{next_text}\n")

            # Oldingi satr (Tepada xira bo'lib turadi)
            if i > 0:
                prev_text = lyrics[i-1]["text"]
                f.write(f"Dialogue: 0,{s_time},{e_time},LyricInactive,,0,0,0,,{{\\pos(540,820)}}{prev_text}\n")

def format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

async def main():
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
