from pathlib import PurePosixPath

from django import forms
from django.conf import settings

from .services import BLOCKED_UPLOAD_EXTENSIONS

MAX_TEXT_LENGTH = 100_000


class TextItemForm(forms.Form):
    """Used by both the composer (create) and the edit view."""

    text = forms.CharField(widget=forms.Textarea, strip=False)

    def clean_text(self):
        text = self.cleaned_data["text"]
        if not text.strip():
            raise forms.ValidationError("Write something before saving.")
        if len(text) > MAX_TEXT_LENGTH:
            raise forms.ValidationError(
                f"That note is too long ({MAX_TEXT_LENGTH:,} character limit)."
            )
        return text


class EditItemForm(TextItemForm):
    pass


class FileUploadForm(forms.Form):
    file = forms.FileField()

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]

        if uploaded_file.size == 0:
            raise forms.ValidationError("Empty files can't be saved.")

        if uploaded_file.size > settings.MAX_UPLOAD_SIZE_BYTES:
            raise forms.ValidationError(
                f"The file is too large. Maximum allowed size: {settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        name = uploaded_file.name or ""
        # Browsers only ever send a bare filename, but a crafted client could try to
        # smuggle path separators in — reject outright rather than trust it.
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise forms.ValidationError("Invalid filename.")

        extension = PurePosixPath(name).suffix.lower()
        if extension in BLOCKED_UPLOAD_EXTENSIONS:
            raise forms.ValidationError("This file type isn't allowed.")

        return uploaded_file
