# ARVEN AI Desktop

This is the first production-style desktop shell for the existing Arven AI project.

## 1. Install

From the Arven project root:

```powershell
cd "C:\Users\supsa\Downloads\Arven AI 7"
python -m pip install -r desktop\requirements-desktop.txt
```

## 2. Run

```powershell
python desktop\desktop_app.py
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File .\desktop\run_arven_desktop.ps1
```

## 3. Backend integration

The Chat page tries these endpoints on the existing FastAPI server:

- `POST http://127.0.0.1:8000/chat`
- `POST http://127.0.0.1:8000/api/chat`

Expected request:

```json
{"message":"Hello Arven"}
```

The response can contain `response`, `reply`, `message`, or `text`.

If your existing API uses a different route/schema, change `ApiWorker.run()` in `desktop_app.py` to match it.

## 4. Windows EXE

Install PyInstaller:

```powershell
python -m pip install pyinstaller
```

Build:

```powershell
pyinstaller --noconfirm --clean --windowed --name ArvenAI desktop\desktop_app.py
```

The executable will be in:

```text
dist\ArvenAI\ArvenAI.exe
```

For the final installer, keep the existing Arven project data/backend packaged alongside the desktop executable. Do not commit databases, API keys, secrets, or generated runtime data to Git.
