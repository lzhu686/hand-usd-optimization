#!/usr/bin/env python3
"""
URDF to USD Converter for Wuji Hand

Uses IsaacLab UrdfConverter to generate USD with full physics, joints, and
collision geometry. Also provides ArticulationCfg for IsaacSim loading.

Usage:
    python scripts/urdf_to_usd.py --side right
    python scripts/urdf_to_usd.py --side left
    python scripts/urdf_to_usd.py --side both
"""

import argparse
import sys
from pathlib import Path

# NOTE: isaaclab.sim / actuators / assets imports are deferred into
# get_wujihand_config() because they require SimulationApp to be
# instantiated first (Carbonite plugin system). The __main__ block
# below handles that via AppLauncher before any conversion runs.

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent.parent  # hand-usd-optimization/
URDF_DIR = PROJECT_DIR / "wuji-hand-description" / "urdf"
RAW_USD_DIR = PROJECT_DIR / "usd_raw"
FINAL_USD_DIR = PROJECT_DIR / "fused"
BLENDER_USD_DIR = PROJECT_DIR / "usd"  # Blender debug exports (UV source)
USD_FILE_NAME = "wujihand"


# ---------------------------------------------------------------------------
# Hand parameters
# ---------------------------------------------------------------------------


def get_hand_params(hand_side: str) -> dict:
    """Return control parameters (PD gains, effort limits) for the hand."""
    kp = {
        f"{hand_side}_finger(1|2|3|4|5)_joint(1|2)": 2,
        f"{hand_side}_finger(1|2|3|4|5)_joint3": 1,
        f"{hand_side}_finger(1|2|3|4|5)_joint4": 0.8,
    }
    kd = {
        f"{hand_side}_finger.*_joint(1|2)": 0.05,
        f"{hand_side}_finger.*_joint(3|4)": 0.03,
    }
    effort_limits = {
        f"{hand_side}_finger(1|2|3|4|5)_joint(1|2)": 3,
        f"{hand_side}_finger(1|2|3|4|5)_joint3": 1.5,
        f"{hand_side}_finger(1|2|3|4|5)_joint4": 1,
    }
    return {"kp": kp, "kd": kd, "effort_limits": effort_limits}


# ---------------------------------------------------------------------------
# URDF -> USD conversion via IsaacLab
# ---------------------------------------------------------------------------


def convert_urdf_to_usd(hand_side: str) -> Path:
    """Convert URDF to USD via IsaacLab UrdfConverter.

    Generates a full USD with physics, joints, collision geometry, and drives.
    Returns the output directory path.
    """
    from isaaclab.sim.converters import UrdfConverter, UrdfConverterCfg

    urdf_path = str(URDF_DIR / f"{hand_side}.urdf")
    params = get_hand_params(hand_side)
    raw_usd_dir = RAW_USD_DIR / hand_side

    print(f"Converting {hand_side} hand: {urdf_path} -> {raw_usd_dir}")

    cfg = UrdfConverterCfg(
        asset_path=urdf_path,
        usd_dir=str(raw_usd_dir),
        usd_file_name=USD_FILE_NAME,
        force_usd_conversion=True,
        fix_base=True,
        root_link_name=f"{hand_side}_palm_link",
        link_density=1,
        collider_type="convex_hull",
        merge_fixed_joints=False,
        self_collision=True,
        joint_drive=UrdfConverterCfg.JointDriveCfg(
            drive_type="force",
            target_type="position",
            gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                stiffness=params["kp"],
                damping=params["kd"],
            ),
        ),
    )

    UrdfConverter(cfg)
    print(f"  Done: {raw_usd_dir}")
    return raw_usd_dir


# ---------------------------------------------------------------------------
# ArticulationCfg for IsaacSim
# ---------------------------------------------------------------------------


def get_wujihand_config(hand_side: str) -> "ArticulationCfg":
    """Return ArticulationCfg using the final (post-processed) USD."""
    import isaaclab.sim as sim_utils
    from isaaclab.actuators.actuator_cfg import ImplicitActuatorCfg
    from isaaclab.assets.articulation import ArticulationCfg

    params = get_hand_params(hand_side)
    usd_path = str(FINAL_USD_DIR / hand_side / f"{USD_FILE_NAME}.usd")

    return ArticulationCfg(
        spawn=sim_utils.UsdFileCfg(
            usd_path=usd_path,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                disable_gravity=False,
                linear_damping=0.0,
                angular_damping=0.0,
                max_linear_velocity=1000.0,
                max_angular_velocity=1000.0,
                max_depenetration_velocity=10.0,
            ),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                enabled_self_collisions=True,
                solver_position_iteration_count=20,
                solver_velocity_iteration_count=10,
            ),
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.0, 0.0, 0.0),
            rot=(1.0, 0.0, 0.0, 0.0),
            joint_pos={
                f"{hand_side}_finger.*_joint1": 0.06,
                f"{hand_side}_finger.*_joint(2|3|4)": 0.0,
            },
        ),
        actuators={
            "fingers": ImplicitActuatorCfg(
                joint_names_expr=[f"{hand_side}_finger.*_joint.*"],
                effort_limit_sim=params["effort_limits"],
                stiffness=params["kp"],
                damping=params["kd"],
            ),
        },
        soft_joint_pos_limit_factor=1.0,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(sides):
    if not URDF_DIR.exists():
        print(f"ERROR: URDF directory not found: {URDF_DIR}")
        sys.exit(1)

    for side in sides:
        convert_urdf_to_usd(side)

    print("\nDone! USD files generated.")


if __name__ == "__main__":
    # Parse args BEFORE AppLauncher (which also adds its own args)
    parser = argparse.ArgumentParser(description="Convert Wuji Hand URDF to USD")
    parser.add_argument(
        "--side",
        choices=["right", "left", "both"],
        default="both",
        help="Which hand to convert",
    )
    # Launch SimulationApp first so isaaclab.sim.converters is importable
    from isaaclab.app import AppLauncher

    AppLauncher.add_app_launcher_args(parser)
    args_cli = parser.parse_args()
    # Force headless for URDF->USD conversion (no GUI needed)
    args_cli.headless = True
    app_launcher = AppLauncher(args_cli)
    simulation_app = app_launcher.app

    sides = ["right", "left"] if args_cli.side == "both" else [args_cli.side]
    try:
        main(sides)
    finally:
        simulation_app.close()
