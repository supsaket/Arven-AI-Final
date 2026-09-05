from brain.brain import Brain

b = Brain()
print("OPEN NOTEPAD AND CALCULATOR:")
try:
    r = b.process("open notepad and calculator")
    print("   ", r["response"])
except Exception as e:
    print("  ERROR:", e)
