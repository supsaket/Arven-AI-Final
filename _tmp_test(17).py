from brain.brain import Brain
b = Brain()
r = b.process("hello, who are you?")
print("CHAT:", r["category"])
print(r["response"])
