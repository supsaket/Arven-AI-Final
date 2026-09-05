import os
import subprocess
import webbrowser
import pyautogui
import time
from urllib.parse import quote_plus


class ActionEngine:

    def __init__(self):

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

        self.processes = {
            "notepad": ["notepad.exe"],
            "calculator": [
                "CalculatorApp.exe",
                "ApplicationFrameHost.exe",
            ],
            "calc": [
                "CalculatorApp.exe",
                "ApplicationFrameHost.exe",
            ],
            "explorer": ["explorer.exe"],
            "file explorer": ["explorer.exe"],
            "files manager": ["explorer.exe"],
            "chrome": ["chrome.exe"],
            "google chrome": ["chrome.exe"],
            "edge": ["msedge.exe"],
            "microsoft edge": ["msedge.exe"],
            "firefox": ["firefox.exe"],
            "brave": ["brave.exe"],
            "opera": ["opera.exe"],
            "spotify": ["Spotify.exe"],
            "discord": ["Discord.exe"],
        }

        # Websites opened by Arven.
        # Used so Arven can safely close its own tab
        # without killing the whole browser.
        self.opened_websites = set()

    def clean_request(self, text):

        text = text.lower().strip()

        prefixes = [
            "do me a favour,",
            "do me a favor,",
            "please ",
            "can you ",
            "could you ",
            "would you ",
            "hey arven,",
            "arven,",
        ]

        changed = True

        while changed:

            changed = False

            for prefix in prefixes:

                if text.startswith(prefix):

                    text = text[len(prefix):].strip()
                    changed = True
                    break

        return text

    def open_target(self, target):

        target = target.strip()

        if target in [
            "browser",
            "the browser",
            "default browser",
        ]:

            webbrowser.open("https://www.google.com")

            return {
                "success": True,
                "message": "Opening your default browser.",
                "action": "open",
                "target": "browser",
            }

        if target in self.websites:

            try:

                webbrowser.open(self.websites[target])

                self.opened_websites.add(target)

                return {
                    "success": True,
                    "message": f"Opening {target}.",
                    "action": "open",
                    "target": target,
                }

            except Exception as error:

                return {
                    "success": False,
                    "message": f"I couldn't open {target}: {error}",
                    "action": "open",
                    "target": target,
                }

        if target in self.apps:

            try:

                subprocess.Popen(
                    self.apps[target],
                    shell=True
                )

                return {
                    "success": True,
                    "message": f"Opening {target}.",
                    "action": "open",
                    "target": target,
                }

            except Exception as error:

                return {
                    "success": False,
                    "message": f"I couldn't open {target}: {error}",
                    "action": "open",
                    "target": target,
                }

        try:

            os.startfile(target)

            return {
                "success": True,
                "message": f"Opening {target}.",
                "action": "open",
                "target": target,
            }

        except Exception:

            return {
                "success": False,
                "message": f"I couldn't find {target}.",
                "action": "open",
                "target": target,
            }

    def search(self, query):

        query = query.strip()

        if not query:

            return {
                "success": False,
                "message": "What should I search for?",
                "action": "search",
                "target": None,
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
                "target": query,
            }

        except Exception as error:

            return {
                "success": False,
                "message": f"I couldn't perform the search: {error}",
                "action": "search",
                "target": query,
            }

    def close_own_website(self, target):

        if target not in self.opened_websites:

            return {
                "success": False,
                "message": (
                    f"I didn't open {target}, Boss, "
                    "so I won't close your existing browser tab."
                ),
                "action": "close",
                "target": target,
            }

        try:

            # Give browser focus
            pyautogui.hotkey("alt", "tab")
            time.sleep(0.3)

            # Close current tab
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.3)

            self.opened_websites.discard(target)

            return {
                "success": True,
                "message": f"Closing the {target} tab.",
                "action": "close",
                "target": target,
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"I couldn't safely close the {target} tab: "
                    f"{error}"
                ),
                "action": "close",
                "target": target,
            }

    def close_target(self, target):

        target = target.strip()

        # Close website opened by Arven
        if target in self.websites:

            return self.close_own_website(target)

        # Close complete browser only when Boss explicitly says browser
        if target in [
            "browser",
            "the browser",
            "default browser",
        ]:

            browser_processes = [
                "brave.exe",
                "chrome.exe",
                "msedge.exe",
                "firefox.exe",
                "opera.exe",
            ]

            closed = False

            for process in browser_processes:

                result = subprocess.run(
                    [
                        "taskkill",
                        "/IM",
                        process,
                        "/F",
                    ],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    closed = True

            return {
                "success": closed,
                "message": (
                    "Closing the browser."
                    if closed
                    else "No supported browser is currently running."
                ),
                "action": "close",
                "target": "browser",
            }

        process_list = self.processes.get(target)

        if process_list:

            closed = False

            for process in process_list:

                result = subprocess.run(
                    [
                        "taskkill",
                        "/IM",
                        process,
                        "/F",
                    ],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    closed = True

            if closed:

                return {
                    "success": True,
                    "message": f"Closing {target}.",
                    "action": "close",
                    "target": target,
                }

            return {
                "success": False,
                "message": f"{target} is not currently running.",
                "action": "close",
                "target": target,
            }

        return {
            "success": False,
            "message": f"I don't know how to close {target}.",
            "action": "close",
            "target": target,
        }

    def execute(self, request):

        text = self.clean_request(request)

        if text.startswith("open "):

            target = text[5:].strip()

            if " and " in target:

                first_target, second_target = target.split(
                    " and ",
                    1
                )

                first = self.open_target(
                    first_target.strip()
                )

                second = self.open_target(
                    second_target.strip()
                )

                return {
                    "success": (
                        first["success"]
                        and second["success"]
                    ),
                    "message": (
                        first["message"]
                        + " "
                        + second["message"]
                    ),
                    "action": "open",
                    "target": target,
                }

            return self.open_target(target)

        if text.startswith("search "):

            return self.search(
                text[7:].strip()
            )

        if text.startswith("close "):

            return self.close_target(
                text[6:].strip()
            )

        return {
            "success": False,
            "message": "I couldn't identify an action.",
            "action": None,
            "target": None,
        }