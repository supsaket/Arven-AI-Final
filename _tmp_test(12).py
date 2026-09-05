from brain.brain import Brain
b = Brain()
r = b.process("explain what a neural network is")
print("REASON:", r["category"])
print(r["response"][:400])
