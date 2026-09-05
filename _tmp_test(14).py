import time
import ollama
t0 = time.time()
try:
    resp = ollama.chat(model="qwen3.5:4b", messages=[{"role":"user","content":"say hi in one word"}])
    print("ollama ok in", round(time.time()-t0,1), "s")
    print(resp["message"]["content"][:100])
except Exception as e:
    print("ollama error:", e)
