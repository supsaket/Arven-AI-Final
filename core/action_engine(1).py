import os
import re
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus


class ActionEngine:

    def __init__(self):

        # =====================================================
        # ARVEN ROOT
        # =====================================================

        self.base_dir = Path(__file__).resolve().parent.parent

        # =====================================================
        # NORMAL WINDOWS APPLICATIONS
        #
        # ``self.apps`` maps a spoken/typed alias to an executable or launch
        # target. Values are resolved to a full path (or kept as a bare exe
        # that resolves via PATH) by ``_resolve_executable``.
        # =====================================================

        self.apps = {
            # Editor / terminal
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
            "files": "explorer.exe",
            "files manager": "explorer.exe",
            "file manager": "explorer.exe",
            "cmd": "cmd.exe",
            "command prompt": "cmd.exe",
            "terminal": "wt.exe",
            "powershell": "powershell.exe",

            # Browsers
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "edge": "msedge.exe",
            "microsoft edge": "msedge.exe",
            "firefox": "firefox.exe",
            "mozilla firefox": "firefox.exe",
            "brave": "brave.exe",
            "opera": "opera.exe",

            # Office
            "word": "WINWORD.EXE",
            "microsoft word": "WINWORD.EXE",
            "excel": "EXCEL.EXE",
            "microsoft excel": "EXCEL.EXE",
            "powerpoint": "POWERPNT.EXE",
            "microsoft powerpoint": "POWERPNT.EXE",
            "outlook": "OUTLOOK.EXE",
            "microsoft outlook": "OUTLOOK.EXE",

            # Windows built-ins
            "paint": "mspaint.exe",
            "microsoft paint": "mspaint.exe",
            "snipping tool": "SnippingTool.exe",
            "task manager": "Taskmgr.exe",
            "control panel": "control.exe",
            "settings": "ms-settings:",

            # Dev tools
            "vscode": "Code.exe",
            "visual studio code": "Code.exe",
            "vs code": "Code.exe",
            "notepad++": "notepad++.exe",
        }

        # Explicit full paths for apps that are frequently NOT on %PATH%.
        # Keyed by exe name -> list of likely full paths. Discovery extends this
        # with Start-Menu shortcuts and Program Files lookups.
        self.app_known_locations = {
            "chrome.exe": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "Google\\Chrome\\Application\\chrome.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                             "Google\\Chrome\\Application\\chrome.exe"),
            ],
            "msedge.exe": [
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                             "Microsoft\\Edge\\Application\\msedge.exe"),
            ],
            "firefox.exe": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "Mozilla Firefox\\firefox.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                             "Mozilla Firefox\\firefox.exe"),
            ],
            "brave.exe": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
            ],
            "opera.exe": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "Opera\\launcher.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                             "Opera\\launcher.exe"),
            ],
            "WINWORD.EXE": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "Microsoft Office\\root\\Office16\\WINWORD.EXE"),
            ],
            "EXCEL.EXE": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "Microsoft Office\\root\\Office16\\EXCEL.EXE"),
            ],
            "POWERPNT.EXE": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "Microsoft Office\\root\\Office16\\POWERPNT.EXE"),
            ],
            "OUTLOOK.EXE": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "Microsoft Office\\root\\Office16\\OUTLOOK.EXE"),
            ],
            "Code.exe": [
                os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Users\\" + os.environ.get("USERNAME", "")),
                             "Programs\\Microsoft VS Code\\Code.exe"),
            ],
            "notepad++.exe": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                             "Notepad++\\notepad++.exe"),
            ],
        }

        # =====================================================
        # WINDOWS STORE / UWP APPLICATIONS
        # =====================================================

        self.windows_apps = {
            "instagram":
                "Facebook.InstagramBeta_8xx8rvfyw5nnt!App",

            "whatsapp":
                "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
        }

        # =====================================================
        # WEBSITES
        # =====================================================

        self.websites = {
            "youtube":
                "https://www.youtube.com",

            "google":
                "https://www.google.com",

            "gmail":
                "https://mail.google.com",

            "github":
                "https://github.com",

            "reddit":
                "https://www.reddit.com",

            "netflix":
                "https://www.netflix.com",

            "spotify":
                "https://open.spotify.com",

            "facebook":
                "https://www.facebook.com",

            "twitter":
                "https://x.com",

            "x":
                "https://x.com",

            "discord":
                "https://discord.com/app",

            "chatgpt":
                "https://chatgpt.com",
        }

        # =====================================================
        # NORMAL APP PROCESSES
        # =====================================================

        self.processes = {

            "notepad": [
                "notepad.exe"
            ],

            "calculator": [
                "CalculatorApp.exe",
                "ApplicationFrameHost.exe",
            ],

            "calc": [
                "CalculatorApp.exe",
                "ApplicationFrameHost.exe",
            ],

            "explorer": [
                "explorer.exe"
            ],

            "file explorer": [
                "explorer.exe"
            ],

            "files": [
                "explorer.exe"
            ],

            "files manager": [
                "explorer.exe"
            ],

            "file manager": [
                "explorer.exe"
            ],

            "chrome": [
                "chrome.exe"
            ],

            "google chrome": [
                "chrome.exe"
            ],

            "edge": [
                "msedge.exe"
            ],

            "microsoft edge": [
                "msedge.exe"
            ],

            "firefox": [
                "firefox.exe"
            ],

            "brave": [
                "brave.exe"
            ],

            "opera": [
                "opera.exe"
            ],

            "spotify": [
                "Spotify.exe"
            ],

            "discord": [
                "Discord.exe"
            ],
        }

        # =====================================================
        # BROWSER PROCESSES
        # =====================================================

        self.browser_processes = [
            "brave.exe",
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "opera.exe",
            "opera_gx.exe",
        ]

        # =====================================================
        # WINDOWS APP PROCESS / WINDOW IDENTIFIERS
        # =====================================================

        self.app_window_titles = {

            "instagram": [
                "instagram"
            ],

            "whatsapp": [
                "whatsapp"
            ],
        }

        # =====================================================
        # STATE
        # =====================================================

        self.opened_websites = set()

        self.last_opened_target = None

        # =====================================================
        # ARVEN OUTPUT DIRECTORIES
        # =====================================================

        self.screenshot_folder = (
            self.base_dir / "Screenshots"
        )

        self.output_folder = (
            self.base_dir / "Output"
        )

        self.screenshot_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        self.output_folder.mkdir(
            parents=True,
            exist_ok=True
        )

    # =========================================================
    # RESULT
    # =========================================================

    def result(
        self,
        success,
        message,
        action,
        target=None
    ):

        return {
            "success": success,
            "message": message,
            "action": action,
            "target": (
                str(target)
                if target is not None
                else None
            ),
        }

    # =========================================================
    # CLEAN REQUEST
    # =========================================================

    def clean_request(self, text):

        if text is None:
            return ""

        text = str(text).lower().strip()

        prefixes = [
            "do me a favour,",
            "do me a favor,",
            "please ",
            "can you ",
            "could you ",
            "would you ",
            "hey arven,",
            "hey arven ",
            "arven,",
            "arven ",
        ]

        changed = True

        while changed:

            changed = False

            for prefix in prefixes:

                if text.startswith(prefix):

                    text = (
                        text[len(prefix):]
                        .strip()
                    )

                    changed = True
                    break

        return text

    # =========================================================
    # NORMALIZE PATH
    # =========================================================

    def normalize_path(self, value):
        """Resolve a user-provided path / folder name to an absolute Path.

        Uses core.paths for machine-independent, shell-aware resolution.
        Handles: absolute paths, special folder names, possessive forms
        ('my Desktop'), trailing location phrases ('X on my Desktop'),
        and project-root-relative paths.
        """
        from core.paths import normalize_path as _central_normalize

        value = (
            str(value or "")
            .strip()
            .strip('"')
            .strip("'")
        )

        return _central_normalize(value, base_dir=self.base_dir)

    # =========================================================
    # OPEN WINDOWS STORE / UWP APP
    # =========================================================

    def open_windows_app(self, target):

        app_id = self.windows_apps.get(
            target
        )

        if not app_id:

            return self.result(
                False,
                f"I don't know the Windows app {target}.",
                "open",
                target
            )

        try:

            subprocess.Popen(
                [
                    "explorer.exe",
                    f"shell:AppsFolder\\{app_id}",
                ],
                shell=False
            )

            self.last_opened_target = target

            return self.result(
                True,
                f"Opening {target}.",
                "open",
                target
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't open {target}: {error}",
                "open",
                target
            )

    # =========================================================
    # APP RESOLUTION
    # =========================================================

    def _install_hint(self, api_folder):
        """Best-effort full install path for a Windows Store app.

        Returns the first matching ``<api_folder>\\AppxManifest.xml`` under the
        per-user Appx packages, or None. This lets ARVEN open installed (even
        non-listed) Windows Store apps without hard-coding every app id.
        """
        try:
            local = (
                os.environ.get(
                    "LOCALAPPDATA",
                    os.path.expanduser("~\\AppData\\Local"),
                )
            )
            packages = os.path.join(local, "Packages")
            if not os.path.isdir(packages):
                return None

            folder = os.path.join(packages, api_folder)
            manifest = os.path.join(folder, "AppxManifest.xml")

            if os.path.isfile(manifest):
                return folder

        except Exception:
            pass

        return None

    def _resolve_executable(self, exe):
        """Return a full path for ``exe`` when it can be found, else ``exe``.

        Precedence:
          1. shutil.which (PATH lookup)
          2. known install locations
          3. a genuine file in the working tree

        If nothing resolves, return the bare name so the caller can still
        attempt to launch it and report failure honestly.
        """
        if not exe:
            return None

        # Registry plus Start-Menu is handled separately; here we handle a
        # direct executable name.
        if exe.endswith(":") or "\\" in exe:
            return exe

        try:
            found = shutil.which(exe)
            if found:
                return found
        except Exception:
            pass

        candidates = self.app_known_locations.get(exe, [])
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate

        return exe

    def _resolve_app(self, target):
        """Resolve a spoken app name to a launch command, or None.

        Never invents apps: only returns a command when the executable can be
        located (known map / PATH / Start-Menu shortcut / Appx package), so an
        unknown app fails honestly instead of appearing to open.
        """
        if not target:
            return None

        target_lower = str(target).strip().strip('"').lower()

        # Direct match in the known apps map.
        entry = self.apps.get(target_lower)
        if entry:
            resolved = self._resolve_executable(entry)

            # If the executable could not be located on disk (bare name with no
            # path -> not on PATH / known location), fall through to Start-Menu
            # discovery before giving up.
            if _is_bare_exe(resolved):
                shortcut = self._find_start_menu_shortcut(target_lower)
                if shortcut:
                    return shortcut
                shortcut2 = self._find_start_menu_shortcut(entry)
                if shortcut2:
                    return shortcut2

            return resolved

        # Start-Menu shortcut lookup by display name.
        shortcut = self._find_start_menu_shortcut(target_lower)
        if shortcut:
            return shortcut

        return None

    def _store_api_folder(self, target_lower):
        # Return the package folder for a known UWP app.
        if target_lower in self.windows_apps:
            package = self.windows_apps[target_lower]
            return package.split("!")[0]
        return None

    def _verify_launchable(self, resolved):
        """Return an error string if ``resolved`` cannot really launch, else None.

        A bare executable name is only considered launchable if it resolves via
        PATH (``shutil.which``). A full path must exist on disk. ms-settings:
        style URIs are always launchable. This stops ARVEN from claiming it
        opened an app that Windows never started.
        """
        if not resolved:
            return "I couldn't find that application."
        value = str(resolved)
        if value.endswith(":"):
            return None
        if "\\" in value or "/" in value:
            if os.path.isfile(value):
                return None
            # A protocol URI or shell command (e.g. "shell:AppsFolder").
            if "://" in value or value.startswith("shell:"):
                return None
            return "the application isn't installed at a location I can find."
        # Bare name -> must be on PATH to launch.
        if shutil.which(value):
            return None
        return "I couldn't find that application on this system."

    def _find_start_menu_shortcut(self, target_lower):
        """Look up a Start-Menu .lnk whose display name matches ``target``."""
        start_dirs = [
            os.path.join(
                os.environ.get("APPDATA", ""),
                "Microsoft\\Windows\\Start Menu\\Programs",
            ),
            os.path.join(
                os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
                "Microsoft\\Windows\\Start Menu\\Programs",
            ),
        ]
        needles = _fold_target(target_lower)

        for start_dir in start_dirs:
            if not start_dir or not os.path.isdir(start_dir):
                continue
            for root, _dirs, files in os.walk(start_dir):
                # Don't descend too deep.
                depth = root[len(start_dir):].count(os.sep)
                if depth > 3:
                    continue
                for name in files:
                    if not name.lower().endswith(".lnk"):
                        continue
                    stem = name[:-4].lower()
                    if needles and _stem_matches(stem, needles):
                        return self._resolve_lnk_target(os.path.join(root, name))
        return None

    def _resolve_lnk_target(self, lnk_path):
        """Return the target path of a .lnk, or its path if unresolved."""
        try:
            import win32com.client  # noqa: F401

            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(lnk_path)
            tgt = shortcut.TargetPath
            if tgt and os.path.isfile(tgt):
                return tgt
            return None
        except Exception:
            # No pywin32: try parsing the LNK as raw bytes for a path.
            try:
                with open(lnk_path, "rb") as handle:
                    blob = handle.read()
                text = blob.decode("utf-16-le", errors="ignore")
                for token in re.findall(r"[A-Za-z]:\\[^\x00]+?\.exe", text):
                    if os.path.isfile(token):
                        return token
            except Exception:
                pass
            return None

    # =========================================================
    # OPEN TARGET
    # =========================================================

    def open_target(self, target):
        target = (
            str(target)
            .strip()
            .strip('"')
            .strip("'")
            .lower()
        )

        # -----------------------------------------------------
        # WINDOWS APP
        # -----------------------------------------------------

        if target in self.windows_apps:

            return self.open_windows_app(target)

        # -----------------------------------------------------
        # DEFAULT BROWSER
        # -----------------------------------------------------

        if target in [
            "browser",
            "the browser",
            "default browser",
        ]:

            try:

                webbrowser.open(
                    "https://www.google.com",
                    new=2
                )

                self.last_opened_target = "browser"

                return self.result(
                    True,
                    "Opening your default browser.",
                    "open",
                    "browser"
                )

            except Exception as error:

                return self.result(
                    False,
                    f"I couldn't open the browser: {error}",
                    "open",
                    "browser"
                )

        # -----------------------------------------------------
        # WEBSITE
        # -----------------------------------------------------

        if target in self.websites:

            try:

                webbrowser.open(
                    self.websites[target],
                    new=2
                )

                self.opened_websites.add(target)

                self.last_opened_target = target

                return self.result(
                    True,
                    f"Opening {target}.",
                    "open",
                    target
                )

            except Exception as error:

                return self.result(
                    False,
                    f"I couldn't open {target}: {error}",
                    "open",
                    target
                )

        # -----------------------------------------------------
        # NORMAL WINDOWS APP
        # -----------------------------------------------------

        resolved = self._resolve_app(target)

        if resolved is not None:
            # NEVER pretend an app opened. If the resolved target cannot be
            # located on disk / PATH, report an honest failure instead of a
            # shell-launch that silently does nothing.
            launch_error = self._verify_launchable(resolved)
            if launch_error:
                return self.result(
                    False,
                    f"I couldn't open {target}, Boss. {launch_error}",
                    "open",
                    target
                )

            try:

                if isinstance(resolved, dict) and resolved.get("appx"):
                    return self.open_windows_app(target)

                subprocess.Popen(
                    resolved,
                    shell=True
                )

                self.last_opened_target = target

                return self.result(
                    True,
                    f"Opening {target}.",
                    "open",
                    target
                )

            except Exception as error:

                return self.result(
                    False,
                    f"I couldn't open {target}, Boss. {error}",
                    "open",
                    target
                )

        # -----------------------------------------------------
        # FILE / FOLDER
        # -----------------------------------------------------

        path = self.normalize_path(target)

        try:

            if path.exists():

                os.startfile(str(path))

                self.last_opened_target = target

                return self.result(
                    True,
                    f"Opening {target}.",
                    "open",
                    path
                )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't open {target}: {error}",
                "open",
                target
            )

        return self.result(
            False,
            f"I couldn't find {target}, Boss.",
            "open",
            target
        )

    # =========================================================
    # SEARCH
    # =========================================================

    def search(self, query):

        query = str(query).strip()

        if not query:

            return self.result(
                False,
                "What should I search for?",
                "search"
            )

        try:

            url = (
                "https://www.google.com/search?q="
                + quote_plus(query)
            )

            webbrowser.open(
                url,
                new=2
            )

            return self.result(
                True,
                f"Searching for {query}.",
                "search",
                query
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't perform the search: {error}",
                "search",
                query
            )

    # =========================================================
    # CLOSE WINDOWS APP
    # =========================================================

    def close_windows_app(self, target):

        titles = self.app_window_titles.get(
            target,
            [target]
        )

        title_pattern = "|".join(
            re.escape(title)
            for title in titles
        )

        try:

            # -------------------------------------------------
            # Graceful close
            # -------------------------------------------------

            powershell_script = f"""
$targets = Get-Process |
    Where-Object {{
        $_.MainWindowHandle -ne 0 -and
        $_.MainWindowTitle -and
        $_.MainWindowTitle -match '{title_pattern}'
    }}

$closed = $false

foreach ($p in $targets) {{
    try {{
        if ($p.CloseMainWindow()) {{
            $closed = $true
        }}
    }}
    catch {{}}
}}

if ($closed) {{
    exit 0
}}

exit 1
"""

            close_result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    powershell_script,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            time.sleep(1)

            # -------------------------------------------------
            # Verify
            # -------------------------------------------------

            check_script = f"""
$targets = Get-Process |
    Where-Object {{
        $_.MainWindowHandle -ne 0 -and
        $_.MainWindowTitle -and
        $_.MainWindowTitle -match '{title_pattern}'
    }}

if ($targets) {{
    exit 1
}}

exit 0
"""

            check = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    check_script,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if check.returncode == 0:

                self.last_opened_target = None

                return self.result(
                    True,
                    f"Closing {target}.",
                    "close",
                    target
                )

            # -------------------------------------------------
            # Fallback: AppActivate + ALT+F4
            # -------------------------------------------------

            for title in titles:

                fallback_script = f"""
$wshell = New-Object -ComObject WScript.Shell

if ($wshell.AppActivate('{title}')) {{
    Start-Sleep -Milliseconds 500
    $wshell.SendKeys('%{{F4}}')
    exit 0
}}

exit 1
"""

                fallback = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        fallback_script,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if fallback.returncode == 0:

                    time.sleep(1)

                    self.last_opened_target = None

                    return self.result(
                        True,
                        f"Closing {target}.",
                        "close",
                        target
                    )

            return self.result(
                False,
                f"I couldn't find a running {target} app.",
                "close",
                target
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't close {target}: {error}",
                "close",
                target
            )

    # =========================================================
    # CLOSE BROWSER
    # =========================================================

    def close_browser(self):

        closed = False

        try:

            for process in self.browser_processes:

                result = subprocess.run(
                    [
                        "taskkill",
                        "/IM",
                        process,
                    ],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:

                    closed = True

            self.opened_websites.clear()

            if closed:

                self.last_opened_target = None

                return self.result(
                    True,
                    "Closing the browser.",
                    "close",
                    "browser"
                )

            return self.result(
                False,
                "No supported browser is currently running.",
                "close",
                "browser"
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't close the browser: {error}",
                "close",
                "browser"
            )

    # =========================================================
    # CLOSE NORMAL PROCESS
    # =========================================================

    def close_process_target(self, target):

        process_list = self.processes.get(
            target
        )

        if not process_list:

            return self.result(
                False,
                f"I don't know how to close {target}.",
                "close",
                target
            )

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

            self.last_opened_target = None

            return self.result(
                True,
                f"Closing {target}.",
                "close",
                target
            )

        return self.result(
            False,
            f"{target} is not currently running.",
            "close",
            target
        )

    # =========================================================
    # CLOSE TARGET
    # =========================================================

    def close_target(self, target):

        target = (
            str(target)
            .strip()
            .strip('"')
            .strip("'")
            .lower()
        )

        # -----------------------------------------------------
        # CLOSE IT / THAT / THIS
        # -----------------------------------------------------

        if target in [
            "it",
            "that",
            "this",
        ]:

            if self.last_opened_target:

                target = self.last_opened_target

            else:

                return self.result(
                    False,
                    "I don't have a recent target to close.",
                    "close",
                    target
                )

        # -----------------------------------------------------
        # WINDOWS APP
        # -----------------------------------------------------

        if target in self.windows_apps:

            return self.close_windows_app(target)

        # -----------------------------------------------------
        # BROWSER
        # -----------------------------------------------------

        if target in [
            "browser",
            "the browser",
            "default browser",
        ]:

            return self.close_browser()

        # -----------------------------------------------------
        # WEBSITE
        # -----------------------------------------------------

        if target in self.websites:

            return self.close_browser()

        # -----------------------------------------------------
        # NORMAL APP
        # -----------------------------------------------------

        return self.close_process_target(target)

    # =========================================================
    # CREATE FOLDER
    # =========================================================

    def create_folder(self, folder):

        path = self.normalize_path(folder)

        try:

            path.mkdir(
                parents=True,
                exist_ok=True
            )

            return self.result(
                True,
                f"Created folder {folder}.",
                "create_folder",
                path
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't create {folder}: {error}",
                "create_folder",
                folder
            )

    # =========================================================
    # CREATE FILE
    # =========================================================

    def create_file(self, file_path):

        path = self.normalize_path(file_path)

        try:

            path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            path.touch(
                exist_ok=True
            )

            return self.result(
                True,
                f"Created file {file_path}.",
                "create_file",
                path
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't create {file_path}: {error}",
                "create_file",
                file_path
            )

    # =========================================================
    # RENAME
    # =========================================================

    def rename(self, source, new_name):

        source_path = self.normalize_path(source)

        new_name = (
            str(new_name)
            .strip()
            .strip('"')
            .strip("'")
        )

        if not source_path.exists():

            return self.result(
                False,
                f"I couldn't find {source}.",
                "rename",
                source
            )

        try:

            destination = (
                source_path.parent / new_name
            )

            source_path.rename(destination)

            return self.result(
                True,
                f"Renamed {source} to {new_name}.",
                "rename",
                destination
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't rename {source}: {error}",
                "rename",
                source
            )

    # =========================================================
    # COPY
    # =========================================================

    def copy_item(self, source, destination):

        source_path = self.normalize_path(source)

        destination_path = self.normalize_path(
            destination
        )

        if not source_path.exists():

            return self.result(
                False,
                f"I couldn't find {source}.",
                "copy",
                source
            )

        try:

            destination_path.mkdir(
                parents=True,
                exist_ok=True
            )

            final_path = (
                destination_path / source_path.name
            )

            if source_path.is_dir():

                shutil.copytree(
                    source_path,
                    final_path,
                    dirs_exist_ok=True
                )

            else:

                shutil.copy2(
                    source_path,
                    final_path
                )

            return self.result(
                True,
                f"Copied {source} to {destination}.",
                "copy",
                final_path
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't copy {source}: {error}",
                "copy",
                source
            )

    # =========================================================
    # MOVE
    # =========================================================

    def move_item(self, source, destination):

        source_path = self.normalize_path(source)

        destination_path = self.normalize_path(
            destination
        )

        if not source_path.exists():

            return self.result(
                False,
                f"I couldn't find {source}.",
                "move",
                source
            )

        try:

            destination_path.mkdir(
                parents=True,
                exist_ok=True
            )

            final_path = (
                destination_path / source_path.name
            )

            shutil.move(
                str(source_path),
                str(final_path)
            )

            return self.result(
                True,
                f"Moved {source} to {destination}.",
                "move",
                final_path
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't move {source}: {error}",
                "move",
                source
            )

    # =========================================================
    # AUDIO INTERFACE
    # =========================================================

    def get_volume_interface(self):

        try:

            from pycaw.pycaw import AudioUtilities

            device = AudioUtilities.GetSpeakers()

            if hasattr(device, "EndpointVolume"):
                return device.EndpointVolume

            from pycaw.pycaw import IAudioEndpointVolume
            from comtypes import CLSCTX_ALL

            interface = device.Activate(
                IAudioEndpointVolume._iid_,
                CLSCTX_ALL,
                None
            )

            return interface.QueryInterface(
                IAudioEndpointVolume
            )

        except Exception:

            return None

    # =========================================================
    # GET VOLUME
    # =========================================================

    def get_volume(self):

        volume = self.get_volume_interface()

        if volume is None:

            return None

        try:

            current = (
                volume.GetMasterVolumeLevelScalar()
            )

            return round(current * 100)

        except Exception:

            return None

    # =========================================================
    # SET VOLUME
    # =========================================================

    def set_volume(self, percent):

        try:

            percent = float(percent)

        except (
            TypeError,
            ValueError
        ):

            return self.result(
                False,
                "The volume percentage is invalid.",
                "volume_set",
                "system"
            )

        percent = max(
            0,
            min(100, percent)
        )

        volume = self.get_volume_interface()

        if volume is None:

            return self.result(
                False,
                "I couldn't access the Windows audio system.",
                "volume_set",
                "system"
            )

        try:

            volume.SetMasterVolumeLevelScalar(
                percent / 100.0,
                None
            )

            return self.result(
                True,
                f"Volume set to {int(percent)}%.",
                "volume_set",
                "system"
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't set the volume: {error}",
                "volume_set",
                "system"
            )

    # =========================================================
    # VOLUME UP
    # =========================================================

    def volume_up(self, amount=10):

        current = self.get_volume()

        if current is not None:

            return self.set_volume(
                current + amount
            )

        try:

            import pyautogui

            presses = max(
                1,
                round(amount / 2)
            )

            for _ in range(presses):

                pyautogui.press("volumeup")

            return self.result(
                True,
                "Volume increased.",
                "volume_up",
                "system"
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't increase the volume: {error}",
                "volume_up",
                "system"
            )

    # =========================================================
    # VOLUME DOWN
    # =========================================================

    def volume_down(self, amount=10):

        current = self.get_volume()

        if current is not None:

            return self.set_volume(
                current - amount
            )

        try:

            import pyautogui

            presses = max(
                1,
                round(amount / 2)
            )

            for _ in range(presses):

                pyautogui.press("volumedown")

            return self.result(
                True,
                "Volume decreased.",
                "volume_down",
                "system"
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't decrease the volume: {error}",
                "volume_down",
                "system"
            )

    # =========================================================
    # MUTE
    # =========================================================

    def mute(self):

        try:

            import pyautogui

            pyautogui.press("volumemute")

            return self.result(
                True,
                "System audio muted or unmuted.",
                "mute",
                "system"
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't mute the system audio: {error}",
                "mute",
                "system"
            )

    # =========================================================
    # VOLUME COMMAND PARSER
    # =========================================================

    def handle_volume_command(self, text):

        text = (
            str(text)
            .lower()
            .strip()
        )

        # -----------------------------------------------------
        # TYPO NORMALIZATION
        # -----------------------------------------------------

        text = re.sub(
            r"\bvoulme\b",
            "volume",
            text
        )

        text = re.sub(
            r"\bvolum\b",
            "volume",
            text
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        # -----------------------------------------------------
        # EXACT VOLUME
        # -----------------------------------------------------

        exact_patterns = [

            r"volume\s+(?:up\s+)?to\s+(\d+)",

            r"volume\s+(?:down\s+)?to\s+(\d+)",

            r"volume\s+(\d+)",

            r"set\s+volume\s+to\s+(\d+)",

            r"set\s+the\s+volume\s+to\s+(\d+)",

            r"set\s+audio\s+to\s+(\d+)",

            r"set\s+audio\s+volume\s+to\s+(\d+)",

            r"audio\s+volume\s+to\s+(\d+)",

            r"volume\s+level\s+to\s+(\d+)",

            r"turn\s+volume\s+to\s+(\d+)",

            r"turn\s+the\s+volume\s+to\s+(\d+)",

            r"increase\s+volume\s+to\s+(\d+)",

            r"decrease\s+volume\s+to\s+(\d+)",

            r"raise\s+volume\s+to\s+(\d+)",

            r"lower\s+volume\s+to\s+(\d+)",
        ]

        for pattern in exact_patterns:

            match = re.fullmatch(
                pattern,
                text
            )

            if match:

                value = int(
                    match.group(1)
                )

                return self.set_volume(value)

        # -----------------------------------------------------
        # VOLUME UP
        # -----------------------------------------------------

        up_patterns = [

            r"volume\s+up",

            r"turn\s+volume\s+up",

            r"turn\s+the\s+volume\s+up",

            r"increase\s+volume",

            r"raise\s+volume",

            r"louder",

            r"make\s+it\s+louder",
        ]

        for pattern in up_patterns:

            if re.fullmatch(
                pattern,
                text
            ):

                return self.volume_up()

        # -----------------------------------------------------
        # VOLUME DOWN
        # -----------------------------------------------------

        down_patterns = [

            r"volume\s+down",

            r"turn\s+volume\s+down",

            r"turn\s+the\s+volume\s+down",

            r"decrease\s+volume",

            r"lower\s+volume",

            r"quieter",

            r"make\s+it\s+quieter",
        ]

        for pattern in down_patterns:

            if re.fullmatch(
                pattern,
                text
            ):

                return self.volume_down()

        return None

    # =========================================================
    # SAFE SCREENSHOT
    # =========================================================

    def screenshot(self):

        try:

            self.screenshot_folder.mkdir(
                parents=True,
                exist_ok=True
            )

            timestamp = time.strftime(
                "%Y%m%d_%H%M%S"
            )

            path = (
                self.screenshot_folder
                / f"screenshot_{timestamp}.png"
            )

            escaped_path = (
                str(path)
                .replace(
                    "'",
                    "''"
                )
            )

            powershell_script = f"""
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen

$bitmap = New-Object System.Drawing.Bitmap(
    $bounds.Width,
    $bounds.Height
)

$graphics = [System.Drawing.Graphics]::FromImage(
    $bitmap
)

$graphics.CopyFromScreen(
    $bounds.Left,
    $bounds.Top,
    0,
    0,
    $bitmap.Size
)

$bitmap.Save(
    '{escaped_path}',
    [System.Drawing.Imaging.ImageFormat]::Png
)

$graphics.Dispose()
$bitmap.Dispose()
"""

            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    powershell_script,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if (
                result.returncode != 0
                or not path.exists()
            ):

                error_text = (
                    result.stderr.strip()
                    or
                    "Windows screenshot backend failed."
                )

                return self.result(
                    False,
                    f"I couldn't take a screenshot: {error_text}",
                    "screenshot"
                )

            return self.result(
                True,
                f"Screenshot saved to {path}.",
                "screenshot",
                path
            )

        except subprocess.TimeoutExpired:

            return self.result(
                False,
                "The screenshot operation timed out.",
                "screenshot"
            )

        except Exception as error:

            return self.result(
                False,
                f"I couldn't take a screenshot: {error}",
                "screenshot"
            )

    # =========================================================
    # EXECUTE
    # =========================================================

    def execute(self, request):

        text = self.clean_request(request)

        # =====================================================
        # VOLUME
        # =====================================================

        volume_result = (
            self.handle_volume_command(text)
        )

        if volume_result is not None:

            return volume_result

        # =====================================================
        # MUTE
        # =====================================================

        if text in [
            "mute",
            "unmute",
            "mute audio",
            "unmute audio",
            "mute system",
            "unmute system",
        ]:

            return self.mute()

        # =====================================================
        # SCREENSHOT
        # =====================================================

        if text in [

            "screenshot",

            "take screenshot",

            "take a screenshot",

            "take screen shot",

            "take a screen shot",

            "capture screenshot",

            "capture screen",

            "capture the screen",
        ]:

            return self.screenshot()

        # =====================================================
        # OPEN
        # =====================================================

        if text.startswith("open "):

            target = text[5:].strip()

            if " and " in target:

                first_target, second_target = (
                    target.split(
                        " and ",
                        1
                    )
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

        # =====================================================
        # CLOSE
        # =====================================================

        if text.startswith("close "):

            target = text[6:].strip()

            return self.close_target(target)

        # =====================================================
        # SEARCH
        # =====================================================

        if text.startswith("search "):

            return self.search(
                text[7:].strip()
            )

        # =====================================================
        # CREATE FOLDER
        # =====================================================

        if text.startswith("create folder "):

            return self.create_folder(
                text[14:].strip()
            )

        # =====================================================
        # CREATE FILE
        # =====================================================

        if text.startswith("create file "):

            return self.create_file(
                text[12:].strip()
            )

        # =====================================================
        # RENAME
        # =====================================================

        rename_match = re.fullmatch(
            r"rename\s+(.+?)\s+to\s+(.+)",
            text
        )

        if rename_match:

            return self.rename(
                rename_match.group(1).strip(),
                rename_match.group(2).strip()
            )

        # =====================================================
        # COPY
        # =====================================================

        copy_match = re.fullmatch(
            r"copy\s+(.+?)\s+to\s+(.+)",
            text
        )

        if copy_match:

            return self.copy_item(
                copy_match.group(1).strip(),
                copy_match.group(2).strip()
            )

        # =====================================================
        # MOVE
        # =====================================================

        move_match = re.fullmatch(
            r"move\s+(.+?)\s+to\s+(.+)",
            text
        )

        if move_match:

            return self.move_item(
                move_match.group(1).strip(),
                move_match.group(2).strip()
            )

        # =====================================================
        # UNKNOWN
        # =====================================================

        return self.result(
            False,
            "I couldn't identify an action.",
            None
        )


# =================================================================
# MODULE-LEVEL HELPERS
# =================================================================


def _find_exe_recursive(root, exe_name, max_depth=6):
    """Return the first path to ``exe_name`` under ``root`` (depth-limited)."""
    exe_name = exe_name.lower()
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth > max_depth:
                dirnames[:] = []
                continue
            if not dirnames:
                continue
            # Prune deep, low-value directories.
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in ("node_modules", "servicing", "winsxs",
                                     "assembly", "installer", ".git")
            ]
            for name in filenames:
                if name.lower() == exe_name:
                    candidate = os.path.join(dirpath, name)
                    if os.path.isfile(candidate):
                        return candidate
            # Don't recurse into every subfolder indefinitely.
            if depth >= max_depth:
                dirnames[:] = []
    except Exception:
        pass
    return None


def _fold_target(target):
    """Return a set of normalized keyword tokens for a target name."""
    tokens = set()
    for word in re.findall(r"[a-z0-9]+", target.lower()):
        tokens.add(word)
    return tokens


def _is_bare_exe(value):
    """True if a resolved value is a bare executable name (not a full path)."""
    if not value:
        return False
    value = str(value)
    if value.endswith(":"):
        return False
    return (
        os.sep not in value
        and (os.altsep is None or os.altsep not in value)
        and value.lower().endswith(".exe")
    )


def _stem_matches(stem, needles):
    """True if the .lnk stem (display name) matches the target keywords."""
    if not needles:
        return False
    stem_tokens = set(re.findall(r"[a-z0-9]+", stem))
    if not stem_tokens:
        return False
    special = {
        "microsoft edge": {"edge", "microsoft"},
        "google chrome": {"chrome", "google"},
    }
    for key, required in special.items():
        key_tokens = set(key.split())
        if key_tokens.issubset(needles) and key_tokens.issubset(stem_tokens):
            return True
    return needles.issubset(stem_tokens)