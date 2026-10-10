import pytest
from generated.navigation_logic import decide_next_move
from runner import scenario_cases

@pytest.mark.parametrize("state, expected", scenario_cases())
def test_navigation(state, expected):
    before = state.copy()
    action = decide_next_move(state)
    assert action == expected
    assert state == before
    assert action in ['FORWARD', 'LEFT', 'RIGHT', 'STOP']
    if action == 'FORWARD':
        assert not state["front_blocked"]
    elif action == 'LEFT':
        assert not state["left_blocked"]
    elif action == 'RIGHT':
        assert not state["right_blocked"]
    elif action == 'STOP':
        assert state["front_blocked"] and state["left_blocked"] and state["right_blocked"]
