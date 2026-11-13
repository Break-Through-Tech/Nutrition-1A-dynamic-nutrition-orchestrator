"""Local web server for the meal-planning agent: serves index.html (React) and runs the agent.

Setup once:   pip3 install flask
Run (from React_Agent, with Ollama running):
    python3 server.py --foods ../cleanedData/clean_usda_foods.csv
Then open http://localhost:8000
"""
import argparse
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from agent_tools import RecipeBank
from food_db import FoodDB
from meal_agent import MealPlanningAgent, OllamaClient

BASE = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
CFG = {}
LOCK = threading.Lock()          # one plan at a time: the local model is the bottleneck


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


def _name(m):
    return (m.get("model") or m.get("name")) if isinstance(m, dict) else getattr(m, "model", None)


@app.get("/api/health")
def health():
    bank = CFG["bank"]
    info = {"default_model": CFG["model"], "recipes_total": len(bank.recipes),
            "recipes_usable": sum(1 for r in bank.recipes.values() if r["usable"]),
            "ollama": False, "models": []}
    try:
        import ollama
        resp = ollama.list()
        items = resp["models"] if isinstance(resp, dict) else resp.models
        info.update(ollama=True, models=[n for n in map(_name, items) if n])
    except Exception:
        pass
    return jsonify(info)


@app.post("/api/plan")
def plan():
    body = request.get_json(silent=True) or {}
    text = str(body.get("request") or "").strip()
    if not text:
        return jsonify(error="Enter your requirements first."), 400
    if not LOCK.acquire(blocking=False):
        return jsonify(error="Another plan is still running. Wait for it to finish."), 429
    try:
        agent = MealPlanningAgent(OllamaClient(body.get("model") or CFG["model"]), CFG["bank"],
                                  max_steps=int(body.get("max_steps") or 20), llm_parse=False)
        return jsonify(agent.plan(text))
    except ConnectionError:
        return jsonify(error="Can’t reach Ollama. Open the Ollama app, then try again."), 503
    except Exception as e:
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    finally:
        LOCK.release()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipes", default="agent_data/recipes_normalized.json")
    ap.add_argument("--foods", default=None, help="USDA CSV (default: ingredient_matching.FOODS_PATH)")
    ap.add_argument("--nutrient-overrides", default="agent_data/nutrient_overrides.json")
    ap.add_argument("--model", default="qwen2.5:3b-instruct")
    ap.add_argument("--port", type=int, default=8000, help="8000, not 5000: macOS AirPlay uses 5000")
    a = ap.parse_args()
    CFG["bank"] = RecipeBank.from_file(a.recipes, FoodDB.from_paths(a.foods, a.nutrient_overrides))
    CFG["model"] = a.model
    print(f"Open http://localhost:{a.port}")
    app.run(host="127.0.0.1", port=a.port, debug=False)


if __name__ == "__main__":
    main()