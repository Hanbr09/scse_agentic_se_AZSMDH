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