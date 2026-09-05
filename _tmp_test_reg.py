from tools.builder import get_registry
reg = get_registry()
names = reg.names()
print("Registered tools:", len(names))
print(names)
