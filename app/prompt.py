from app.errors import NonRetryableError


BASE_POSITIVE_PROMPT = (
    "Create a clean pixel-art character avatar source image for a perler bead pattern from the reference. "
    "The image must already be bead-ready before any grid is added: chunky square shapes, crisp silhouette, "
    "flat limited colors, readable pixel blocks, cute polished look. Prioritize an attractive stylized result "
    "over exact realism. Preserve only key visible traits: hair color, hair length, hair silhouette, bangs, skin tone, "
    "main clothing colors, and real accessories. Do not change long hair into short hair unless the reference is short-haired. "
    "If real eyeglasses are present, keep simple continuous frames; if absent, "
    "do not add glasses, and do not turn eyeliner or eyelashes into glasses. "
    "Use a square canvas with a plain warm-white background. Compose as a bust portrait: large readable head, "
    "clear neck, shoulders, and upper chest in the lower quarter to third. Prefer front-facing or near-front-facing "
    "for bead readability. No head-only crop, no tiny floating avatar. "
    "Use clean doll-like facial geometry. Face skin: one main flat skin color plus at most one light highlight; "
    "avoid blush by default. No freckles, moles, beauty marks, mottled skin, or scattered peach pixels. "
    "Facial features must survive bead conversion: two separated eyes, each eye wider than the mouth, with dark "
    "upper line, visible light eye area, iris/pupil block, and tiny catchlight. Eyebrows should be short clear "
    "dark pixel lines. Mouth must be visible as a short horizontal 3-5 block muted dark-rose line; never a square "
    "mouth block, never a vertical mouth block, no lipstick, no full lips. Nose should be absent or only 1-2 subtle skin-shade pixels. "
    "Use a dark outer contour around hair, face, neck, and clothing, with only a few internal lines for bangs, "
    "eyes, mouth, collar, and real accessories. Merge strands into chunky hair locks. Clothing should be broad "
    "clean blocks with the reference main color. Make the final source cute, simple, harmonious, and grid-ready."
)

BASE_NEGATIVE_PROMPT = (
    "photorealistic, realistic portrait, exact likeness, smooth painting, airbrush, gradients, anti-aliased edges, "
    "skin texture, freckles, moles, beauty marks, mottled skin, many skin colors, blush, red cheeks, noisy cheek pixels, "
    "paper texture, noisy background, shadows, thin sketch lines, many hair strands, dense eyelashes, tiny pupils, "
    "dot eyes, single-pixel eyes, solid black eyes, broken eye fragments, tiny mouth, pale mouth, square mouth, vertical mouth block, lipstick, red lips, "
    "full lips, filled lips, teeth, nose bridge, realistic nose shading, dark bib, black chest shadow, invented clothing details, "
    "invented glasses, fake eyewear, glasses if absent, text, logo, watermark, grid, mosaic noise, dirty colors, blurry"
)


def build_final_prompt(prompt_template: str | None, user_prompt: str | None) -> str:
    """Build the positive prompt from shared rules, style template, and optional user text."""
    template = (prompt_template or "").strip()
    user = (user_prompt or "").strip()

    if not template:
        raise NonRetryableError("promptTemplate is empty")

    parts = [BASE_POSITIVE_PROMPT, f"Style: {template}"]
    if user:
        parts.append(f"User note: {user}")
    return "\n".join(parts)


def build_negative_prompt(negative_prompt_template: str | None) -> str:
    template = (negative_prompt_template or "").strip()
    if not template:
        return BASE_NEGATIVE_PROMPT
    return f"{BASE_NEGATIVE_PROMPT}, {template}"


def append_negative_prompt(prompt: str, negative_prompt: str | None) -> str:
    negative = (negative_prompt or "").strip()
    if not negative:
        return prompt
    return f"{prompt}\n\nAvoid: {negative}"
