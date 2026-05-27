from app.errors import NonRetryableError


def build_final_prompt(prompt_template: str | None, user_prompt: str | None) -> str:
    """拼接 promptTemplate 与 userPrompt（空格连接）。"""
    template = (prompt_template or "").strip()
    user = (user_prompt or "").strip()

    if not template:
        raise NonRetryableError("promptTemplate 为空，无法生成")

    if not user:
        return template
    return f"{template} {user}"
