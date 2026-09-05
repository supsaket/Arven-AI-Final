from memory.database import MemoryDatabase
db = MemoryDatabase()
allm = db.get_all()
print("get_all rows:", len(allm))
for r in allm:
    print("  id", r["id"], "|", r["content"][:60])

from memory.retriever import MemoryRetriever
try:
    ret = MemoryRetriever()
    print("embedder:", ret._embedder)
except Exception as e:
    print("retriever init error:", type(e).__name__, e)
