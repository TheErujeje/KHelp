from khelp_scoring import lookup_discriminators


def active_ids(text):
    return {m.id for m in lookup_discriminators(text) if not m.negated}


def test_abbreviations():
    assert "disc.orange.sob_acute" in active_ids("c/o SOB x 2 days")
    assert "disc.orange.sob_acute" in active_ids("DIB since morning")


def test_pidgin_phrases():
    assert "disc.yellow.abdominal_pain" in active_ids("Mama say belle dey pain me since yesterday")
    assert "disc.orange.chest_pain" in active_ids("oga talk say chest dey pain am")
    assert "disc.orange.sob_acute" in active_ids("him breath dey cut")


def test_negation_within_clause():
    matches = {m.id: m for m in lookup_discriminators("Headache. No SOB or chest pain.")}
    assert matches["disc.orange.sob_acute"].negated
    assert matches["disc.orange.chest_pain"].negated


def test_negation_does_not_cross_clauses():
    ids = active_ids("SOB, no fever, chest pain")
    assert {"disc.orange.sob_acute", "disc.orange.chest_pain"} <= ids


def test_denies():
    assert "disc.orange.chest_pain" not in active_ids("pt denies chest pain")


def test_all_of_requires_every_set():
    assert "disc.orange.pregnancy_abdominal" in active_ids("32 weeks pregnant, lower abdominal pain")
    assert "disc.orange.pregnancy_abdominal" not in active_ids("lower abdominal pain")
    assert "disc.yellow.pregnancy_trauma" in active_ids("she get belle, fell from okada")


def test_whole_words_only():
    assert "disc.yellow.burn_other" not in active_ids("heartburn after meals")
    assert "disc.yellow.burn_other" not in active_ids("burning micturition")
    assert "disc.orange.pain_severe" not in active_ids("BP 128/100")


def test_pain_score():
    assert "disc.orange.pain_severe" in active_ids("pain 9/10")
    assert "disc.yellow.pain_moderate" in active_ids("pain 6/10")


def test_every_match_carries_source():
    for m in lookup_discriminators("convulsing, vomiting blood, burns to face"):
        assert m.source["document"]
        assert m.verified is False


def test_no_match_for_routine_follow_up():
    assert active_ids("came for BP drug refill, no complaints") == set()
