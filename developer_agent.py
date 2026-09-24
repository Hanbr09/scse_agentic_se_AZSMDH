"""Generate navigation code, then check its syntax, scope, and behavior."""

import ast
import io
from itertools import product
import json
from pathlib import Path
import tokenize

from analyst_agent import ask_qwen
from planner_agent import validate_plan


BASE_DIR = Path(__file__).resolve().parent
ORIGINAL_CODE = (BASE_DIR / "artifacts" / "baseline" / "navigation_logic.py").read_text(encoding="utf-8")
SYSTEM_PROMPT = """Output an ENTIRE Python file, not a patch or just a new helper.
It must contain TWO complete def functions. No Markdown, comments or examples.
The user supplies this group's seven-rule navigation plan.
FIRST output this original function, unchanged, including every elif and else:

""" + ORIGINAL_CODE + """
SECOND output def decide_next_move(state):
state is a DICTIONARY, never a list or tuple. Use exact string keys.
Start its body with these assignments:
    front_blocked = state["front_blocked"]
    left_blocked = state["left_blocked"]
    right_blocked = state["right_blocked"]
Start a local goal_direction variable as None.
Use one if/elif chain to select the FIRST CLEAR indicated goal:
state["goal_ahead"] and not front_blocked -> goal_direction = 'AHEAD';
state["goal_on_left"] and not left_blocked -> goal_direction = 'LEFT';
state["goal_on_right"] and not right_blocked -> goal_direction = 'RIGHT'.
All goal flags False means unknown goal. A blocked goal must not prevent a
different clear goal being selected. The order is ahead, left, right.
Finish with return choose_action(front_blocked, left_blocked, right_blocked, goal_direction).
No other fallback in the wrapper. No slicing, unpacking, loops, imports or annotations.
True blocked means unsafe. Keep the original choose_action as the FIRST function;
do NOT omit it even though it appears in this prompt. Both functions must be in
your response. The first line MUST start with def choose_action(.
"""

PARAMETERS = ["front_blocked", "left_blocked", "right_blocked", "goal_direction"]
ALLOWED_NODES = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If,
    ast.Assign, ast.Name, ast.Load, ast.Store, ast.Constant, ast.Expr,
    ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Compare,
    ast.Eq, ast.NotEq, ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.Tuple, ast.List, ast.Dict, ast.Subscript,
)


def _load_original(code):
    """Accept only a small, bounded Python subset before evaluating any code."""
    if not isinstance(code, str) or not code.strip() or len(code) > 12000:
        raise ValueError("Expected nonempty Python source of at most 12000 characters.")
    try:
        tree = ast.parse(code)
    except (SyntaxError, RecursionError) as error:
        raise ValueError(f"Invalid Python syntax: {error}") from error
    nodes = list(ast.walk(tree))
    if len(nodes) > 600 or any(not isinstance(node, ALLOWED_NODES) for node in nodes):
        raise ValueError("Only simple bounded decision logic is allowed; no calls, loops or imports.")
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "choose_action":
        raise ValueError("Define exactly one function named choose_action.")
    for node in tree.body:
        if node is not functions[0] and not (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            raise ValueError("Module-level execution is not allowed.")
    function = functions[0]
    args = function.args
    if (
        [arg.arg for arg in args.args] != PARAMETERS or args.posonlyargs or args.kwonlyargs
        or args.vararg or args.kwarg or len(args.defaults) != 1
        or not isinstance(args.defaults[0], ast.Constant) or args.defaults[0].value is not None
        or function.decorator_list or function.returns
        or any(arg.annotation for arg in args.args)
    ):
        raise ValueError("Use the required four-parameter signature with goal_direction=None.")
    if sum(isinstance(node, ast.FunctionDef) for node in nodes) != 1:
        raise ValueError("Nested functions are not allowed.")
    for node in nodes:
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Special Python names are not allowed.")
        if isinstance(node, ast.Assign) and any(not isinstance(target, ast.Name) for target in node.targets):
            raise ValueError("Assignments may only target local names.")
        if isinstance(node, ast.Constant) and node.value is not None and type(node.value) not in (str, bool):
            raise ValueError("Only strings, booleans and None are needed for decisions.")
    namespace = {"__builtins__": {}}
    try:
        exec(compile(tree, "<validated navigation>", "exec"), namespace)
    except Exception as error:
        raise ValueError(f"Navigation module could not be loaded: {error}") from error
    return namespace["choose_action"]


def load_navigation(code):
    """Load only bounded code; behavioral tests call the returned public entrypoint."""
    if not isinstance(code, str) or not code.strip() or len(code) > 12000:
        raise ValueError("Expected a Python navigation module of at most 12000 characters.")
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError("Invalid navigation source.") from error
    if (len(tree.body) != 2 or any(not isinstance(node, ast.FunctionDef) for node in tree.body)
            or [node.name for node in tree.body] != ["choose_action", "decide_next_move"]):
        raise ValueError("Define choose_action followed by decide_next_move.")
    _load_original(ast.unparse(tree.body[0]))
    wrapper = tree.body[1]
    args = wrapper.args
    if (args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults
            or [arg.arg for arg in args.args] != ["state"] or args.args[0].annotation
            or wrapper.decorator_list or wrapper.returns):
        raise ValueError("The public signature must be decide_next_move(state).")
    nodes = list(ast.walk(wrapper))
    if (len(nodes) > 600 or any(not isinstance(node, ALLOWED_NODES + (ast.Call,)) for node in nodes)
            or sum(isinstance(node, ast.FunctionDef) for node in nodes) != 1):
        raise ValueError("Use only bounded sensor-adapter statements.")
    for node in nodes:
        if isinstance(node, ast.Call) and (
                not isinstance(node.func, ast.Name) or node.func.id != "choose_action"
                or node.keywords or len(node.args) not in (3, 4)):
            raise ValueError("The adapter may call only choose_action with its sensor arguments.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Special names are not sensor variables.")
        if isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Load):
            raise ValueError("State must not be modified.")
        if isinstance(node, ast.Assign) and any(
                not isinstance(target, ast.Name) or target.id in {"state", "choose_action", "decide_next_move"}
                for target in node.targets):
            raise ValueError("Assignments must use local adapter variables.")
        if isinstance(node, ast.Constant) and node.value is not None and type(node.value) not in (str, bool):
            raise ValueError("Only strings, booleans and None are supported.")
        if isinstance(node, ast.Expr) and not (
                isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            raise ValueError("Standalone expressions must be docstrings.")
    namespace = {"__builtins__": {}}
    exec(compile(tree, "<validated navigation>", "exec"), namespace)
    return namespace["decide_next_move"]


def planned_action(plan, front, left, right, goal):
    conditions = {
        "goal_ahead_and_clear": goal == "AHEAD" and not front,
        "goal_left_and_clear": goal == "LEFT" and not left,
        "goal_right_and_clear": goal == "RIGHT" and not right,
        "front_clear": not front,
        "left_clear": not left,
        "right_clear": not right,
        "all_blocked": front and left and right,
    }
    for rule in plan["decisions"]:
        if conditions[rule["condition"]]:
            return rule["action"]
    raise ValueError("The plan has no matching decision.")


def check_navigation(code, plan):
    validate_plan(plan)
    decide = load_navigation(code)
    cases = []
    for front, left, right, ahead_goal, left_goal, right_goal in product((False, True), repeat=6):
        state = {
            "front_blocked": front, "left_blocked": left, "right_blocked": right,
            "goal_ahead": ahead_goal, "goal_on_left": left_goal, "goal_on_right": right_goal,
        }
        clear_goals = [name for name, wall, indicated in (
            ("AHEAD", front, ahead_goal), ("LEFT", left, left_goal), ("RIGHT", right, right_goal))
            if indicated and not wall]
        goal = clear_goals[0] if clear_goals else None
        supplied = state.copy()
        try:
            actual = decide(supplied)
            if supplied != state:
                raise ValueError("Navigation changed its input state.")
        except Exception as error:
            raise ValueError(f"Navigation failed for {(front, left, right, goal)}: {error}") from error
        expected = planned_action(plan, front, left, right, goal)
        blocked = {"FORWARD": front, "LEFT": left, "RIGHT": right}
        if not isinstance(actual, str) or actual not in (*blocked, "STOP"):
            raise ValueError("Navigation returned an invalid action.")
        if actual != "STOP" and blocked[actual]:
            raise ValueError("Navigation would move into a blocked direction.")
        if (actual == "STOP") != (front and left and right):
            raise ValueError("Stop only when no safe direction is available.")
        goal_action = {"AHEAD": "FORWARD", "LEFT": "LEFT", "RIGHT": "RIGHT"}.get(goal)
        if goal_action is not None and not blocked[goal_action] and actual != goal_action:
            raise ValueError("Navigation ignored an available safe goal direction.")
        if actual != expected:
            raise ValueError(f"Navigation disagrees with the plan for {(front, left, right, goal)}.")
        cases.append({
            "state": state, "selected_clear_goal": goal, "expected": expected, "actual": actual,
        })
    return cases


def validate_code(code, plan):
    check_navigation(code, plan)
    tree = ast.parse(code)
    if ast.dump(tree.body[0]) != ast.dump(ast.parse(ORIGINAL_CODE).body[0]):
        raise ValueError("The previous choose_action function must be retained unchanged.")
    if any(token.type == tokenize.COMMENT for token in tokenize.generate_tokens(io.StringIO(code).readline)):
        raise ValueError("Return code only, without commented examples.")
    returns = [node for node in ast.walk(tree.body[1]) if isinstance(node, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.Call):
        raise ValueError("The adapter must finish with one call to choose_action.")
    return code


def run_developer(plan, *, trace_dir=None):
    validate_plan(plan)
    code = ask_qwen(SYSTEM_PROMPT, json.dumps(plan, ensure_ascii=False), trace_dir=trace_dir)
    return validate_code(code, plan)
