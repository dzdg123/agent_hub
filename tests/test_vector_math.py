import pytest

from research_agent.vector_math import cosine


@pytest.mark.parametrize(("left", "right", "expected"), [
    ([1, 0], [1, 0], 1.0),
    ([1, 0], [0, 1], 0.0),
    ([1, 0], [-1, 0], -1.0),
    ([1, 0], [10, 0], 1.0),
    ([3, 1], [1, 3], 0.6),
    ([1e200, 0], [1e200, 0], 1.0),
])
def test_m01_cosine_direction_and_magnitude(left, right, expected):
    assert cosine(left, right) == pytest.approx(expected)
    assert cosine(right, left) == pytest.approx(expected)


@pytest.mark.parametrize(("left", "right"), [
    ([], []), ([1], []), ([1, 0], [1]),
    ([0, 0], [1, 0]), ([1, 0], [0, 0]),
    ([float("nan"), 1], [1, 0]),
    ([1, 0], [float("inf"), 0]),
    ([float("-inf"), 0], [1, 0]),
])
def test_m01_cosine_invalid_input_fails_explicitly(left, right):
    with pytest.raises(ValueError):
        cosine(left, right)
