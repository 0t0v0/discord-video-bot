import discord
from discord.ext import commands
import anthropic
import requests
import os
import asyncio
import tempfile
import json
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, ColorClip, TextClip
from elevenlabs.client import ElevenLabs
from elevenlabs import save

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=’!’, intents=intents)

DISCORD_TOKEN = os.environ.get(‘DISCORD_TOKEN’)
ANTHROPIC_API_KEY = os.environ.get(‘ANTHROPIC_API_KEY’)
PEXELS_API_KEY = os.environ.get(‘PEXELS_API_KEY’)
ELEVENLABS_API_KEY = os.environ.get(‘ELEVENLABS_API_KEY’)

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

def write_script(topic, lang):
lang_instruction = “in Arabic” if lang == “ar” else “in English”
prompt = f””“You are an expert TikTok/Instagram Reels content writer.
Write a video script {lang_instruction} about: {topic}

Return ONLY valid JSON, no other text:
{{
“hook”: “Strong opening line (5-10 words)”,
“script”: “Full video narration (60-90 words)”,
“keywords”: [“keyword1”, “keyword2”, “keyword3”],
“caption”: “Post caption with hashtags”
}}”””
response = anthropic_client.messages.create(
model=“claude-opus-4-5”,
max_tokens=1000,
messages=[{“role”: “user”, “content”: prompt}]
)
text = response.content[0].text.strip()
if “`" in text: text = text.split("`”)[1]
if text.startswith(“json”):
text = text[4:]
text = text.strip()
return json.loads(text)

def fetch_images(keywords, count=5):
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

def generate_audio(text, lang):
voice_id = “21m00Tcm4TlvDq8ikWAM” if lang == “en” else “pNInz6obpgDQGcFmaJgB”
audio = eleven_client.text_to_speech.convert(
voice_id=voice_id,
text=text,
model_id=“eleven_multilingual_v2”
)
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=”.mp3”)
save(audio, tmp.name)
return tmp.name

def create_video(images, audio_path, script_data):
audio = AudioFileClip(audio_path)
duration = audio.duration
img_duration = duration / len(images)
clips = []
for img_path in images:
clip = ImageClip(img_path, duration=img_duration)
clip = clip.resize(height=1920)
clip = clip.crop(x_center=clip.w / 2, width=1080)
clips.append(clip)
video = concatenate_videoclips(clips, method=“compose”)
overlay = ColorClip(size=(1080, 1920), color=[0, 0, 0], duration=duration).set_opacity(0.45)
txt = TextClip(
script_data[“hook”],
fontsize=65,
color=‘white’,
font=‘DejaVu-Sans-Bold’,
method=‘caption’,
size=(900, None),
align=‘center’
).set_duration(min(3, duration)).set_position((‘center’, 180))
final = CompositeVideoClip([video, overlay, txt])
final = final.set_audio(audio)
output = tempfile.NamedTemporaryFile(delete=False, suffix=”.mp4”).name
final.write_videofile(
output, fps=30, codec=‘libx264’, audio_codec=‘aac’,
temp_audiofile=‘temp-audio.m4a’, remove_temp=True,
verbose=False, logger=None
)
return output

@bot.event
async def on_ready():
print(f’Bot is ready: {bot.user}’)

@bot.command(name=‘video’)
async def make_video(ctx, lang=‘ar’, *, topic=None):
if not topic:
await ctx.send(“Use: `!video ar [topic]` or `!video en [topic]`”)
return
msg = await ctx.send(f”Creating video about: **{topic}** …”)
try:
await msg.edit(content=“Writing script with Claude AI…”)
script_data = write_script(topic, lang)
await msg.edit(content=“Fetching images from Pexels…”)
images = fetch_images(script_data[“keywords”])
if not images:
await msg.edit(content=“Could not fetch images. Try a different topic.”)
return
await msg.edit(content=“Generating voiceover with ElevenLabs…”)
audio_path = generate_audio(script_data[“script”], lang)
await msg.edit(content=“Assembling video… (this takes ~1 min)”)
video_path = await asyncio.get_event_loop().run_in_executor(
None, create_video, images, audio_path, script_data
)
embed = discord.Embed(
title=f”Video: {topic}”,
description=script_data[“caption”],
color=0x00ff88
)
embed.add_field(name=“Hook”, value=script_data[“hook”], inline=False)
embed.add_field(name=“Script”, value=script_data[“script”][:400], inline=False)
await ctx.send(embed=embed)
await ctx.send(file=discord.File(video_path, filename=“video.mp4”))
await msg.delete()
for img in images:
try:
os.unlink(img)
except:
pass
try:
os.unlink(audio_path)
os.unlink(video_path)
except:
pass
except Exception as e:
await msg.edit(content=f”Error: {str(e)}”)
print(f”Error: {e}”)

bot.run(DISCORD_TOKEN)