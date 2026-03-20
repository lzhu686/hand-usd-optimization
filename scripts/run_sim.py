"""
run_sim.py
Full pipeline: URDF -> raw USD -> fuse appearance -> IsaacSim validation.

Usage:
    python scripts/run_sim.py --side left
    python scripts/run_sim.py --side right --regenerate
"""

import argparse
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="WujiHand simulation")
AppLauncher.add_app_launcher_args(parser)
parser.add_argument("--side", choices=["left", "right"], default="left")
parser.add_argument("--regenerate", action="store_true", help="Force USD regeneration")
args_cli = parser.parse_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import subprocess
import sys

import numpy as np
import omni.usd
import torch
from pathlib import Path
from pxr import UsdPhysics

import isaaclab.sim as sim_utils
import isaacsim.core.utils.prims as prim_utils
from isaaclab.assets import Articulation
from isaaclab.utils.math import saturate

from urdf_to_usd import (
    FINAL_USD_DIR,
    RAW_USD_DIR,
    USD_FILE_NAME,
    convert_urdf_to_usd,
    get_wujihand_config,
)

HAND_SIDE = args_cli.side


def prepare_usd(force: bool = False):
    """
    USD preparation pipeline:
    1. URDF -> raw USD (IsaacLab UrdfConverter)
    2. raw USD + Blender appearance -> final USD (fuse_rl_appearance.py)
    """
    final_usd = FINAL_USD_DIR / f"{USD_FILE_NAME}.usd"

    if final_usd.exists() and not force:
        print(f"[prepare] Final USD exists: {final_usd} (use --regenerate to force)")
        return

    # Step 1: URDF -> raw USD
    print("[prepare] Step 1: URDF -> raw USD ...")
    convert_urdf_to_usd(HAND_SIDE)

    # Step 2: Fuse appearance (textures + dual materials)
    print("[prepare] Step 2: Fusing appearance ...")
    fuse_script = Path(__file__).parent / "fuse_rl_appearance.py"
    cmd = [
        sys.executable,
        str(fuse_script),
        "--side", HAND_SIDE,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[prepare] fuse_rl_appearance failed:\n{result.stderr}")
        raise RuntimeError("fuse_rl_appearance.py failed")
    print(result.stdout)
    print(f"[prepare] Final USD: {final_usd}")


def design_scene():
    """Set up scene with WujiHand."""
    cfg = sim_utils.GroundPlaneCfg()
    cfg.func("/World/ground", cfg)
    cfg = sim_utils.DomeLightCfg(intensity=2000.0)
    cfg.func("/World/light", cfg)

    prim_utils.create_prim("/World/hand", "Xform")
    hand_cfg = get_wujihand_config(HAND_SIDE).replace(
        prim_path="/World/hand/WujiHand"
    )
    hand = Articulation(cfg=hand_cfg)

    # Filter collisions between palm and finger link2
    stage = omni.usd.get_context().get_stage()
    base_path = "/World/hand/WujiHand"
    palm_candidates = [
        f"{base_path}/{HAND_SIDE}_palm_link",
        f"{base_path}/wujihand/{HAND_SIDE}_palm_link",
    ]
    palm_prim = None
    base_prefix = base_path
    for p in palm_candidates:
        palm_prim = stage.GetPrimAtPath(p)
        if palm_prim:
            base_prefix = p.replace(f"/{HAND_SIDE}_palm_link", "")
            break

    if palm_prim:
        filtered_api = UsdPhysics.FilteredPairsAPI.Apply(palm_prim)
        filtered_rel = filtered_api.CreateFilteredPairsRel()
        for i in range(1, 6):
            finger_prim = stage.GetPrimAtPath(
                f"{base_prefix}/{HAND_SIDE}_finger{i}_link2"
            )
            if finger_prim:
                filtered_rel.AddTarget(finger_prim.GetPath())
    else:
        print("[WARNING] palm_link prim not found, skipping collision filter")

    return hand


def run_simulator(sim, hand):
    """Run simulation with trajectory tracking."""
    sim_dt = sim.get_physics_dt()
    count = 0

    trajectory = np.load(Path(__file__).parent.parent / "data" / "wave.npy")
    mujoco_joints = [
        f"{HAND_SIDE}_finger{i}_joint{j}"
        for i in range(1, 6)
        for j in range(1, 5)
    ]

    joint_name_to_idx = {name: idx for idx, name in enumerate(hand.joint_names)}
    joint_mapping = [
        (mj_idx, joint_name_to_idx[name])
        for mj_idx, name in enumerate(mujoco_joints)
        if name in joint_name_to_idx
    ]
    joint_pos_target = torch.zeros(len(hand.joint_names), device=args_cli.device)

    while simulation_app.is_running():
        if count % 500 == 0:
            count = 0
            joint_pos = hand.data.default_joint_pos.clone()
            joint_vel = hand.data.default_joint_vel.clone()
            hand.set_joint_position_target(joint_pos)
            hand.write_joint_state_to_sim(joint_pos, joint_vel)
            hand.reset()
            print("[INFO] Resetting robot state...")

        joint_pos_target.zero_()
        traj_data = trajectory[count % len(trajectory)]
        for mj_idx, hand_idx in joint_mapping:
            joint_pos_target[hand_idx] = traj_data[mj_idx]

        clamped = saturate(
            joint_pos_target,
            hand.data.soft_joint_pos_limits[..., 0],
            hand.data.soft_joint_pos_limits[..., 1],
        )
        hand.set_joint_position_target(clamped)
        hand.write_data_to_sim()

        sim.step()
        count += 1
        hand.update(sim_dt)


def main():
    prepare_usd(force=args_cli.regenerate)

    sim = sim_utils.SimulationContext(
        sim_utils.SimulationCfg(dt=1.0 / 100, device=args_cli.device)
    )
    sim.set_camera_view([3.5, 0.0, 3.2], [0.0, 0.0, 0.5])
    hand = design_scene()
    sim.reset()
    print("WujiHand simulation running...")
    run_simulator(sim, hand)


if __name__ == "__main__":
    main()
    simulation_app.close()
