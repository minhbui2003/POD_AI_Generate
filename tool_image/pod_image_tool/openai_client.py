import base64
import json
import os

import requests

from .analysis_prompt import ANALYSIS_INSTRUCTION
from .constants import (
    OPENAI_ANALYSIS_MODEL,
    OPENAI_IMAGE_API_URL,
    OPENAI_MODELS_API_URL,
    OPENAI_RESPONSES_API_URL,
)
from .image_processing import ImageProcessor
from .prompt_builder import build_generation_prompt


class OpenAIImageClient:
    @staticmethod
    def _reference_png_bytes(image_path):
        return ImageProcessor.api_input_png_bytes(image_path)

    @staticmethod
    def _reference_png_base64(image_path):
        return base64.b64encode(OpenAIImageClient._reference_png_bytes(image_path).getvalue()).decode("utf-8")

    @staticmethod
    def _extract_response_text(result):
        if result.get("output_text"):
            return result["output_text"]

        chunks = []
        for item in result.get("output") or []:
            for content in item.get("content") or []:
                text = content.get("text") or content.get("output_text")
                if text:
                    chunks.append(text)
        return "".join(chunks)

    @staticmethod
    def _load_json_response(text):
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(cleaned)

    @staticmethod
    def analyze(api_key, image_path):
        """Analyze a reference image with an OpenAI vision-capable text model."""
        b64 = OpenAIImageClient._reference_png_base64(image_path)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": OPENAI_ANALYSIS_MODEL,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": ANALYSIS_INSTRUCTION,
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64}",
                            "detail": "high",
                        },
                    ],
                }
            ],
            "max_output_tokens": 900,
        }

        response = requests.post(OPENAI_RESPONSES_API_URL, headers=headers, json=body, timeout=120)
        if response.status_code != 200:
            error_msg = response.text
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg = error_data["error"].get("message", response.text)
            except Exception:
                pass
            raise Exception(f"OpenAI Analysis Error ({response.status_code}): {error_msg}")

        text = OpenAIImageClient._extract_response_text(response.json())
        if not text:
            raise Exception("OpenAI did not return analysis text")

        return OpenAIImageClient._load_json_response(text)

    @staticmethod
    def list_model_ids(api_key):
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(OPENAI_MODELS_API_URL, headers=headers, timeout=30)
        if response.status_code != 200:
            error_msg = response.text
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg = error_data["error"].get("message", response.text)
            except Exception:
                pass
            raise Exception(f"OpenAI Models Error ({response.status_code}): {error_msg}")

        return {item.get("id") for item in response.json().get("data", []) if item.get("id")}

    @staticmethod
    def generate(
        api_key,
        image_path,
        prompt,
        negative_prompt,
        model,
        mode,
        output_size,
        quality,
        background_mode,
        guardrail_mode,
    ):
        """Generate/edit an image with OpenAI's Image API using a reference image."""
        url = f"{OPENAI_IMAGE_API_URL}/edits"
        full_prompt = build_generation_prompt(prompt, negative_prompt, mode, background_mode, guardrail_mode)
        image_buffer = OpenAIImageClient._reference_png_bytes(image_path)

        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "model": model,
            "prompt": full_prompt,
            "quality": quality,
            "size": output_size,
        }
        files = [
            (
                "image[]",
                (f"{os.path.splitext(os.path.basename(image_path))[0]}.png", image_buffer, "image/png"),
            )
        ]

        response = requests.post(url, headers=headers, data=data, files=files, timeout=180)
        if response.status_code != 200:
            error_msg = response.text
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg = error_data["error"].get("message", response.text)
            except Exception:
                pass
            raise Exception(f"OpenAI API Error ({response.status_code}): {error_msg}")

        result = response.json()
        data_items = result.get("data") or []
        if not data_items:
            raise Exception("OpenAI did not return an image")

        image_data = data_items[0].get("b64_json")
        if not image_data:
            raise Exception("OpenAI response did not include b64_json image data")

        return base64.b64decode(image_data)
