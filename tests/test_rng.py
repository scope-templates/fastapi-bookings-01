from app.rng import Rng, mulberry32


def test_mulberry32_is_deterministic_for_a_seed():
    draw = mulberry32(7)
    assert [f"{draw():.10f}" for _ in range(5)] == [
        "0.0117047532",
        "0.0619582576",
        "0.9769076328",
        "0.6990287057",
        "0.5214452685",
    ]


def test_int_is_inclusive_of_both_bounds_and_stable():
    rng = Rng(1)
    seen = {rng.int(3, 5) for _ in range(500)}
    assert sorted(seen) == [3, 4, 5]
    assert Rng(1).int(0, 1000) == Rng(1).int(0, 1000)


def test_pick_and_chance_use_the_stream():
    rng = Rng(7)
    assert rng.pick(["a", "b", "c"]) == "a"
    assert rng.chance(0.5) is True


def test_hex_is_as_long_as_asked():
    assert len(Rng(3).hex(12)) == 12
    assert all(c in "0123456789abcdef" for c in Rng(3).hex(12))
