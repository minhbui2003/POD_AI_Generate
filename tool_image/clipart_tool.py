"""
Clipart AI Tool - Batch Re-generation with Gemini
Generates new styled versions of clipart images while preserving exact shape.
"""

import os
import io
import json
import base64
import sys
import threading
import time

import requests
import numpy as np
import traceback
from PIL import Image, ImageFilter, ImageEnhance
import customtkinter as ctk
from tkinter import PhotoImage, filedialog, messagebox

import config
import updater

# ============================================================
#  Constants
# ============================================================
APP_TITLE = f"POD SOFTWARE - v{config.CURRENT_VERSION}"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


SETTINGS_FILE = os.path.join(app_dir(), "clipart_settings.json")


MODEL_OPTIONS = {
    "Gemini 2.5 Flash Image": "gemini-2.5-flash-image",
    "Gemini 3.1 Flash Image (Preview)": "gemini-3.1-flash-image-preview",
    "Gemini 3 Pro Image (Preview)": "gemini-3-pro-image-preview",
}

ANALYSIS_MODEL = "gemini-2.5-flash"


# ============================================================
#  Gemini API Client
# ============================================================
class GeminiClient:

    @staticmethod
    def _call_api(api_key, model, parts, response_modalities=None):
        """Make a generateContent API call."""
        url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"
        body = {
            "contents": [{"parts": parts}]
        }
        if response_modalities:
            body["generationConfig"] = {"responseModalities": response_modalities}

        resp = requests.post(url, json=body, timeout=120)
        if resp.status_code != 200:
            error_msg = resp.text
            try:
                error_data = resp.json()
                if "error" in error_data:
                    error_msg = error_data["error"].get("message", resp.text)
            except Exception:
                pass
            raise Exception(f"API Error ({resp.status_code}): {error_msg}")

        return resp.json()

    @staticmethod
    def _get_image_data(image_path):
        """Read image, composite transparent on white, return base64 string + mime type."""
        img = ImageProcessor.load_original(image_path)
        white = ImageProcessor.composite_on_white(img)
        buf = io.BytesIO()
        white.save(buf, format="JPEG", quality=95)
        data = base64.b64encode(buf.getvalue()).decode("utf-8")
        return data, "image/jpeg"

    @staticmethod
    def analyze(api_key, image_path):
        """Analyze a clipart image and return structured info."""
        b64, mime = GeminiClient._get_image_data(image_path)
        parts = [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": (
                "Analyze this clipart image carefully. Return a JSON object "
                "(no markdown, no code block, just raw JSON) with a single field:\n"
                '- "suggested_prompt": A detailed, specific description of ONLY this exact item and its style. '
                'DO NOT specify the exact color. Focus on: object type, shape, pattern details, and artistic style. '
                'Be very explicit about what the object is to avoid confusion (e.g., write "decorative frame" not just "frame", '
                'or "floral wreath" not just "wreath"). Keep the description concise and precise.'
            )}
        ]
        result = GeminiClient._call_api(api_key, ANALYSIS_MODEL, parts)
        text = ""
        for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if "text" in part:
                text += part["text"]

        # Parse JSON from response
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(cleaned)

    @staticmethod
    def generate(api_key, image_path, prompt, negative_prompt, model):
        """Generate a new image based on reference image + prompt."""
        b64, mime = GeminiClient._get_image_data(image_path)
        full_prompt = (
            "Look at this reference clipart image carefully. You must use it as the base for a high-quality, creative enhancement.\n\n"
            "*** CRITICAL INSTRUCTION - DO NOT ADD HUMAN BODY PARTS ***\n"
            "If the reference image contains ONLY isolated parts (hair, clothing, food, objects) WITHOUT a face, head, neck, ears, or body, you MUST NOT generate any of those human anatomical parts. Keep it EXACTLY as an isolated, floating object. DO NOT invent a human body, face, ears, neck, or any human anatomy that wasn't in the original. This is MANDATORY.\n\n"
            "- CRITICAL NO-BLUR RULE: The reference image is low resolution. YOU MUST IGNORE ITS LOW QUALITY! Generate a hyper-sharp, crystal-clear, extreme high-definition 4K illustration. Do NOT reproduce any blurriness or pixelation.\n"
            "- Enhance the details and textures to make it look incredibly high-resolution and professional.\n"
            "- DO NOT add any glossy white highlights, harsh white reflections, or artificial white lighting on the object itself. The lighting must strictly match the object's natural color.\n"
            "- You MUST creatively alter the internal elements, decorations, and micro-structures! Depending on the object, apply these redesign strategies:\n"
            "   * DRINKS/FOOD: Swap straw design, ice cube count, liquid texture, or fruit garnishes.\n"
            "   * HAIR/BEARDS: Shift curl directions, tweak stranded flow, or alter waviness.\n"
            "   * ANIMALS/PEOPLE: Tweak facial expressions, ear positions, or micro-poses (e.g., tail wag, finger curl).\n"
            "   * FLOWERS/PLANTS: Rearrange the layout of petals, add or remove leaves, slightly alter the stem structure, or change the cluster arrangement.\n"
            "   * WREATHS/LACE/FRAMES: Redesign the weaving pattern, alter leaf/flower placements, or change the lace complexity.\n"
            "   * OBJECTS/TOOLS: Alter materials, add engravings, resize handles, or change mechanical sub-parts.\n"
            "   * CLOTHING: Change folding wrinkles, fabric texture, or stitch patterns.\n"
            "- Give it a distinct new flavor! Ensure visible structural variations. DO NOT just blindly upscale the original.\n"
            "- DO NOT radically change the overall hairstyle or silhouette. Keep the general bounding box and theme the same, just with internal variations.\n"
            "- STRICT RULE: The object MUST maintain the exact same orientation and upright posture. NEVER tilt or rotate the object.\n"
            "- MUST output on a PURE, FLAT WHITE (#FFFFFF) solid background.\n"
            "- DO NOT draw any drop shadows, floor shadows, reflections, or glowing auras.\n"
            "- The object must be floating in empty space on the white background.\n"
            "- DO NOT add any extra elements that clutter the canvas unless requested.\n"
            "- Generate at the HIGHEST quality with sharp, crisp details and vibrant, accurate colors.\n"
            "- Ensure clean, well-defined edges on the object with NO fuzzy boundaries against the white background.\n"
            f"\nCreative Design Instruction: {prompt}"
        )

        # Always add human anatomy restrictions to negative prompt for safety
        anatomy_ban = "human face, human body, human head, ears, neck, shoulders, arms, hands, legs, facial features, extra body parts"
        if negative_prompt:
            full_prompt += f"\n\nDo NOT include: {negative_prompt}, {anatomy_ban}"
        else:
            full_prompt += f"\n\nDo NOT include: {anatomy_ban}"

        parts = [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": full_prompt}
        ]
        result = GeminiClient._call_api(api_key, model, parts, ["TEXT", "IMAGE"])

        # Extract generated image
        for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline:
                img_data = inline.get("data")
                if img_data:
                    return base64.b64decode(img_data)

        raise Exception("AI did not return an image")


# ============================================================
#  Image Processor (shape preservation + sharpening)
# ============================================================
class ImageProcessor:

    @staticmethod
    def load_original(image_path):
        """Load original image as RGBA."""
        return Image.open(image_path).convert("RGBA")

    @staticmethod
    def composite_on_white(img):
        """Composite RGBA image on white background (for API input)."""
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        white.paste(img, mask=img.split()[3])
        return white.convert("RGB")

    @staticmethod
    def sharpen(img):
        """Apply print-quality sharpening + color enhancement to RGB channels."""
        from PIL import ImageFilter, ImageEnhance
        r, g, b, a = img.split()
        rgb = Image.merge("RGB", (r, g, b))

        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
        enhancer = ImageEnhance.Color(rgb)
        rgb = enhancer.enhance(1.12)

        r2, g2, b2 = rgb.split()
        return Image.merge("RGBA", (r2, g2, b2, a))

    @staticmethod
    def upscale_for_print(img, min_long_edge):
        """Upscale image to a minimum longest edge for better print quality."""
        if min_long_edge <= 0:
            return img

        width, height = img.size
        longest_edge = max(width, height)
        if longest_edge >= min_long_edge:
            return img

        scale_factor = min_long_edge / longest_edge
        new_width = max(1, int(width * scale_factor))
        new_height = max(1, int(height * scale_factor))
        return img.resize((new_width, new_height), Image.LANCZOS)

    @classmethod
    def full_pipeline(cls, original_path, generated_bytes, canvas_w=2400, canvas_h=2400, target_size=1800, print_enhance=False):
        """Return Gemini output as-is, optionally upscaling for print quality."""
        generated = Image.open(io.BytesIO(generated_bytes)).convert("RGBA")
        if not print_enhance:
            return generated

        min_long_edge = max(canvas_w, canvas_h, target_size)
        generated = cls.upscale_for_print(generated, min_long_edge)
        return cls.sharpen(generated)


# ============================================================
#  Settings Manager
# ============================================================
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ============================================================
#  Main Application
# ============================================================
class UpdateProgressDialog(ctk.CTkToplevel):
    def __init__(self, parent, download_url, sha256):
        super().__init__(parent)
        self.title("Dang cap nhat")
        self.geometry("420x160")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self.status = ctk.CTkLabel(self, text="Dang tai ban cap nhat moi...")
        self.status.pack(fill="x", padx=18, pady=(20, 10))

        self.progress = ctk.CTkProgressBar(self, width=360)
        self.progress.set(0)
        self.progress.pack(padx=18, pady=(0, 12))

        self.close_btn = ctk.CTkButton(self, text="Dang xu ly...", state="disabled")
        self.close_btn.pack(pady=(0, 14))

        updater.download_and_install_update(
            download_url,
            sha256,
            self._thread_progress,
            self._thread_success,
            self._thread_error,
        )

    def _dispatch(self, fn, *args):
        try:
            self.after(0, fn, *args)
        except Exception:
            pass

    def _thread_progress(self, percent):
        self._dispatch(self._on_progress, percent)

    def _thread_success(self, script_path):
        self._dispatch(self._on_success, script_path)

    def _thread_error(self, message):
        self._dispatch(self._on_error, message)

    def _on_progress(self, percent):
        if percent == -1:
            self.progress.set(1)
            self.status.configure(text="Dang kiem tra checksum...")
            return

        self.progress.set(max(0, min(100, percent)) / 100)
        self.status.configure(text=f"Dang tai: {percent}%")

    def _on_success(self, script_path):
        self.progress.set(1)
        self.status.configure(text="Cap nhat san sang. Ung dung se khoi dong lai...")
        self.after(700, lambda: updater.execute_updater_and_exit(script_path))

    def _on_error(self, message):
        self.grab_release()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.progress.set(0)
        self.status.configure(text="Cap nhat that bai.")
        self.close_btn.configure(text="Dong", state="normal", command=self.destroy)
        messagebox.showerror("Cap nhat that bai", message, parent=self)


class ClipartAITool(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self._window_icon_ref = None
        self._set_window_icon()
        
        self.geometry("1280x820")
        self.minsize(1000, 700)

        self.images = []           # list of dicts: {filename, path, size, width, height}
        self.selected_index = -1
        self.is_running = False
        self.should_stop = False
        self.preview_photo_refs = []  # keep references to prevent GC
        self.image_check_vars = {}

        self._create_ui()
        self._load_saved_settings()
        self.after(1200, self._check_for_updates)

    def _set_window_icon(self):
        ico_path = resource_path("Logo.ico")
        if os.path.exists(ico_path):
            try:
                self.wm_iconbitmap(ico_path)
                return
            except Exception:
                pass

        png_path = resource_path("Logo.png")
        if os.path.exists(png_path):
            try:
                self._window_icon_ref = PhotoImage(file=png_path)
                self.iconphoto(True, self._window_icon_ref)
            except Exception:
                pass

    def _check_for_updates(self):
        updater.check_for_updates(self, self._on_update_found)

    def _on_update_found(self, new_version, release_notes, download_url, sha256):
        notes = release_notes or f"Version {new_version}"
        wants_update = messagebox.askyesno(
            "Co ban cap nhat moi",
            (
                f"Ban dang dung v{config.CURRENT_VERSION}.\n"
                f"Ban moi v{new_version} da san sang.\n\n"
                f"{notes}\n\n"
                "Cap nhat ngay bay gio?"
            ),
            parent=self,
        )
        if wants_update:
            UpdateProgressDialog(self, download_url, sha256)

    # ---- UI Construction ----
    def _create_ui(self):
        # Top bar: API + Model
        top = ctk.CTkFrame(self, height=50)
        top.pack(fill="x", padx=10, pady=(10, 5))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="API Key:").pack(side="left", padx=(10, 5))
        self.api_key_var = ctk.StringVar()
        self.api_key_var.trace_add("write", lambda *args: self._update_buttons())
        self.api_key_entry = ctk.CTkEntry(top, textvariable=self.api_key_var, width=300, show="*",
                                           placeholder_text="Paste your Gemini API key here")
        self.api_key_entry.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(top, text="Model:").pack(side="left", padx=(0, 5))
        self.model_var = ctk.StringVar(value=list(MODEL_OPTIONS.keys())[0])
        self.model_menu = ctk.CTkOptionMenu(top, variable=self.model_var,
                                             values=list(MODEL_OPTIONS.keys()), width=260)
        self.model_menu.pack(side="left")

        # Main area: left panel + right panel
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=10, pady=5)

        # Left panel: Folders + Image list
        left = ctk.CTkFrame(main, width=320)
        left.pack(side="left", fill="y", padx=(0, 5))
        left.pack_propagate(False)

        # -- Folder section --
        folder_frame = ctk.CTkFrame(left)
        folder_frame.pack(fill="x", padx=8, pady=(8, 4))

        img_label_frame = ctk.CTkFrame(folder_frame, fg_color="transparent")
        img_label_frame.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(img_label_frame, text="INPUT SOURCES", font=("", 11, "bold"), text_color="gray").pack(side="left")
        ctk.CTkButton(img_label_frame, text="Clear All", width=60, height=20, font=("", 10), fg_color="#8b3a3a", hover_color="#a54545", command=self._clear_images).pack(side="right")

        input_row = ctk.CTkFrame(folder_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=8, pady=2)
        self.input_folder_var = ctk.StringVar()
        ctk.CTkButton(input_row, text="Add Folder...", width=130, fg_color="#444", hover_color="#555", command=self._browse_input).pack(side="left", expand=True, padx=(0, 2))
        ctk.CTkButton(input_row, text="Add Files...", width=130, command=self._browse_files).pack(side="right", expand=True, padx=(2, 0))

        ctk.CTkLabel(folder_frame, text="OUTPUT FOLDER", font=("", 11, "bold"),
                     text_color="gray").pack(anchor="w", padx=8, pady=(6, 2))
        output_row = ctk.CTkFrame(folder_frame, fg_color="transparent")
        output_row.pack(fill="x", padx=8, pady=(2, 6))
        self.output_folder_var = ctk.StringVar()
        ctk.CTkEntry(output_row, textvariable=self.output_folder_var, width=150,
                     placeholder_text="Auto: input/output").pack(side="left", fill="x", expand=True, padx=(0, 4))
        
        ctk.CTkButton(output_row, text="Open", width=45, fg_color="#444", hover_color="#555",
                      command=self._open_output_folder).pack(side="right", padx=(4, 0))
        ctk.CTkButton(output_row, text="Browse", width=60, command=self._browse_output).pack(side="right")

        # -- Image list --
        list_header = ctk.CTkFrame(left, fg_color="transparent")
        list_header.pack(fill="x", padx=16, pady=(8, 2))
        ctk.CTkLabel(list_header, text="IMAGES", font=("", 11, "bold"), text_color="gray").pack(side="left")
        self.remove_selected_btn = ctk.CTkButton(
            list_header,
            text="Remove Checked",
            width=100,
            height=20,
            font=("", 10),
            fg_color="#444",
            hover_color="#555",
            command=self._remove_checked_images,
            state="disabled",
        )
        self.remove_selected_btn.pack(side="right")
        self.image_list_frame = ctk.CTkScrollableFrame(left)
        self.image_list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.image_list_buttons = []

        # -- Analyze button --
        self.analyze_btn = ctk.CTkButton(left, text="Analyze Selected Image",
                                          command=self._analyze_sample, state="disabled")
        self.analyze_btn.pack(fill="x", padx=8, pady=(0, 8))

        # Right panel: Preview + Settings + Actions
        right = ctk.CTkFrame(main)
        right.pack(side="left", fill="both", expand=True)

        # -- Preview area --
        preview_container = ctk.CTkFrame(right)
        preview_container.pack(fill="both", expand=True, padx=8, pady=8)

        preview_labels = ctk.CTkFrame(preview_container, fg_color="transparent")
        preview_labels.pack(fill="x")
        ctk.CTkLabel(preview_labels, text="Original", font=("", 12, "bold"),
                     text_color="gray").pack(side="left", expand=True)
        ctk.CTkLabel(preview_labels, text="Generated", font=("", 12, "bold"),
                     text_color="gray").pack(side="left", expand=True)

        preview_imgs = ctk.CTkFrame(preview_container, fg_color="transparent")
        preview_imgs.pack(fill="both", expand=True, pady=4)

        self.original_preview = ctk.CTkLabel(preview_imgs, text="Select an image\nfrom the list",
                                              fg_color="#2b2b2b", corner_radius=8)
        self.original_preview.pack(side="left", fill="both", expand=True, padx=(0, 4))

        self.generated_preview = ctk.CTkLabel(preview_imgs, text="Click Preview\nto generate",
                                               fg_color="#2b2b2b", corner_radius=8)
        self.generated_preview.pack(side="left", fill="both", expand=True, padx=(4, 0))

        # -- Settings area --
        settings_frame = ctk.CTkFrame(right)
        settings_frame.pack(fill="x", padx=8, pady=(0, 4))

        # Settings Header & Config
        settings_header = ctk.CTkFrame(settings_frame, fg_color="transparent")
        settings_header.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkLabel(settings_header, text="PROMPT & CANVAS", font=("", 11, "bold"),
                     text_color="gray").pack(side="left")
                     
        # Print upscale options (kept in code, currently hidden)
        self.print_options_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        config_row = ctk.CTkFrame(self.print_options_frame, fg_color="transparent")
        config_row.pack(fill="x", padx=8, pady=(2, 4))
        
        ctk.CTkLabel(config_row, text="Canvas W:", font=("", 11)).pack(side="left")
        self.canvas_w_var = ctk.StringVar(value="2400")
        ctk.CTkEntry(config_row, textvariable=self.canvas_w_var, width=50, height=24).pack(side="left", padx=(4, 15))
        
        ctk.CTkLabel(config_row, text="Canvas H:", font=("", 11)).pack(side="left")
        self.canvas_h_var = ctk.StringVar(value="2400")
        ctk.CTkEntry(config_row, textvariable=self.canvas_h_var, width=50, height=24).pack(side="left", padx=(4, 15))
        
        ctk.CTkLabel(config_row, text="Target Size:", font=("", 11)).pack(side="left")
        self.target_size_var = ctk.StringVar(value="1800")
        ctk.CTkEntry(config_row, textvariable=self.target_size_var, width=50, height=24).pack(side="left", padx=(4, 0))

        self.print_enhance_var = ctk.BooleanVar(value=False)
        # ctk.CTkCheckBox(
        #     settings_frame,
        #     text="Upscale for print (recommended)",
        #     variable=self.print_enhance_var,
        #     command=self._toggle_print_options,
        # ).pack(anchor="w", padx=8, pady=(0, 4))

        # Prompt input
        prompt_row = ctk.CTkFrame(settings_frame, fg_color="transparent")
        prompt_row.pack(fill="x", padx=8, pady=(2, 4))
        ctk.CTkLabel(prompt_row, text="Prompt:", font=("", 11)).pack(anchor="w")
        self.prompt_box = ctk.CTkTextbox(
            prompt_row,
            height=84,
            wrap="word",
            font=("", 11),
        )
        self.prompt_box.pack(fill="x", expand=True, pady=(2, 0))
        self.prompt_box.bind("<KeyRelease>", lambda event: self._update_buttons())

        # Negative prompt (hidden by default)
        self.neg_visible = False
        self.neg_toggle_btn = ctk.CTkButton(settings_frame, text="Show advanced settings",
                                             font=("", 11), fg_color="transparent",
                                             hover_color="#333333", text_color="gray",
                                             height=24, command=self._toggle_negative)
        self.neg_toggle_btn.pack(anchor="w", padx=8)

        self.neg_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        self.neg_prompt_var = ctk.StringVar(
            value="blurry, low quality, deformed, ugly, distorted, watermark, text, human face, human body, anatomy, hair, wig, hairstyle, multiple unrelated items, different object"
        )
        ctk.CTkLabel(self.neg_frame, text="Negative prompt:", font=("", 11)).pack(anchor="w")
        ctk.CTkEntry(self.neg_frame, textvariable=self.neg_prompt_var).pack(fill="x", pady=2)
        # neg_frame is hidden by default

        # Action buttons
        action_frame = ctk.CTkFrame(right, fg_color="transparent")
        action_frame.pack(fill="x", padx=8, pady=4)

        self.preview_btn = ctk.CTkButton(action_frame, text="Generate",
                          command=self._run_generate_checked, state="disabled", width=160)
        self.preview_btn.pack(side="left", padx=4)

        self.generate_btn = ctk.CTkButton(action_frame, text="Generate All",
                                           command=self._run_generate_all, state="disabled",
                                           fg_color="#2d8f4e", hover_color="#3aa85f", width=160)
        self.generate_btn.pack(side="left", padx=4)

        self.stop_btn = ctk.CTkButton(action_frame, text="Stop",
                                       command=self._stop, fg_color="#c04040",
                                       hover_color="#d05050", width=80)

        # Bottom: Progress + Log
        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self.progress_var = ctk.DoubleVar(value=0)
        self.progress_bar = ctk.CTkProgressBar(bottom, variable=self.progress_var)
        self.progress_bar.pack(fill="x", padx=8, pady=(8, 2))
        self.progress_bar.set(0)

        self.status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(bottom, textvariable=self.status_var, font=("", 11),
                     text_color="gray").pack(anchor="w", padx=8, pady=(0, 2))

        self.log_box = ctk.CTkTextbox(bottom, height=100, font=("Consolas", 11))
        self.log_box.pack(fill="x", padx=8, pady=(0, 8))
        self.log_box.configure(state="disabled")

    # ---- Settings persistence ----
    def _load_saved_settings(self):
        s = load_settings()
        if s.get("model"):
            self.model_var.set(s["model"])
        if s.get("input_folder"):
            self.input_folder_var.set(s["input_folder"])
            self.after(500, self._scan_folder)
        if s.get("output_folder"):
            self.output_folder_var.set(s["output_folder"])
        if "print_enhance" in s:
            self.print_enhance_var.set(bool(s["print_enhance"]))
        # The print-upscale controls are intentionally hidden.

    def _save_settings(self):
        save_settings({
            "model": self.model_var.get(),
            "input_folder": self.input_folder_var.get(),
            "output_folder": self.output_folder_var.get(),
            "print_enhance": bool(self.print_enhance_var.get()),
        })

    # ---- File browsing / List Management ----
    def _browse_input(self):
        folder = filedialog.askdirectory(title="Add all images from folder")
        if folder:
            self.input_folder_var.set(folder)
            
            # Auto set output folder when input changes
            if not self.output_folder_var.get().strip():
                self.output_folder_var.set(os.path.join(folder, "output"))
            
            self._scan_folder(folder)
            self._save_settings()

    def _browse_files(self):
        files = filedialog.askopenfilenames(title="Select images", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if files:
            folder = os.path.dirname(files[0])
            self.input_folder_var.set(folder)
            
            if not self.output_folder_var.get().strip():
                self.output_folder_var.set(os.path.join(folder, "output"))
                
            self._add_file_paths(files)
            self._save_settings()

    def _clear_images(self):
        if not self.images:
            return
        if messagebox.askyesno("Confirm", "Clear all images from the list?"):
            self.images.clear()
            self.image_check_vars.clear()
            self.selected_index = -1
            self.original_preview.configure(image=None, text="List cleared")
            self.generated_preview.configure(image=None, text="Click Preview\nto generate")
            self.analyze_btn.configure(state="disabled")
            self.remove_selected_btn.configure(state="disabled")
            self._render_image_list()
            self._update_buttons()
            self._update_progress(0, 0)
            self._log("All images cleared.")

    def _remove_checked_images(self):
        checked_images = self._get_selected_images()
        if not checked_images:
            messagebox.showwarning("Warning", "Tick one or more images first.")
            return

        removed_paths = {img["path"] for img in checked_images}
        removed_count = len(checked_images)
        self.images = [img for img in self.images if img["path"] not in removed_paths]

        for p in removed_paths:
            self.image_check_vars.pop(p, None)

        self.selected_index = -1
        self.original_preview.configure(image=None, text="Select an image\nfrom the list")
        self.generated_preview.configure(image=None, text="Click Preview\nto generate")
        self.analyze_btn.configure(state="disabled")
        self.remove_selected_btn.configure(state="disabled")
        self._render_image_list()
        self._update_buttons()
        self._update_progress(0, len(self.images))
        self._log(f"Removed {removed_count} checked image(s)")

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_folder_var.set(folder)

    def _open_output_folder(self):
        folder = self.output_folder_var.get().strip()
        if folder and os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showinfo("Info", "Output folder does not exist yet. Run a preview or batch first.")

    def _scan_folder(self, folder=None):
        if not folder:
            folder = self.input_folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            return

        valid_ext = {".png", ".jpg", ".jpeg", ".webp"}
        paths = []
        for f in sorted(os.listdir(folder)):
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_ext:
                paths.append(os.path.join(folder, f))
        
        self._add_file_paths(paths)

    def _add_file_paths(self, paths):
        existing_paths = {img["path"] for img in self.images}
        added = 0
        
        for fp in paths:
            if fp in existing_paths:
                continue
                
            try:
                size = os.path.getsize(fp)
                if size < 1000:
                    continue  # skip placeholders
                with Image.open(fp) as img:
                    w, h = img.size
                
                f = os.path.basename(fp)
                check_var = ctk.BooleanVar(value=False)
                self.images.append({
                    "filename": f,
                    "name": os.path.splitext(f)[0],
                    "path": fp,
                    "size": size,
                    "width": w,
                    "height": h,
                    "check_var": check_var,
                })
                self.image_check_vars[fp] = check_var
                added += 1
            except Exception:
                continue

        self._render_image_list()
        self._update_buttons()
        self._update_progress(0, len(self.images))
        if added > 0:
            self._log(f"Added {added} new images. Total: {len(self.images)}")

    def _render_image_list(self):
        # Clear existing
        for child in self.image_list_frame.winfo_children():
            child.destroy()
        self.image_list_buttons = []

        for i, img in enumerate(self.images):
            row = ctk.CTkFrame(self.image_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            check_var = img.get("check_var")
            if check_var is None:
                check_var = ctk.BooleanVar(value=False)
                img["check_var"] = check_var
                self.image_check_vars[img["path"]] = check_var

            ctk.CTkCheckBox(row, text="", variable=check_var, width=18, command=self._update_buttons).pack(side="left", padx=(0, 4))

            btn = ctk.CTkButton(
                row,
                text=f"{img['name']}",
                anchor="w",
                height=30,
                font=("", 12),
                fg_color="transparent",
                hover_color="#333333",
                text_color="#cccccc",
                command=lambda idx=i: self._select_image(idx)
            )
            btn.pack(side="left", fill="x", expand=True)
            self.image_list_buttons.append(btn)

    def _select_image(self, idx):
        self.selected_index = idx

        # Highlight selected
        for i, btn in enumerate(self.image_list_buttons):
            if i == idx:
                btn.configure(fg_color="#1f538d")
            else:
                btn.configure(fg_color="transparent")

        # Show original preview
        img_info = self.images[idx]
        self._show_original_preview(img_info["path"])
        self.analyze_btn.configure(state="normal")
        self._update_buttons()

    def _show_original_preview(self, image_path):
        try:
            img = Image.open(image_path).convert("RGBA")
            # Composite on checkered/white background for display
            bg = Image.new("RGBA", img.size, (40, 40, 40, 255))
            bg.paste(img, mask=img.split()[3])
            # Resize for preview
            display_size = self._calc_preview_size(img.size)
            bg = bg.resize(display_size, Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=display_size)
            self.original_preview.configure(image=ctk_img, text="")
            self.preview_photo_refs.append(ctk_img)  # prevent GC
        except Exception as e:
            self.original_preview.configure(image=None, text=f"Error: {e}")

    def _show_generated_preview(self, pil_image):
        try:
            img = pil_image.convert("RGBA")
            bg = Image.new("RGBA", img.size, (40, 40, 40, 255))
            bg.paste(img, mask=img.split()[3])
            display_size = self._calc_preview_size(img.size)
            bg = bg.resize(display_size, Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=display_size)
            self.generated_preview.configure(image=ctk_img, text="")
            self.preview_photo_refs.append(ctk_img)
        except Exception as e:
            self.generated_preview.configure(image=None, text=f"Error: {e}")

    def _calc_preview_size(self, original_size):
        max_w, max_h = 350, 380
        w, h = original_size
        ratio = min(max_w / w, max_h / h)
        return (int(w * ratio), int(h * ratio))

    def _toggle_negative(self):
        self.neg_visible = not self.neg_visible
        if self.neg_visible:
            self.neg_frame.pack(fill="x", padx=8, pady=(0, 6))
            self.neg_toggle_btn.configure(text="Hide advanced settings")
        else:
            self.neg_frame.pack_forget()
            self.neg_toggle_btn.configure(text="Show advanced settings")

    # def _toggle_print_options(self):
    #     if self.print_enhance_var.get():
    #         self.print_options_frame.pack(fill="x", padx=8, pady=(0, 4))
    #     else:
    #         self.print_options_frame.pack_forget()
    #     self._save_settings()

    def _get_prompt_text(self):
        return self.prompt_box.get("1.0", "end").strip()

    def _set_prompt_text(self, value):
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", value)

    # ---- Build prompt ----
    def _build_prompt(self):
        prompt_text = self._get_prompt_text()
        neg = self.neg_prompt_var.get().strip()

        if not prompt_text:
            prompt_text = "clipart item"
            
        prompt = f"{prompt_text}, high quality, isolated on white background"
        return prompt, neg

    def _get_selected_images(self):
        return [img for img in self.images if img.get("check_var") and img["check_var"].get()]

    def _get_generation_images(self):
        return self._get_selected_images()

    # ---- Analyze sample ----
    def _analyze_sample(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("Warning", "Please enter your API key first.")
            return
        if self.selected_index < 0:
            messagebox.showwarning("Warning", "Please select an image first.")
            return

        img_info = self.images[self.selected_index]
        self.analyze_btn.configure(state="disabled", text="Analyzing...")
        self._log(f"Analyzing: {img_info['filename']}...")

        def do_analyze():
            try:
                result = GeminiClient.analyze(api_key, img_info["path"])
                self.after(0, lambda: self._on_analyze_done(result))
            except Exception as e:
                err_ext = traceback.format_exc()
                self.after(0, lambda: self._on_analyze_error(err_ext))

        threading.Thread(target=do_analyze, daemon=True).start()

    def _on_analyze_done(self, result):
        self.analyze_btn.configure(state="normal", text="Analyze Selected Image")

        if result.get("suggested_prompt"):
            self._set_prompt_text(result["suggested_prompt"])

        self._log(f"Suggested Prompt: {result.get('suggested_prompt', '-')}")
        self._save_settings()
        self._update_buttons()

    def _on_analyze_error(self, error):
        self.analyze_btn.configure(state="normal", text="Analyze Selected Image")
        self._log(f"Analysis failed: {error}")
        messagebox.showerror("Analysis Failed", error)

    # ---- Preview ----
    def _run_preview(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("Warning", "Enter API key first.")
            return

        idx = self.selected_index if self.selected_index >= 0 else 0
        img_info = self.images[idx]

        self.preview_btn.configure(state="disabled", text="Generating...")
        self.generated_preview.configure(image=None, text="Generating...\nPlease wait")
        self._log(f"Generating preview for: {img_info['filename']}...")
        self._save_settings()

        model = MODEL_OPTIONS.get(self.model_var.get(), list(MODEL_OPTIONS.values())[0])
        prompt, neg = self._build_prompt()
        self._log(f"Prompt sent: {prompt}")
        if neg:
            self._log(f"Negative prompt: {neg}")

        def do_preview():
            try:
                try:
                    cw = int(self.canvas_w_var.get().strip())
                    ch = int(self.canvas_h_var.get().strip())
                    ts = int(self.target_size_var.get().strip())
                except ValueError:
                    cw, ch, ts = 2400, 2400, 1800

                gen_bytes = GeminiClient.generate(api_key, img_info["path"], prompt, neg, model)
                result_img = ImageProcessor.full_pipeline(
                    img_info["path"],
                    gen_bytes,
                    cw,
                    ch,
                    ts,
                    self.print_enhance_var.get(),
                )
                self.after(0, lambda: self._on_preview_done(result_img, img_info))
            except Exception as e:
                err_ext = traceback.format_exc()
                self.after(0, lambda: self._on_preview_error(err_ext))

        threading.Thread(target=do_preview, daemon=True).start()

    def _on_preview_done(self, result_img, img_info):
        self.preview_btn.configure(state="normal", text="Generate (1 image)")
        self._show_generated_preview(result_img)
        self._log(f"Preview done: {img_info['filename']}")

        # Save preview to output folder automatically
        output_folder = self.output_folder_var.get().strip()
        if not output_folder:
            output_folder = os.path.join(self.input_folder_var.get().strip(), "output")
            self.output_folder_var.set(output_folder)
        
        try:
            os.makedirs(output_folder, exist_ok=True)
            out_path = os.path.join(output_folder, img_info["filename"])
            # Always save with strict 300 DPI metadata
            result_img.save(out_path, "PNG", dpi=(300, 300))
            self._log(f"Saved to: {out_path} (300 DPI)")
        except Exception as e:
            self._log(f"Failed to save preview: {e}")

        # Ask if user wants to generate all
        if messagebox.askyesno("Preview Complete",
                               f"Preview image saved to output folder.\n\n"
                               "Does it look good? Click YES to start generating all other images now, or NO to continue tweaking the prompt."):
            self._run_generate_all()

    def _on_preview_error(self, error):
        self.preview_btn.configure(state="normal", text="Generate")
        self.generated_preview.configure(image=None, text="Generation failed")
        self._log(f"Preview failed: {error}")
        messagebox.showerror("Generation Failed", error)

    def _run_generate_checked(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("Warning", "Enter API key first.")
            return

        batch_images = self._get_generation_images()
        if not batch_images:
            messagebox.showwarning("Warning", "Select one image or tick one or more images first.")
            return

        output_folder = self.output_folder_var.get().strip()
        if not output_folder:
            output_folder = os.path.join(self.input_folder_var.get().strip(), "output")
            self.output_folder_var.set(output_folder)

        if not messagebox.askyesno("Confirm",
                                    f"Generate {len(batch_images)} image(s)?\n\nOutput: {output_folder}"):
            return

        self.is_running = True
        self.should_stop = False
        self._save_settings()
        self._update_buttons()

        model = MODEL_OPTIONS.get(self.model_var.get(), list(MODEL_OPTIONS.values())[0])
        prompt, neg = self._build_prompt()
        self._log(f"Prompt sent: {prompt}")
        if neg:
            self._log(f"Negative prompt: {neg}")

        def do_batch():
            os.makedirs(output_folder, exist_ok=True)
            total = len(batch_images)
            succeeded = 0
            failed = 0

            self.after(0, lambda: self._log(f"Starting batch: {total} images"))
            self.after(0, lambda: self._log(f"Output: {output_folder}"))

            for i, img_info in enumerate(batch_images):
                if self.should_stop:
                    self.after(0, lambda: self._log("Stopped by user"))
                    break

                fname = img_info["filename"]
                self.after(0, lambda f=fname, n=i: self._update_progress(n, total, f))

                try:
                    try:
                        cw = int(self.canvas_w_var.get().strip())
                        ch = int(self.canvas_h_var.get().strip())
                        ts = int(self.target_size_var.get().strip())
                    except ValueError:
                        cw, ch, ts = 2400, 2400, 1800

                    gen_bytes = GeminiClient.generate(api_key, img_info["path"], prompt, neg, model)
                    result_img = ImageProcessor.full_pipeline(
                        img_info["path"],
                        gen_bytes,
                        cw,
                        ch,
                        ts,
                        self.print_enhance_var.get(),
                    )

                    out_path = os.path.join(output_folder, img_info["filename"])
                    result_img.save(out_path, "PNG", dpi=(300, 300))

                    succeeded += 1
                    self.after(0, lambda f=fname, n=i: self._log(f"[{n+1}/{total}] Done: {f}"))
                    self.after(0, lambda r=result_img: self._show_generated_preview(r))

                except Exception as e:
                    error_msg = str(e)
                    failed += 1
                    self.after(0, lambda f=fname, n=i, em=error_msg:
                               self._log(f"[{n+1}/{total}] Error: {f} - {em}"))

                    if "429" in error_msg or "rate" in error_msg.lower():
                        self.after(0, lambda: self._log("Rate limit hit. Waiting 60 seconds..."))
                        if not self._interruptible_sleep(60):
                            self.after(0, lambda: self._log("Stop requested during cooldown."))
                            break
                        continue

                    if "403" in error_msg or "402" in error_msg or "quota" in error_msg.lower():
                        self.after(0, lambda: self._log("API quota exceeded. Stopping."))
                        break

                if i < total - 1 and not self.should_stop:
                    if not self._interruptible_sleep(2):
                        self.after(0, lambda: self._log("Stop requested."))
                        break

            self.after(0, lambda: self._on_batch_done(succeeded, failed, total))

        threading.Thread(target=do_batch, daemon=True).start()

    # ---- Generate All (Batch) ----
    def _run_generate_all(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("Warning", "Enter API key first.")
            return

        output_folder = self.output_folder_var.get().strip()
        if not output_folder:
            output_folder = os.path.join(self.input_folder_var.get().strip(), "output")
            self.output_folder_var.set(output_folder)

        batch_images = self.images
        if not batch_images:
            messagebox.showwarning("Warning", "No images available to generate.")
            return

        if not messagebox.askyesno("Confirm",
                                    f"Generate {len(batch_images)} images?\n\nOutput: {output_folder}"):
            return

        self.is_running = True
        self.should_stop = False
        self._save_settings()
        self._update_buttons()

        model = MODEL_OPTIONS.get(self.model_var.get(), list(MODEL_OPTIONS.values())[0])
        prompt, neg = self._build_prompt()
        self._log(f"Prompt sent: {prompt}")
        if neg:
            self._log(f"Negative prompt: {neg}")

        def do_batch():
            os.makedirs(output_folder, exist_ok=True)
            total = len(batch_images)
            succeeded = 0
            failed = 0

            self.after(0, lambda: self._log(f"Starting batch: {total} images"))
            self.after(0, lambda: self._log(f"Output: {output_folder}"))

            for i, img_info in enumerate(batch_images):
                if self.should_stop:
                    self.after(0, lambda: self._log("Stopped by user"))
                    break

                fname = img_info["filename"]
                self.after(0, lambda f=fname, n=i: self._update_progress(n, total, f))

                try:
                    try:
                        cw = int(self.canvas_w_var.get().strip())
                        ch = int(self.canvas_h_var.get().strip())
                        ts = int(self.target_size_var.get().strip())
                    except ValueError:
                        cw, ch, ts = 2400, 2400, 1800

                    gen_bytes = GeminiClient.generate(api_key, img_info["path"], prompt, neg, model)
                    result_img = ImageProcessor.full_pipeline(
                        img_info["path"],
                        gen_bytes,
                        cw,
                        ch,
                        ts,
                        self.print_enhance_var.get(),
                    )

                    # Save with strict 300 DPI metadata
                    out_path = os.path.join(output_folder, img_info["filename"])
                    result_img.save(out_path, "PNG", dpi=(300, 300))

                    succeeded += 1
                    self.after(0, lambda f=fname, n=i: self._log(f"[{n+1}/{total}] Done: {f}"))

                    # Show latest result in preview
                    self.after(0, lambda r=result_img: self._show_generated_preview(r))

                except Exception as e:
                    error_msg = str(e)
                    failed += 1
                    self.after(0, lambda f=fname, n=i, em=error_msg:
                               self._log(f"[{n+1}/{total}] Error: {f} - {em}"))

                    # Rate limit retry
                    if "429" in error_msg or "rate" in error_msg.lower():
                        self.after(0, lambda: self._log("Rate limit hit. Waiting 60 seconds..."))
                        if not self._interruptible_sleep(60):
                            self.after(0, lambda: self._log("Stop requested during cooldown."))
                            break
                        # Don't count as failed, will be retried implicitly on next run
                        continue

                    # Quota error - stop
                    if "403" in error_msg or "402" in error_msg or "quota" in error_msg.lower():
                        self.after(0, lambda: self._log("API quota exceeded. Stopping."))
                        break

                # Delay between requests
                if i < total - 1 and not self.should_stop:
                    if not self._interruptible_sleep(2):
                        self.after(0, lambda: self._log("Stop requested."))
                        break

            self.after(0, lambda: self._on_batch_done(succeeded, failed, total))

        threading.Thread(target=do_batch, daemon=True).start()

    def _on_batch_done(self, succeeded, failed, total):
        self.is_running = False
        self.should_stop = False
        self.stop_btn.configure(text="Stop", state="normal")
        self._update_progress(total, total, "Complete")
        self._log(f"\nBatch complete: {succeeded} succeeded, {failed} failed out of {total}")
        self._update_buttons()
        messagebox.showinfo("Complete", f"Done!\n\n{succeeded}/{total} images generated successfully.")

    def _stop(self):
        self.should_stop = True
        self.stop_btn.configure(text="Stopping...", state="disabled")
        self._log("Stop requested. Finishing current API request before stopping...")

    def _interruptible_sleep(self, seconds):
        end_time = time.time() + max(0, seconds)
        while time.time() < end_time:
            if self.should_stop:
                return False
            time.sleep(0.1)
        return True

    # ---- UI helpers ----
    def _update_buttons(self):
        has_images = len(self.images) > 0
        has_checked = any(img.get("check_var") and img["check_var"].get() for img in self.images)

        if self.is_running:
            self.preview_btn.pack_forget()
            self.generate_btn.pack_forget()
            self.stop_btn.pack(side="left", padx=4)
        else:
            self.stop_btn.pack_forget()
            self.preview_btn.pack(side="left", padx=4)
            self.generate_btn.pack(side="left", padx=4)

        state_preview = "normal" if (has_checked and not self.is_running) else "disabled"
        state_generate = "normal" if (has_images and not self.is_running) else "disabled"
        self.preview_btn.configure(state=state_preview)
        self.generate_btn.configure(state=state_generate)
        if not has_checked:
            self.remove_selected_btn.configure(state="disabled")
        elif not self.is_running:
            self.remove_selected_btn.configure(state="normal")

    def _update_progress(self, current, total, filename=""):
        pct = current / total if total > 0 else 0
        self.progress_bar.set(pct)
        self.status_var.set(f"Processing: {filename} ({current}/{total})" if filename else "Ready")

    def _log(self, text):
        self.log_box.configure(state="normal")
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{timestamp}] {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


# ============================================================
#  Entry Point
# ============================================================
if __name__ == "__main__":
    updater.cleanup_update_artifacts()
    app = ClipartAITool()
    app.mainloop()
