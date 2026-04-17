import glob
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import config


def _https_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _urlopen(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout, context=_https_context())


def is_frozen():
    return getattr(sys, "frozen", False)


def is_windows():
    return sys.platform == "win32"


def parse_version(version_text):
    try:
        parts = []
        for part in str(version_text).strip().lstrip("vV").split("."):
            digits = []
            for char in part:
                if not char.isdigit():
                    break
                digits.append(char)
            parts.append(int("".join(digits) or 0))

        while len(parts) < 3:
            parts.append(0)

        return tuple(parts[:3])
    except Exception:
        return (0, 0, 0)


def is_valid_sha256(value):
    if not value:
        return False
    value = str(value).strip().lower()
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _parse_update_data(data):
    new_version = data.get("version", "0.0.0")
    release_notes = data.get("release_notes", f"Version {new_version}")

    if "windows" in data and isinstance(data["windows"], dict):
        platform_data = data["windows"]
        download_url = platform_data.get("download_url", "")
        sha256 = str(platform_data.get("sha256", "")).strip().lower()
    elif "download_url" in data:
        download_url = data.get("download_url", "")
        sha256 = str(data.get("sha256", "")).strip().lower()
    else:
        return None

    return new_version, download_url, sha256, release_notes


def check_for_updates(root, on_update_found, force_check_in_dev=False):
    if not is_windows():
        return

    if not is_frozen() and not force_check_in_dev:
        print("Dev mode: skip automatic update check.")
        return

    def dispatch(fn, *args):
        if hasattr(root, "after"):
            root.after(0, fn, *args)
        else:
            fn(*args)

    def _check():
        try:
            cache_buster = f"_={int(time.time())}"
            update_url = (
                f"{config.UPDATE_JSON_URL}&{cache_buster}"
                if "?" in config.UPDATE_JSON_URL
                else f"{config.UPDATE_JSON_URL}?{cache_buster}"
            )
            req = urllib.request.Request(
                update_url,
                headers={
                    "User-Agent": "POD-Image-Updater/1.0",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )

            with _urlopen(req, timeout=15) as response:
                if response.status != 200:
                    return
                data = json.loads(response.read().decode("utf-8"))

            result = _parse_update_data(data)
            if result is None:
                print("Updater: no Windows update data found.")
                return

            new_version, download_url, sha256, release_notes = result
            if parse_version(new_version) <= parse_version(config.CURRENT_VERSION):
                return

            if not download_url:
                print("Updater: missing download_url.")
                return

            if not is_valid_sha256(sha256):
                print("Updater: missing or invalid SHA256.")
                return

            dispatch(on_update_found, new_version, release_notes, download_url, sha256)
        except urllib.error.URLError:
            print("Updater: network unavailable or server did not respond.")
        except json.JSONDecodeError:
            print("Updater: invalid JSON format.")
        except Exception as exc:
            print(f"Updater error: {exc}")

    thread = threading.Thread(target=_check, daemon=True)
    thread.start()


def download_and_install_update(download_url, expected_sha256, progress_callback, success_callback, error_callback):
    if not is_windows():
        error_callback("Cong cu nay chi ho tro cap nhat tu dong tren Windows.")
        return

    def _download():
        temp_download_path = None
        try:
            exe_path = sys.executable
            exe_dir = os.path.dirname(exe_path)
            exe_name = os.path.basename(exe_path)
            temp_dir = os.environ.get("TEMP", exe_dir)

            temp_download_path = os.path.join(temp_dir, f"{exe_name}.download")
            new_exe_path = os.path.join(exe_dir, f"{exe_name}.new")

            for stale_path in (temp_download_path, new_exe_path):
                if os.path.exists(stale_path):
                    os.remove(stale_path)

            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "POD-Image-Updater/1.0"},
            )

            with _urlopen(req, timeout=30) as response:
                total_size_header = response.getheader("Content-Length")
                try:
                    total_size = int(total_size_header.strip()) if total_size_header else 0
                except ValueError:
                    total_size = 0

                downloaded_size = 0
                block_size = 1024 * 128

                with open(temp_download_path, "wb") as file:
                    while True:
                        chunk = response.read(block_size)
                        if not chunk:
                            break
                        file.write(chunk)
                        downloaded_size += len(chunk)

                        if total_size > 0:
                            percent = min(100, int(downloaded_size * 100 / total_size))
                            progress_callback(percent)
                        else:
                            progress_callback(0)

            if not is_valid_sha256(expected_sha256):
                os.remove(temp_download_path)
                error_callback("Thieu ma SHA256 hop le. Viec cap nhat da bi huy.")
                return

            progress_callback(-1)
            sha_hash = hashlib.sha256()
            with open(temp_download_path, "rb") as file:
                for byte_block in iter(lambda: file.read(1024 * 1024), b""):
                    sha_hash.update(byte_block)

            file_hash = sha_hash.hexdigest()
            if file_hash.lower() != expected_sha256.lower():
                os.remove(temp_download_path)
                error_callback("File tai ve bi loi hoac khong dung checksum. Viec cap nhat da bi huy.")
                return

            try:
                shutil.move(temp_download_path, new_exe_path)
            except PermissionError:
                if os.path.exists(temp_download_path):
                    os.remove(temp_download_path)
                error_callback("Khong co quyen ghi file. Hay chay ung dung bang Run as Administrator.")
                return
            except Exception as exc:
                error_callback(f"Loi khi chuan bi file cap nhat: {exc}")
                return

            script_path = _create_windows_update_script(exe_dir, exe_path, exe_name, new_exe_path)
            success_callback(script_path)
        except urllib.error.URLError as exc:
            error_callback(f"Loi ket noi khi tai ban cap nhat: {exc.reason}")
        except Exception as exc:
            if temp_download_path and os.path.exists(temp_download_path):
                try:
                    os.remove(temp_download_path)
                except Exception:
                    pass
            error_callback(f"Co loi he thong khi cap nhat: {exc}")

    thread = threading.Thread(target=_download, daemon=True)
    thread.start()


def cleanup_update_artifacts():
    if not is_frozen() or not is_windows():
        return

    exe_path = sys.executable
    exe_dir = os.path.dirname(exe_path)
    exe_name = os.path.basename(exe_path)
    temp_dir = os.environ.get("TEMP", exe_dir)
    now = time.time()
    max_age_seconds = 60 * 60

    exact_stale_paths = [
        os.path.join(exe_dir, f"{exe_name}.bak"),
        os.path.join(exe_dir, f"{exe_name}.new"),
        os.path.join(exe_dir, "updater.bat"),
        os.path.join(temp_dir, f"{exe_name}.download"),
    ]

    for stale_path in exact_stale_paths:
        try:
            if os.path.exists(stale_path):
                os.remove(stale_path)
        except Exception:
            pass

    safe_suffixes = (".tmp", ".crdownload", ".download")
    safe_prefixes = (exe_name, "updater", "Unconfirmed")

    for folder in {exe_dir, temp_dir}:
        try:
            for file_path in glob.glob(os.path.join(folder, "*")):
                file_name = os.path.basename(file_path)
                lower_name = file_name.lower()
                if not lower_name.endswith(safe_suffixes):
                    continue
                if not file_name.startswith(safe_prefixes):
                    continue
                try:
                    if now - os.path.getmtime(file_path) <= max_age_seconds:
                        os.remove(file_path)
                except Exception:
                    pass
        except Exception:
            pass


def _create_windows_update_script(exe_dir, exe_path, exe_name, new_exe_path):
    bat_path = os.path.join(exe_dir, "updater.bat")
    bak_exe_path = os.path.join(exe_dir, f"{exe_name}.bak")
    pid = os.getpid()

    bat_content = f"""@echo off
setlocal
echo Dang cap nhat POD Image, vui long doi...
set "EXE_PATH={exe_path}"
set "EXE_NAME={exe_name}"
set "NEW_PATH={new_exe_path}"
set "BAK_PATH={bak_exe_path}"

:wait
tasklist /FI "PID eq {pid}" | find "{pid}" >nul 2>&1
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >nul
    goto wait
)

if exist "%BAK_PATH%" del /f /q "%BAK_PATH%"

move /y "%EXE_PATH%" "%BAK_PATH%" >nul
if errorlevel 1 (
    echo Loi khi backup file cu. Dung qua trinh cap nhat.
    exit /b 1
)

move /y "%NEW_PATH%" "%EXE_PATH%" >nul
if errorlevel 1 (
    echo Loi ghi file moi. Dang khoi phuc ban cu...
    move /y "%BAK_PATH%" "%EXE_PATH%" >nul
    exit /b 1
)

set PYINSTALLER_RESET_ENVIRONMENT=1
start "" "%EXE_PATH%"

(goto) 2>nul & del "%~f0"
"""

    with open(bat_path, "w", encoding="utf-8") as file:
        file.write(bat_content)

    return bat_path


def execute_updater_and_exit(script_path):
    script_dir = os.path.dirname(script_path)
    subprocess.Popen(
        ["cmd.exe", "/c", script_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
        cwd=script_dir,
    )
    sys.exit(0)
