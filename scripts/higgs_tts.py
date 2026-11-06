"""Speak a list of lines in a cloned voice with Higgs TTS 3 (Boson AI), offline through vLLM-Omni.

Runs inside the Linux venv that has vllm-omni (WSL on Windows); dub.py and dub_regen.py start it.

  python higgs_tts.py <jobs.json>
  jobs.json: {"ref": "ref.wav", "ref_text": "what ref.wav says", "model": "bosonai/higgs-tts-3-4b",
              "jobs": [{"text": "...", "out": "take.wav", "seed": 7}, ...]}

The model loads once and every seed goes as one batch: the pipeline's sampling has a fixed seed, so
takes of the same line differ only by the seed set here. Paths are Linux paths (/mnt/c/...).
The reference must be in the language spoken: from a Ukrainian reference, Polish came out accented
with a glitch after every word. Licence: monetised creator content is allowed if the video's
description credits "Boson AI's Higgs Audio"; outputs must not train other speech models.
"""
import os

os.environ.setdefault("VLLM_USE_DEEP_GEMM", "0")
os.environ.setdefault("VLLM_MOE_USE_DEEP_GEMM", "0")

import copy
import json
import sys

import numpy as np
import soundfile as sf
import torch

SR = 24000


def pcm(mm):
    a = mm.get("model_outputs")
    if a is None:
        a = mm.get("audio")
    if isinstance(a, list):
        a = torch.cat([torch.as_tensor(x).float().cpu().reshape(-1) for x in a if x is not None])
    return np.clip(torch.as_tensor(a).float().cpu().reshape(-1).numpy(), -1, 1)


def main():
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    from transformers import AutoTokenizer
    from vllm_omni import Omni
    from vllm_omni.model_executor.models.higgs_audio_v3.higgs_audio_v3_tokenizer import (
        HiggsAudioV3TokenizerAdapter, apply_delay_pattern, encode_reference_audio)
    model = spec.get("model", "bosonai/higgs-tts-3-4b")
    engine = Omni(model=model, trust_remote_code=True)
    adapter = HiggsAudioV3TokenizerAdapter(AutoTokenizer.from_pretrained(model, trust_remote_code=True))
    wav, sr = sf.read(spec["ref"], always_2d=False)
    if wav.ndim == 2:
        wav = wav.mean(axis=1)
    codes = apply_delay_pattern(encode_reference_audio(wav, int(sr))).to(torch.long)

    def prompt(text):
        ids = adapter.build_prompt(text, num_ref_tokens=int(codes.shape[0]), reference_text=spec["ref_text"])
        ids, pos = adapter.prepare_prompt_for_engine(ids)
        return {"prompt_token_ids": ids,
                "additional_information": {"audio_input_ids": codes,
                                           "audio_input_ids_mask": torch.ones(codes.shape[0], dtype=torch.bool),
                                           "audio_placeholder_positions": pos}}

    jobs = [j for j in spec["jobs"] if not os.path.exists(j["out"])]   # resumable
    for seed in sorted({j["seed"] for j in jobs}):
        batch = [j for j in jobs if j["seed"] == seed]
        params = copy.deepcopy(list(engine.default_sampling_params_list))
        params[0].seed = seed
        outs = engine.generate([prompt(j["text"]) for j in batch], params, use_tqdm=False)
        # outputs come in the order they finish; request ids are "<prompt index>_<uuid>"
        outs = sorted(outs, key=lambda o: int(str(o.request_id).split("_")[0]))
        for j, o in zip(batch, outs):
            os.makedirs(os.path.dirname(j["out"]), exist_ok=True)
            sf.write(j["out"], (pcm(o.outputs[0].multimodal_output) * 32767).astype(np.int16), SR, subtype="PCM_16")
        print("seed %d: %d lines" % (seed, len(batch)), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
