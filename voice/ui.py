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
    assistant = os.getenv("ASSISTANT_NAME", "JARVIS")
    with gr.Blocks(title=f"{assistant} Voice") as demo:
        gr.Markdown(
            f"#  {assistant} - Speech-to-Text\n"
            "Select a microphone, click **Listen**, and speak. "
            "The transcribed text appears below."
        )

        with gr.Row():
            mic_dropdown = gr.Dropdown(
                label="Microphone",
                choices=[],
                value=None,
                interactive=True,
                scale=4,
            )
            refresh_btn = gr.Button("Refresh", variant="secondary", scale=1)
            clear_btn = gr.Button("Clear", variant="secondary", scale=1)

        listen_btn = gr.Button("Listen", variant="primary", scale=4)
        status_box = gr.Textbox(
            label="Status",
            value="Ready. Click Listen to begin.",
            interactive=False,
            lines=1,
        )
        output_box = gr.Textbox(
            label="Transcription",
            lines=6,
            placeholder="Press **Listen** and speak into the selected microphone ...",
            interactive=False,
        )

        with gr.Accordion("Settings", open=False):
            energy = gr.Slider(
                label="Energy threshold (mic sensitivity)",
                minimum=50, maximum=400, step=10, value=STT_ENERGY_THRESHOLD,
            )
            pause = gr.Slider(
                label="Pause threshold (seconds)",
                minimum=0.3, maximum=2.0, step=0.1, value=STT_PAUSE_THRESHOLD,
            )
            lang_dropdown = gr.Dropdown(
                label="Language",
                choices=["en-US", "hi-IN", "mr-IN"],
                value=STT_LANGUAGE,
            )
            apply_btn = gr.Button("Apply settings")

        # Populate the dropdown on start and on refresh.
        refresh_btn.click(
            fn=lambda: [choice[1] for choice in list_mics()],
            inputs=None,
            outputs=mic_dropdown,
        )
        demo.load(
            fn=lambda: [choice[1] for choice in list_mics()],
            inputs=None,
            outputs=mic_dropdown,
        )

        clear_btn.click(fn=lambda: "", inputs=None, outputs=output_box)

        def _apply(energy_val, pause_val, lang_val):
            """Persist chosen settings to the environment for this session."""
            os.environ["STT_ENERGY_THRESHOLD"] = str(int(energy_val))
            os.environ["STT_PAUSE_THRESHOLD"] = str(float(pause_val))
            os.environ["STT_LANGUAGE"] = lang_val
            return f"Applied: energy={int(energy_val)}, pause={float(pause_val)}, lang={lang_val}"

        apply_btn.click(fn=_apply, inputs=[energy, pause, lang_dropdown], outputs=status_box)

        # When the user clicks Listen, map the selected name back to its index.
        def _listen(sel_name):
            idx = next((i for i, n in list_mics() if n == sel_name), None)
            try:
                return listen(idx)
            except Exception as e:
                return f"Error: {e}"

        listen_btn.click(fn=_listen, inputs=mic_dropdown, outputs=output_box)

    demo.launch(
        share=False,
        debug=False,
        server_name=os.getenv("GRADIO_HOST", "127.0.0.1"),
        server_port=int(os.getenv("GRADIO_PORT", "7860")),
    )


if __name__ == "__main__":
    # Running ``python -m voice.ui`` (or ``python voice/ui.py``) starts the UI.
    launch_ui()
