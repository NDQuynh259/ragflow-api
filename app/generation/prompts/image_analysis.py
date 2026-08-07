"""Image analysis prompt templates (future implementation)."""
class ImageAnalysisPrompt:
    """Prompt templates for multimodal image analysis."""
    SYSTEM = "You are an expert image analyst. Describe images accurately and thoroughly."

    @classmethod
    def build(cls, instruction: str = "") -> str:
        return f"{cls.SYSTEM}\n\n{instruction}" if instruction else cls.SYSTEM
