import os
import subprocess
import webbrowser
from urllib.parse import quote_plus


class ActionEngine:

    def __init__(self):

        # Common Windows application aliases.
        # These are only shortcuts; unknown apps are searched automatically.
        self.apps = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
            "files manager": "explorer.exe",
            "cmd": "cmd.exe",
            "terminal": "wt.exe",
        }

        # Known websites.
        self.websites = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://github.com",
            "instagram": "https://www.instagram.com",
            "whatsapp": "https://web.whatsapp.com",
            "reddit": "https://www.reddit.com",
            "netflix": "https://www.netflix.com",
            "spotify": "https://open.spotify.com",
            "facebook": "https://www.facebook.com",
            "twitter": "https://x.com",
            "x": "https://x.com",
            "discord": "https://discord.com/app",
            "chatgpt": "https://chatgpt.com",
        }

        # Common app aliases.
        self.aliases = {
            "vs code": "visual studio code",
            "vscode": "visual studio code",
            "code": "visual studio code",
            "ms word": "word",
            "microsoft word": "word",
            "ms excel": "excel",
            "microsoft excel": "excel",
            "ms powerpoint": "powerpoint",
            "microsoft powerpoint": "powerpoint",
            "file manager": "explorer",
        }

    # --------------------------------------------------
    # CLEAN REQUEST
    # --------------------------------------------------

    def clean_request(self, text):

        prefixes = [
            "do me a favour,",
            "do me a favor,",
            "please ",
            "can you ",
            "could you ",
            "would you ",
            "hey arven,",
            "arven,"
        ]

        text = text.strip()

        for prefix in prefixes:

            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        return text

    # --------------------------------------------------
    # FIND WINDOWS APP
    # --------------------------------------------------

    def find_windows_app(self, target):

        # Direct aliases first.
        if target in self.apps:
            return self.apps[target]

        # Windows Start Menu search.
        search_locations = [
            os.path.expandvars(
                r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"
            ),
            os.path.expandvars(
                r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"
            )
        ]

        target_lower = target.lower()

        for location in search_locations:

            if not os.path.exists(location):
                continue

            for root, dirs, files in os.walk(location):

                for file in files:

                    if not file.lower().endswith(
                        (".lnk", ".exe", ".url")
                    ):
                        continue

                    name = os.path.splitext(file)[0].lower()

                    if (
                        name == target_lower
                        or target_lower in name
                    ):
                        return os.path.join(root, file)

        # Try Windows shell/app launcher.
        return None

    # --------------------------------------------------
    # OPEN
    # --------------------------------------------------

    def open_target(self, target):

        target = target.strip()

        # Apply aliases.
        target = self.aliases.get(target, target)

        # Default browser.
        if target in [
            "browser",
            "the browser",
            "default browser"
        ]:

            try:

                webbrowser.open("https://www.google.com")

                return {
                    "success": True,
                    "message": "Opening your default browser.",
                    "action": "open",
                    "target": "default_browser"
                }

            except Exception as error:

                return {
                    "success": False,
                    "message": f"I couldn't open your default browser: {error}",
                    "action": "open",
                    "target": "default_browser"
                }

        # Website.
        if target in self.websites:

            try:

                webbrowser.open(self.websites[target])

                return {
                    "success": True,
                    "message": f"Opening {target}.",
                    "action": "open",
                    "target": target
                }

            except Exception as error:

                return {
                    "success": False,
                    "message": f"I couldn't open {target}: {error}",
                    "action": "open",
                    "target": target
                }

        # Known application.
        app = self.find_windows_app(target)

        if app:

            try:

                os.startfile(app)

                return {
                    "success": True,
                    "message": f"Opening {target}.",
                    "action": "open",
                    "target": target
                }

            except Exception as error:

                return {
                    "success": False,
                    "message": f"I couldn't open {target}: {error}",
                    "action": "open",
                    "target": target
                }

        # Try Windows directly.
        try:

            os.startfile(target)

            return {
                "success": True,
                "message": f"Opening {target}.",
                "action": "open",
                "target": target
            }

        except Exception:
            pass

        return {
            "success": False,
            "message": f"I couldn't find an installed app called {target}.",
            "action": "open",
            "target": target
        }

    # --------------------------------------------------
    # SEARCH
    # --------------------------------------------------

    def search(self, query):

        query = query.strip()

        if not query:

            return {
                "success": False,
                "message": "What should I search for?",
                "action": "search",
                "target": None
            }

        try:

            url = (
                "https://www.google.com/search?q="
                + quote_plus(query)
            )

            webbrowser.open(url)

            return {
                "success": True,
                "message": f"Searching for {query}.",
                "action": "search",
                "target": query
            }

        except Exception as error:

            return {
                "success": False,
                "message": f"I couldn't perform the search: {error}",
                "action": "search",
                "target": query
            }

    # --------------------------------------------------
    # CLOSE
    # --------------------------------------------------

    def close_target(self, target):

        target = target.strip()

        processes = {
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "edge": "msedge.exe",
            "microsoft edge": "msedge.exe",
            "firefox": "firefox.exe",
            "brave": "brave.exe",
            "opera": "opera.exe",
            "notepad": "notepad.exe",
            "calculator": "CalculatorApp.exe",
            "calc": "CalculatorApp.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
            "files manager": "explorer.exe",
            "spotify": "Spotify.exe",
            "discord": "Discord.exe",
            "steam": "steam.exe",
        }

        # Browser group.
        if target in [
            "browser",
            "the browser",
            "default browser"
        ]:

            browser_processes = [
                "brave.exe",
                "chrome.exe",
                "msedge.exe",
                "firefox.exe",
                "opera.exe"
            ]

            closed = False

            for process in browser_processes:

                result = subprocess.run(
                    ["taskkill", "/IM", process, "/F"],
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    closed = True

            if closed:

                return {
                    "success": True,
                    "message": "Closing the browser.",
                    "action": "close",
                    "target": "browser"
                }

            return {
                "success": False,
                "message": "No supported browser is currently running.",
                "action": "close",
                "target": "browser"
            }

        process = processes.get(target)

        if not process:

            return {
                "success": False,
                "message": f"I don't know how to close {target}.",
                "action": "close",
                "target": target
            }

        try:

            result = subprocess.run(
                ["taskkill", "/IM", process, "/F"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:

                return {
                    "success": False,
                    "message": f"{target} is not currently running.",
                    "action": "close",
                    "target": target
                }

            return {
                "success": True,
                "message": f"Closing {target}.",
                "action": "close",
                "target": target
            }

        except Exception as error:

            return {
                "success": False,
                "message": f"I couldn't close {target}: {error}",
                "action": "close",
                "target": target
            }

    # --------------------------------------------------
    # MAIN EXECUTOR
    # --------------------------------------------------

    def execute(self, request):

        text = self.clean_request(request.lower())

        # OPEN
        if text.startswith("open "):

            target = text[5:].strip()

            if not target:

                return {
                    "success": False,
                    "message": "What should I open?",
                    "action": "open",
                    "target": None
                }

            return self.open_target(target)

        # SEARCH
        if text.startswith("search "):

            query = text[7:].strip()

            return self.search(query)

        # CLOSE
        if text.startswith("close "):

            target = text[6:].strip()

            if not target:

                return {
                    "success": False,
                    "message": "What should I close?",
                    "action": "close",
                    "target": None
                }

            return self.close_target(target)

        return {
            "success": False,
            "message": "I couldn't identify an action.",
            "action": None,
            "target": None
        }