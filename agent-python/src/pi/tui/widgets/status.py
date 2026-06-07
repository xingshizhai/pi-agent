# src/pi/tui/widgets/status.py
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary-background;
        color: $text-muted;
        padding: 0 1;
    }
    """

    model_name: reactive[str] = reactive("—")
    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)
    elapsed_ms: reactive[int] = reactive(0)
    is_streaming: reactive[bool] = reactive(False)

    def render(self) -> Text:
        parts: list[str] = [self.model_name]

        if self.input_tokens > 0 or self.output_tokens > 0:
            parts.append(f"↑{self.input_tokens} ↓{self.output_tokens} tokens")

        if self.elapsed_ms:
            parts.append(f"{self.elapsed_ms / 1000:.1f}s")

        if self.is_streaming:
            parts.append("● streaming")

        line = "  │  ".join(parts)
        return Text(f" {line} ", style="dim")
