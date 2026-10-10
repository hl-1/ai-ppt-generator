"""Bounded subprocess worker for yt-dlp and CPU speech recognition."""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

import httpx


def timestamp_seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    return sum(float(part) * 60**index for index, part in enumerate(reversed(parts)))


def parse_subtitles(content: str, ext: str) -> list[dict]:
    result = []
    if ext in {"json", "json3"}:
        data = json.loads(content)
        for item in data.get("body", []):
            result.append(
                {
                    "start": item.get("from", 0),
                    "end": item.get("to"),
                    "text": item.get("content", ""),
                }
            )
        for event in data.get("events", []):
            result.append(
                {
                    "start": event.get("tStartMs", 0) / 1000,
                    "end": (event.get("tStartMs", 0) + event.get("dDurationMs", 0)) / 1000,
                    "text": "".join(segment.get("utf8", "") for segment in event.get("segs", [])),
                }
            )
    else:
        timing = re.compile(r"([\d:.]+)\s*-->\s*([\d:.]+)")
        for block in re.split(r"\n\s*\n", content.replace("\r", "").replace(",", ".")):
            lines = block.splitlines()
            for index, line in enumerate(lines):
                match = timing.search(line)
                if match:
                    result.append(
                        {
                            "start": timestamp_seconds(match[1]),
                            "end": timestamp_seconds(match[2]),
                            "text": " ".join(lines[index + 1 :]),
                        }
                    )
                    break
    cleaned = []
    for segment in result:
        text = html.unescape(re.sub(r"<[^>]+>", "", segment["text"])).strip()
        if text and (not cleaned or text != cleaned[-1]["text"]):
            cleaned.append({**segment, "text": text[:2000]})
    return cleaned[:1200]


class QuietLogger:
    def __init__(self):
        self.download_too_large = False

    def debug(self, message, *args):
        # yt-dlp skips oversized files without raising an exception.
        if "larger than max-filesize" in message:
            self.download_too_large = True

    def warning(self, *args):
        pass

    def error(self, *args):
        pass


def ydl_options(payload: dict) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "noplaylist": True,
        "socket_timeout": 10,
        "retries": 0,
        "extractor_retries": 0,
        "fragment_retries": 0,
        "http_headers": {
            "User-Agent": "Mozilla/5.0",
            "Referer": payload["url"],
        },
    }
    if payload.get("cookie_file"):
        target = Path(payload["work_dir"]) / "cookies.txt"
        shutil.copyfile(payload["cookie_file"], target)
        options["cookiefile"] = str(target)
    return options


def inspect_video(payload: dict) -> dict:
    from yt_dlp import YoutubeDL

    from app.services.travel_video import public_media_url

    with YoutubeDL(ydl_options(payload)) as ydl:
        info = ydl.extract_info(payload["url"], download=False)
        metadata = {
            "title": info.get("title"),
            "author": info.get("uploader"),
            "timestamp": info.get("timestamp"),
            "upload_date": info.get("upload_date"),
            "duration_seconds": info.get("duration"),
            "likes": info.get("like_count"),
            "favorites": info.get("favorite_count"),
        }
        if payload.get("metadata_only"):
            return metadata
        subtitles = []
        for source in ("subtitles", "automatic_captions"):
            for language, tracks in (info.get(source) or {}).items():
                if language == "danmaku":
                    continue
                for track in tracks:
                    if track.get("ext") not in {"json", "json3", "vtt", "srt"}:
                        continue
                    rank = (not language.startswith(("zh", "ai-zh")), source != "subtitles")
                    subtitles.append((rank, track))
        segments = []
        for _, track in sorted(subtitles, key=lambda item: item[0])[:3]:
            if not public_media_url(track.get("url", "")):
                continue
            try:
                response = httpx.get(
                    track["url"], headers=options_headers(info, payload), timeout=10
                )
                response.raise_for_status()
                segments = parse_subtitles(response.text, track["ext"])
                if segments:
                    break
            except (httpx.HTTPError, ValueError, TypeError):
                continue
        return {**metadata, "segments": segments}


def options_headers(info: dict, payload: dict) -> dict:
    return {**(info.get("http_headers") or {}), "Referer": payload["url"]}


def download_audio(payload: dict) -> dict:
    from yt_dlp import YoutubeDL

    from app.services.travel_video import public_media_url

    limit = payload["max_bytes"]

    def size_guard(progress):
        if max(progress.get("downloaded_bytes") or 0, progress.get("total_bytes") or 0) > limit:
            raise RuntimeError("download_too_large")

    options = {
        **ydl_options(payload),
        "format": "worstaudio/best",
        "outtmpl": str(Path(payload["work_dir"]) / "audio.%(ext)s"),
        "max_filesize": limit,
        "progress_hooks": [size_guard],
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "64"}
        ],
    }
    url = payload.get("media_url") or payload["url"]
    if payload.get("media_url") and not public_media_url(url):
        raise ValueError("invalid_media_url")
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        duration = info.get("duration")
        if duration is not None and duration > payload["max_duration"]:
            raise ValueError("video_too_long")
        ydl.process_info(info)
    if options["logger"].download_too_large:
        raise ValueError("download_too_large")
    path = Path(payload["work_dir"]) / "audio.mp3"
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("audio_unavailable")
    return {"path": str(path)}


def transcribe_audio(payload: dict) -> dict:
    from faster_whisper import WhisperModel
    from huggingface_hub import try_to_load_from_cache

    model_name = payload["model"]
    cached = (
        try_to_load_from_cache(
            f"Systran/faster-whisper-{model_name}", "model.bin", cache_dir=payload["cache_dir"]
        )
        if not Path(model_name).is_dir()
        else None
    )
    model_path = str(Path(cached).parent) if isinstance(cached, str) else model_name
    model = WhisperModel(
        model_path,
        device="cpu",
        compute_type="int8",
        cpu_threads=payload["threads"],
        download_root=payload["cache_dir"],
    )
    segments, info = model.transcribe(
        payload["path"],
        language="zh",
        vad_filter=True,
        beam_size=3,
        condition_on_previous_text=False,
    )
    if info.duration > payload["max_duration"]:
        raise ValueError("video_too_long")
    result = []
    for segment in segments:
        text = segment.text.strip()
        if text and segment.no_speech_prob < 0.8:
            result.append({"start": segment.start, "end": segment.end, "text": text[:2000]})
            if payload.get("progress_path") and (len(result) == 1 or len(result) % 10 == 0):
                progress = Path(payload["progress_path"])
                pending = progress.with_suffix(".tmp")
                pending.write_text(
                    json.dumps({"segments": result}, ensure_ascii=True), encoding="utf-8"
                )
                pending.replace(progress)
        if len(result) >= 1200:
            break
    return {"segments": result}


def main():
    payload = json.load(sys.stdin)
    try:
        actions = {
            "inspect": inspect_video,
            "audio": download_audio,
            "transcribe": transcribe_audio,
        }
        result = actions[payload["action"]](payload)
    except Exception as error:
        message = str(error).lower()
        result = {
            "error_type": type(error).__name__,
            "error_code": "dependency_missing"
            if isinstance(error, ImportError) or ("ffmpeg" in message and "not found" in message)
            else "verification_required"
            if any(word in message for word in ("captcha", "verify", "验证码", "安全验证"))
            else "metadata_timeout"
            if any(word in message for word in ("timed out", "timeout"))
            else "access_restricted"
            if any(word in message for word in ("cookie", "login", "403", "412"))
            else "download_too_large"
            if "download_too_large" in message
            else "video_too_long"
            if "video_too_long" in message
            else "audio_unavailable"
            if "audio_unavailable" in message or "unable to obtain file audio codec" in message
            else "extraction_failed",
        }
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
