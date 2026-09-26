from sloppy.features.duration import duration_bucket, duration_deviation


def test_duration_bucket_short():
    assert duration_bucket(45) == "short"
    assert duration_bucket(180) == "short"


def test_duration_bucket_mid():
    assert duration_bucket(181) == "mid"
    assert duration_bucket(600) == "mid"


def test_duration_bucket_long():
    assert duration_bucket(1200) == "long"
    assert duration_bucket(7200) == "long"


def test_duration_bucket_unknown_for_none():
    assert duration_bucket(None) == "unknown"


def test_duration_deviation_none_when_duration_missing():
    assert duration_deviation(None, [600, 620, 610]) is None


def test_duration_deviation_none_with_fewer_than_two_peers():
    assert duration_deviation(45, []) is None
    assert duration_deviation(45, [600]) is None


def test_duration_deviation_flags_short_video_among_long_peers():
    # 45s video amid 20 documentary-length (~600s, with natural variance) peers - the
    # exact "45 seconds is normal for Shorts, suspicious for a documentary" signal the
    # roadmap calls out. Peers vary slightly (not all identical) so this exercises real
    # z-score behavior rather than the zero-spread edge case.
    peers = [560, 580, 600, 620, 640, 590, 610, 605, 615, 595] * 2
    deviation = duration_deviation(45, peers, use_log=True)
    assert deviation is not None
    assert deviation < -1.0


def test_duration_deviation_near_zero_for_typical_video():
    peers = [590, 600, 610, 605, 595, 600, 600, 598]
    deviation = duration_deviation(600, peers, use_log=True)
    assert deviation is not None
    assert abs(deviation) < 1.0


def test_duration_deviation_zero_when_peers_have_no_spread():
    assert duration_deviation(600, [600, 600, 600]) == 0.0


def test_duration_deviation_zero_spread_edge_case_even_with_different_target():
    # Documented limitation: a z-score is undefined when peer spread is zero. We return
    # 0.0 (no deviation) rather than raising or returning infinity, even though the target
    # differs from the identical peers - this is a safe fallback for an edge case that's
    # extremely unlikely with real data (15-30 real video durations are never all
    # identical), not a claim that 45s "looks normal" among 600s peers.
    assert duration_deviation(45, [600, 600, 600]) == 0.0
