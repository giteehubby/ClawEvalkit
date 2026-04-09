"""Test summarizer output."""
from clawevalkit.summarizer import Summarizer


def test_summarizer_init():
    s = Summarizer()
    assert s.output_dir is None


def test_collect_all():
    s = Summarizer()
    table, models = s.collect_all()
    # Should find some cached results (from assets/results/)
    assert isinstance(table, dict)
    assert isinstance(models, list)


def test_to_markdown():
    s = Summarizer()
    md = s.to_markdown()
    assert isinstance(md, str)
