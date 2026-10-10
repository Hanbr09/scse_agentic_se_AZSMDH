import pytest
from generated.navigation_logic import decide_next_move
from runner import scenario_cases

@pytest.mark.parametrize("state, expected", scenario_cases())
def test_navigation(state, expected):
    before = state.copy()
    result = decide_next_move(state)
    assert result == expected
    assert state == before
    assert result in ['FORWARD', 'LEFT', 'RIGHT', 'STOP']
    if result == 'FORWARD':
        assert not state["front_blocked"]
    elif result == 'LEFT':
        assert not state["left_blocked"]
    elif result == 'RIGHT':
        assert not state["right_blocked"]
    elif result == 'STOP':
        assert state["front_blocked"] and state["left_blocked"] and state["right_blocked"]
