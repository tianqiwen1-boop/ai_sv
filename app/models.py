from pydantic import BaseModel


class GenerateMessage(BaseModel):
    taskId: str
    imageUrl: str
    userPrompt: str | None = None
    style: str
    promptTemplate: str | None = None
    negativePromptTemplate: str | None = None
    modelKey: str | None = None
    sizeMode: str | None = None
    gridMin: int | None = None
    gridMax: int | None = None
    candidateGrids: list[int] | None = None
    brand: str | None = None
    colorCount: int | None = None
    mirror: bool | None = None
    createdAt: str | None = None


class CallbackPayload(BaseModel):
    taskId: str
    status: str
    aiImageUrl: str | None = None
    aiImageKey: str | None = None
    rawAiImageUrl: str | None = None
    rawAiImageKey: str | None = None
    sizeMode: str | None = None
    gridMin: int | None = None
    gridMax: int | None = None
    detectedGridWidth: int | None = None
    detectedGridHeight: int | None = None
    finalGridWidth: int | None = None
    finalGridHeight: int | None = None
    perfectPixelStatus: str | None = None
    perfectPixelError: str | None = None
    errorMessage: str | None = None
