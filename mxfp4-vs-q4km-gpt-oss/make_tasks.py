"""Generate 60 deterministic, auto-gradable tasks (seed 7). Answers computed by code."""
import json, random

random.seed(7)
tasks = []


def add(cat, prompt, answer):
    tasks.append({"id": f"{cat}-{sum(t['cat']==cat for t in tasks)+1:02d}", "cat": cat,
                  "prompt": prompt + "\nEnd your reply with a last line of the form `FINAL: <answer>` (answer only, no units, no extra text).",
                  "answer": str(answer).strip()})


# 1. multi-step arithmetic
for _ in range(15):
    a, b, c, d = (random.randint(12, 99) for _ in range(4))
    add("arith", f"Compute ({a} * {b}) - ({c} * {d}) + {a + d}.", a * b - c * d + a + d)

# 2. string manipulation
words = ["quantization", "benchmark", "perplexity", "throughput", "microscaling", "inference",
         "bandwidth", "tokenizer", "attention", "embedding", "latency", "calibration"]
for i in range(15):
    w = random.choice(words) + random.choice(words)
    if i % 3 == 0:
        ch = random.choice("aeiou")
        add("string", f"How many times does the letter '{ch}' appear in the string \"{w}\"?", w.count(ch))
    elif i % 3 == 1:
        add("string", f"Reverse the string \"{w}\" and give the first 6 characters of the result.", w[::-1][:6])
    else:
        add("string", f"What is the 7th character (1-indexed) of the string \"{w}\" converted to uppercase?", w.upper()[6])

# 3. python output prediction
for i in range(15):
    n = random.randint(5, 12)
    m = random.randint(2, 5)
    k = random.randint(1, 3)
    code = f"s = 0\nfor i in range({n}):\n    if i % {m} != {k % m}:\n        s += i * {m}\nprint(s)"
    ns = {}
    out = []
    exec(code.replace("print(s)", "out.append(s)"), {"out": out})
    add("code", f"What does this Python program print?\n```python\n{code}\n```", out[0])

# 4. sorting / logic
for i in range(15):
    xs = random.sample(range(10, 99), 7)
    if i % 3 == 0:
        add("logic", f"Sort these numbers ascending and give the 4th one: {xs}", sorted(xs)[3])
    elif i % 3 == 1:
        add("logic", f"What is the sum of the even numbers in this list: {xs}?", sum(x for x in xs if x % 2 == 0))
    else:
        add("logic", f"What is the difference between the largest and smallest of: {xs}?", max(xs) - min(xs))

json.dump(tasks, open("tasks.json", "w"), indent=1)
print(len(tasks), "tasks", {c: sum(t['cat'] == c for t in tasks) for c in ("arith", "string", "code", "logic")})
