"""The sliding-window limiter, driven by a fake clock so nothing here sleeps."""

from sloppy.predict.limits import SlidingWindowLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_allows_up_to_the_limit_then_refuses():
    limiter = SlidingWindowLimiter(3, 3600, clock=FakeClock())

    assert [limiter.allow("a") for _ in range(5)] == [True, True, True, False, False]


def test_each_client_has_its_own_allowance():
    limiter = SlidingWindowLimiter(1, 3600, clock=FakeClock())

    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True


def test_the_allowance_comes_back_as_old_events_leave_the_window():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(2, 100, clock=clock)
    assert limiter.allow("a") and limiter.allow("a")
    assert limiter.allow("a") is False

    clock.now += 99
    assert limiter.allow("a") is False  # the first event is still inside the window
    clock.now += 2
    assert limiter.allow("a") is True


def test_a_refused_attempt_is_not_recorded_so_it_cannot_extend_the_lockout():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, 100, clock=clock)
    assert limiter.allow("a")

    for _ in range(10):
        clock.now += 5
        assert limiter.allow("a") is False

    clock.now = 1000.0 + 101
    assert limiter.allow("a") is True


def test_a_limit_of_zero_means_unlimited():
    limiter = SlidingWindowLimiter(0, 3600, clock=FakeClock())

    assert all(limiter.allow("a") for _ in range(1000))


def test_retry_after_counts_down_to_the_oldest_event_leaving():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, 100, clock=clock)
    assert limiter.retry_after_seconds("a") == 0
    limiter.allow("a")

    clock.now += 40
    assert 59 <= limiter.retry_after_seconds("a") <= 61
    clock.now += 61
    assert limiter.retry_after_seconds("a") == 0
