import tkinter as tk
from gui.app import ArvenApp
root = tk.Tk()
root.withdraw()
try:
    app = ArvenApp(root)
    root.update()
    print("GUI instantiated OK; tabs:", len(app.notebook.tabs()))
    app.close()
except Exception as e:
    import traceback; traceback.print_exc()
    print("GUI init failed:", e)
