import time
t0 = time.time()
from brain.brain import Brain
print("brain import:", round(time.time()-t0,1))
b = Brain()
print("brain ctor:", round(time.time()-t0,1))
r = b.process("hello")
print("process done:", round(time.time()-t0,1), "category:", r["category"])
print(r["response"][:200])
