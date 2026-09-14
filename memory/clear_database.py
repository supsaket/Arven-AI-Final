from memory.database import MemoryDatabase

db = MemoryDatabase()

for memory in db.get_all():
    db.delete(memory[0])

print("Memory database cleaned.")
