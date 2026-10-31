"""Check and set up everything the vlog-film skill needs.

usage:
  python setup/setup.py            check only: report what is present and what is missing
  python setup/setup.py --install  also install what is missing (asks nothing; the agent should
                                   get the user's OK before running this), create the Python venv,
                                   download the licence-plate model and write config.json
  --python <path>                  use an existing Python (venv) that already has the packages
  --plate-model <path>             use an already downloaded plate model instead of downloading

Uses only the Python standard library, so it runs with any Python 3.10+ before the venv exists.
Tested on Windows 11 with an NVIDIA RTX GPU. On macOS / Linux it checks and prints the commands
to run instead of installing system programs itself.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = os.path.join(SKILL, ".venv")
VPY = os.path.join(VENV, "Scripts" if os.name == "nt" else "bin", "python" + (".exe" if os.name == "nt" else ""))
MODEL_URL = ("https://huggingface.co/morsetechlab/yolov11-license-plate-detection/resolve/main/"
             "license-plate-finetune-v1l.onnx")
MODEL = os.path.join(SKILL, "models", "plate", "license-plate-finetune-v1l.onnx")
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
WIN = platform.system() == "Windows"
INSTALL = "--install" in sys.argv


def _arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv[:-1] else None


if _arg("--python"):
    VPY = os.path.abspath(_arg("--python"))
if _arg("--plate-model"):
    MODEL = os.path.abspath(_arg("--plate-model"))
problems = []


def say(ok, what, hint=""):
    print("[%s] %s%s" % ("ok" if ok else "--", what, ("   -> " + hint) if (hint and not ok) else ""))
    if not ok:
        problems.append(what)


def out(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    except OSError:
        return ""


def winget(pkg):
    print("    installing %s with winget ..." % pkg)
    subprocess.run(["winget", "install", "--id", pkg, "-e", "--accept-source-agreements",
                    "--accept-package-agreements", "--silent"])


def find_melt():
    cands = [shutil.which("melt")]
    if WIN:
        cands += [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Shotcut\melt.exe"), r"C:\Program Files\Shotcut\melt.exe"]
    elif platform.system() == "Darwin":
        cands += ["/Applications/Shotcut.app/Contents/MacOS/melt"]
    return next((c for c in cands if c and os.path.exists(c)), None)


def main():
    cfg_path = os.path.join(SKILL, "config.json")
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    global VPY, MODEL
    if not _arg("--python") and cfg.get("python") and os.path.exists(cfg["python"]):
        VPY = cfg["python"]
    if not _arg("--plate-model") and cfg.get("plate_model") and os.path.exists(cfg["plate_model"]):
        MODEL = cfg["plate_model"]

    print("vlog-film setup (%s, Python %s)\n" % (platform.platform(), platform.python_version()))
    say(sys.version_info >= (3, 10), "Python 3.10+ to run setup", "install Python 3.11 (python.org or: winget install Python.Python.3.11)")

    # --- GPU -----------------------------------------------------------------------------
    smi = out(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    say(bool(smi.strip()), "NVIDIA GPU (%s)" % (smi.strip().replace("\n", "; ") or "none"),
        "WhisperX speech recognition and the fast encoder need an NVIDIA GPU with a current driver")
    if not smi.strip():
        cfg.setdefault("hevc_encoder", "libx265")

    # --- ffmpeg with libplacebo (HDR conversion) and an HEVC encoder ---------------------------
    ff = shutil.which("ffmpeg")
    if not ff and INSTALL and WIN:
        winget("Gyan.FFmpeg")       # the "full" build: libplacebo, vulkan, nvenc, libx265
        ff = shutil.which("ffmpeg") or next((os.path.join(r, f) for r, _, fs in os.walk(
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet")) for f in fs if f.lower() == "ffmpeg.exe"), None)
    say(bool(ff), "ffmpeg", "Windows: winget install Gyan.FFmpeg (full build); macOS: brew install ffmpeg; Linux: a build with libplacebo")
    if ff:
        cfg["ffmpeg"] = ff
        probe = shutil.which("ffprobe") or os.path.join(os.path.dirname(ff), "ffprobe" + (".exe" if WIN else ""))
        cfg["ffprobe"] = probe
        filters = out([ff, "-hide_banner", "-filters"])
        encs = out([ff, "-hide_banner", "-encoders"])
        say("libplacebo" in filters, "ffmpeg has libplacebo (SDR<->HLG conversion)",
            "use a full ffmpeg build (gyan.dev full, or BtbN builds) and a Vulkan-capable GPU driver")
        if "hevc_nvenc" in encs and smi.strip():
            cfg.setdefault("hevc_encoder", "hevc_nvenc")
        elif "libx265" in encs:
            cfg["hevc_encoder"] = cfg.get("hevc_encoder") if cfg.get("hevc_encoder") != "hevc_nvenc" else "libx265"
        say("hevc_nvenc" in encs or "libx265" in encs, "ffmpeg has an HEVC encoder (%s)" % cfg.get("hevc_encoder"))

    # --- Shotcut's melt (final render) -----------------------------------------------------------
    melt = find_melt()
    if not melt and INSTALL and WIN:
        winget("Meltytech.Shotcut")
        melt = find_melt()
    say(bool(melt), "Shotcut / melt (final render)", "install Shotcut: winget install Meltytech.Shotcut, or shotcut.org")
    if melt:
        cfg["melt"] = melt

    # --- Python venv with WhisperX, torch, onnxruntime --------------------------------------------
    if not os.path.exists(VPY) and INSTALL:
        print("    creating venv %s ..." % VENV)
        subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
        subprocess.run([VPY, "-m", "pip", "install", "-U", "pip"], check=True)
        subprocess.run([VPY, "-m", "pip", "install", "torch==2.8.0", "torchaudio==2.8.0",
                        "--index-url", TORCH_INDEX], check=True)
        subprocess.run([VPY, "-m", "pip", "install", "-r", os.path.join(SKILL, "setup", "requirements.txt")],
                       check=True)
    venv_ok = os.path.exists(VPY) and "ok" in out([VPY, "-c", "import whisperx, onnxruntime, cv2, pillow_heif, torch; "
                                                   "print('ok' if torch.cuda.is_available() else 'nocuda')"])
    say(venv_ok, "Python with WhisperX, torch (CUDA), onnxruntime, OpenCV, pillow-heif (%s)" % VPY,
        "run: python setup/setup.py --install")
    if os.path.exists(VPY):
        cfg["python"] = VPY

    # --- licence-plate detector --------------------------------------------------------------------
    if not os.path.exists(MODEL) and INSTALL:
        os.makedirs(os.path.dirname(MODEL), exist_ok=True)
        print("    downloading plate model (~100 MB) ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL)
    say(os.path.exists(MODEL), "licence-plate model (morsetechlab/yolov11-license-plate-detection, AGPL-3.0)",
        "run: python setup/setup.py --install")
    if os.path.exists(MODEL):
        cfg["plate_model"] = MODEL

    # --- music and fonts -------------------------------------------------------------------------------
    music = cfg.get("music_dir") or os.path.expanduser("~/Music")
    cfg["music_dir"] = music
    say(os.path.isdir(music), "music folder %s" % music,
        "download tracks from YouTube Audio Library into it, or set music_dir in config.json")
    if WIN:
        say(os.path.exists(r"C:\Windows\Fonts\segoeuib.ttf"), "Segoe UI fonts")
    cfg.setdefault("language", "uk")

    if INSTALL or not os.path.exists(cfg_path) or _arg("--python") or _arg("--plate-model"):
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print("\nwrote %s" % cfg_path)
    print("\n%s" % ("all set" if not problems else "missing: " + "; ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
