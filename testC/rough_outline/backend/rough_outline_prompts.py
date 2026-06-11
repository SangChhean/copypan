import importlib.util
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "rough-outline" / "backend" / "rough_outline_prompts.py"
_spec = importlib.util.spec_from_file_location("_rough_outline_prompts_src", _SRC)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
PROMPT_TEMPLATES = _mod.PROMPT_TEMPLATES
AI_CONFIGS = _mod.AI_CONFIGS
