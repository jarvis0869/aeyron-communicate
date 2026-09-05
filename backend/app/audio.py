"""Bounded decoding from memory; no application audio files are created.

External decoders receive only stdin, cannot use network protocols, and are killed
and reaped on timeout/cancellation. Decoded PCM is bounded to 91 seconds. Parser
sandboxing at OS/container level remains a deployment requirement.
"""

import asyncio
import json
import math
import struct


class AudioError(Exception):
    def __init__(self, code: str, status: int = 422):
        self.code = code
        self.status = status


async def run_decoder(args: list[str], data: bytes, output_limit: int, timeout: float = 8) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        limit=65536,
    )

    async def write_input():
        try:
            proc.stdin.write(data)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            proc.stdin.close()

    async def read_output():
        parts, size = [], 0
        while chunk := await proc.stdout.read(65536):
            size += len(chunk)
            if size > output_limit:
                raise AudioError("decoded_audio_too_large", 413)
            parts.append(chunk)
        return b"".join(parts)

    tasks = [asyncio.create_task(write_input()), asyncio.create_task(read_output())]
    try:
        async with asyncio.timeout(timeout):
            await tasks[0]
            output = await tasks[1]
            await proc.wait()
        if proc.returncode:
            raise AudioError("invalid_audio")
        return output
    except TimeoutError:
        raise AudioError("audio_validation_timeout") from None
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        await asyncio.gather(*tasks, return_exceptions=True)


MIME_FORMATS = {
    "audio/webm": ({"webm", "matroska"}, ".webm"),
    "audio/ogg": ({"ogg"}, ".ogg"),
    "audio/wav": ({"wav"}, ".wav"),
    "audio/x-wav": ({"wav"}, ".wav"),
    "audio/mpeg": ({"mp3"}, ".mp3"),
    "audio/mp4": ({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}, ".m4a"),
}


async def validate_audio(data: bytes, mime: str, max_seconds: float) -> str:
    """Return ok/no_speech/low_quality. Low energy is not a clinical judgment."""
    if not data:
        raise AudioError("empty_audio", 400)
    if mime not in MIME_FORMATS:
        raise AudioError("unsupported_audio_type", 415)
    meta_raw = await run_decoder([
        "ffprobe", "-v", "error", "-protocol_whitelist", "pipe",
        "-probesize", "1048576", "-analyzeduration", "2000000",
        "-show_entries", "format=format_name,duration:stream=codec_type,channels,sample_rate,duration",
        "-of", "json", "-i", "pipe:0",
    ], data, 32768)
    try:
        meta = json.loads(meta_raw)
        streams = meta["streams"]
        fmt = meta["format"]
        formats = set(fmt["format_name"].split(","))
        if not formats.intersection(MIME_FORMATS[mime][0]):
            raise AudioError("audio_mime_mismatch", 415)
        if len(streams) != 1 or streams[0]["codec_type"] != "audio":
            raise AudioError("audio_only_required", 415)
        if not 1 <= int(streams[0].get("channels", 0)) <= 2:
            raise AudioError("unsupported_audio_channels", 415)
        if not 8000 <= int(streams[0].get("sample_rate", 0)) <= 192000:
            raise AudioError("unsupported_sample_rate", 415)
        declared = fmt.get("duration", streams[0].get("duration"))
        if declared is not None and (not math.isfinite(float(declared)) or float(declared) > max_seconds + 0.1):
            raise AudioError("audio_too_long", 413)
    except (KeyError, ValueError, TypeError):
        raise AudioError("invalid_audio") from None
    pcm = await run_decoder([
        "ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "pipe",
        "-probesize", "1048576", "-analyzeduration", "2000000", "-i", "pipe:0",
        "-t", str(max_seconds + 1), "-vn", "-ac", "1", "-ar", "16000",
        "-f", "s16le", "pipe:1",
    ], data, int((max_seconds + 1.1) * 32000))
    if len(pcm) > (max_seconds + 0.1) * 32000:
        raise AudioError("audio_too_long", 413)
    if len(pcm) < 3200:
        raise AudioError("audio_too_short")
    values = struct.iter_unpack("<h", pcm[:len(pcm) // 2 * 2])
    sum_sq, count, peak = 0, 0, 0
    for (sample,) in values:
        sum_sq += sample * sample
        count += 1
        peak = max(peak, abs(sample))
    if peak == 0:
        return "no_speech"
    if math.sqrt(sum_sq / count) / 32768 < 0.0001:
        return "low_quality"
    return "ok"
