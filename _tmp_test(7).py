from brain.brain import Brain

b = Brain()
tests = [
    "what is my name",
    "who is your creator",
    "what is your name",
    "what is your version",
]

for t in tests:
    try:
        r = b.process(t)
        print(f"Q: {t}\n  -> {r['category']}: {r['response']}\n")
    except Exception as e:
        print(f"Q: {t}\n  ERROR: {type(e).__name__}: {e}\n")
