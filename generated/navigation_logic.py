def choose_action(front_blocked, left_blocked, right_blocked, goal_direction=None):
    if goal_direction == 'AHEAD' and not front_blocked:
        return 'FORWARD'
    elif goal_direction == 'LEFT' and not left_blocked:
        return 'LEFT'
    elif goal_direction == 'RIGHT' and not right_blocked:
        return 'RIGHT'
    elif not front_blocked:
        return 'FORWARD'
    elif not left_blocked:
        return 'LEFT'
    elif not right_blocked:
        return 'RIGHT'
    else:
        return 'STOP'

def decide_next_move(state):
    front_blocked = state["front_blocked"]
    left_blocked = state["left_blocked"]
    right_blocked = state["right_blocked"]
    goal_direction = None
    
    if state["goal_ahead"] and not front_blocked:
        goal_direction = 'AHEAD'
    elif state["goal_on_left"] and not left_blocked:
        goal_direction = 'LEFT'
    elif state["goal_on_right"] and not right_blocked:
        goal_direction = 'RIGHT'
    
    return choose_action(front_blocked, left_blocked, right_blocked, goal_direction)