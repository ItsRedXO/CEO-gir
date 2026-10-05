"""
YouTube Shorts worker — assembles 60-second AI-narrated vertical videos.

Pipeline:
  1. Generate script (Pollinations text API, free)
  2. TTS narration (gTTS, free)
  3. Background footage (Pexels API, free 200 req/hr key required)
     OR solid-color animated fallback (no key needed)
  4. Composite with MoviePy → 1080x1920 MP4
  5. Upload to YouTube via Data API v3 (free 10,000 units/day quota)

Environment vars:
  PEXELS_API_KEY        — free at pexels.com/api (optional, enables stock video)
  YOUTUBE_CLIENT_ID     — OAuth2 client id (from Google Cloud Console)
  YOUTUBE_CLIENT_SECRET — OAuth2 client secret
  YOUTUBE_REFRESH_TOKEN — refresh token (one-time setup via OAuth flow)
  SHORTS_OUTPUT_DIR     — where to write MP4s (default: /tmp/shorts)

Worker capabilities: ["youtube_shorts", "video_content", "content", "social_media"]
"""
from __future__ import annotations

import os
import json
import hashlib
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base import BaseWorker

# ── Dependency guards ─────────────────────────────────────────────────────────

def _try_import(name: str):
    try:
        return __import__(name)
    except ImportError:
        return None

_moviepy    = _try_import("moviepy.editor")
_gtts       = _try_import("gtts")
_pil        = _try_import("PIL.Image")
_requests_m = _try_import("requests")

MOVIEPY_OK  = _moviepy is not None
GTTS_OK     = _gtts is not None
REQUESTS_OK = _requests_m is not None

PEXELS_KEY     = os.environ.get("PEXELS_API_KEY", "")
YT_CLIENT_ID   = os.environ.get("YOUTUBE_CLIENT_ID", "")
YT_SECRET      = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YT_REFRESH     = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
SHORTS_DIR     = Path(os.environ.get("SHORTS_OUTPUT_DIR", "/tmp/shorts"))

# ── Capabilities ──────────────────────────────────────────────────────────────

CAPABILITIES = ["youtube_shorts", "video_content", "content", "social_media"]

# ── Niche/topic catalog ───────────────────────────────────────────────────────

_NICHE_PROMPTS = {
    "ai_tips": (
        "Write a 60-second YouTube Shorts script about {topic} AI tip. "
        "Hook in first 3 seconds. 3 bullet points. Call to action at end. "
        "Plain text only, no markdown, no hashtags in script."
    ),
    "trending_gaming": (
        "Write a 60-second YouTube Shorts hype script about {topic} gaming moment. "
        "Excited commentary style. Hook + 3 facts + 'drop a comment' CTA. Plain text."
    ),
    "money_tips": (
        "Write a 60-second YouTube Shorts script: '{topic} money tip'. "
        "Relatable hook. 3 actionable steps. 'Save this' CTA. Plain text."
    ),
    "facts": (
        "Write a 60-second YouTube Shorts script: '5 facts about {topic}'. "
        "Surprising opener. Numbered facts 1-5. 'Follow for more' CTA. Plain text."
    ),
}

_DEFAULT_TOPICS = {
    "ai_tips": ["ChatGPT prompts", "AI side hustles", "Claude vs GPT", "AI art tools", "automation bots"],
    "trending_gaming": ["Minecraft speedrun", "GTA VI leak", "Elden Ring", "Fortnite meta", "Roblox trend"],
    "money_tips": ["freelancing online", "passive income 2025", "digital products", "Fiverr gigs", "reselling"],
    "facts": ["the human brain", "space exploration", "cryptocurrency", "artificial intelligence", "social media"],
}


class ShortsWorker(BaseWorker):
    """Assembles and uploads YouTube Shorts using free tools."""

    capabilities = CAPABILITIES

    def execute(self, task: dict) -> dict:
        input_data = task.get("input_json") or task.get("input_data") or {}
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except Exception:
                input_data = {}

        niche   = input_data.get("niche", "ai_tips")
        topic   = input_data.get("topic") or self._pick_topic(niche)
        title   = input_data.get("title") or f"{topic} — AI Short"
        tags    = input_data.get("tags", ["#shorts", "#AI", "#viral"])

        # 1. Generate script
        script = self._gen_script(niche, topic)

        # 2. Build video
        output_path, duration_s = self._assemble_video(script, topic, niche)

        # 3. Upload (if credentials available)
        video_id, upload_status = self._upload_to_youtube(output_path, title, script, tags)

        revenue   = 0.0
        spend     = 0.0
        note      = "video assembled"
        if upload_status == "uploaded":
            note = f"uploaded to YouTube: https://youtu.be/{video_id}"
        elif upload_status == "no_credentials":
            note = f"video saved locally (no YouTube credentials): {output_path}"

        return {
            "niche":        niche,
            "topic":        topic,
            "title":        title,
            "script":       script[:300],
            "duration_s":   duration_s,
            "output_path":  str(output_path) if output_path else None,
            "video_id":     video_id,
            "upload_status": upload_status,
            "note":         note,
            "platforms":    ["youtube"],
            "tags":         tags,
            "economic_data": {
                "revenue":  revenue,
                "spend":    spend,
                "profit":   revenue - spend,
                "price_usd": 0.0,
            },
            "listing_ready": upload_status == "uploaded",
        }

    # ── Script generation ──────────────────────────────────────────────────────

    def _gen_script(self, niche: str, topic: str) -> str:
        template = _NICHE_PROMPTS.get(niche, _NICHE_PROMPTS["ai_tips"])
        prompt = template.format(topic=topic)

        # Try Pollinations text API (free)
        script = None
        if REQUESTS_OK:
            try:
                from ..providers.image_gen import generate_text
                script = generate_text(prompt, model="openai", timeout=30)
            except Exception:
                pass

        if not script:
            # Deterministic fallback — no API needed
            script = self._fallback_script(niche, topic)

        return script

    def _fallback_script(self, niche: str, topic: str) -> str:
        scripts = {
            "ai_tips": (
                f"Did you know this ONE {topic} trick saves hours every week? "
                f"First: use it to automate your workflow. "
                f"Second: combine it with prompts for better results. "
                f"Third: save yourself 3 hours daily. "
                f"Try it and tell me in the comments. Follow for more AI tips!"
            ),
            "trending_gaming": (
                f"This {topic} moment broke the internet. "
                f"Players are going insane over this. "
                f"Here's everything you need to know. "
                f"Drop a comment — did you see this coming?"
            ),
            "money_tips": (
                f"Here's the {topic} money tip nobody talks about. "
                f"Step one: start small, be consistent. "
                f"Step two: reinvest early profits. "
                f"Step three: scale what works. "
                f"Save this and come back when you're ready to start!"
            ),
            "facts": (
                f"5 facts about {topic} that will blow your mind. "
                f"Number one will surprise you. "
                f"Number three changed how experts think about this. "
                f"And number five nobody believes at first. "
                f"Follow for more mind-bending facts!"
            ),
        }
        return scripts.get(niche, scripts["ai_tips"])

    # ── Video assembly ─────────────────────────────────────────────────────────

    def _assemble_video(self, script: str, topic: str, niche: str) -> tuple[Optional[Path], float]:
        SHORTS_DIR.mkdir(parents=True, exist_ok=True)

        seed = int(hashlib.md5(f"{topic}{niche}".encode()).hexdigest()[:8], 16)
        slug = "".join(c if c.isalnum() else "_" for c in topic.lower())[:24]
        out  = SHORTS_DIR / f"short_{slug}_{seed % 10000}.mp4"

        if not MOVIEPY_OK or not GTTS_OK:
            # Can't assemble — return placeholder path
            out.write_text(f"placeholder:{script[:100]}")
            return out, 60.0

        try:
            return self._moviepy_assemble(script, out), 59.0
        except Exception as e:
            # Write error marker so the caller still has a result
            out.write_text(f"assembly_error:{e}")
            return out, 0.0

    def _moviepy_assemble(self, script: str, out_path: Path) -> Path:
        from moviepy.editor import (
            ColorClip, TextClip, CompositeVideoClip, AudioFileClip, concatenate_videoclips
        )
        from gtts import gTTS

        # 1. TTS audio
        tts_path = out_path.with_suffix(".mp3")
        gTTS(text=script, lang="en", slow=False).save(str(tts_path))

        audio_clip = AudioFileClip(str(tts_path))
        total_dur  = min(audio_clip.duration, 58.0)  # Shorts < 60s

        # 2. Background — try Pexels video, fall back to animated gradient
        bg = self._get_background(total_dur)

        # 3. Caption overlay — simple word-wrap text
        words = script.split()
        chunks = [" ".join(words[i:i+8]) for i in range(0, len(words), 8)]
        chunk_dur = total_dur / max(len(chunks), 1)

        text_clips = []
        for i, chunk in enumerate(chunks):
            try:
                tc = (
                    TextClip(
                        chunk,
                        fontsize=52,
                        color="white",
                        stroke_color="black",
                        stroke_width=2,
                        method="caption",
                        size=(900, None),
                        align="center",
                    )
                    .set_start(i * chunk_dur)
                    .set_duration(chunk_dur)
                    .set_position(("center", 1400))
                )
                text_clips.append(tc)
            except Exception:
                pass  # ImageMagick not available — skip text overlay

        clips = [bg] + text_clips
        final = CompositeVideoClip(clips, size=(1080, 1920)).set_audio(audio_clip).subclip(0, total_dur)
        final.write_videofile(
            str(out_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            logger=None,
        )

        # Cleanup temp audio
        try:
            tts_path.unlink()
        except Exception:
            pass

        return out_path

    def _get_background(self, duration: float):
        """Returns a 1080x1920 background clip — Pexels video or solid color."""
        from moviepy.editor import ColorClip, VideoFileClip

        if REQUESTS_OK and PEXELS_KEY:
            video_path = self._fetch_pexels_video(duration)
            if video_path:
                try:
                    vc = VideoFileClip(str(video_path)).resize((1080, 1920)).subclip(0, min(duration, 30))
                    # Loop if needed
                    if vc.duration < duration:
                        from moviepy.editor import concatenate_videoclips
                        loops = int(duration / vc.duration) + 1
                        vc = concatenate_videoclips([vc] * loops).subclip(0, duration)
                    return vc
                except Exception:
                    pass

        # Fallback: dark gradient background
        return ColorClip(size=(1080, 1920), color=(15, 10, 30), duration=duration)

    def _fetch_pexels_video(self, min_dur: float) -> Optional[Path]:
        """Downloads a free stock video from Pexels. Returns local path or None."""
        try:
            resp = _requests_m.get(
                "https://api.pexels.com/videos/search",
                params={"query": "abstract dark technology", "per_page": 5, "orientation": "portrait"},
                headers={"Authorization": PEXELS_KEY},
                timeout=15,
            )
            if resp.status_code != 200:
                return None
            videos = resp.json().get("videos", [])
            for v in videos:
                for file in v.get("video_files", []):
                    if file.get("quality") in ("hd", "sd") and file.get("height", 0) >= 720:
                        video_url = file["link"]
                        dl = _requests_m.get(video_url, timeout=30, stream=True)
                        if dl.status_code == 200:
                            tmp = SHORTS_DIR / f"bg_{int(time.time())}.mp4"
                            with open(tmp, "wb") as f:
                                for chunk in dl.iter_content(8192):
                                    f.write(chunk)
                            return tmp
        except Exception:
            pass
        return None

    # ── YouTube upload ─────────────────────────────────────────────────────────

    def _upload_to_youtube(
        self,
        video_path: Optional[Path],
        title: str,
        description: str,
        tags: list[str],
    ) -> tuple[Optional[str], str]:
        if not video_path or not video_path.exists():
            return None, "no_video"
        if not (YT_CLIENT_ID and YT_SECRET and YT_REFRESH):
            return None, "no_credentials"
        if not REQUESTS_OK:
            return None, "no_requests"

        # Check file is a real video (not a placeholder text file)
        try:
            content = video_path.read_bytes()
            if len(content) < 1024:
                return None, "placeholder_only"
        except Exception:
            return None, "read_error"

        try:
            access_token = self._refresh_yt_token()
            if not access_token:
                return None, "auth_failed"
            return self._yt_resumable_upload(video_path, title, description, tags, access_token)
        except Exception as e:
            return None, f"error:{e}"

    def _refresh_yt_token(self) -> Optional[str]:
        resp = _requests_m.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id":     YT_CLIENT_ID,
                "client_secret": YT_SECRET,
                "refresh_token": YT_REFRESH,
                "grant_type":    "refresh_token",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        return None

    def _yt_resumable_upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        access_token: str,
    ) -> tuple[Optional[str], str]:
        file_size = video_path.stat().st_size
        metadata = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": [t.lstrip("#") for t in tags][:15],
                "categoryId": "24",  # Entertainment
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        # Initiate resumable upload
        init_resp = _requests_m.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(file_size),
            },
            json=metadata,
            timeout=20,
        )
        if init_resp.status_code not in (200, 201):
            return None, f"init_failed:{init_resp.status_code}"

        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            return None, "no_upload_url"

        # Upload video bytes
        with open(video_path, "rb") as f:
            up_resp = _requests_m.put(
                upload_url,
                data=f,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(file_size),
                },
                timeout=300,
            )

        if up_resp.status_code in (200, 201):
            video_id = up_resp.json().get("id")
            return video_id, "uploaded"
        return None, f"upload_failed:{up_resp.status_code}"

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _pick_topic(self, niche: str) -> str:
        topics = _DEFAULT_TOPICS.get(niche, _DEFAULT_TOPICS["ai_tips"])
        import random
        return random.choice(topics)
