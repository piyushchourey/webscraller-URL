"""Gemini-powered content analysis layer."""

import logging
import os
import textwrap

from dotenv import load_dotenv
from google import genai
from google.genai import types

from scraper.models import AnalysisResult

load_dotenv()
logger = logging.getLogger(__name__)

# ── Pre-built analysis templates ─────────────────────────────────────────────
ANALYSIS_TEMPLATES: dict[str, str] = {
    "Summarize": (
        "Provide a concise summary of the following web page content. "
        "Highlight the main topic, key arguments, and conclusions."
    ),
    "Extract Key Facts": (
        "Extract all key facts, statistics, names, dates, and important data points "
        "from the following content. Return them as a bullet-point list."
    ),
    "Sentiment Analysis": (
        "Analyze the sentiment and tone of the following content. "
        "Identify whether it is positive, negative, or neutral, and explain why. "
        "Note any emotional language, bias, or persuasive techniques."
    ),
    "Extract Entities": (
        "Extract all named entities (people, organizations, locations, products, "
        "dates, monetary values) from the following content. "
        "Return them grouped by category."
    ),
    "Action Items / Takeaways": (
        "Identify the main takeaways, recommendations, or action items "
        "from the following content. Present them as a numbered list."
    ),
    "Q&A Format": (
        "Convert the following content into a Q&A format. "
        "Generate the most important questions a reader would have "
        "and answer them based on the content."
    ),
}

# ── Chunking ─────────────────────────────────────────────────────────────────
_MAX_CHARS_PER_CHUNK = 25_000  # ~6k tokens, safe for Gemini context


def _chunk_text(text: str, max_chars: int = _MAX_CHARS_PER_CHUNK) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


# ── Analyzer ─────────────────────────────────────────────────────────────────

class GeminiAnalyzer:
    """Sends scraped content to Gemini and returns structured analysis."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "Gemini API key is required. Set GEMINI_API_KEY in .env or pass it directly."
            )
        self._client = genai.Client(api_key=resolved_key)
        self._model = model

    def analyze(
        self,
        text: str,
        user_prompt: str,
        *,
        source_url: str = "",
        page_title: str = "",
    ) -> AnalysisResult:
        """Analyze *text* using Gemini with the given *user_prompt*."""

        system_instruction = textwrap.dedent("""\
            You are an expert web-content analyst. You will receive the textual
            content extracted from a web page along with an analysis instruction.
            Base your answer ONLY on the provided content — do not fabricate
            information. If the content is insufficient to answer, say so.
            Format your response in clean Markdown.
        """)

        chunks = _chunk_text(text)
        if len(chunks) == 1:
            content_block = f"## Page: {page_title}\n\n{text}"
        else:
            # For multi-chunk: analyze each, then merge
            partial_results: list[str] = []
            for i, chunk in enumerate(chunks, 1):
                partial = self._call_gemini(
                    system_instruction,
                    f"[Chunk {i}/{len(chunks)}]\n\n{chunk}",
                    user_prompt,
                )
                partial_results.append(partial.response_text)

            merge_prompt = (
                "Below are partial analysis results from different chunks of the same web page. "
                "Merge and deduplicate them into one coherent final answer.\n\n"
                + "\n\n---\n\n".join(partial_results)
            )
            return self._call_gemini(
                system_instruction,
                merge_prompt,
                user_prompt,
                source_url=source_url,
            )

        return self._call_gemini(
            system_instruction,
            content_block,
            user_prompt,
            source_url=source_url,
        )

    def _call_gemini(
        self,
        system_instruction: str,
        content: str,
        user_prompt: str,
        *,
        source_url: str = "",
    ) -> AnalysisResult:
        full_prompt = f"{user_prompt}\n\n---\n\nWEB PAGE CONTENT:\n\n{content}"

        response = self._client.models.generate_content(
            model=self._model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )

        tokens_used = 0
        if response.usage_metadata:
            tokens_used = (
                (response.usage_metadata.prompt_token_count or 0)
                + (response.usage_metadata.candidates_token_count or 0)
            )

        return AnalysisResult(
            prompt_used=user_prompt,
            response_text=response.text or "No response generated.",
            model=self._model,
            tokens_used=tokens_used,
            source_url=source_url,
        )