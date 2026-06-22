from ingestion_worker.ids import deterministic_point_id


def test_deterministic_point_id_is_stable_uuid():
    first = deterministic_point_id("orbit", "default", "projects", "123")
    second = deterministic_point_id("orbit", "default", "projects", "123")
    other = deterministic_point_id("orbit", "other", "projects", "123")

    assert first == second
    assert first != other
    assert len(first) == 36
