ANALYSIS_INSTRUCTION = (
    "Analyze this clipart, design, or mockup reference carefully. Return only raw JSON, no markdown and no code block.\n\n"
    "JSON fields:\n"
    '- "image_summary": one concise sentence describing the exact visible subject, composition, and style.\n'
    '- "subject": the main object or design type, named as specifically as possible.\n'
    '- "style": the visual style, finish, illustration/rendering method, and important visible color palette if useful.\n'
    '- "composition": layout, orientation, silhouette, framing, background, and whether it is isolated or in a scene.\n'
    '- "must_keep": 3 to 6 short strings describing what a redesign must preserve.\n'
    '- "redesign_opportunities": 3 to 6 short strings describing safe internal details that can be varied.\n'
    '- "suggested_prompt": one complete English prompt for generating a redesigned asset from this reference image.\n\n'
    "Rules for suggested_prompt:\n"
    "- Preserve the same subject, silhouette, orientation, composition, and core design identity.\n"
    "- Change internal details by about 20-40 percent so the output is visibly new but still in the same product family.\n"
    "- Mention the important style and visible palette only when they are clear from the image.\n"
    "- Ask for sharper details, cleaner edges, refined texture, commercial POD quality, and no watermark or readable text.\n"
    "- For isolated clipart/assets, ask for a clean white background and avoid shadows unless the image clearly needs a mockup scene.\n"
    "- Do not invent human anatomy, unrelated characters, brand names, logos, or text.\n"
    "- If an exact detail is uncertain, describe it conservatively instead of guessing."
)
