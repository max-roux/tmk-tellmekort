import pytest

from app.web.templating import TEMPLATES, display_title


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("[Infrared thermography in oral cancer].", "Infrared thermography in oral cancer."),
        ("[Is it safe?]", "Is it safe?"),
        ("Plain title.", "Plain title."),
        ("Outcomes of [18F]-FDG PET in oral cancer.", "Outcomes of [18F]-FDG PET in oral cancer."),
        ("[A] and [B].", "[A] and [B]."),
    ],
)
def test_display_title_drops_pubmeds_translation_brackets(raw: str, shown: str) -> None:
    assert display_title(raw) == shown


def test_headline_filter_is_registered() -> None:
    shown = TEMPLATES.env.from_string("{{ t | headline }}").render(t="[Translated].")
    assert shown == "Translated."
