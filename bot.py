import discord
from discord.ext import commands
import anthropic
import requests
import os
import asyncio
import tempfile
from moviepy.editor import *
import textwrap
from elevenlabs.client import ElevenLabs
from elevenlabs import save
import json

# ============================================================

# إعداد البوت

# ============================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=’!’, intents=intents)

# ============================================================

# المفاتيح

# ============================================================


anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# ============================================================

# دالة كتابة السكريبت بـ Claude

# ============================================================

def write_script(topic: str, lang: str) -> dict:
lang_instruction = “باللغة العربية” if lang == “ar” else “in English”
prompt = f””“أنت خبير في كتابة محتوى TikTok/Instagram Reels.
اكتب سكريبت فيديو {lang_instruction} عن: {topic}
أعد JSON فقط بهذا الشكل:
{{
“hook”: “جملة افتتاحية قوية (5-10 كلمات)”,
“script”: “النص الكامل للفيديو (60-90 كلمة)”,
“keywords”: [“كلمة1”, “كلمة2”, “كلمة3”],
“caption”: “كابشن للنشر مع هاشتاقات”
}}”””
response = anthropic_client.messages.create(
model=“claude-opus-4-5”,
max_tokens=1000,
messages=[{“role”: “user”, “content”: prompt}]
)
text = response.content[0].text.strip()
if text.startswith(”`"): text = text.split("`”)[1]
if text.startswith(“json”):
text = text[4:]
return json.loads(text.strip())

# ============================================================

# دالة جلب الصور من Pexels

# ============================================================

def fetch_images(keywords: list, count: int = 5) -> list:
headers = {“Authorization”: PEXELS_API_KEY}
images = []
for keyword in keywords[:3]:
url = f”https://api.pexels.com/v1/search?query={keyword}&per_page=3&orientation=portrait”
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
for photo in resp.json().get(“photos”, []):
img_resp = requests.get(photo[“src”][“portrait”])
if img_resp.status_code == 200:
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=”.jpg”)
tmp.write(img_resp.content)
tmp.close()
images.append(tmp.name)
if len(images) >= count:
break
if len(images) >= count:
break
return images

# ============================================================

# دالة توليد الصوت بـ ElevenLabs

# ============================================================

def generate_audio(text: str, lang: str) -> str:
voice_id = “21m00Tcm4TlvDq8ikWAM” if lang == “en” else “pNInz6obpgDQGcFmaJgB”
audio = eleven_client.text_to_speech.convert(
voice_id=voice_id,
text=text,
model_id=“eleven_multilingual_v2”
)
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=”.mp3”)
save(audio, tmp.name)
return tmp.name

# ============================================================

# دالة تجميع الفيديو بـ MoviePy

# ============================================================

def create_video(images: list, audio_path: str, script_data: dict) -> str:
audio = AudioFileClip(audio_path)
duration = audio.duration
img_duration = duration / len(images)
clips = []
for img_path in images:
clip = ImageClip(img_path, duration=img_duration)
clip = clip.resize(height=1920)
clip = clip.crop(x_center=clip.w/2, width=1080)
clips.append(clip)
video = concatenate_videoclips(clips, method=“compose”)
overlay = ColorClip(size=(1080, 1920), color=[0, 0, 0], duration=duration).set_opacity(0.4)
txt_clip = TextClip(
script_data[“hook”],
fontsize=70, color=‘white’, font=‘Arial-Bold’,
method=‘caption’, size=(900, None), align=‘center’
).set_duration(3).set_position((‘center’, 200))
final = CompositeVideoClip([video, overlay, txt_clip])
final = final.set_audio(audio)
output_path = tempfile.NamedTemporaryFile(delete=False, suffix=”.mp4”).name
final.write_videofile(output_path, fps=30, codec=‘libx264’, audio_codec=‘aac’,
temp_audiofile=‘temp-audio.m4a’, remove_temp=True, verbose=False, logger=None)
return output_path

# ============================================================

# أوامر البوت

# ============================================================

@bot.event
async def on_ready():
print(f’✅ البوت شغّال: {bot.user}’)

@bot.command(name=‘video’)
async def make_video(ctx, lang: str = ‘ar’, *, topic: str = None):
if not topic:
await ctx.send(“❌ استخدم: `!video ar [موضوع]` أو `!video en [topic]`”)
return
if lang not in [‘ar’, ‘en’]:
await ctx.send(“❌ اللغة: `ar` أو `en` فقط”)
return
msg = await ctx.send(f”🎬 جاري صنع فيديو عن: **{topic}**…”)
try:
await msg.edit(content=“✍️ Claude يكتب السكريبت…”)
script_data = write_script(topic, lang)
await msg.edit(content=“🖼️ جلب الصور من Pexels…”)
images = fetch_images(script_data[“keywords”])
if not images:
await msg.edit(content=“❌ ما قدرت أجيب صور، جرب موضوع ثاني”)
return
await msg.edit(content=“🎙️ ElevenLabs يولّد الصوت…”)
audio_path = generate_audio(script_data[“script”], lang)
await msg.edit(content=“🎞️ تجميع الفيديو…”)
video_path = await asyncio.get_event_loop().run_in_executor(
None, create_video, images, audio_path, script_data)
embed = discord.Embed(title=f”🎬 {topic}”, description=script_data[“caption”], color=0x00ff88)
embed.add_field(name=“🎣 Hook”, value=script_data[“hook”], inline=False)
embed.add_field(name=“📝 السكريبت”, value=script_data[“script”][:500], inline=False)
await ctx.send(embed=embed)
await ctx.send(file=discord.File(video_path, filename=“video.mp4”))
await msg.delete()
for img in images:
os.unlink(img)
os.unlink(audio_path)
os.unlink(video_path)
except Exception as e:
await msg.edit(content=f”❌ خطأ: {str(e)}”)

@bot.command(name=‘مساعدة’)
async def help_cmd(ctx):
embed = discord.Embed(title=“🤖 أوامر البوت”, color=0x00ff88)
embed.add_field(name=”!video ar [موضوع]”, value=“مثال: `!video ar فوائد شرب الماء`”, inline=False)
embed.add_field(name=”!video en [topic]”, value=“Example: `!video en morning routine tips`”, inline=False)
await ctx.send(embed=embed)

bot.run(DISCORD_TOKEN)