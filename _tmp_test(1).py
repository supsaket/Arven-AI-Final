import time
from models.ollama_provider import OllamaProvider
p = OllamaProvider()
t0=time.time()
out = p.chat([{"role":"user","content":"say hello in 5 words"}])
print("provider chat:", round(time.time()-t0,1), "s ->", repr(out))

from brain.brain import Brain
t1=time.time()
b = Brain()
r = b.process("hello")
print("brain process:", round(time.time()-t1,1), "s ->", r["response"][:120])
