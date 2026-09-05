import time
t0 = time.time()
from brain.brain import Brain
b = Brain()
print("brain ready:", round(time.time()-t0,1))
r = b.process("hello")
print("process:", round(time.time()-t0,1), "category:", r["category"])
print(r["response"][:200])
