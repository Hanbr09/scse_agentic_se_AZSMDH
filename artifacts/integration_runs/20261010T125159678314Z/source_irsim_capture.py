"""Run the unchanged teacher script and observe its frames before cleanup."""

import argparse
import json
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    args.capture.mkdir(parents=True, exist_ok=True)
    import matplotlib
    if not args.interactive:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import irsim
    original_make = irsim.make

    def observed_make(*positional, **keywords):
        keywords["display"] = args.interactive
        env = original_make(*positional, **keywords)
        robot = env.robot_list[0]
        poses = [[float(value) for value in robot.state[:, 0]]]
        original_step, original_end, original_render = env.step, env.end, env.render
        frames = []

        def observed_step(*step_args, **step_keywords):
            result = original_step(*step_args, **step_keywords)
            poses.append([float(value) for value in robot.state[:, 0]])
            return result

        def observed_render(*render_args, **render_keywords):
            result = original_render(*render_args, **render_keywords)
            if len(poses) % 6 == 0:
                from PIL import Image
                figure = plt.gcf()
                figure.canvas.draw()
                frame = Image.frombuffer("RGBA", figure.canvas.get_width_height(),
                                         figure.canvas.buffer_rgba(), "raw", "RGBA", 0, 1).convert("RGB")
                frame.thumbnail((600, 600))
                frames.append(frame)
            return result

        def observed_end(*end_args, **end_keywords):
            # Only record measurements: actions, obstacles and physics are unchanged.
            before_cleanup = {
                "poses": poses, "done_before_cleanup": bool(env.done()),
                "collision_before_cleanup": bool(robot.collision),
                "goal": [float(value) for value in robot.goal[:, 0]],
                "world": args.world.name,
            }
            (args.capture / "trajectory.json").write_text(
                json.dumps(before_cleanup, indent=2) + "\n", encoding="utf-8")
            figure = plt.gcf()
            axis = figure.axes[0]
            axis.plot([p[0] for p in poses], [p[1] for p in poses],
                      color="#067647", linewidth=1.5, label="Observed trajectory")
            axis.set_title(args.world.stem.replace("_", " ").title())
            axis.legend(loc="upper left")
            figure.savefig(args.capture / "trajectory.png", dpi=130)
            if frames:
                frames[0].save(args.capture / "simulation.gif", save_all=True,
                               append_images=frames[1:], duration=100, loop=0)
            return original_end(*end_args, **end_keywords)

        env.step, env.end, env.render = observed_step, observed_end, observed_render
        return env

    irsim.make = observed_make
    sys.path.insert(0, str(args.script.resolve().parent))
    sys.argv = [str(args.script), str(args.world)]
    try:
        runpy.run_path(str(args.script), run_name="__main__")
    finally:
        irsim.make = original_make
        plt.close("all")


if __name__ == "__main__":
    main()
