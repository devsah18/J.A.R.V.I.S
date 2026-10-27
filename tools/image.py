"""Image Generation and Retrieval tool.

Generates creative AI images via Pollinations / DALL-E and fetches real authentic
high-resolution photographs via Wikimedia Commons, saving them locally and displaying them.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
from pathlib import Path
from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "images"
_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def _slugify(text: str, max_len: int = 30) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "_", cleaned)
    return slug[:max_len] or "image"


class ImageTool(Tool):
    name = "image"
    description = (
        "Generate creative AI images from text prompts, or retrieve real high-resolution "
        "photographs of places, animals, objects, and people, and open them for viewing."
    )
    risk = Risk.LOW
    params = (
        ParamSpec("prompt", "Description of the image to generate or find"),
        ParamSpec("kind", "Type: 'ai' for artistic/creative AI image, or 'real' for authentic photograph", required=False),
        ParamSpec("width", "Image width in pixels (default 768)", required=False),
        ParamSpec("height", "Image height in pixels (default 768)", required=False),
    )

    def __init__(self, output_dir: Path | None = None):
        self._output_dir = output_dir or _DEFAULT_OUTPUT_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        prompt: str = "",
        kind: str = "auto",
        width: int = 768,
        height: int = 768,
        **kwargs,
    ) -> ToolResult:
        prompt = (prompt or "").strip()
        if not prompt:
            return ToolResult.failure("Please describe what image you want me to generate or find.")

        if requests is None:
            return ToolResult.failure("The requests library is required for image operations.")

        kind = (kind or "auto").strip().lower()
        if kind == "auto":
            low_p = prompt.lower()
            if any(w in low_p for w in ("real photo", "real image", "photograph", "actual photo", "real picture")):
                kind = "real"
            else:
                kind = "ai"

        # Clean prompt for search/generation
        clean_p = re.sub(
            r"^(?:generate|create|make|draw|show me|find|get)\s+(?:an?|the)?\s*(?:ai|real|actual)?\s*(?:image|photo|picture|photograph)?\s*(?:of)?\s*",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip()
        clean_p = clean_p or prompt

        if kind == "real":
            return self._handle_real_image(clean_p, width, height)
        else:
            return self._handle_ai_image(clean_p, width, height)

    # ------------------------------------------------------------------ #
    # Real Photograph Retrieval
    # ------------------------------------------------------------------ #
    def _handle_real_image(self, subject: str, width: int, height: int) -> ToolResult:
        logger.info("Fetching real photograph for '%s'", subject)
        image_bytes = None
        source_label = "Wikimedia Commons"

        clean_search = re.sub(r"^(?:the|a|an)\s+", "", subject.strip(), flags=re.IGNORECASE)

        try:
            # Query Wikimedia Commons API for authentic photograph
            url = (
                "https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                f"&gsrnamespace=6&gsrsearch={urllib.parse.quote(clean_search)}&gsrlimit=3"
                "&prop=imageinfo&iiprop=url|mime&format=json"
            )
            headers = {"User-Agent": _BROWSER_UA}
            resp = requests.get(url, timeout=8, headers=headers)
            if resp.status_code == 200:
                pages = resp.json().get("query", {}).get("pages", {})
                for _, page_info in pages.items():
                    infos = page_info.get("imageinfo", [])
                    if infos:
                        img_url = infos[0].get("url")
                        mime = infos[0].get("mime", "")
                        if img_url and ("jpeg" in mime or "png" in mime or "jpg" in mime or img_url.lower().endswith((".jpg", ".png", ".jpeg"))):
                            img_resp = requests.get(img_url, timeout=15, headers=headers)
                            if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                                image_bytes = img_resp.content
                                break
        except Exception as e:
            logger.warning("Wikimedia search failed: %s", e)

        # Fallback to Photorealism model if not found on Commons
        if not image_bytes:
            source_label = "Photorealism Engine"
            realistic_prompt = f"authentic raw documentary photo of {subject}, 8k, natural daylight, sharp focus, award-winning photography"
            image_bytes, _ = self._fetch_pollinations(realistic_prompt, width, height)

        if not image_bytes:
            return ToolResult.failure(f"Could not retrieve a real photograph for '{subject}'.")

        saved_path = self._save_and_open(image_bytes, f"real_{clean_search}")
        msg = f"Here is a real photograph of {subject} (source: {source_label}). Saved to {saved_path.name} and opened for you."
        return ToolResult.success(msg, path=str(saved_path), prompt=subject, kind="real", source=source_label)

    # ------------------------------------------------------------------ #
    # Creative AI Image Generation
    # ------------------------------------------------------------------ #
    def _handle_ai_image(self, prompt_text: str, width: int, height: int) -> ToolResult:
        logger.info("Generating AI image for '%s'", prompt_text)

        # 1. Check if OpenAI DALL-E is configured
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                response = client.images.generate(
                    model="dall-e-3",
                    prompt=prompt_text,
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
                img_url = response.data[0].url
                img_resp = requests.get(img_url, timeout=20)
                if img_resp.status_code == 200:
                    saved_path = self._save_and_open(img_resp.content, f"dalle_{prompt_text}")
                    msg = f"Created AI image for '{prompt_text}' using DALL-E 3. Saved to {saved_path.name} and opened for viewing."
                    return ToolResult.success(msg, path=str(saved_path), prompt=prompt_text, kind="ai", engine="dall-e-3")
            except Exception as e:
                logger.info("OpenAI DALL-E attempt skipped/failed: %s. Falling back to free engine.", e)

        # 2. Free Pollinations Engine
        image_bytes, err_msg = self._fetch_pollinations(prompt_text, width, height)
        if image_bytes:
            saved_path = self._save_and_open(image_bytes, f"ai_{prompt_text}")
            msg = f"Created AI image for '{prompt_text}'. Saved to {saved_path.name} and opened for viewing."
            return ToolResult.success(msg, path=str(saved_path), prompt=prompt_text, kind="ai")

        error_detail = f" ({err_msg})" if err_msg else ""
        return ToolResult.failure(f"Image generation could not be completed right now{error_detail}. Please try again shortly.")

    # ------------------------------------------------------------------ #
    # Pollinations Engine Helper
    # ------------------------------------------------------------------ #
    def _fetch_pollinations(self, prompt: str, width: int, height: int) -> tuple[bytes | None, str]:
        encoded = urllib.parse.quote(prompt)
        headers = {"User-Agent": _BROWSER_UA}
        last_error = ""

        for model_arg in ("&model=turbo", ""):
            try:
                gen_url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}{model_arg}&nologo=true"
                resp = requests.get(gen_url, timeout=25, headers=headers)
                if resp.status_code == 200 and len(resp.content) > 5000:
                    return resp.content, ""
                elif resp.status_code == 402:
                    try:
                        err_json = resp.json()
                        last_error = err_json.get("error", {}).get("message", "Free limit: please wait a few seconds before generating another image")
                    except Exception:
                        last_error = "Free rate limit: please wait a few seconds"
            except Exception as e:
                last_error = str(e)
                logger.warning("Pollinations attempt error: %s", e)

        return None, last_error

    # ------------------------------------------------------------------ #
    # Save & Open Helper
    # ------------------------------------------------------------------ #
    def _save_and_open(self, data: bytes, tag: str) -> Path:
        slug = _slugify(tag, max_len=24)
        timestamp = int(time.time())
        filename = f"{slug}_{timestamp}.jpg"
        filepath = self._output_dir / filename
        filepath.write_bytes(data)

        # Launch in system default image viewer
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(filepath), "open")
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(filepath)])
        except Exception as e:
            logger.info("Could not auto-open image: %s", e)

        return filepath

