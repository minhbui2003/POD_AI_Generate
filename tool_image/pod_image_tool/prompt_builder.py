from .constants import (
    BACKGROUND_TRANSPARENT,
    GUARDRAIL_SOCIAL_CREATIVE,
    GUARDRAIL_TIKTOK_LISTING,
    MODE_MOCKUP,
)


ANATOMY_BAN = (
    "human face, human body, human head, ears, neck, shoulders, arms, hands, legs, "
    "facial features, extra body parts"
)


def _background_instruction(background_mode):
    if background_mode == BACKGROUND_TRANSPARENT:
        return (
            "- Place the subject on a pure flat white (#FFFFFF) background so the app can remove the background after generation.\n"
            "- Keep the subject separated from the canvas edges whenever possible, with no floor shadow, glow, gradient, or background texture.\n"
        )

    return (
        "- Use a pure flat white (#FFFFFF) background.\n"
        "- Do not add floor shadows, drop shadows, reflections, glowing auras, gradients, or background texture.\n"
    )


def _guardrail_instruction(guardrail_mode):
    if guardrail_mode == GUARDRAIL_TIKTOK_LISTING:
        return (
            "\nTikTok Shop Listing Guardrail:\n"
            "- Keep the real product/design truthful: do not change its core color, shape, size impression, material, function, or included parts.\n"
            "- Do not invent prices, discounts, badges, claims, logos, QR codes, website links, platform references, endorsements, or brand names.\n"
            "- Do not exaggerate product effects or create a scene that makes the product appear more advanced or different than it is.\n"
            "- If text is not explicitly provided in the user instruction, do not render readable text.\n"
        )

    if guardrail_mode == GUARDRAIL_SOCIAL_CREATIVE:
        return (
            "\nSocial Creative Guardrail:\n"
            "- You may include short text only when the user explicitly provides exact wording; otherwise do not invent text.\n"
            "- Do not invent brand names, logos, prices, discounts, unverifiable claims, QR codes, or website links.\n"
            "- Keep the referenced product/design recognizable and commercially truthful.\n"
        )

    return (
        "\nPOD Asset Guardrail:\n"
        "- Keep the result usable as a clean product design asset; do not add listing claims, prices, badges, logos, QR codes, or unrelated scene text.\n"
    )


def build_generation_prompt(prompt, negative_prompt="", mode=None, background_mode=None, guardrail_mode=None):
    user_prompt = (prompt or "").strip() or "clipart item"
    negative = (negative_prompt or "").strip()
    background = _background_instruction(background_mode)
    guardrail = _guardrail_instruction(guardrail_mode)

    if mode == MODE_MOCKUP:
        full_prompt = (
            "Use the provided reference image as the main visual source for a finished POD mockup or social creative.\n\n"
            "- Preserve the recognizable subject, design language, colors, and key details from the reference.\n"
            "- Create a polished composition suitable for shop listings, ads, thumbnails, product previews, or mockup posts.\n"
            "- If the instruction mentions a product, surface, scene, or format, place the design naturally into that mockup context.\n"
            "- If no product or scene is specified, make the redesigned asset the clear hero subject in a clean social-media layout.\n"
            "- Keep the composition commercially usable: sharp details, clear focal point, tasteful lighting, and no visual clutter.\n"
            "- Do not invent readable text, brand names, watermarks, or logos unless the instruction explicitly asks for them.\n"
            "- If the reference is an isolated object, do not invent human anatomy or unrelated characters.\n"
            f"{background}"
            f"{guardrail}"
            f"\nCreative Design Instruction: {user_prompt}"
        )
    else:
        full_prompt = (
            "Look at this reference clipart image carefully. Use it as the base for a high-quality redesign.\n\n"
            "*** CRITICAL INSTRUCTION - DO NOT ADD HUMAN BODY PARTS ***\n"
            "If the reference image contains only isolated parts or objects without a face, head, neck, ears, or body, "
            "do not generate those human anatomical parts. Keep it as an isolated object.\n\n"
            "- Preserve the same main object, orientation, upright posture, silhouette, theme, and bounding box.\n"
            "- Create visible internal redesign variations instead of only upscaling the original.\n"
            "- Improve details, textures, decorative elements, edges, and overall visual polish.\n"
            "- Generate a sharp, clean, professional image with vibrant and accurate colors.\n"
            f"{background}"
            "- Do not add unrelated objects, watermarks, or readable text.\n"
            "- Keep edges crisp and easy to isolate for POD production.\n"
            f"{guardrail}"
            f"\nCreative Design Instruction: {user_prompt}"
        )

    avoid = f"{negative}, {ANATOMY_BAN}" if negative else ANATOMY_BAN
    return f"{full_prompt}\n\nDo NOT include: {avoid}"
