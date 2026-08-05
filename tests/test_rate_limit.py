from services.rate_limit import CAPACITY, calculate_token_state


def test_new_bucket_consumes_one_token() -> None:
    allowed, tokens, retry_after = calculate_token_state(None, None, now=100.0)

    assert allowed
    assert tokens == CAPACITY - 1
    assert retry_after == 0


def test_empty_bucket_reports_retry_delay() -> None:
    allowed, tokens, retry_after = calculate_token_state(0, 100.0, now=105.0)

    assert not allowed
    assert tokens == 0.25
    assert retry_after == 15


def test_refill_is_capped_at_capacity() -> None:
    allowed, tokens, retry_after = calculate_token_state(4, 100.0, now=200.0)

    assert allowed
    assert tokens == CAPACITY - 1
    assert retry_after == 0


def test_clock_rollback_does_not_remove_tokens() -> None:
    allowed, tokens, _ = calculate_token_state(2, 100.0, now=90.0)

    assert allowed
    assert tokens == 1
