from backend.curriculum.loader import CURRICULUM


def test_curriculum_loads_at_least_six_lessons():
    """Expanded curriculum: ≥6 lessons (spec minimum 3)."""
    lessons = CURRICULUM.all()
    assert len(lessons) >= 6, f"curriculum has {len(lessons)} lessons, expected ≥6"


def test_lesson_ids_are_unique():
    ids = [l.id for l in CURRICULUM.all()]
    assert len(set(ids)) == len(ids)


def test_lessons_have_required_pedagogy_fields():
    for l in CURRICULUM.all():
        assert l.objective and isinstance(l.objective, str)
        assert l.vocabulary, f"lesson {l.id} has no vocabulary"
        assert l.checks, f"lesson {l.id} has no check questions"
        assert l.examples, f"lesson {l.id} has no examples"
        assert l.grammar_notes, f"lesson {l.id} has no grammar notes"
        assert l.practice_prompts, f"lesson {l.id} has no practice prompts"


def test_by_topic_keyword_match():
    for topic, expected_id in [
        ("greetings", "greetings-001"),
        ("numbers", "numbers-001"),
        ("food", "ordering-food-001"),
        ("family", "family-001"),
        ("days", "days-time-001"),
        ("directions", "directions-001"),
    ]:
        lesson = CURRICULUM.by_topic(topic)
        assert lesson is not None, f"no lesson found for topic={topic!r}"
        assert lesson.id == expected_id, (
            f"topic {topic!r} mapped to {lesson.id}, expected {expected_id}"
        )


def test_by_topic_natural_phrases():
    """User-natural phrases should still map."""
    cases = [
        ("teach me how to greet people", "greetings-001"),
        ("how do I count", "numbers-001"),
        ("ordering at a restaurant", "ordering-food-001"),
        ("my brother and sister", "family-001"),
        ("what time is it today", "days-time-001"),
        ("where is the bathroom", "directions-001"),
    ]
    for phrase, expected_id in cases:
        lesson = CURRICULUM.by_topic(phrase)
        assert lesson is not None, f"no lesson found for phrase={phrase!r}"
        assert lesson.id == expected_id, (
            f"phrase {phrase!r} mapped to {lesson.id}, expected {expected_id}"
        )


def test_vocab_lookup_bilingual():
    v = CURRICULUM.find_vocab("hola")
    assert v is not None
    assert v.en == "hello"
    v2 = CURRICULUM.find_vocab("hello")
    assert v2 is not None and v2.es == "hola"


def test_vocab_in_new_lessons():
    """Spot-check vocab from the new family/days/directions lessons."""
    for word in ["el padre", "lunes", "a la derecha"]:
        assert CURRICULUM.find_vocab(word) is not None, f"missing {word}"


def test_targets_spanish():
    assert CURRICULUM.language == "es"
    assert CURRICULUM.native_language == "en"
