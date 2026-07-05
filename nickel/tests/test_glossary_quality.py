"""Tests for glossary term quality helpers."""

from services.glossary_quality import clean_glossary_display, is_worthy_glossary_term, term_language


def test_rejects_job_id_artifact():
    junk = "01c384d7-4474-4f2c-bd21-02d55de408a9_13 Приложение. Статья_yandex_graph"
    assert not is_worthy_glossary_term(junk)


def test_clean_strips_job_prefix():
    raw = "01c384d7-4474-4f2c-bd21-02d55de408a9_13 Приложение. Статья_yandex_graph"
    assert clean_glossary_display(raw) == "Приложение. Статья"


def test_accepts_parameter_names():
    assert is_worthy_glossary_term("% Cu in ore")
    assert term_language("% Cu in ore") == "en"
