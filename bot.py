i
import os
import json
import asyncio
import subprocess
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# --- ASOSIY SOZLAMALAR ---
BOT_TOKEN = "8745450390:AAHLfFSs3xeBzlcQBTqvHTTQupWE_9V2dLI"
ADMIN_ID = 6526744258
CHANNEL_ID = -1004491053728

# Mini App havolasi (Vercel yoki serveringiz manzili)
WEBAPP_URL = "https://sizning-saytingiz.vercel.app"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

os.makedirs("downloads", exist_ok=True)
os.makedirs("output", exist_ok=True)

# 1. BOT KOMANDALARI
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Kechirasiz, bu bot faqat admin uchun!")
    
    await message.answer(
        "👋 **VibeStudio Botiga xush kelibsiz!**\n\n"
        "Menga MP3 musiqa yoki video yuboring. Men uni tayyorlab, studiyani ochib beraman.",
        parse_mode="Markdown"
    )

# Audio yoki Video qabul qilib saqlash
@dp.message(F.audio | F.video | F.document)
async def media_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    msg = await message.answer("⏳ Fayl yuklab olinmoqda...")
    file_id = message.audio.file_id if message.audio else (message.video.file_id if message.video else message.document.file_id)
    is_video = bool(message.video)

    file = await bot.get_file(file_id)
    raw_path = f"downloads/raw_{ADMIN_ID}.mp4" if is_video else f"downloads/audio_{ADMIN_ID}.mp3"
    audio_path = f"downloads/audio_{ADMIN_ID}.mp3"

    await bot.download_file(file.file_path, raw_path)

    # Agar video yuborilgan bo'lsa, audiosini ajratamiz
    if is_video:
        await msg.edit_text("🎵 Videodan audio ajratib olinmoqda...")
        subprocess.run(["ffmpeg", "-y", "-i", raw_path, "-vn", "-b:a", "192k", audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(raw_path):
            os.remove(raw_path)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Studiyani ochish (Video yasash)", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await msg.delete()
    await message.answer("✅ **Audio qabul qilindi!**\nQuyidagi tugma orqali studiyani oching va satrlarni sinxronlang:", reply_markup=keyboard, parse_mode="Markdown")

# 2. HTTP API (MINI APP’DAN RASM VA MA'LUMOTLARNI QABUL QILISH)
async def api_render_endpoint(request):
    try:
        reader = await request.multipart()
        custom_bg = None
        custom_audio = None
        payload = {}

        while True:
            part = await reader.next()
            if part is None:
                break
            
            if part.name == 'image':
                if part.filename:
                    custom_bg = f"downloads/bg_{ADMIN_ID}.jpg"
                    with open(custom_bg, 'wb') as f:
                        while True:
                            chunk = await part.read_chunk()
                            if not chunk:
                                break
                            f.write(chunk)
            elif part.name == 'audio':
                if part.filename:
                    custom_audio = f"downloads/audio_{ADMIN_ID}.mp3"
                    with open(custom_audio, 'wb') as f:
                        while True:
                            chunk = await part.read_chunk()
                            if not chunk:
                                break
                            f.write(chunk)
            elif part.name == 'data':
                text = await part.text()
                payload = json.loads(text)

        # Orqa fonda 60 FPS render jarayonini boshlash
        asyncio.create_task(execute_video_pipeline(payload, custom_bg))
        return web.json_response({"status": "ok", "message": "Rendering started in background"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# 3. YUQORI SIFATLI 60 FPS RENDER VA AVTOMATIK KESISH
async def execute_video_pipeline(data, custom_bg):
    audio_path = f"downloads/audio_{ADMIN_ID}.mp3"
    if not os.path.exists(audio_path):
        return await bot.send_message(ADMIN_ID, "❌ Audio fayl topilmadi! Avval botga audio yuboring.")

    title = data.get("title", "Korolmaslar")
    artist = data.get("artist", "Afruza")
    lyrics = data.get("lyrics", [])
    bg_color = data.get("bgColor", "#1f0814")
    font_name = data.get("font", "Montserrat")

    # TALABINGIZ: Oxirgi satr aytilgach, 2 soniya o'tib videoni aniq kesib tashlash
    last_lyric_time = float(lyrics[-1]["time"]) if lyrics else 30.0
    end_cut_time = last_lyric_time + 2.0  # Ortiqcha jimjit joylari kesiladi

    ass_path = f"output/lyrics_{ADMIN_ID}.ass"
    output_video = f"output/vibe_{ADMIN_ID}.mp4"

    # ASS Subtitle yaratish
    build_spotify_ass(ass_path, lyrics, title, artist, font_name)

    await bot.send_message(ADMIN_ID, f"🎬 **60 FPS Video renderlash boshlandi...**\n⏱ Davomiyligi: {int(end_cut_time)} soniya.\nIlovadan chiqavering, tayyor bo'lgach maxfiy kanalga tashlayman!", parse_mode="Markdown")

    # FFmpeg Buyrug'i
    if custom_bg and os.path.exists(custom_bg):
        # Galereyadagi rasmni 1080x1920 ga crop qilish, xiralashtirish va qora filtr berish
        filter_str = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"boxblur=12:6,drawbox=c=black@0.45:w=iw:h=ih:t=fill,ass={ass_path}[outv]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", custom_bg,
            "-i", audio_path,
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "1:a",
            "-t", str(end_cut_time),  # AVTOMATIK KESISH
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-r", "60",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", output_video
        ]
    else:
        # Baxmal fon rangi
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={bg_color}:s=1080x1920:r=60",
            "-i", audio_path,
            "-vf", f"ass={ass_path}",
            "-t", str(end_cut_time),  # AVTOMATIK KESISH
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-r", "60",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", output_video
        ]

    # Renderni orqa fonda bajarish
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await process.communicate()

    # KANALGA YUBORISH
    if os.path.exists(output_video):
        video_file = FSInputFile(output_video)
        caption = (
            f"🎵 **{title}** — {artist}\n"
            f"🔥 **Sifat:** 1080x1920 (60 FPS)\n"
            f"⏱ **Davomiyligi:** {int(end_cut_time)} soniya\n\n"
            f"✨ @ms.music uslubida tayyorlandi"
        )
        
        await bot.send_video(chat_id=CHANNEL_ID, video=video_file, caption=caption, parse_mode="Markdown")
        await bot.send_message(ADMIN_ID, "✅ **Video tayyor!** Maxfiy kanalga muvaffaqiyatli tashlandi.")

        # Vaqtinchalik fayllarni o'chirish
        try:
            if custom_bg and os.path.exists(custom_bg):
                os.remove(custom_bg)
            os.remove(ass_path)
            os.remove(output_video)
        except:
            pass
    else:
        await bot.send_message(ADMIN_ID, "❌ Renderda xatolik yuz berdi. FFmpeg buyrug'i bajarilmadi.")

# SPOTIFY DILIK SILIQ SCROLL QILUVCHI ASS GENERATORI
def build_spotify_ass(filepath, lyrics, title, artist, font):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: SongTitle,{font},64,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,80,80,180,1
Style: ArtistName,{font},38,&H00C0C0C0,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,80,80,265,1
Style: ActiveLine,{font},60,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,5,80,80,0,1
Style: DimmedLine,{font},48,&H70A0A0A0,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header)
        # Nomi va Ijrochi (tepada proporsional)
        f.write(f"Dialogue: 0,0:00:00.00,10:00:00.00,SongTitle,,0,0,0,,{title}\n")
        f.write(f"Dialogue: 0,0:00:00.00,10:00:00.00,ArtistName,,0,0,0,,{artist}\n")

        # Satrlar sinxroni (Spotify scroll)
        for i, item in enumerate(lyrics):
            start = item["time"]
            end = lyrics[i+1]["time"] if i+1 < len(lyrics) else start + 2.5
            
            s_ass = format_time_ass(start)
            e_ass = format_time_ass(end)
            text = item["text"]

            # Faol qator markazda oq yonadi
            f.write(f"Dialogue: 2,{s_ass},{e_ass},ActiveLine,,0,0,0,,{{\\pos(540,960)}}{text}\n")
            
            # Oldingi qator tepaga surilib xiralashadi
            if i > 0:
                prev_text = lyrics[i-1]["text"]
                f.write(f"Dialogue: 1,{s_ass},{e_ass},DimmedLine,,0,0,0,,{{\\pos(540,830)}}{prev_text}\n")

            # Keyingi qator pastda xira kutadi
            if i + 1 < len(lyrics):
                next_text = lyrics[i+1]["text"]
                f.write(f"Dialogue: 1,{s_ass},{e_ass},DimmedLine,,0,0,0,,{{\\pos(540,1090)}}{next_text}\n")

def format_time_ass(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int((sec - int(sec)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

# API SERVER VA BOTNI BIRGA ISHGATUSHIRISH
async def main():
    app = web.Application()
    app.router.add_post('/api/render', api_render_endpoint)

    # CORS ruxsatnomalari (Mini App xatosiz ulanishi uchun)
    async def add_cors(request, response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
    app.on_response_prepare.append(add_cors)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 7860)
    await site.start()
    
    print("Veb-server (7860) va Aiogram Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
