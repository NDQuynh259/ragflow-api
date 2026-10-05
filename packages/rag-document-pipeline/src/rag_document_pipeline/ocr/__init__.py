"""Image OCR providers.

The ``ImageChunker`` accepts an ``ocr_fn: Callable[[str], str]`` callback that
receives an image source (path or URI) and returns extracted text.  These
providers implement that callback, e.g. with a Gemini multimodal LLM.
"""
