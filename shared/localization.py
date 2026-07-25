import json
import os
from typing import Dict


class Localization:
    """Localization helper."""

    def __init__(self):
        self.languages = ["en", "ua"]
        self.default_language = "en"
        self.translations: Dict[str, Dict[str, str]] = {}
        self._load_translations()

    def _load_translations(self) -> None:
        """Load translations from files."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        translations_dir = os.path.join(current_dir, "translations")

        for lang in self.languages:
            file_path = os.path.join(translations_dir, f"{lang}.json")
            if not os.path.exists(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.translations[lang] = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error loading {lang}.json: {e}")
                print(f"File path: {file_path}")
                with open(file_path, "rb") as f:
                    first_bytes = f.read(10)
                    print(f"First bytes (hex): {' '.join(f'{b:02x}' for b in first_bytes)}")
                raise

    def reload_translations(self) -> None:
        """Reload translations from files (without restart)."""
        print("Reloading translations...")
        self._load_translations()
        print("Translations reloaded successfully!")

    def get_text(self, key: str, language: str = "en", **kwargs) -> str:
        """Return a localized string with a safe fallback."""
        lang_data = self.translations.get(language, {})
        text = lang_data.get(key)

        if text is None:
            default_data = self.translations.get(self.default_language, {})
            text = default_data.get(key)

        if text is None:
            text = f"[missing:{key}]"

        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass

        return text

    def get_available_languages(self) -> Dict[str, str]:
        """Return the list of available languages."""
        return {"en": "English", "ua": "Українська"}


# Global localization instance
localization = Localization()

