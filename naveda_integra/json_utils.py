"""HTML-safe JSON serialization for embedding in <script> blocks.

Plain ``json.dumps`` does not escape ``<``, ``>`` or ``&``, so a value such as
``</script><script>...`` injected into a template via ``{{ x|safe }}`` breaks
out of the script element and executes (stored XSS). ``safe_json`` escapes those
characters as ``\\uXXXX`` — JSON.parse / JS reads identical values, but the
HTML parser can no longer be tricked into ending the script early.

``ensure_ascii=True`` (the json default) already escapes the line-separator
characters U+2028 / U+2029, which JS would otherwise treat as newlines.

Use this for any data rendered into a template with ``|safe`` inside a
``<script>`` tag, in place of ``json.dumps``.
"""
import json

# Mirrors django.utils.html.json_script's escape table.
_SCRIPT_ESCAPES = {
    ord('<'): '\\u003c',
    ord('>'): '\\u003e',
    ord('&'): '\\u0026',
}


def safe_json(value, **dumps_kwargs) -> str:
    """json.dumps(value) with <, >, & escaped for safe <script> embedding."""
    return json.dumps(value, **dumps_kwargs).translate(_SCRIPT_ESCAPES)
