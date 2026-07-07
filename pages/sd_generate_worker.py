"""
sd_generate_worker.py — 完全离线版 v5
所有必要的 config 内嵌在代码里，不依赖网络，不依赖外部缓存文件。
"""

import sys, os, json, random, time, gc, tempfile, shutil

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stdin  = io.TextIOWrapper(sys.stdin.buffer,  encoding="utf-8", errors="replace")

def emit(obj):
    print(json.dumps(obj, ensure_ascii=True), flush=True)

def log(msg):
    emit({"type": "log", "msg": msg})

def progress(pct):
    emit({"type": "progress", "pct": pct})


# ══════════════════════════════════════════════════════════════
# 内嵌 Config（彻底离线，不依赖任何缓存）
# ══════════════════════════════════════════════════════════════

# CLIP ViT-L/14 (SD1.5 text encoder)
_CLIP_L_CONFIG = {
    "architectures": ["CLIPTextModel"],
    "attention_dropout": 0.0, "bos_token_id": 49406,
    "dropout": 0.0, "eos_token_id": 49407,
    "hidden_act": "quick_gelu", "hidden_size": 768,
    "initializer_factor": 1.0, "initializer_range": 0.02,
    "intermediate_size": 3072, "layer_norm_eps": 1e-05,
    "max_position_embeddings": 77, "model_type": "clip_text_model",
    "num_attention_heads": 12, "num_hidden_layers": 12,
    "pad_token_id": 1, "projection_dim": 768,
    "torch_dtype": "float32", "vocab_size": 49408
}

# CLIP ViT-bigG (SDXL text_encoder_2)
_CLIP_G_CONFIG = {
    "architectures": ["CLIPTextModelWithProjection"],
    "attention_dropout": 0.0, "bos_token_id": 49406,
    "dropout": 0.0, "eos_token_id": 49407,
    "hidden_act": "gelu", "hidden_size": 1280,
    "initializer_factor": 1.0, "initializer_range": 0.02,
    "intermediate_size": 5120, "layer_norm_eps": 1e-05,
    "max_position_embeddings": 77, "model_type": "clip_text_model",
    "num_attention_heads": 20, "num_hidden_layers": 32,
    "pad_token_id": 0, "projection_dim": 1280,
    "torch_dtype": "float32", "vocab_size": 49408
}

# EulerDiscreteScheduler config
_EULER_SCHEDULER_CONFIG = {
    "_class_name": "EulerDiscreteScheduler",
    "_diffusers_version": "0.21.4",
    "beta_end": 0.012, "beta_schedule": "scaled_linear",
    "beta_start": 0.00085, "clip_sample": False,
    "interpolation_type": "linear", "num_train_timesteps": 1000,
    "prediction_type": "epsilon", "rescale_betas_zero_snr": False,
    "sample_max_value": 1.0, "set_alpha_to_one": False,
    "skip_prk_steps": True, "steps_offset": 1,
    "timestep_spacing": "leading", "timestep_type": "discrete",
    "trained_betas": None, "use_karras_sigmas": False
}

# SDXL model_index.json
_SDXL_MODEL_INDEX = {
    "_class_name": "StableDiffusionXLPipeline",
    "_diffusers_version": "0.31.0",
    "force_zeros_for_empty_prompt": True,
    "add_watermarker": None,
    "scheduler": ["diffusers", "EulerDiscreteScheduler"],
    "text_encoder": ["transformers", "CLIPTextModel"],
    "text_encoder_2": ["transformers", "CLIPTextModelWithProjection"],
    "tokenizer": ["transformers", "CLIPTokenizer"],
    "tokenizer_2": ["transformers", "CLIPTokenizer"],
    "unet": ["diffusers", "UNet2DConditionModel"],
    "vae": ["diffusers", "AutoencoderKL"],
    "image_encoder": [None, None],
    "feature_extractor": [None, None],
}

# SD1.5 model_index.json
_SD15_MODEL_INDEX = {
    "_class_name": "StableDiffusionPipeline",
    "_diffusers_version": "0.31.0",
    "feature_extractor": [None, None],
    "image_encoder": [None, None],
    "requires_safety_checker": False,
    "safety_checker": [None, None],
    "scheduler": ["diffusers", "PNDMScheduler"],
    "text_encoder": ["transformers", "CLIPTextModel"],
    "tokenizer": ["transformers", "CLIPTokenizer"],
    "unet": ["diffusers", "UNet2DConditionModel"],
    "vae": ["diffusers", "AutoencoderKL"]
}

# PNDM Scheduler config (SD1.5 默认)
_PNDM_SCHEDULER_CONFIG = {
    "_class_name": "PNDMScheduler",
    "_diffusers_version": "0.21.4",
    "beta_end": 0.012, "beta_schedule": "scaled_linear",
    "beta_start": 0.00085, "clip_sample": False,
    "num_train_timesteps": 1000, "set_alpha_to_one": False,
    "skip_prk_steps": True, "steps_offset": 1,
    "timestep_spacing": "leading", "trained_betas": None
}


def _make_tmp_config(model_index: dict, scheduler_cfg: dict,
                     clip_l_cfg: dict = None, clip_g_cfg: dict = None) -> str:
    """
    创建临时目录，写入完整的 diffusers pipeline config。
    包含 model_index.json + scheduler/scheduler_config.json
    + 可选的 text_encoder/config.json、text_encoder_2/config.json
    """
    tmp = tempfile.mkdtemp(prefix="sd_cfg_")

    # model_index.json
    with open(os.path.join(tmp, "model_index.json"), "w") as f:
        json.dump(model_index, f)

    # scheduler/scheduler_config.json
    sched_dir = os.path.join(tmp, "scheduler")
    os.makedirs(sched_dir)
    with open(os.path.join(sched_dir, "scheduler_config.json"), "w") as f:
        json.dump(scheduler_cfg, f)

    # text_encoder/config.json（CLIP-L）
    if clip_l_cfg:
        te_dir = os.path.join(tmp, "text_encoder")
        os.makedirs(te_dir)
        with open(os.path.join(te_dir, "config.json"), "w") as f:
            json.dump(clip_l_cfg, f)

    # text_encoder_2/config.json（CLIP-G，仅 SDXL）
    if clip_g_cfg:
        te2_dir = os.path.join(tmp, "text_encoder_2")
        os.makedirs(te2_dir)
        with open(os.path.join(te2_dir, "config.json"), "w") as f:
            json.dump(clip_g_cfg, f)

    return tmp


# ══════════════════════════════════════════════════════════════
# 路径查找（tokenizer 文件）
# ══════════════════════════════════════════════════════════════

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_TOKENIZER_CANDIDATES = [
    r"D:\sd-webui-aki-v4.10\.cache\sdwebuilauncher\hfmirror\refs\openai\clip-vit-large-patch14\main",
    r"D:\huggingface\hub\models--openai--clip-vit-large-patch14\snapshots\32bd64288804d66eefd0ccbe215aa642df71cc41",
]

_HF_CACHE_ROOTS = [
    r"D:\huggingface\hub",
    os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"),
]

def _find_tokenizer_dir() -> str:
    """找包含 tokenizer_config.json 的目录"""
    for p in _TOKENIZER_CANDIDATES:
        if os.path.isfile(os.path.join(p, "tokenizer_config.json")):
            return p
    return None

def _find_sd15_yaml() -> str:
    for p in [
        os.path.join(_SCRIPT_DIR, "v1-inference.yaml"),
        r"D:\sd-webui-aki-v4.10\configs\v1-inference.yaml",
    ]:
        if os.path.isfile(p):
            return p
    return None

def _find_hf_snapshot(repo_id: str) -> str:
    folder = "models--" + repo_id.replace("/", "--")
    for root in _HF_CACHE_ROOTS:
        snap_root = os.path.join(root, folder, "snapshots")
        if not os.path.isdir(snap_root):
            continue
        for s in sorted(os.listdir(snap_root), reverse=True):
            full = os.path.join(snap_root, s)
            if os.path.isdir(full) and os.path.isfile(os.path.join(full, "model_index.json")):
                return full
    return None


# ══════════════════════════════════════════════════════════════
# 采样器
# ══════════════════════════════════════════════════════════════

_SAMPLER_MAP = {
    "Euler a":          "EulerAncestralDiscreteScheduler",
    "Euler":            "EulerDiscreteScheduler",
    "DPM++ 2M":         "DPMSolverMultistepScheduler",
    "DPM++ 2M Karras":  "DPMSolverMultistepScheduler",
    "DPM++ SDE":        "DPMSolverSDEScheduler",
    "DPM++ SDE Karras": "DPMSolverSDEScheduler",
    "DDIM":             "DDIMScheduler",
    "UniPC":            "UniPCMultistepScheduler",
    "LMS":              "LMSDiscreteScheduler",
    "Heun":             "HeunDiscreteScheduler",
}
_KARRAS = {"DPM++ 2M Karras", "DPM++ SDE Karras"}

def _set_scheduler(pipe, name, arch):
    import diffusers
    cls = (getattr(diffusers, "FlowMatchEulerDiscreteScheduler", None)
           if arch == "flux"
           else getattr(diffusers, _SAMPLER_MAP.get(name, ""), None))
    if not cls:
        return
    try:
        cfg = dict(pipe.scheduler.config)
        if name in _KARRAS:
            cfg["use_karras_sigmas"] = True
        pipe.scheduler = cls.from_config(cfg)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 模型加载
# ══════════════════════════════════════════════════════════════

def _load_sd15(model_path, dtype):
    from diffusers import StableDiffusionPipeline
    from transformers import CLIPTokenizer

    tok_dir  = _find_tokenizer_dir()
    yaml_path = _find_sd15_yaml()

    # 构建完整的临时 config 目录（含 CLIP-L config.json + scheduler）
    tmp = _make_tmp_config(
        model_index   = _SD15_MODEL_INDEX,
        scheduler_cfg = _PNDM_SCHEDULER_CONFIG,
        clip_l_cfg    = _CLIP_L_CONFIG,
    )
    log(f"   临时 config 目录：{tmp}")

    extra = {}
    if tok_dir:
        log(f"   tokenizer：{tok_dir}")
        try:
            extra["tokenizer"] = CLIPTokenizer.from_pretrained(tok_dir, local_files_only=True)
        except Exception as e:
            log(f"   tokenizer 加载失败（跳过）：{e}")

    try:
        if yaml_path:
            log(f"   yaml：{yaml_path}  →  legacy 模式 + 内置 CLIP config")
            pipe = StableDiffusionPipeline.from_single_file(
                model_path,
                config=tmp,              # 提供完整 config 目录（含 CLIP config.json）
                original_config=yaml_path,
                torch_dtype=dtype,
                safety_checker=None,
                local_files_only=True,
                **extra,
            )
        else:
            log("   使用内置 config（无 yaml）")
            pipe = StableDiffusionPipeline.from_single_file(
                model_path,
                config=tmp,
                torch_dtype=dtype,
                safety_checker=None,
                local_files_only=True,
                **extra,
            )
    finally:
        try: shutil.rmtree(tmp)
        except Exception: pass

    return pipe


def _load_sdxl(model_path, dtype):
    from diffusers import StableDiffusionXLPipeline
    from transformers import CLIPTokenizer

    # 先查 HF 缓存里有没有完整的 SDXL config
    sdxl_cached = _find_hf_snapshot("stabilityai/stable-diffusion-xl-base-1.0")
    tok_dir = _find_tokenizer_dir()

    if sdxl_cached:
        log(f"   SDXL 缓存 config：{sdxl_cached}")
        cfg_arg = dict(config=sdxl_cached, local_files_only=True)
    else:
        # 构建完整临时 config（含 scheduler + 两个 CLIP config）
        tmp = _make_tmp_config(
            model_index   = _SDXL_MODEL_INDEX,
            scheduler_cfg = _EULER_SCHEDULER_CONFIG,
            clip_l_cfg    = _CLIP_L_CONFIG,
            clip_g_cfg    = _CLIP_G_CONFIG,
        )
        log(f"   内置 SDXL config：{tmp}")
        cfg_arg = dict(config=tmp, local_files_only=True)

    extra = {}
    if tok_dir:
        log(f"   tokenizer：{tok_dir}")
        try:
            extra["tokenizer"] = CLIPTokenizer.from_pretrained(tok_dir, local_files_only=True)
        except Exception as e:
            log(f"   tokenizer 加载失败（跳过）：{e}")

    try:
        pipe = StableDiffusionXLPipeline.from_single_file(
            model_path, torch_dtype=dtype, **cfg_arg, **extra)
    finally:
        if "tmp" in locals():
            try: shutil.rmtree(tmp)
            except Exception: pass

    return pipe


def _load_flux(model_path, dtype):
    from diffusers import FluxPipeline
    for repo in ["black-forest-labs/FLUX.1-dev", "black-forest-labs/FLUX.1-schnell"]:
        cached = _find_hf_snapshot(repo)
        if cached:
            log(f"   Flux 缓存：{cached}")
            return FluxPipeline.from_single_file(
                model_path, config=cached, torch_dtype=dtype, local_files_only=True)
    log("   未找到 Flux 本地缓存，尝试直接加载...")
    return FluxPipeline.from_single_file(model_path, torch_dtype=dtype)


def _apply_device(pipe, device, cpu_offload, use_xformers):
    if cpu_offload:
        pipe.enable_model_cpu_offload()
        log("   CPU Offload 已启用")
    else:
        pipe = pipe.to(device)
    pipe.enable_attention_slicing()
    if use_xformers:
        try:
            pipe.enable_xformers_memory_efficient_attention()
            log("   xformers 已启用")
        except Exception as e:
            log(f"   xformers 不可用（跳过）：{e}")
    return pipe


# ══════════════════════════════════════════════════════════════
# 主函数
# ══════════════════════════════════════════════════════════════

def main():
    try:
        p = json.loads(sys.stdin.read())
    except Exception as e:
        emit({"type": "error", "msg": f"参数解析失败：{e}"}); return

    arch  = p["arch"]
    steps = p["steps"]
    batch = p.get("batch", 1)

    log("► 初始化 torch / CUDA ...")
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype  = torch.float16 if device == "cuda" else torch.float32
    log(f"   torch {torch.__version__}  CUDA:{torch.cuda.is_available()}  device:{device}")
    log(f"   tokenizer 路径：{_find_tokenizer_dir() or '未找到（将使用内置 config）'}")
    log(f"   yaml 路径：{_find_sd15_yaml() or '未找到'}")

    log(f"► 加载模型：{os.path.basename(p['model_path'])}  [{arch.upper()}]")
    t0 = time.time()

    if arch == "flux":
        pipe = _load_flux(p["model_path"], dtype)
    elif arch == "sdxl":
        pipe = _load_sdxl(p["model_path"], dtype)
    else:
        pipe = _load_sd15(p["model_path"], dtype)

    pipe = _apply_device(pipe, device, p.get("cpu_offload", False), p.get("use_xformers", False))
    _set_scheduler(pipe, p.get("sampler", "Euler a"), arch)
    log(f"   加载完成 {time.time()-t0:.1f}s  采样器：{p.get('sampler','Euler a')}")

    seed = p["seed"] if p.get("seed", -1) >= 0 else random.randint(0, 2**31)
    generator = torch.Generator(device=device).manual_seed(seed)
    log(f"► 推理  steps={steps}  cfg={p.get('cfg',7)}  {p['width']}x{p['height']}  batch={batch}  seed={seed}")
    t1 = time.time()

    import diffusers as _df
    df_ver = tuple(int(x) for x in getattr(_df, "__version__", "0.0.0").split(".")[:2])
    if df_ver >= (0, 27):
        def _cb(pipe, i, t, kw):
            progress(int((i+1)/steps*100))
            log(f"   step {i+1}/{steps}")
            return kw
        cb_kw = dict(callback_on_step_end=_cb)
    else:
        def _cb_old(pipe, step, ts, latents):
            progress(int((step+1)/steps*100))
            log(f"   step {step+1}/{steps}")
        cb_kw = dict(callback=_cb_old, callback_steps=1)

    common = dict(
        prompt=p["prompt"],
        num_inference_steps=steps,
        width=p["width"], height=p["height"],
        generator=generator,
        num_images_per_prompt=batch,
        **cb_kw,
    )
    if arch == "flux":
        images = pipe(guidance_scale=1.0, **common).images
    else:
        images = pipe(
            negative_prompt=p.get("negative_prompt", ""),
            guidance_scale=float(p.get("cfg", 7)),
            **common,
        ).images

    elapsed = time.time() - t1

    from datetime import datetime
    os.makedirs(p["save_dir"], exist_ok=True)
    saved = []
    ts = datetime.now().strftime("sd_%Y%m%d_%H%M%S")
    for idx, img in enumerate(images):
        fname = f"{ts}_{idx+1}.png" if batch > 1 else f"{ts}.png"
        fp = os.path.join(p["save_dir"], fname)
        img.save(fp); saved.append(fp)
        log(f"saved: {fp}")

    del pipe
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

    progress(100)
    emit({"type": "done", "paths": saved, "elapsed": elapsed, "seed": seed})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        emit({"type": "error", "msg": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"})
