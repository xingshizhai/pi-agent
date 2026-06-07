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
    token_count: reactive[int] = reactive(0)
    elapsed_ms: reactive[int] = reactive(0)
    is_streaming: reactive[bool] = reactive(False)

    def render(self) -> Text:
        spinner = "⠋" if self.is_streaming else " "
        elapsed = f"{self.elapsed_ms / 1000:.1f}s" if self.elapsed_ms else "—"
        return Text(
            f" {spinner} {self.model_name}  |  {self.token_count} tokens  |  {elapsed}",
            style="dim",
        )
