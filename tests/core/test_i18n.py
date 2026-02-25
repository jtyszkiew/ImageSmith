import os
import tempfile

import pytest
import yaml

from src.core.i18n import I18n, _deep_merge


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def defaults_file(tmp_dir):
    data = {
        "client": {
            "media": {
                "image_generated": "🖼 New image generated!"
            },
            "progress": {
                "processing_node": "🔄 Processing node {node}..."
            },
            "status": {
                "generation_complete": "✅ Generation complete!"
            }
        },
        "embed": {
            "titles": {
                "error": "❌ Error",
                "forge": "🔨 ImageSmith Forge"
            }
        },
        "deep": {
            "level1": {
                "level2": {
                    "level3": "deep value"
                }
            }
        }
    }
    path = os.path.join(tmp_dir, "strings.yml")
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


class TestLoadDefaults:
    def test_load_defaults(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        assert s.get("client.media.image_generated") == "🖼 New image generated!"

    def test_load_missing_file(self):
        s = I18n()
        s.load(defaults_path="/nonexistent/strings.yml")
        # Should not crash; missing key returns key path
        assert s.get("client.media.image_generated") == "client.media.image_generated"

    def test_load_invalid_yaml(self, tmp_dir):
        path = os.path.join(tmp_dir, "bad.yml")
        with open(path, "w") as f:
            f.write(": : : invalid yaml [[[")
        s = I18n()
        s.load(defaults_path=path)
        assert s.get("anything") == "anything"


class TestGet:
    def test_get_simple(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        assert s.get("embed.titles.error") == "❌ Error"

    def test_get_with_substitution(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        result = s.get("client.progress.processing_node", node="KSampler")
        assert result == "🔄 Processing node KSampler..."

    def test_get_missing_key(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        assert s.get("nonexistent.key") == "nonexistent.key"

    def test_get_deep_nesting(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        assert s.get("deep.level1.level2.level3") == "deep value"

    def test_get_partial_path(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        # Path to a dict, not a string — returns key
        assert s.get("embed.titles") == "embed.titles"

    def test_get_missing_variable(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        result = s.get("client.progress.processing_node", missing_var="value")
        # {node} should be preserved since it wasn't provided
        assert "{node}" in result


class TestOverrides:
    def test_override_merges(self, defaults_file):
        s = I18n()
        overrides = {"embed": {"titles": {"error": "Custom Error"}}}
        s.load(defaults_path=defaults_file, overrides=overrides)
        assert s.get("embed.titles.error") == "Custom Error"

    def test_override_preserves_others(self, defaults_file):
        s = I18n()
        overrides = {"embed": {"titles": {"error": "Custom Error"}}}
        s.load(defaults_path=defaults_file, overrides=overrides)
        # forge should still be the default
        assert s.get("embed.titles.forge") == "🔨 ImageSmith Forge"

    def test_override_adds_new_keys(self, defaults_file):
        s = I18n()
        overrides = {"custom": {"new_key": "new value"}}
        s.load(defaults_path=defaults_file, overrides=overrides)
        assert s.get("custom.new_key") == "new value"


class TestDeepMerge:
    def test_deep_merge_nested(self):
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"b": 10}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": 10, "c": 2}}

    def test_deep_merge_does_not_mutate(self):
        base = {"a": {"b": 1}}
        override = {"a": {"b": 2}}
        _deep_merge(base, override)
        assert base == {"a": {"b": 1}}


class TestLanguageLayer:
    def test_language_layer(self, tmp_dir):
        defaults = {"greeting": "Hello", "farewell": "Goodbye"}
        lang = {"greeting": "Cześć"}

        defaults_path = os.path.join(tmp_dir, "strings.yml")
        lang_path = os.path.join(tmp_dir, "strings.pl.yml")

        with open(defaults_path, "w") as f:
            yaml.dump(defaults, f)
        with open(lang_path, "w") as f:
            yaml.dump(lang, f)

        s = I18n()
        s.load(defaults_path=defaults_path, language="pl")
        assert s.get("greeting") == "Cześć"

    def test_language_fallback(self, tmp_dir):
        defaults = {"greeting": "Hello", "farewell": "Goodbye"}
        lang = {"greeting": "Cześć"}

        defaults_path = os.path.join(tmp_dir, "strings.yml")
        lang_path = os.path.join(tmp_dir, "strings.pl.yml")

        with open(defaults_path, "w") as f:
            yaml.dump(defaults, f)
        with open(lang_path, "w") as f:
            yaml.dump(lang, f)

        s = I18n()
        s.load(defaults_path=defaults_path, language="pl")
        # farewell not in language file, falls back to default
        assert s.get("farewell") == "Goodbye"


class TestSanitizeError:
    def test_hides_error_in_prod(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file, env="prod")
        s._data["error"] = {"generic_message": "An unexpected error occurred. Please try again later."}
        result = s.sanitize_error("ConnectionRefusedError: [Errno 111]")
        assert result == "An unexpected error occurred. Please try again later."

    def test_shows_error_in_dev(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file, env="dev")
        result = s.sanitize_error("ConnectionRefusedError: [Errno 111]")
        assert result == "ConnectionRefusedError: [Errno 111]"

    def test_default_env_is_prod(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        s._data["error"] = {"generic_message": "An unexpected error occurred. Please try again later."}
        result = s.sanitize_error("some error")
        assert result == "An unexpected error occurred. Please try again later."

    def test_empty_error_in_dev(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file, env="dev")
        result = s.sanitize_error("")
        assert result == ""

    def test_empty_error_in_prod(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file, env="prod")
        s._data["error"] = {"generic_message": "An unexpected error occurred. Please try again later."}
        result = s.sanitize_error("")
        assert result == "An unexpected error occurred. Please try again later."


class TestRaw:
    def test_raw_returns_template(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        raw = s.raw("client.progress.processing_node")
        assert raw == "🔄 Processing node {node}..."

    def test_raw_missing_returns_none(self, defaults_file):
        s = I18n()
        s.load(defaults_path=defaults_file)
        assert s.raw("nonexistent.key") is None
