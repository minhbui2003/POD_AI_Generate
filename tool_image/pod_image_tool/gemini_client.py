import base64
import io
import json

import requests

from .analysis_prompt import ANALYSIS_INSTRUCTION
from .constants import ANALYSIS_MODEL, GEMINI_API_URL, GEMINI_INTERACTIONS_API_URL
from .image_processing import ImageProcessor
from .prompt_builder import build_generation_prompt


class GeminiClient:
    @staticmethod
    def _call_api(api_key, model, parts, response_modalities=None):
        """Make a generateContent API call."""
        url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"
        body = {"contents": [{"parts": parts}]}
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
    def _call_interactions_api(api_key, body):
        """Make an Interactions API call for Gemini native image models."""
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        resp = requests.post(GEMINI_INTERACTIONS_API_URL, headers=headers, json=body, timeout=180)
        if resp.status_code != 200:
            error_msg = resp.text
            try:
                error_data = resp.json()
                if "error" in error_data:
                    error_msg = error_data["error"].get("message", resp.text)
            except Exception:
                pass
            raise Exception(f"Gemini API Error ({resp.status_code}): {error_msg}")

        return resp.json()

    @staticmethod
    def _get_image_data(image_path):
        """Read image, composite transparent pixels on white, and return base64 data."""
        img = ImageProcessor.load_original(image_path)
        white = ImageProcessor.composite_on_white(img)
        buf = io.BytesIO()
        white.save(buf, format="JPEG", quality=95)
        data = base64.b64encode(buf.getvalue()).decode("utf-8")
        return data, "image/jpeg"

    @staticmethod
    def _get_png_image_data(image_path):
        """Read image as PNG and return base64 data for image editing."""
        buf = ImageProcessor.api_input_png_bytes(image_path)
        data = base64.b64encode(buf.getvalue()).decode("utf-8")
        return data, "image/png"

    @staticmethod
    def _extract_interaction_image_data(value):
        if isinstance(value, dict):
            for key in ("output_image", "outputImage"):
                output_image = value.get(key)
                if isinstance(output_image, dict) and output_image.get("data"):
                    yield output_image["data"]

            if value.get("type") == "image" and value.get("data"):
                yield value["data"]

            inline = value.get("inlineData") or value.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                yield inline["data"]

            for child in value.values():
                yield from GeminiClient._extract_interaction_image_data(child)
        elif isinstance(value, list):
            for item in value:
                yield from GeminiClient._extract_interaction_image_data(item)

    @staticmethod
    def analyze(api_key, image_path):
        """Analyze a clipart image and return structured info."""
        b64, mime = GeminiClient._get_image_data(image_path)
        parts = [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": ANALYSIS_INSTRUCTION},
        ]
        result = GeminiClient._call_api(api_key, ANALYSIS_MODEL, parts)
        text = ""
        for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if "text" in part:
                text += part["text"]

        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(cleaned)

    @staticmethod
    def generate(api_key, image_path, prompt, negative_prompt, model, mode, output_config, background_mode, guardrail_mode):
        """Generate a new image based on a reference image and prompt."""
        b64, mime = GeminiClient._get_png_image_data(image_path)
        full_prompt = build_generation_prompt(prompt, negative_prompt, mode, background_mode, guardrail_mode)
        response_format = {
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": output_config.get("gemini_aspect_ratio", "1:1"),
            "image_size": output_config.get("gemini_image_size", "1K"),
        }
        body = {
            "model": model,
            "input": [
                {"type": "text", "text": full_prompt},
                {"type": "image", "mime_type": mime, "data": b64},
            ],
            "response_format": response_format,
        }
        result = GeminiClient._call_interactions_api(api_key, body)

        for img_data in GeminiClient._extract_interaction_image_data(result):
            if img_data:
                return base64.b64decode(img_data)

        raise Exception("AI did not return an image")
