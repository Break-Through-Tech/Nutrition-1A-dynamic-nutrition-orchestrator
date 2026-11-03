"""Single ReAct agent: user requirements -> validated daily plans -> weekly plan.

Loop (per day):  model picks a tool -> Python runs it -> model reads the result
-> repeat until check_plan returns ok=true (Python stops the loop) or the step
cap is hit (the best attempt is kept and reported honestly, never faked).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from agent_tools import MEAL_TYPES, DayTools, PlanState, RecipeBank, normalize_constraints

SYSTEM_PROMPT = """You are a meal-planning agent. You plan ONE day at a time, using only tools.
Rules:
1. Never calculate or guess nutrition. Use only numbers returned by tools.
2. Fill every meal slot named in the brief. Call search_recipes for a slot, compare candidates
   with get_recipe_macros, then commit one with set_meal.
3. Call check_plan once the slots are filled. If it reports a violation (for example protein short by
   17g), fix it: swap a meal for a higher-protein recipe, or raise servings (0.5 to 3 in steps of 0.5),
   then call check_plan again.
4. When check_plan returns ok=true, reply with one short sentence and stop calling tools.
5. If a tool returns an error, read it and correct your next call."""


# ------------------------------------------------------------------ LLM clients
@dataclass
class ToolCall:
    name: str
    args: dict = field(default_factory=dict)


@dataclass
class LLMReply:
    content: str = ""
    tool_calls: list = field(default_factory=list)


def call(name: str, **args) -> LLMReply:
    """Helper for scripted tests: a reply that makes one tool call."""
    return LLMReply("", [ToolCall(name, args)])


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _inline_call(content: str):
    """Some small models print the call as JSON text instead of a structured tool call."""
    m = re.search(r"\{.*\}", content or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    if isinstance(obj, dict) and isinstance(obj.get("name"), str):
        args = obj.get("arguments", obj.get("parameters", {}))
        return ToolCall(obj["name"], args if isinstance(args, dict) else {})
    return None


class OllamaClient:
    """Local model through Ollama. Needs `pip install -U ollama` and a tool-capable model."""

    def __init__(self, model="qwen2.5:7b-instruct", host=None, temperature=0.0, num_ctx=8192):
        try:
            import ollama
        except ImportError as e:
            raise RuntimeError("pip install -U ollama") from e
        self.model, self.temperature, self.num_ctx = model, temperature, num_ctx
        self._client = ollama.Client(host=host) if host else ollama.Client()

    def chat(self, messages, tools=None) -> LLMReply:
        resp = self._client.chat(model=self.model, messages=messages, tools=tools,
                                 options={"temperature": self.temperature, "num_ctx": self.num_ctx})
        msg = _get(resp, "message")
        content = _get(msg, "content") or ""
        calls = []
        for tc in _get(msg, "tool_calls") or []:
            fn = _get(tc, "function")
            args = _get(fn, "arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            calls.append(ToolCall(_get(fn, "name"), dict(args)))
        if not calls and tools:
            inline = _inline_call(content)
            if inline:
                calls.append(inline)
        return LLMReply(content, calls)


class ScriptedClient:
    """Deterministic stand-in for tests/demos: replays a fixed list of replies in order."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, messages, tools=None) -> LLMReply:
        self.seen.append(messages)
        return self.replies.pop(0) if self.replies else LLMReply("(script exhausted)")


def _assistant_msg(reply: LLMReply) -> dict:
    msg = {"role": "assistant", "content": reply.content}
    if reply.tool_calls:
        msg["tool_calls"] = [{"function": {"name": c.name, "arguments": c.args}} for c in reply.tool_calls]
    return msg


# ------------------------------------------------------------------ requirement parsing
_MEAL_WORDS = {"breakfast": "breakfast", "breakfasts": "breakfast", "lunch": "lunch", "lunches": "lunch",
               "dinner": "dinner", "dinners": "dinner", "snack": "snack", "snacks": "snack"}
_UNSUPPORTED = ["vegan", "gluten", "keto", "low carb", "low-carb", "halal", "kosher", "diabetic"]
_EXCL_TRIGGER = (r"(?:\bno\b|\bwithout\b|\bexclud(?:e|ing)\b|\bavoid\b|\ballergic to\b|\bdon'?t eat\b|"
                 r"\bdo not eat\b|\bcan'?t eat\b|\bcan'?t have\b|\bnot eat\b|\bdon'?t want\b)")
_EXCL_STOP = {"at", "under", "over", "below", "with", "for", "but", "that", "per", "a", "the", "any", "more",
              "less", "than", "repeat", "repeats", "repeating", "i", "my", "please", "least", "meals", "meal",
              "i'd", "id", "want", "need", "to"} | set(_MEAL_WORDS)


def parse_constraints_regex(text: str) -> dict:
    """Deterministic extraction of the constraints a user states explicitly."""
    t, found = text.lower(), {}
    m = re.search(r"(\d+)\s*-?\s*days?\b", t)
    if m:
        found["days"] = int(m.group(1))
    elif re.search(r"\bweek(?:ly)?\b", t):
        found["days"] = 7
    elif re.search(r"\b(?:a|one|1|single)\s+day\b|\btoday\b|\btomorrow\b", t):
        found["days"] = 1
    m = (re.search(r"(\d+(?:\.\d+)?)\s*g(?:rams?)?\s*(?:of\s+)?protein", t)
         or re.search(r"protein[^0-9.]{0,30}(\d+(?:\.\d+)?)\s*g", t))
    if m:
        found["protein_g_min_per_day"] = float(m.group(1))
    m = (re.search(r"(?:under|below|less than|fewer than|at most|up to|no more than|max(?:imum)?(?:\s+of)?|<=?)"
                   r"\s*(\d{3,5})\s*k?cal(?:ories)?", t)
         or re.search(r"(\d{3,5})\s*k?cal(?:ories)?\s*(?:max|maximum|or less|or fewer|limit)", t))
    if m:
        found["calories_max_per_day"] = float(m.group(1))
    tags = [tag for tag in ("vegetarian", "kid-friendly") if tag in t or tag.replace("-", " ") in t]
    if tags:
        found["required_tags"] = tags
    # meal slots
    negated = {_MEAL_WORDS[w] for w in re.findall(
        r"(?:\bno\b|\bwithout\b|\bskip\b|\bexcept\b|\bexclude\b)\s+(?:any\s+)?(" + "|".join(_MEAL_WORDS) + r")\b", t)}
    mentioned = {_MEAL_WORDS[w] for w in re.findall(r"\b(" + "|".join(_MEAL_WORDS) + r")\b", t)}
    positive = [m_ for m_ in MEAL_TYPES if m_ in mentioned - negated]
    if positive:
        found["meal_types"] = positive
    elif negated:
        found["meal_types"] = [m_ for m_ in MEAL_TYPES if m_ not in negated]
    # excluded ingredients
    excluded: list[str] = []
    for m in re.finditer(_EXCL_TRIGGER + r"\s+([a-z][a-z,' \-]*)", t):
        for w in re.split(r"[ ,]+", m.group(1).strip()):
            if w in ("or", "and", ""):
                continue
            if w in _EXCL_STOP or w[0].isdigit():
                break
            excluded.append(w)
    if excluded:
        found["excluded_ingredients"] = list(dict.fromkeys(excluded))
    if re.search(r"(?:allow|ok|fine)\s+repeats|repeats?\s+(?:are\s+)?(?:ok|fine|allowed)", t):
        found["no_repeat_days"] = 0
    unsupported = [k for k in _UNSUPPORTED if k in t]
    if unsupported:
        found["unsupported"] = unsupported
    return found


_EXTRACT_PROMPT = """Extract meal-plan constraints from the user's request. Reply with ONLY a JSON object with keys:
days (integer), protein_g_min_per_day (number or null), calories_max_per_day (number or null),
meal_types (list from breakfast/lunch/dinner/snack, [] if not stated), excluded_ingredients (list of strings),
no_repeat_days (integer or null). Use null or [] for anything not stated. Do not guess."""


def _llm_extract(text: str, client) -> dict:
    reply = client.chat([{"role": "system", "content": _EXTRACT_PROMPT}, {"role": "user", "content": text}], None)
    m = re.search(r"\{.*\}", reply.content or "", re.S)
    return json.loads(m.group(0)) if m else {}


def parse_constraints(text: str, client=None):
    """Regex first (reliable on explicit numbers); the LLM may only fill what regex missed."""
    found = parse_constraints_regex(text)
    filled = []
    if client is not None:
        try:
            llm = _llm_extract(text, client)
        except Exception:
            llm = {}
        for k in ("days", "protein_g_min_per_day", "calories_max_per_day", "meal_types",
                  "excluded_ingredients", "no_repeat_days"):
            if k not in found and llm.get(k) not in (None, [], "", 0):
                found[k] = llm[k]
                filled.append(k)
    constraints, notes = normalize_constraints(found)
    if filled:
        notes.append(f"interpreted by the language model (please verify): {filled}")
    if constraints["unsupported"]:
        notes.append(f"not supported by this recipe bank, so NOT enforced: {constraints['unsupported']}")
    return constraints, notes


# ------------------------------------------------------------------ the agent
class MealPlanningAgent:
    def __init__(self, client, bank: RecipeBank, max_steps=12, repair_rounds=1, llm_parse=True, verbose=False):
        self.client, self.bank = client, bank
        self.max_steps, self.repair_rounds = max_steps, repair_rounds
        self.llm_parse, self.verbose = llm_parse, verbose

    def plan(self, request: str) -> dict:
        constraints, notes = parse_constraints(request, self.client if self.llm_parse else None)
        state, trace = PlanState(constraints, self.bank), []
        for day in range(1, constraints["days"] + 1):
            self._run_day(state, day, trace)
        for _ in range(self.repair_rounds):
            bad = [d["day"] for d in state.check_week()["days"] if not d["ok"]]
            if not bad:
                break
            for day in bad:
                self._run_day(state, day, trace, repair=True)
        return self._assemble(request, constraints, notes, state, trace)

    # -- one day ---------------------------------------------------------------
    def _brief(self, state: PlanState, day: int, repair: bool) -> str:
        c = state.c
        text = (f"Plan day {day} of {c['days']}.\nMeal slots to fill: {c['meal_types']}\n"
                f"Protein minimum per day: {c['protein_g_min_per_day']} g\n"
                f"Calorie maximum per day: {c['calories_max_per_day']} kcal\n"
                f"Excluded ingredients: {c['excluded_ingredients']}")
        if repair:
            chk = state.check_day(day)
            text += (f"\nThis day failed its check. Current meals: {chk['meals']}. "
                     f"Violations: {chk['violations']}. Fix it.")
        return text

    def _run_day(self, state: PlanState, day: int, trace: list, repair: bool = False) -> dict:
        tools = DayTools(state, day)
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._brief(state, day, repair)}]
        nudges = 0
        for step in range(self.max_steps):
            reply = self.client.chat(messages, tools.schemas)
            messages.append(_assistant_msg(reply))
            if not reply.tool_calls:
                trace.append({"day": day, "step": step, "thought": reply.content, "action": None})
                check = state.check_day(day)
                if check["ok"] or nudges >= 2:
                    break
                nudges += 1
                messages.append({"role": "user", "content":
                                 f"Day {day} is not finished yet: {check['violations']}. Continue with tool calls."})
                continue
            done = False
            for tc in reply.tool_calls:
                obs = tools.call(tc.name, tc.args)
                trace.append({"day": day, "step": step, "thought": reply.content,
                              "action": {"tool": tc.name, "args": tc.args}, "observation": obs})
                if self.verbose:
                    print(f"[day {day} step {step}] {tc.name}({tc.args}) -> {json.dumps(obs)[:160]}")
                messages.append({"role": "tool", "tool_name": tc.name, "content": json.dumps(obs)})
                if tc.name == "check_plan" and obs.get("ok"):
                    done = True
            if done:
                break
        return state.check_day(day)

    # -- output -----------------------------------------------------------------
    def _assemble(self, request, constraints, notes, state: PlanState, trace) -> dict:
        week = state.check_week()
        days, warnings = [], list(notes)
        for chk in week["days"]:
            d = chk["day"]
            days.append({"day": d, "meals": state.meal_details(d), "totals": chk["totals"],
                         "constraints_met": chk["ok"], "violations": chk["violations"], "warnings": chk["warnings"]})
            warnings += [f"day {d}: {w}" for w in chk["warnings"]]
        return {"request": request, "constraints": constraints, "assumptions": notes, "days": days,
                "weekly": week["weekly"], "constraints_met": week["ok"], "violations": week["violations"],
                "warnings": warnings, "trace": trace}


def format_plan(result: dict) -> str:
    c = result["constraints"]
    out = [f"Request: {result['request']}", ""]
    for d in result["days"]:
        status = "OK" if d["constraints_met"] else "NOT MET"
        t = d["totals"]
        out.append(f"Day {d['day']}  [{status}]  protein {t['protein_g']} g, {t['calories_kcal']} kcal")
        for mt, m in d["meals"].items():
            out.append(f"   {mt:<9} {m['name']}  x{m['servings']:g}  ({m['protein_g']} g protein, {m['calories_kcal']} kcal)")
        out += [f"   ! {v}" for v in d["violations"]]
    w = result["weekly"]
    out += ["", f"Weekly average: {w['avg_protein_g_per_day']} g protein/day, {w['avg_calories_per_day']} kcal/day",
            f"All constraints met: {result['constraints_met']}"]
    if result["warnings"]:
        out += ["", "Notes:"] + [f"  - {x}" for x in dict.fromkeys(result["warnings"])]
    return "\n".join(out)