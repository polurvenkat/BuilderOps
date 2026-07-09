from typing import Literal

ComplexityBucket = Literal["low", "medium", "high"]


def compute_complexity_buckets(byte_counts: dict[int, int | None]) -> dict[int, ComplexityBucket | None]:
    """Bucket repos into complexity tertiles by real total code size (bytes).

    Repos with no byte count (never synced, or GitHub reports zero languages) get None --
    never a fabricated bucket. Tertiles are computed only over repos with a real byte count,
    sorted ascending (stable -- ties keep dict iteration order), split by index using integer
    division so every repo lands in exactly one bucket.
    """
    result: dict[int, ComplexityBucket | None] = {repo_id: None for repo_id in byte_counts}

    ranked = sorted(
        (repo_id for repo_id, size in byte_counts.items() if size is not None),
        key=lambda repo_id: byte_counts[repo_id],
    )
    n = len(ranked)
    low_end = n // 3
    medium_end = 2 * (n // 3)
    for index, repo_id in enumerate(ranked):
        if index < low_end:
            result[repo_id] = "low"
        elif index < medium_end:
            result[repo_id] = "medium"
        else:
            result[repo_id] = "high"
    return result
