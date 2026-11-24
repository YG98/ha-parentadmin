"""Test the ParentAdmin parser against a saved diary page, outside Home Assistant.

Save the page from your browser (Ctrl+S on child-diary.php -> "Webpage, HTML only"), then:
    pip install beautifulsoup4
    python tools/test_parser.py saved-diary.html
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "parentadmin"))
from parser import parse_diary  # noqa: E402

html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
child, entries = parse_diary(html, "https://uk.parentadmin.com")
print(f"Child: {child}\nEntries: {len(entries)}\n")
for e in entries:
    extra = e.percent if e.kind == "food" else e.millilitres if e.kind == "drink" else e.minutes if e.kind == "sleep" else ""
    print(f"{e.start} {str(e.end or ''):8} {e.kind:9} {e.title:10} {e.figure:12} {extra!s:6} {e.detail[:50]} {'[%d photos]' % len(e.photos) if e.photos else ''}")
