import time
from models.ollama_provider import OllamaProvider
p = OllamaProvider()
t0=time.time()
out = p.chat([{"role":"user","content":"say hello in 5 words"}])
print("provider chat:", round(time.time()-t0,1), "s")
print("out:", repr(out))
