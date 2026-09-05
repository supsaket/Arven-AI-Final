from brain.brain import Brain
b = Brain()
r = b.process("what is my favorite color")
print("MEMORY->", r["category"], "|", r["response"][:200])
print()
r = b.process("what do you remember")
print("MEMORIES->", r["category"], "|", r["response"][:300])
