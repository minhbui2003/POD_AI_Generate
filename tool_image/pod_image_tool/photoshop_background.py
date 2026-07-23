import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


class PhotoshopNotFoundError(RuntimeError):
    pass


class PhotoshopRunError(RuntimeError):
    pass


def find_photoshop_exe():
    env_path = os.environ.get("PHOTOSHOP_EXE", "").strip()
    candidates = [env_path] if env_path else []

    if os.name == "nt":
        candidates.extend(_windows_photoshop_candidates())
    else:
        candidates.extend(
            [
                "/Applications/Adobe Photoshop 2026/Adobe Photoshop 2026.app/Contents/MacOS/Adobe Photoshop 2026",
                "/Applications/Adobe Photoshop 2025/Adobe Photoshop 2025.app/Contents/MacOS/Adobe Photoshop 2025",
            ]
        )

    existing = []
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            try:
                existing.append((os.path.getmtime(candidate), candidate))
            except OSError:
                existing.append((0, candidate))

    if not existing:
        return None

    existing.sort(reverse=True)
    return existing[0][1]


def remove_background_with_photoshop(input_path, output_path, timeout_seconds=240):
    photoshop_exe = find_photoshop_exe()
    if not photoshop_exe:
        raise PhotoshopNotFoundError(
            "Adobe Photoshop was not found. Install Photoshop or set PHOTOSHOP_EXE to Photoshop.exe."
        )

    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pod_ps_bg_") as temp_dir:
        script_path = os.path.join(temp_dir, "remove_background.jsx")
        status_path = os.path.join(temp_dir, "status.json")

        with open(script_path, "w", encoding="utf-8") as script_file:
            script_file.write(_build_remove_background_jsx(input_path, output_path, status_path))

        try:
            subprocess.Popen(
                [photoshop_exe, "-r", script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise PhotoshopRunError(f"Could not start Photoshop: {exc}") from exc

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            status = _read_status(status_path)
            if status:
                if status.get("ok") and os.path.exists(output_path):
                    return output_path
                message = status.get("message") or "Photoshop did not return an error message."
                raise PhotoshopRunError(message)

            time.sleep(0.5)

    raise PhotoshopRunError(
        "Photoshop background removal timed out. Photoshop may be waiting for sign-in, a dialog, or scratch disk space."
    )


def _windows_photoshop_candidates():
    candidates = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(env_name)
        if not root:
            continue

        adobe_root = Path(root) / ("Programs/Adobe" if env_name == "LOCALAPPDATA" else "Adobe")
        if not adobe_root.exists():
            continue

        candidates.extend(str(path) for path in adobe_root.glob("Adobe Photoshop */Photoshop.exe"))
        candidates.extend(str(path) for path in adobe_root.glob("*/Photoshop.exe"))

    return candidates


def _read_status(status_path):
    if not os.path.exists(status_path):
        return None

    try:
        with open(status_path, "r", encoding="utf-8") as status_file:
            return json.load(status_file)
    except (OSError, json.JSONDecodeError):
        return None


def _jsx_path(path):
    return os.path.abspath(path).replace("\\", "/")


def _jsx_string(value):
    return json.dumps(value, ensure_ascii=True)


def _build_remove_background_jsx(input_path, output_path, status_path):
    input_js = _jsx_string(_jsx_path(input_path))
    output_js = _jsx_string(_jsx_path(output_path))
    status_js = _jsx_string(_jsx_path(status_path))

    return f"""#target photoshop
app.displayDialogs = DialogModes.NO;

var inputPath = {input_js};
var outputPath = {output_js};
var statusPath = {status_js};

function jsonQuote(value) {{
    return '"' + String(value)
        .replace(/\\\\/g, '\\\\\\\\')
        .replace(/"/g, '\\\\"')
        .replace(/\\r/g, '\\\\r')
        .replace(/\\n/g, '\\\\n') + '"';
}}

function writeStatus(ok, message) {{
    var statusFile = new File(statusPath);
    statusFile.encoding = "UTF8";
    statusFile.open("w");
    statusFile.write('{{"ok":' + (ok ? "true" : "false") + ',"message":' + jsonQuote(message) + '}}');
    statusFile.close();
}}

function revealSelectionAsLayerMask() {{
    var maskDesc = new ActionDescriptor();
    var channelRef = new ActionReference();
    maskDesc.putClass(charIDToTypeID("Nw  "), charIDToTypeID("Chnl"));
    channelRef.putEnumerated(
        charIDToTypeID("Chnl"),
        charIDToTypeID("Chnl"),
        charIDToTypeID("Msk ")
    );
    maskDesc.putReference(charIDToTypeID("At  "), channelRef);
    maskDesc.putEnumerated(charIDToTypeID("Usng"), charIDToTypeID("UsrM"), charIDToTypeID("RvlS"));
    executeAction(charIDToTypeID("Mk  "), maskDesc, DialogModes.NO);
}}

function selectSubject() {{
    var subjectDesc = new ActionDescriptor();
    subjectDesc.putBoolean(stringIDToTypeID("sampleAllLayers"), false);
    executeAction(stringIDToTypeID("autoCutout"), subjectDesc, DialogModes.NO);
}}

function removeBackground() {{
    try {{
        executeAction(stringIDToTypeID("removeBackground"), new ActionDescriptor(), DialogModes.NO);
    }} catch (removeError) {{
        selectSubject();
        revealSelectionAsLayerMask();
    }}
}}

try {{
    var inputFile = new File(inputPath);
    if (!inputFile.exists) {{
        throw new Error("Input image does not exist: " + inputPath);
    }}

    var doc = app.open(inputFile);
    try {{
        if (doc.activeLayer.isBackgroundLayer) {{
            doc.activeLayer.isBackgroundLayer = false;
        }}
    }} catch (layerError) {{}}

    removeBackground();

    var outputFile = new File(outputPath);
    var pngOptions = new PNGSaveOptions();
    pngOptions.compression = 6;
    pngOptions.interlaced = false;
    doc.saveAs(outputFile, pngOptions, true, Extension.LOWERCASE);
    doc.close(SaveOptions.DONOTSAVECHANGES);

    writeStatus(true, outputPath);
}} catch (err) {{
    try {{
        if (app.documents.length > 0) {{
            app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);
        }}
    }} catch (closeErr) {{}}
    writeStatus(false, err.toString());
}}
"""
