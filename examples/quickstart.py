"""ClawEvalKit Quickstart — minimal example of running a benchmark."""
from clawevalkit.config import load_env, get_model_config
from clawevalkit.dataset import BENCHMARKS
from clawevalkit.summarizer import Summarizer

# 1. Load API keys from .env
load_env()

# 2. Run Tribe benchmark (8 pure LLM tests, fastest)
tribe = BENCHMARKS["tribe"]()
config = get_model_config("claude-sonnet")
result = tribe.evaluate("claude-sonnet", config)
print(f"Tribe score: {result['score']}  ({result['pass_rate']})")

# 3. View all cached results
Summarizer().summary()
