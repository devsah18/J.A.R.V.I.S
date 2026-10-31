# -*- coding: utf-8 -*-
"""Voice UI - a minimal Gradio front-end for SpeechToText.

The UI lets you:
1. Select a microphone (auto-selected by default).
2. Press **Listen** to capture one utterance.
3. See the transcribed text (or an error/status message).

It re-uses the existing ``SpeechToText`` implementation and reads
configuration values from ``config.py`` so you can tune thresholds
without code changes.
"""

from __future__ import annotations

import logging
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


try:
    import gradio as gr
except ImportError as e:
    raise ImportError("Gradio is required for the UI. Install it with `pip install gradio`." ) from e

# Project configuration (environment-aware)
from config import (
    STT_DEVICE_INDEX,
    STT_ENABLED,
    STT_ENERGY_THRESHOLD,
    STT_LANGUAGE,
    STT_LISTEN_TIMEOUT,
    STT_PAUSE_THRESHOLD,
    STT_PHRASE_TIME_LIMIT,
)

# Core speech-to-text class
from .speech_to_text import SpeechToText

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper - build a SpeechToText instance respecting the current .env settings
# --------------------------------------------------------------------------- #
def _make_stt() -> SpeechToText:
    """Create a SpeechToText with the current configuration."""
    return SpeechToText(
        language=STT_LANGUAGE,
        energy_threshold=STT_ENERGY_THRESHOLD,
        pause_threshold=STT_PAUSE_THRESHOLD,
        listen_timeout=STT_LISTEN_TIMEOUT,
        phrase_time_limit=STT_PHRASE_TIME_LIMIT,
        enabled=bool(STT_ENABLED),
        device_index=STT_DEVICE_INDEX,
    )


# --------------------------------------------------------------------------- #
# Gradio callbacks
# --------------------------------------------------------------------------- #
def list_mics() -> list[tuple[int, str]]:
    """Return a list of (index, name) for the currently visible microphones."""
    stt = _make_stt()
    names = stt.list_microphones()
    return [(i, name) for i, name in enumerate(names)]


def listen(mic_index: int | None) -> str:
    """Capture a single utterance from the selected microphone."""
    stt = _make_stt()
    # Override the auto-selected device if the user explicitly chose one.
    if mic_index is not None:
        stt.device_index = mic_index
    text = stt.take_input(prompt="Listening...")
    if not text:
        return "[No speech detected / microphone unavailable]"
    return f"    {text}"


# --------------------------------------------------------------------------- #
# Build the UI
# --------------------------------------------------------------------------- #
def launch_ui() -> None:
    """Start the Gradio demo."""
    with gr.Blocks() as demo:
        gr.Markdown(
            f"##    {os.getenv('ASSISTANT_NAME', 'JARVIS')} - Speech-to-Text Demo"
        )
        with gr.Row():
            mic_dropdown = gr.Dropdown(
                label="Microphone (auto-select if empty)",
                choices=[],
                type="value",
                allow_custom_value=False,
                interactive=True,
            )
            refresh_btn = gr.Button("Refresh List", variant="secondary")
        listen_btn = gr.Button("Listen", variant="primary")
        output_box = gr.Textbox(
            label="Transcription",
            lines=4,
            placeholder="Press **Listen** and speak into the selected microphone ...",
        )

        # Populate the dropdown on start and on refresh
        refresh_btn.click(
            fn=lambda: [choice[1] for choice in list_mics()],  # return just the names
            inputs=None,
            outputs=mic_dropdown,
        )
        # Initial population
        demo.load(
            fn=lambda: [choice[1] for choice in list_mics()],
            inputs=None,
            outputs=mic_dropdown,
        )

        # When the user clicks **Listen**, map the selected name back to its index.
        listen_btn.click(
            fn=lambda sel_name: listen(
                next((idx for idx, name in list_mics() if name == sel_name), None)
            ),
            inputs=mic_dropdown,
            outputs=output_box,
        )

    demo.launch(
        share=False,
        debug=False,
        # The host/port can be changed via env vars if desired.
        server_name=os.getenv("GRADIO_HOST", "127.0.0.1"),
        server_port=int(os.getenv("GRADIO_PORT", "7860")),
    )


if __name__ == "__main__":
    # Running ``python -m voice.ui`` (or ``python voice/ui.py``) starts the UI.
    launch_ui()
