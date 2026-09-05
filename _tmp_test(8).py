from brain.brain import Brain
b = Brain()
r = b.process("remember my favorite color is teal")
print("SAVE:", r["category"], "|", r["response"][:150])
r = b.process("what is my favorite color")
print("RECALL:", r["response"][:200])
