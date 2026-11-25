"""Render a branded 16:9 beat-promo video from artwork and audio."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

WIDTH, HEIGHT = 1280, 720


def _font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _fit_cover(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    scale = max(WIDTH / image.width, HEIGHT / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left, top = (resized.width - WIDTH) // 2, (resized.height - HEIGHT) // 2
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))


def build_poster(cover_path: str, title: str, producer: str, output_path: str) -> None:
    with Image.open(cover_path) as cover:
        poster = _fit_cover(cover).filter(ImageFilter.GaussianBlur(26))
        poster = ImageEnhance.Brightness(poster).enhance(0.28).convert("RGBA")
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 95))
        poster = Image.alpha_composite(poster, overlay)

        art = cover.convert("RGB")
        art.thumbnail((430, 430), Image.Resampling.LANCZOS)
        x, y = 82, (HEIGHT - art.height) // 2
        shadow = Image.new("RGBA", (art.width + 44, art.height + 44), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((12, 12, shadow.width - 12, shadow.height - 12), radius=14, fill=(0, 0, 0, 190))
        poster.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)), (x - 22, y - 22))
        poster.paste(art, (x, y))

        draw = ImageDraw.Draw(poster)
        white, muted = (255, 255, 255, 255), (220, 226, 236, 255)
        draw.text((590, 105), "SUS10 BEATS", font=_font(24, True), fill=muted)
        draw.rounded_rectangle((590, 154, 735, 160), radius=3, fill=(233, 183, 90, 255))

        clean_title = " ".join(title.split())[:90] or "Untitled Beat"
        lines, current = [], ""
        font = _font(52, True)
        for word in clean_title.split():
            candidate = f"{current} {word}".strip()
            if draw.textbbox((0, 0), candidate, font=font)[2] <= 590:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
            if len(lines) >= 3:
                break
        if current and len(lines) < 3:
            lines.append(current)
        for index, line in enumerate(lines[:3]):
            draw.text((590, 205 + index * 68), line, font=font, fill=white)
        producer_y = 205 + max(1, len(lines)) * 68 + 18
        draw.text((594, producer_y), "PRODUCED BY", font=_font(17, True), fill=muted)
        draw.text((594, producer_y + 34), " ".join(producer.split())[:60], font=_font(30, True), fill=white)
        draw.text((594, 590), "LISTEN  •  LICENSE  •  CREATE", font=_font(18, True), fill=muted)
        poster.convert("RGB").save(output_path, quality=94)


def render_video(audio_path: str, cover_path: str, title: str, producer: str, max_seconds: int) -> tuple[str, float]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg and FFprobe must be installed on the cloud runner.")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        check=True, capture_output=True, text=True, timeout=30,
    )
    try:
        duration = float(probe.stdout.strip())
    except ValueError as exc:
        raise ValueError("Could not determine the audio duration.") from exc
    if duration <= 0 or duration > max_seconds:
        raise ValueError(f"Audio duration must be between 1 and {max_seconds} seconds.")

    temp_dir = tempfile.mkdtemp(prefix="sus10-render-")
    poster_path = str(Path(temp_dir) / "poster.jpg")
    video_path = str(Path(temp_dir) / "promo.mp4")
    build_poster(cover_path, title, producer, poster_path)
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", "30", "-i", poster_path, "-i", audio_path,
        "-filter_complex",
        "[1:a]showwaves=s=700x100:mode=line:rate=30:colors=white,format=rgba[w];"
        "[0:v][w]overlay=x=500:y=565:format=auto,format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
        "-tune", "stillimage", "-crf", "23", "-r", "30", "-c:a", "aac",
        "-b:a", "192k", "-shortest", "-movflags", "+faststart", video_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=max(180, int(duration * 2)))
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("FFmpeg could not render this media job.") from exc
    return video_path, duration
