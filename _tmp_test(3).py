import time, ollama
t0=time.time()
r = ollama.Client(host="http://127.0.0.1:11434").chat(
    model="qwen3.5:4b",
    messages=[{"role":"user","content":"say hello in 5 words"}],
    options={"num_predict": 512},
)
print("with num_predict:", round(time.time()-t0,1), "s")
print("content:", repr(r["message"]["content"]))
print("done_reason:", r.get("done_reason"))
