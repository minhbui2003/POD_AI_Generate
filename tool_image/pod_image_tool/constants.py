import os
import sys

from . import config


APP_TITLE = f"POD SOFTWARE - v{config.CURRENT_VERSION}"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_INTERACTIONS_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
OPENAI_IMAGE_API_URL = "https://api.openai.com/v1/images"
OPENAI_RESPONSES_API_URL = "https://api.openai.com/v1/responses"
OPENAI_MODELS_API_URL = "https://api.openai.com/v1/models"

PROVIDER_GEMINI = "Gemini"
PROVIDER_OPENAI = "OpenAI"
DEFAULT_PROVIDER = PROVIDER_GEMINI

GEMINI_MODEL_OPTIONS = {
    "Gemini 3.1 Flash Lite Image": "gemini-3.1-flash-lite-image",
    "Gemini 3.1 Flash Image": "gemini-3.1-flash-image",
    "Gemini 3 Pro Image": "gemini-3-pro-image",
    "Gemini 2.5 Flash Image": "gemini-2.5-flash-image",
}

OPENAI_MODEL_OPTIONS = {
    "GPT Image 2": "gpt-image-2",
    "GPT Image 1.5": "gpt-image-1.5",
    "GPT Image 1": "gpt-image-1",
    "GPT Image 1 Mini": "gpt-image-1-mini",
}

MODEL_OPTIONS_BY_PROVIDER = {
    PROVIDER_GEMINI: GEMINI_MODEL_OPTIONS,
    PROVIDER_OPENAI: OPENAI_MODEL_OPTIONS,
}

ANALYSIS_MODEL = "gemini-2.5-flash"
OPENAI_ANALYSIS_MODEL = "gpt-5.4-mini"

MODE_REDESIGN = "Redesign Asset"
MODE_MOCKUP = "Mockup / Social Creative"
GENERATION_MODES = [MODE_REDESIGN, MODE_MOCKUP]
DEFAULT_GENERATION_MODE = MODE_REDESIGN

BACKGROUND_WHITE = "White"
BACKGROUND_TRANSPARENT = "Transparent"
BACKGROUND_OPTIONS = [BACKGROUND_WHITE, BACKGROUND_TRANSPARENT]
DEFAULT_BACKGROUND_MODE = BACKGROUND_WHITE

GUARDRAIL_POD_ASSET = "POD Asset"
GUARDRAIL_TIKTOK_LISTING = "TikTok Listing"
GUARDRAIL_SOCIAL_CREATIVE = "Social Creative"
GUARDRAIL_OPTIONS = [GUARDRAIL_POD_ASSET, GUARDRAIL_TIKTOK_LISTING, GUARDRAIL_SOCIAL_CREATIVE]
DEFAULT_GUARDRAIL_MODE = GUARDRAIL_POD_ASSET

OUTPUT_PRESETS = {
    "Square 1K": {
        "openai_size": "1024x1024",
        "gemini_aspect_ratio": "1:1",
        "gemini_image_size": "1K",
    },
    "Portrait / TikTok 1K": {
        "openai_size": "1024x1536",
        "gemini_aspect_ratio": "9:16",
        "gemini_image_size": "1K",
    },
    "Landscape 1K": {
        "openai_size": "1536x1024",
        "gemini_aspect_ratio": "16:9",
        "gemini_image_size": "1K",
    },
}
DEFAULT_OUTPUT_PRESET = "Square 1K"

OPENAI_QUALITY_OPTIONS = ["low", "medium", "high", "auto"]
DEFAULT_OPENAI_QUALITY = "medium"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = os.path.join(getattr(sys, "_MEIPASS", app_dir()), "pod_image_tool")
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


SETTINGS_FILE = os.path.join(app_dir(), "clipart_settings.json")
