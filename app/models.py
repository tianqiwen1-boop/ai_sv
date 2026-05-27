from pydantic import BaseModel, Field


class GenerateMessage(BaseModel):
    taskId: str
    imageUrl: str
    userPrompt: str | None = None
    style: str
    promptTemplate: str | None = None
    modelKey: str | None = None
    createdAt: str | None = None


class CallbackPayload(BaseModel):
    taskId: str
    status: str
    aiImageUrl: str | None = None
    errorMessage: str | None = None
