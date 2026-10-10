"""Ask Qwen for pytest tests, then reject executable code outside the test contract."""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from analyst_agent import validate_requirements
from artifact_io import write_json, write_text
from developer_agent import validate_code
from planner_agent import validate_plan


ROOT = Path(__file__).resolve().parent
SYSTEM_PROMPT = """Write a short complete pytest test module, with Python code only.
Use the supplied brief, requirements, plan and navigation source as data.
Import exactly:
import pytest
from generated.navigation_logic import decide_next_move
from runner import scenario_cases
scenario_cases() supplies an independently written oracle: 64 (state, expected)
pairs covering all obstacle and goal-flag combinations of this group's plan.
Use @pytest.mark.parametrize("state, expected", scenario_cases()).
Define one function test_navigation(state, expected).
Copy the state into a local before variable, call decide_next_move(state),
and assert that its result equals expected and that state still equals before.
Also check that the action belongs to FORWARD, LEFT, RIGHT, STOP.
Do not import anything else, define fixtures or helpers, access files or the
network, skip tests, catch exceptions, modify the inputs, or add Markdown.
Never implement the navigation function in the test. Test the supplied module.
"""


def validate_test_code(code):
    if not isinstance(code, str) or not code.strip() or len(code) > 8000 or "```" in code:
        raise ValueError("Expected a small Python test module without Markdown.")
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError("Invalid generated test syntax.") from error
    allowed = (ast.Module, ast.Import, ast.ImportFrom, ast.alias, ast.FunctionDef,
               ast.arguments, ast.arg, ast.Assign, ast.Name, ast.Load, ast.Store,
               ast.Call, ast.Attribute, ast.Constant, ast.Tuple, ast.List, ast.Set,
               ast.Assert, ast.Compare, ast.Eq, ast.In, ast.Expr)
    nodes = list(ast.walk(tree))
    if len(nodes) > 400 or any(not isinstance(node, allowed) for node in nodes):
        raise ValueError("Tests may contain only imports, parametrization, assignments and assertions.")
    imports = []
    functions = []
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            if len(statement.names) != 1 or statement.names[0].name != "pytest" or statement.names[0].asname:
                raise ValueError("Only import pytest.")
            imports.append("pytest")
        elif isinstance(statement, ast.ImportFrom):
            permitted = {"generated.navigation_logic": "decide_next_move", "runner": "scenario_cases"}
            if (statement.level or statement.module not in permitted or len(statement.names) != 1
                    or statement.names[0].name != permitted[statement.module] or statement.names[0].asname):
                raise ValueError("Unexpected generated-test import.")
            imports.append(statement.module)
        elif isinstance(statement, ast.FunctionDef):
            functions.append(statement)
        else:
            raise ValueError("Unexpected top-level test statement.")
    if sorted(imports) != ["generated.navigation_logic", "pytest", "runner"] or len(functions) != 1:
        raise ValueError("Use the three required imports and one test function.")
    function = functions[0]
    args = function.args
    if (not function.name.startswith("test_") or [a.arg for a in args.args] != ["state", "expected"]
            or args.posonlyargs or args.kwonlyargs or args.defaults or args.vararg or args.kwarg
            or function.returns or any(a.annotation for a in args.args)):
        raise ValueError("Use test_navigation(state, expected).")
    if len(function.decorator_list) != 1:
        raise ValueError("Parametrize the test over the complete scenario table.")
    decorator = function.decorator_list[0]
    if (not isinstance(decorator, ast.Call) or ast.unparse(decorator.func) != "pytest.mark.parametrize"
            or len(decorator.args) != 2 or not isinstance(decorator.args[0], ast.Constant)
            or str(decorator.args[0].value).replace(" ", "") != "state,expected"
            or ast.unparse(decorator.args[1]) != "scenario_cases()"):
        raise ValueError("The test must cover all 64 state/expected pairs.")
    for node in nodes:
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name not in ("pytest.mark.parametrize", "scenario_cases", "decide_next_move", "state.copy"):
                raise ValueError(f"Unexpected call: {name}")
            if node.keywords:
                raise ValueError("Keyword calls are unnecessary in this test.")
        if isinstance(node, ast.Attribute) and node.attr not in ("mark", "parametrize", "copy"):
            raise ValueError("Unexpected attribute access.")
        if isinstance(node, ast.Assign):
            if any(not isinstance(t, ast.Name) or t.id in
                   {"state", "expected", "pytest", "decide_next_move", "scenario_cases"}
                   for t in node.targets):
                raise ValueError("Do not replace the test inputs or imported functions.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Special Python names are not allowed.")
        if isinstance(node, ast.FunctionDef) and node is not function:
            raise ValueError("Nested test functions are not allowed.")
    if sum(isinstance(n, ast.Assert) for n in nodes) < 3:
        raise ValueError("Check the expected action, action vocabulary and input preservation.")
    if not any(isinstance(n, ast.Call) and ast.unparse(n) == "decide_next_move(state)" for n in nodes):
        raise ValueError("The actual navigation function must be called.")
    return code


def run_test_agent(requirements, plan, navigation_code, brief, *, ask, trace_dir):
    validate_requirements(requirements)
    validate_plan(plan)
    validate_code(navigation_code, plan)
    payload = {"brief": brief, "requirements": requirements, "plan": plan,
               "navigation_code": navigation_code}
    code = ask(SYSTEM_PROMPT, json.dumps(payload), trace_dir=trace_dir)
    return validate_test_code(code)


def execute_tests(code, navigation_code, output_dir, *, timeout=45):
    validate_test_code(code)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    write_text(output_dir / "test_navigation.py", code)
    write_text(output_dir / "generated/__init__.py", "")
    write_text(output_dir / "generated/navigation_logic.py", navigation_code)
    command = [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
               "--junitxml=results.xml", "test_navigation.py"]
    environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                       PYTHONUTF8="1", OPENBLAS_NUM_THREADS="2", OMP_NUM_THREADS="2")
    with (output_dir / "pytest.log").open("w", encoding="utf-8") as stream:
        process = subprocess.run(command, cwd=output_dir, env=environment,
                                 stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    xml = ET.parse(output_dir / "results.xml").getroot()
    suites = list(xml.iter("testsuite"))
    counts = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    counts["returncode"] = process.returncode
    counts["passed"] = (process.returncode == 0 and counts["tests"] == 64
                        and not any(counts[k] for k in ("failures", "errors", "skipped")))
    write_json(output_dir / "result.json", counts)
    return counts
