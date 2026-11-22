"""Machine settings shared by the scripts.

Read from config.json in the skill folder (written by setup/setup.py), then overridden by
environment variables of the same name in upper case with a VF_ prefix (VF_MELT, VF_GPU, ...).
Anything missing falls back to a sensible guess, so a script still runs on a half-set-up machine
and fails with a clear message only when it actually needs the missing tool.
"""
import json
import os
import platform
import shutil
import subprocess

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG_PATH = os.path.join(SKILL_DIR, "config.json")
try:
    with open(_CFG_PATH, encoding="utf-8") as _f:
        CONFIG = json.load(_f)
except (OSError, ValueError):
    CONFIG = {}


def get(key, default=None):
    env = os.environ.get("VF_" + key.upper())
    if env not in (None, ""):
        return env
    return CONFIG.get(key, default)


def _first_existing(paths):
    return next((p for p in paths if p and os.path.exists(p)), None)


_SYSTEM = platform.system()
if _SYSTEM == "Windows":
    _FONTS = "C:/Windows/Fonts"
    _DEF_BOLD, _DEF_LIGHT, _DEF_BLACK = (_FONTS + "/segoeuib.ttf", _FONTS + "/segoeuil.ttf", _FONTS + "/seguibl.ttf")
    _MELT_GUESS = [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Shotcut\melt.exe"),
                   r"C:\Program Files\Shotcut\melt.exe"]
elif _SYSTEM == "Darwin":
    _DEF_BOLD = _DEF_LIGHT = _DEF_BLACK = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    _MELT_GUESS = ["/Applications/Shotcut.app/Contents/MacOS/melt"]
else:
    _DEF_BOLD = _DEF_BLACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    _DEF_LIGHT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    _MELT_GUESS = []

FFMPEG = get("ffmpeg") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = get("ffprobe") or shutil.which("ffprobe") or "ffprobe"
MELT = get("melt") or shutil.which("melt") or _first_existing(_MELT_GUESS) or "melt"
PLATE_MODEL = get("plate_model") or os.path.join(SKILL_DIR, "models", "plate", "license-plate-finetune-v1l.onnx")
FACE_MODEL = get("face_model") or os.path.join(SKILL_DIR, "models", "face", "face_detection_yunet_2023mar.onnx")
MUSIC_DIR = get("music_dir") or os.path.expanduser("~/Music")
FONT_BOLD = get("font_bold") or _DEF_BOLD          # captions, card titles
FONT_LIGHT = get("font_light") or _DEF_LIGHT       # subtitles under titles
FONT_BLACK = get("font_black") or _DEF_BLACK       # thumbnail headline
LANGUAGE = get("language") or "uk"                 # speech language for WhisperX
WHISPER_MODEL = get("whisper_model") or "large-v3"
HEVC_ENCODER = get("hevc_encoder") or "hevc_nvenc"  # hevc_nvenc (NVIDIA), libx265 (any CPU), hevc_videotoolbox (Mac)


def hevc_args():
    """ffmpeg arguments for a 10-bit HEVC intermediate of good quality."""
    if HEVC_ENCODER == "hevc_nvenc":
        # "nvenc_gpu" / VF_NVENC_GPU picks the card in NVENC's own numbering, as in render_final.py;
        # without it ffmpeg takes NVENC 0, whatever that card is busy with
        gpu = get("nvenc_gpu")
        return (["-c:v", "hevc_nvenc", "-profile:v", "main10", "-preset", "p6", "-cq", "14"]
                + (["-gpu", str(gpu)] if gpu is not None else []))
    if HEVC_ENCODER == "hevc_videotoolbox":
        return ["-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-q:v", "75"]
    return ["-c:v", "libx265", "-pix_fmt", "yuv420p10le", "-crf", "14", "-preset", "medium",
            "-x265-params", "log-level=error"]


def sdr_args(gpu=None):
    """ffmpeg arguments for an 8-bit SDR H.264 intermediate (dash-cam parts): NVENC when the config uses it.
    gpu: the card in NVENC's numbering (default "nvenc_gpu", else NVENC 0)."""
    if HEVC_ENCODER == "hevc_nvenc":
        gpu = gpu if gpu is not None else get("nvenc_gpu")
        return (["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "14", "-b:v", "0", "-pix_fmt", "yuv420p"]
                + (["-gpu", str(gpu)] if gpu is not None else []))
    return ["-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p"]


def encode_slots(per_card=2, cpu=2):
    """Parallel SDR encode slots by the load right now: a list of sdr_args() lists, one per job that may run.
    Each NVENC card gets per_card slots when its encoder is under 40% busy, one under 75%, none above
    (other sessions encode too); the CPU gets `cpu` libx264 slots when under 30% load, one under 60%.
    Sets CUDA_DEVICE_ORDER=PCI_BUS_ID, which makes NVENC's -gpu N the card nvidia-smi calls N."""
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    slots = []
    if HEVC_ENCODER == "hevc_nvenc":
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.encoder", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=20).stdout
            for ln in out.strip().splitlines():
                idx, util = [int(v) for v in ln.split(",")]
                n = per_card if util < 40 else 1 if util < 75 else 0
                slots += [sdr_args(idx)] * n
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:
        load = float(subprocess.run(["powershell", "-NoProfile", "-Command",
                                     "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average"],
                                    capture_output=True, text=True, timeout=30).stdout.strip() or 100)
    except (OSError, ValueError, subprocess.SubprocessError):
        load = 100.0
    n = cpu if load < 30 else 1 if load < 60 else 0
    slots += [["-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p"]] * n
    return slots or [sdr_args()]


def ff_font(path):
    """A font path as ffmpeg's drawtext wants it inside single quotes (drive colon escaped)."""
    return path.replace("\\", "/").replace(":", "\\:")


def cuda_index(min_free_gb=None):
    """The CUDA device to use: VF_GPU / config "gpu", else the one with the most FREE memory.

    Another job (a local LLM server, Higgs, another session's WhisperX) may already fill a card. Loading a
    model next to it does not fail on Windows: the driver spills into system RAM and both jobs crawl or
    hang (22.11.2026: WhisperX on a 3090 held by an LLM server). So pick by free memory, and stop when no
    card has "gpu_min_free_gb" (default 6; WhisperX ran out of memory on a 3060 with 5 GB free, 22.11.2026) free, instead of loading anyway. A forced VF_GPU / "gpu" card
    is also checked and only warned about."""
    import sys
    import torch
    n = torch.cuda.device_count()
    if n == 0:
        raise SystemExit("No CUDA GPU found: WhisperX needs an NVIDIA GPU (or edit the scripts for CPU).")
    need = float(min_free_gb if min_free_gb is not None else (get("gpu_min_free_gb") or 6))
    # Free memory from nvidia-smi, matched by UUID: on Windows (WDDM) torch.cuda.mem_get_info() reports
    # almost the whole card free while another process holds 23 GB of it (checked 22.11.2026), and
    # nvidia-smi numbers the cards differently from CUDA.
    import subprocess
    smi = {}
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.used,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
        for line in out.strip().splitlines():
            u, used, total = [x.strip() for x in line.split(",")]
            smi[u.lower().replace("gpu-", "")] = (float(total) - float(used)) / 1024
    except Exception as e:
        print("nvidia-smi failed (%s); falling back to torch's numbers" % e, file=sys.stderr)
    free = {}
    for i in range(n):
        p = torch.cuda.get_device_properties(i)
        u = str(getattr(p, "uuid", "")).lower().replace("gpu-", "")
        if u in smi:
            free[i] = smi[u]
        else:
            free[i] = torch.cuda.mem_get_info(i)[0] / 2**30
        print("CUDA %d %s: %.1f of %.1f GB free" % (i, p.name, free[i], p.total_memory / 2**30), file=sys.stderr)
    g = get("gpu")
    if g not in (None, ""):
        g = int(g)
        if free.get(g, 0) < need:
            print("WARNING: forced CUDA %d has only %.1f GB free (want %.1f): another job is on it"
                  % (g, free.get(g, 0), need), file=sys.stderr)
        return g
    best = max(free, key=free.get)
    if free[best] < need:
        raise SystemExit("No GPU has %.1f GB free (best: CUDA %d, %.1f GB). Another job holds the cards: "
                         "check nvidia-smi, wait or ask the user; set VF_GPU to force one." % (need, best, free[best]))
    return best


def torch_dlls():
    """On Windows, let onnxruntime/ctranslate2 find the cuDNN DLLs bundled with torch."""
    if _SYSTEM != "Windows":
        return
    import torch
    lib = os.path.join(os.path.dirname(torch.__file__), "lib")
    os.add_dll_directory(lib)
    os.environ["PATH"] = lib + os.pathsep + os.environ["PATH"]
