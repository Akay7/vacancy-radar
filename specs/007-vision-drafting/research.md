# Phase 0 Research: Vision-Based Image Drafting

## 1. How Claude receives an image alongside structured JSON output

**Decision**: Send the image as a `type: "image"` content block (base64-encoded, alongside a
`type: "text"` block carrying the prompt) in the same `messages.create()` call that already
uses `output_config: {"format": {"type": "json_schema", ...}}` for `analyze()` and the
existing text-only `draft_vacancy_metadata()`. Vision input and `output_config.format` are
independent features of the same Messages API endpoint — nothing in Anthropic's documentation
treats them as mutually exclusive (only *citations* + `output_config.format` are documented as
incompatible, and this feature doesn't use citations). Verified against the bundled
`claude-api` skill's Python reference (`Vision (Images)` + `Structured Outputs` sections):

```python
image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
response = self._client.messages.create(
    model=self.model,
    max_tokens=1024,
    output_config={
        "format": {"type": "json_schema", "schema": DRAFT_METADATA_JSON_SCHEMA}
    },
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,  # "image/png" | "image/jpeg"
                    "data": image_b64,
                },
            },
            {"type": "text", "text": prompt},
        ],
    }],
)
text = next(block.text for block in response.content if block.type == "text")
```

This is a straightforward extension of the pattern `ClaudeProvider` already uses for
`analyze()` and the existing `draft_vacancy_metadata()` — same `output_config.format`, same
`DRAFT_METADATA_JSON_SCHEMA`, only the `messages[0].content` shape changes from a plain string
to a list of content blocks.

**Alternatives considered**: Anthropic's Files API (`client.beta.files.upload` + a
`{"type": "image", "source": {"type": "file", "file_id": ...}}` reference) — rejected as
unnecessary complexity for a single one-shot request per upload; base64 inline is simpler and
this feature only ever sends one image once, never re-references it across requests.

## 2. Removing local OCR entirely (superseding the original "OCR as hint/fallback" design)

**Decision (revised)**: Per explicit direction, local OCR (`pytesseract` + the `Pillow`
dependency it needs) is removed from the project entirely — not kept as a hint alongside the
image, and not kept as a fallback path. `documents.extract_text()` returns `""` immediately for
image extensions rather than attempting extraction:

```python
def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in IMAGE_EXTENSIONS:
        return ""  # No local OCR — vision-capable LLMs read image bytes directly (llm/).
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return ""
```

**Rationale for the reversal**: the original plan (see git history of this file) sent OCR'd
text alongside the image as a "hint" specifically so a non-vision model would still get
*something* to work with, framing that as a soft fallback. Explicit direction overrode this:
if a configured model/backend can't actually read the image, the maintainer should be told
that plainly rather than shown a result that came from a degraded, silent, and now-removed
OCR step. This trades "always produce *some* draft" for "always be honest about whether
drafting actually worked" — consistent with FR-002's requirement for a specific message rather
than an unexplained empty/inaccurate draft.

**Consequence for `ingest.py`** (verified by reading the file — **no code change needed
there**): `_read_source_document()` already routes `.png`/`.jpg`/`.jpeg` files through
`documents.extract_text()` (via `NON_TEXT_SOURCE_EXTENSIONS`, unchanged) rather than a raw
`.read_text()` call. With OCR removed, that call now simply returns `""` for image source
files instead of OCR'd text — `chunk_vacancy_folder()` already handles an empty `"document"`
value gracefully (it embeds an empty string, which is a wasted-but-harmless Chroma entry, not a
crash), exactly as it already does for any unreadable/empty document today. The vacancy's own
`vacancy.yaml` chunk (company/position/date/outcome) is unaffected and remains fully
discoverable — only the image file's own content stops being separately searchable. This is
documented as an accepted side effect in spec.md's Edge Cases / Assumptions, not something this
feature compensates for (doing so would require calling an LLM from the offline CLI ingestion
path — a new coupling explicitly out of scope).

## 3. Failure handling: no text-based fallback, just a clear, specific message

**Decision (revised)**: Because there is no OCR text for images anymore, there is nothing
meaningful to "fall back" to internally. `draft_vacancy_metadata()` on both providers, when
given `image_bytes`, attempts the vision request and — on any failure (backend error,
malformed/non-JSON response, no vision support) — raises `LLMProviderError` directly, exactly
as the existing text-only path already does for its own failures. No second internal request
is attempted. The *only* new behavior is in `api.py`: since it already knows whether the
upload was an image (it's the one that read the image bytes), it can render a distinctly
worded, specific message for an image-drafting failure ("Your configured LLM backend couldn't
read this image directly — image-based drafting isn't available with the current setup. Fill
in every field manually below, or switch to a vision-capable model.") instead of the existing
generic "Automatic drafting didn't work" message used for non-image failures — satisfying
FR-002 without needing the provider layer to distinguish *why* it failed.

**Alternatives considered**: A capability-detection call (Models API, model-name string
matching) to decide up front whether the configured model supports vision, so the maintainer
never even attempts an upload that can't work — rejected per spec.md's Assumptions: it would
require special-casing model names/providers (tension with Constitution III) and still needs
the same failure-path messaging for the harder case (backend error mid-attempt), so it adds
complexity without removing the need for FR-002's message.

## 4. Sending an image to Ollama's `/api/chat`

**Decision**: Extend `OllamaProvider._chat()` to accept an optional `images: list[str] | None`
parameter, included in the request JSON body only when provided:

```python
payload = {
    "model": self.model,
    "messages": [{"role": "user", "content": prompt, "images": images or []}],
    "stream": False,
    "format": "json",
}
```

Ollama's `/api/chat` endpoint has long accepted a per-message `images` field (a list of
base64-encoded image strings) for multimodal-capable models (e.g. `llava`, `qwen2.5vl`,
`llama3.2-vision`) — this is a stable, long-standing part of Ollama's own REST API, not the
Anthropic API the `claude-api` skill's "API drift" warnings apply to, so it isn't re-verified
against live docs here. Since OCR is no longer a fallback, a non-vision Ollama model that
either ignores the field or errors on it is treated identically: any failure surfaces as
`LLMProviderError`, which `api.py` turns into the same specific "this backend can't read
images" message described in #3.

**Alternatives considered**: A stricter typed image-input object shared across providers —
rejected as unnecessary; two plain `bytes`/`str` parameters are enough for a single image, one
per upload — each provider owns its own wire encoding behind the identical method signature,
matching how `analyze()` already differs internally today (Constitution III).

## 5. Dependency removal: `pytesseract` + `Pillow` + `tesseract-ocr`

**Decision**: Remove `pytesseract>=0.3` and `Pillow>=10.0` from `pyproject.toml`'s
`[project].dependencies`, and remove the `apt-get install tesseract-ocr` step from the
`Dockerfile`. Neither package is used anywhere else in the codebase (confirmed: `Pillow`/`PIL`
was added in 006 specifically for `pytesseract`'s `Image.open()` call in the now-deleted
`_extract_image()`; nothing else in `src/vacancy_radar/` imports `PIL`). `reportlab` (a
**dev-only** test dependency used to synthesize PDF fixtures) is unrelated and unaffected.

**Alternatives considered**: Keeping the dependencies installed but simply unused — rejected;
Constitution IV requires new dependencies (and by extension, no-longer-needed ones) to justify
their presence, and an unused system package (`tesseract-ocr`) in the Docker image is pure
waste (image size, install time) once nothing calls it.

## 6. `api.py`: attempting drafting for images without calling `extract_text()` at all

**Decision**: Since `documents.extract_text()` now always returns `""` for image extensions
(per #2), `ingest_draft()` skips calling it for images entirely and passes `document_text=""`
directly to `draft_vacancy_metadata()` — making the "this is vision-only, there's no text
input" nature explicit in the code rather than relying on an indirect empty-string return. The
existing skip-condition (`if not document_text: message = "Couldn't read any text..."`) is
narrowed to `if not document_text and image_bytes is None:` so an image upload always attempts
drafting (there's always something to send — the image itself), while non-image uploads keep
their exact existing behavior (FR-005) unchanged.
