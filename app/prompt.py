from app.errors import NonRetryableError


def build_final_prompt(prompt_template: str | None, user_prompt: str | None) -> str:
    """Build the positive prompt from the style template and optional user text."""
    template = (prompt_template or "").strip()
    user = (user_prompt or "").strip()

    if not template:
        raise NonRetryableError("promptTemplate 为空，无法生成")

    if not user:
        return template
    return f"{template} {user}"


def build_negative_prompt(negative_prompt_template: str | None) -> str:
    return (negative_prompt_template or "").strip()


def append_negative_prompt(prompt: str, negative_prompt: str | None) -> str:
    negative = (negative_prompt or "").strip()
    if not negative:
        return prompt
    return f"{prompt}\n\n请避免：{negative}"
