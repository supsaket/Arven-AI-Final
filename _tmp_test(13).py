from memory.system import MemorySystem
m = MemorySystem()
for q in ["what is my favorite color", "what are my favorite colors", "what is my favorite game", "Germany", "python"]:
    res = m.recall(q, limit=5)
    print("Q:", q)
    for r in res:
        print("    %.2f | %s" % (r["score"], r["content"]))
    if not res:
        print("    (none)")
    print()
