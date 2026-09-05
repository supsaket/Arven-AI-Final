import time, ollama
t0 = time.time()
resp = ollama.chat(model="qwen3.5:4b", messages=[{"role":"user","content":"say hello in 5 words"}], think=False)
print("think=False time:", round(time.time()-t0,1), "s")
print("content:", repr(resp["message"]["content"]))
print("done_reason:", resp.get("done_reason"))
