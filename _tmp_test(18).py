from memory.system import MemorySystem
m = MemorySystem()
for q in ["what is my favorite color", "what are my favorite colors", "colors", "What did I tell you about Germany"]:
    res = m.recall(q, limit=5)
    print("Q:", q)
    for r in res:
        print("   ", r["score"], "|", r["content"])
    print()
