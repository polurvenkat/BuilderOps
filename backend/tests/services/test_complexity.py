from app.services.complexity import compute_complexity_buckets


def test_buckets_split_into_real_tertiles_for_nine_repos():
    byte_counts = {i: (i + 1) * 1000 for i in range(9)}  # repo 0 smallest ... repo 8 largest
    result = compute_complexity_buckets(byte_counts)

    assert [result[i] for i in range(3)] == ["low", "low", "low"]
    assert [result[i] for i in range(3, 6)] == ["medium", "medium", "medium"]
    assert [result[i] for i in range(6, 9)] == ["high", "high", "high"]


def test_repo_with_no_byte_count_gets_none_not_a_fabricated_bucket():
    byte_counts = {1: 1000, 2: 2000, 3: None}
    result = compute_complexity_buckets(byte_counts)

    assert result[3] is None
    assert result[1] in ("low", "medium", "high")


def test_fewer_than_three_repos_all_land_in_high():
    byte_counts = {1: 500, 2: 1500}
    result = compute_complexity_buckets(byte_counts)

    assert result[1] == "high"
    assert result[2] == "high"


def test_single_repo_lands_in_high():
    result = compute_complexity_buckets({1: 500})
    assert result[1] == "high"


def test_ties_are_broken_by_stable_input_order():
    byte_counts = {1: 1000, 2: 1000, 3: 1000, 4: 1000, 5: 1000, 6: 1000}
    result = compute_complexity_buckets(byte_counts)

    assert [result[i] for i in range(1, 7)] == ["low", "low", "medium", "medium", "high", "high"]


def test_empty_input_returns_empty_dict():
    assert compute_complexity_buckets({}) == {}


def test_all_none_byte_counts_all_map_to_none():
    result = compute_complexity_buckets({1: None, 2: None})
    assert result == {1: None, 2: None}
