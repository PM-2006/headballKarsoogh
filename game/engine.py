from __future__ import annotations

from dataclasses import dataclass, field, asdict
from math import hypot
import os
import random

from .validators import validate_strategy


PHYSICS_VERSION = "v3-headball-fast-arcade"


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class GameConfig:
    # Playground & Geometry
    width: float = 1500.0
    height: float = 860.0
    ground_y: float = 730.0
    goal_depth: float = 122.0
    goal_height: float = 205.0
    goal_post_radius: float = 7.0

    # Ball Physics & Elasticity
    ball_radius: float = 23.0
    gravity: float = 1700.0
    ball_max_speed: float = 1450.0
    floor_bounce: float = 0.58
    floor_friction: float = 0.980
    horizontal_drag_per_60fps: float = 0.999
    ball_wall_bounce: float = 0.84
    ball_ceiling_bounce: float = 0.82
    ball_body_restitution: float = 0.46
    ball_head_restitution: float = 0.78
    ball_contact_impulse_cap: float = 850.0
    ball_sleep_speed: float = 8.0
    body_ball_impulse_scale: float = 0.05

    # Player Dimensions & Dynamics
    player_width: float = 66.0
    player_height: float = 84.0
    player_speed: float = 385.0
    player_jump_speed: float = 790.0
    player_gravity: float = 2050.0
    player_acceleration: float = 2800.0
    player_deceleration: float = 3400.0
    player_air_acceleration: float = 1300.0
    player_air_deceleration: float = 90.0
    jump_cooldown: float = 0.38
    head_radius: float = 34.0
    head_center_y: float = 18.0
    body_inset_x: float = 10.0
    body_top_offset: float = 36.0
    player_bump_restitution: float = 0.32
    player_bump_extra_separation: float = 1.5
    player_contact_velocity_transfer: float = 0.18

    # Kicks & Actions
    kick_reach: float = 126.0
    kick_low_x: float = 850.0
    kick_low_y: float = -170.0
    kick_low_cooldown: float = 0.40
    kick_high_x: float = 760.0
    kick_high_y: float = -620.0
    kick_high_cooldown: float = 0.46
    kick_clear_x: float = 1000.0
    kick_clear_y: float = -360.0
    kick_clear_cooldown: float = 0.52
    kick_keep_ball_velocity: float = 0.38
    kick_player_velocity_transfer: float = 0.52
    move_deadzone: float = 6.0

    # Anti-lock / fast-arcade tuning. Players rebound instead of becoming
    # a motionless wall, and truly contested ball touches pop upward.
    player_bump_restitution: float = 0.32
    player_bump_extra_separation: float = 1.5
    # Player-vs-player collision uses a narrower box than the full sprite width
    # so two players can stand shoulder-to-shoulder without an ugly visible gap.
    # Effective bump width = player_width - 2*player_collision_inset.
    player_collision_inset: float = 6.0
    player_contact_velocity_transfer: float = 0.18
    running_touch_lift: float = 135.0
    contested_ball_pop_y: float = 640.0
    contested_ball_horizontal_keep: float = 0.65
    contested_player_recoil: float = 95.0
    contested_kick_pop_y: float = 820.0
    contested_kick_horizontal_keep: float = 0.55
    contested_kick_recoil: float = 135.0
    contested_escape_x: float = 175.0

    # Anti-Stall Watchdog
    stall_speed_threshold: float = 45.0
    stall_pop_after: float = 6.0
    stall_kickoff_after: float = 10.0
    stall_pop_vx: float = 220.0
    stall_pop_vy: float = 640.0

    # Match Timing & Precision
    match_time: float = 60.0
    kickoff_freeze: float = 0.90
    physics_fps: int = 60
    record_fps: int = 20
    physics_substeps: int = 2

    def to_dict(self) -> dict:
        return asdict(self)


def get_base_config() -> GameConfig:
    """Config from code defaults + environment variables (no DB overrides)."""
    return GameConfig(
        # Playground Geometry
        width=_env_float("GAME_PLAYGROUND_WIDTH", 1500.0),
        height=_env_float("GAME_PLAYGROUND_HEIGHT", 860.0),
        ground_y=_env_float("GAME_GROUND_Y", 730.0),
        goal_depth=_env_float("GAME_GOAL_DEPTH", 122.0),
        goal_height=_env_float("GAME_GOAL_HEIGHT", 205.0),
        goal_post_radius=_env_float("GAME_GOAL_POST_RADIUS", 7.0),

        # Ball Physics & Elasticity
        ball_radius=_env_float("GAME_BALL_RADIUS", 23.0),
        gravity=_env_float("GAME_GRAVITY", 1700.0),
        ball_max_speed=_env_float("GAME_BALL_MAX_SPEED", 1450.0),
        floor_bounce=_env_float("GAME_FLOOR_BOUNCE", 0.58),
        floor_friction=_env_float("GAME_FLOOR_FRICTION", 0.980),
        horizontal_drag_per_60fps=_env_float("GAME_BALL_AIR_DRAG", 0.999),
        ball_wall_bounce=_env_float("GAME_BALL_WALL_BOUNCE", 0.84),
        ball_ceiling_bounce=_env_float("GAME_BALL_CEILING_BOUNCE", 0.82),
        ball_body_restitution=_env_float("GAME_BALL_BODY_RESTITUTION", 0.46),
        ball_head_restitution=_env_float("GAME_BALL_HEAD_RESTITUTION", 0.78),
        ball_contact_impulse_cap=_env_float("GAME_BALL_CONTACT_IMPULSE_CAP", 850.0),
        ball_sleep_speed=_env_float("GAME_BALL_SLEEP_SPEED", 8.0),
        body_ball_impulse_scale=_env_float("GAME_BALL_IMPULSE_SCALE", 0.05),

        # Player Dimensions & Dynamics
        player_width=_env_float("GAME_PLAYER_WIDTH", 66.0),
        player_height=_env_float("GAME_PLAYER_HEIGHT", 84.0),
        player_speed=_env_float("GAME_PLAYER_SPEED", 385.0),
        player_jump_speed=_env_float("GAME_PLAYER_JUMP_SPEED", 790.0),
        player_gravity=_env_float("GAME_PLAYER_GRAVITY", 2050.0),
        player_acceleration=_env_float("GAME_PLAYER_ACCELERATION", 2800.0),
        player_deceleration=_env_float("GAME_PLAYER_DECELERATION", 3400.0),
        player_air_acceleration=_env_float("GAME_PLAYER_AIR_ACCELERATION", 1300.0),
        player_air_deceleration=_env_float("GAME_PLAYER_AIR_DECELERATION", 90.0),
        jump_cooldown=_env_float("GAME_JUMP_COOLDOWN", 0.38),
        head_radius=_env_float("GAME_PLAYER_HEAD_RADIUS", 34.0),
        head_center_y=_env_float("GAME_PLAYER_HEAD_CENTER_Y", 18.0),
        body_inset_x=_env_float("GAME_PLAYER_BODY_INSET_X", 10.0),
        body_top_offset=_env_float("GAME_PLAYER_BODY_TOP_OFFSET", 36.0),
        player_bump_restitution=_env_float("GAME_PLAYER_BUMP_RESTITUTION", 0.32),
        player_bump_extra_separation=_env_float("GAME_PLAYER_BUMP_SEPARATION", 1.5),
        player_collision_inset=_env_float("GAME_PLAYER_COLLISION_INSET", 6.0),
        player_contact_velocity_transfer=_env_float("GAME_PLAYER_CONTACT_VELOCITY_TRANSFER", 0.18),

        # Kicks & Actions
        kick_reach=_env_float("GAME_KICK_REACH", 126.0),
        kick_low_x=_env_float("GAME_KICK_LOW_X", 850.0),
        kick_low_y=_env_float("GAME_KICK_LOW_Y", -170.0),
        kick_low_cooldown=_env_float("GAME_KICK_LOW_COOLDOWN", 0.40),
        kick_high_x=_env_float("GAME_KICK_HIGH_X", 760.0),
        kick_high_y=_env_float("GAME_KICK_HIGH_Y", -620.0),
        kick_high_cooldown=_env_float("GAME_KICK_HIGH_COOLDOWN", 0.46),
        kick_clear_x=_env_float("GAME_KICK_CLEAR_X", 1000.0),
        kick_clear_y=_env_float("GAME_KICK_CLEAR_Y", -360.0),
        kick_clear_cooldown=_env_float("GAME_KICK_CLEAR_COOLDOWN", 0.52),
        kick_keep_ball_velocity=_env_float("GAME_KICK_KEEP_BALL_VELOCITY", 0.38),
        kick_player_velocity_transfer=_env_float("GAME_KICK_PLAYER_VELOCITY_TRANSFER", 0.52),
        move_deadzone=_env_float("GAME_MOVE_DEADZONE", 6.0),

        # Anti-Lock & Contested Dynamics
        running_touch_lift=_env_float("GAME_RUNNING_TOUCH_LIFT", 135.0),
        contested_ball_pop_y=_env_float("GAME_CONTESTED_BALL_POP_Y", 640.0),
        contested_ball_horizontal_keep=_env_float("GAME_CONTESTED_BALL_HORIZONTAL_KEEP", 0.65),
        contested_player_recoil=_env_float("GAME_CONTESTED_PLAYER_RECOIL", 95.0),
        contested_kick_pop_y=_env_float("GAME_CONTESTED_KICK_POP_Y", 820.0),
        contested_kick_horizontal_keep=_env_float("GAME_CONTESTED_KICK_HORIZONTAL_KEEP", 0.55),
        contested_kick_recoil=_env_float("GAME_CONTESTED_KICK_RECOIL", 135.0),
        contested_escape_x=_env_float("GAME_CONTESTED_ESCAPE_X", 175.0),

        # Anti-Stall Watchdog
        stall_speed_threshold=_env_float("GAME_STALL_SPEED_THRESHOLD", 45.0),
        stall_pop_after=_env_float("GAME_STALL_POP_AFTER", 6.0),
        stall_kickoff_after=_env_float("GAME_STALL_KICKOFF_AFTER", 10.0),
        stall_pop_vx=_env_float("GAME_STALL_POP_VX", 220.0),
        stall_pop_vy=_env_float("GAME_STALL_POP_VY", 640.0),

        # Match Timing & Precision
        match_time=_env_float("GAME_MATCH_TIME", 60.0),
        kickoff_freeze=_env_float("GAME_KICKOFF_FREEZE", 0.90),
        physics_fps=_env_int("GAME_PHYSICS_FPS", 60),
        record_fps=_env_int("GAME_RECORD_FPS", 20),
        physics_substeps=_env_int("GAME_PHYSICS_SUBSTEPS", 2),
    )


def get_game_config() -> GameConfig:
    """Effective config: base (defaults+env) with admin DB overrides layered on.

    DB overrides are applied lazily so this stays safe to call before the
    database/migrations exist (falls back to the base config).
    """
    base = get_base_config()
    try:
        from .gameconfig import apply_overrides, load_overrides
        return apply_overrides(base, load_overrides())
    except Exception:
        return base

MAX_BATCH_MATCHES = 50
DEFAULT_BATCH_MATCHES = 50

CONFIG = get_base_config()


@dataclass(slots=True)
class Player:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    face: int = 1
    on_ground: bool = True
    kick_cd: float = 0.0
    jump_cd: float = 0.0


@dataclass(slots=True)
class Ball:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0


@dataclass(slots=True)
class World:
    players: list[Player]
    ball: Ball
    score: list[int] = field(default_factory=lambda: [0, 0])
    remaining_time: float = 60.0
    freeze: float = 0.0
    debug: list[dict] = field(default_factory=lambda: [{}, {}])
    contest_escape_dir: int = 1
    stall_time: float = 0.0
    stall_popped: bool = False


@dataclass(frozen=True)
class Intent:
    action: str
    move_dir: int = 0
    jump: bool = False
    kick: str | None = None


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _move_toward(current: float, target: float, max_delta: float) -> float:
    if current < target:
        return min(current + max_delta, target)
    if current > target:
        return max(current - max_delta, target)
    return target


def _player_center(player: Player, config: GameConfig) -> tuple[float, float]:
    return player.x + config.player_width / 2, player.y + config.player_height / 2


def _head_center(player: Player, config: GameConfig) -> tuple[float, float]:
    return player.x + config.player_width / 2, player.y + config.head_center_y


def _new_world(rng: random.Random, config: GameConfig | None = None) -> World:
    if config is None:
        config = get_game_config()
    p0_x = config.goal_depth + 150.0
    p1_x = max(p0_x + config.player_width + 10.0, config.width - config.goal_depth - 150.0 - config.player_width)
    drop_y = max(50.0, config.ground_y - 460.0) if config.ground_y > 460.0 else config.height * 0.2
    world = World(
        players=[
            Player(p0_x, config.ground_y - config.player_height, face=1),
            Player(p1_x, config.ground_y - config.player_height, face=-1),
        ],
        ball=Ball(config.width / 2, drop_y),
        remaining_time=config.match_time,
    )
    _kickoff(world, rng, config, initial=True)
    return world


def _kickoff(world: World, rng: random.Random, config: GameConfig, initial: bool = False):
    p0, p1 = world.players
    p0.x = config.goal_depth + 150.0
    p1.x = max(p0.x + config.player_width + 10.0, config.width - config.goal_depth - 150.0 - config.player_width)
    for player, face in ((p0, 1), (p1, -1)):
        player.y = config.ground_y - config.player_height
        player.vx = 0.0
        player.vy = 0.0
        player.face = face
        player.on_ground = True
        player.kick_cd = 0.0
        player.jump_cd = 0.0

    # A centred falling restart is closer to the readable arcade rhythm of
    # Head Ball than the old hard horizontal launch. The tiny seeded drift prevents every kickoff from being identical. Batch
    # comparisons swap sides, so this randomness does not favor one strategy.
    direction = rng.choice((-1, 1))
    world.contest_escape_dir = direction
    world.ball.x = config.width / 2
    world.ball.y = max(50.0, config.ground_y - 460.0) if config.ground_y > 460.0 else config.height * 0.2
    world.ball.vx = direction * rng.uniform(30.0, 65.0)
    world.ball.vy = rng.uniform(15.0, 35.0)

    if not initial:
        world.freeze = config.kickoff_freeze


def _can_kick(player: Player, ball: Ball, config: GameConfig) -> bool:
    px, py = _player_center(player, config)
    return (
        hypot(ball.x - px, ball.y - py) <= config.kick_reach
        and player.kick_cd <= 0.0
    )


def _sensor_state(world: World, team: int, config: GameConfig) -> dict:
    me = world.players[team]
    opponent = world.players[1 - team]
    ball = world.ball
    my_x, my_y = _player_center(me, config)
    opp_x, opp_y = _player_center(opponent, config)
    dx, dy = ball.x - my_x, ball.y - my_y
    odx, ody = ball.x - opp_x, ball.y - opp_y

    # Goal distance now refers to the actual front goal line, not the back net.
    own_goal_x = config.goal_depth if team == 0 else config.width - config.goal_depth
    enemy_goal_x = config.width - config.goal_depth if team == 0 else config.goal_depth
    own_half = ball.x < config.width / 2 if team == 0 else ball.x > config.width / 2

    t = 0.38
    predicted_x = _clamp(ball.x + ball.vx * t, 0.0, config.width)
    predicted_y = _clamp(
        ball.y + ball.vy * t + 0.5 * config.gravity * t * t,
        0.0,
        config.ground_y,
    )

    return {
        "my_x": my_x,
        "opponent_x": opp_x,
        "ball_x": ball.x,
        "ball_y": ball.y,
        "ball_vx": ball.vx,
        "ball_vy": ball.vy,
        "ball_speed": hypot(ball.vx, ball.vy),
        "distance_to_ball": hypot(dx, dy),
        "opponent_distance_to_ball": hypot(odx, ody),
        "distance_to_own_goal": abs(my_x - own_goal_x),
        "distance_to_enemy_goal": abs(my_x - enemy_goal_x),
        "ball_distance_to_own_goal": abs(ball.x - own_goal_x),
        "ball_distance_to_enemy_goal": abs(ball.x - enemy_goal_x),
        "predicted_ball_x": predicted_x,
        "predicted_ball_y": predicted_y,
        "remaining_time": world.remaining_time,
        "my_score": world.score[team],
        "opponent_score": world.score[1 - team],
        "score_difference": world.score[team] - world.score[1 - team],
        "can_kick": _can_kick(me, ball, config),
        "on_ground": me.on_ground,
        "ball_in_own_half": own_half,
        "ball_in_enemy_half": not own_half,
        "ball_above_me": ball.y < my_y - 6.0 and abs(dx) < 125.0,
        "ball_moving_toward_me": (
            (ball.vx > 0 and ball.x < my_x)
            or (ball.vx < 0 and ball.x > my_x)
        ),
    }


def _compare(left, operator, right):
    return {
        "<": left < right,
        "<=": left <= right,
        ">": left > right,
        ">=": left >= right,
        "==": left == right,
        "!=": left != right,
    }.get(operator, False)


def _condition_true(cond: dict, state: dict) -> bool:
    right = state[cond["right"]] if cond["rightType"] == "sensor" else cond["right"]
    return _compare(state[cond["left"]], cond["operator"], right)


def _choose_action(strategy: dict, state: dict) -> tuple[int | str, str]:
    for item in sorted(strategy["rules"], key=lambda row: row["priority"]):
        if all(_condition_true(cond, state) for cond in item["conditions"]):
            return item["priority"], item["action"]
    return "default", strategy.get("default_action", "IDLE")


def _direction_to_target(current: float, target: float, deadzone: float) -> int:
    delta = target - current
    if abs(delta) <= deadzone:
        return 0
    return 1 if delta > 0 else -1


def _resolve_intent(action: str, state: dict, team: int, config: GameConfig) -> Intent:
    if action == "MOVE_LEFT":
        return Intent(action, move_dir=-1)
    if action == "MOVE_RIGHT":
        return Intent(action, move_dir=1)
    if action == "MOVE_TO_BALL":
        return Intent(
            action,
            move_dir=_direction_to_target(
                state["my_x"], state["ball_x"], config.move_deadzone
            ),
        )
    if action == "MOVE_TO_GOAL":
        target = (
            config.goal_depth + 42.0
            if team == 0
            else config.width - config.goal_depth - 42.0
        )
        return Intent(
            action,
            move_dir=_direction_to_target(state["my_x"], target, config.move_deadzone),
        )
    if action == "MOVE_TO_CENTER":
        target = config.width / 2 + (-80.0 if team == 0 else 80.0)
        return Intent(
            action,
            move_dir=_direction_to_target(state["my_x"], target, config.move_deadzone),
        )
    if action == "JUMP":
        # Jump TOWARD the ball instead of straight up, so a bot can run under a
        # high ball and actually head it. Previously JUMP carried move_dir=0,
        # which stopped the bot dead -- you could never move and jump at once.
        return Intent(
            action,
            jump=True,
            move_dir=_direction_to_target(
                state["my_x"], state["ball_x"], config.move_deadzone
            ),
        )
    if action.startswith("KICK_"):
        return Intent(action, kick=action)
    return Intent("IDLE")


def _kick_parameters(action: str, config: GameConfig):
    if action == "KICK_LOW":
        return config.kick_low_x, config.kick_low_y, config.kick_low_cooldown
    if action == "KICK_HIGH":
        return config.kick_high_x, config.kick_high_y, config.kick_high_cooldown
    if action == "KICK_CLEAR":
        return config.kick_clear_x, config.kick_clear_y, config.kick_clear_cooldown
    return None


def _limit_ball_speed(ball: Ball, config: GameConfig):
    speed = hypot(ball.vx, ball.vy)
    if speed > config.ball_max_speed and speed > 0:
        scale = config.ball_max_speed / speed
        ball.vx *= scale
        ball.vy *= scale


def _apply_kicks(world: World, intents: list[Intent], config: GameConfig):
    impulses = []
    cooldowns = []

    for team, intent in enumerate(intents):
        if not intent.kick:
            continue
        player = world.players[team]
        if not _can_kick(player, world.ball, config):
            continue
        params = _kick_parameters(intent.kick, config)
        if params is None:
            continue

        kick_x, kick_y, cooldown = params
        direction = 1 if team == 0 else -1
        impulses.append(
            (
                team,
                direction * kick_x
                + player.vx * config.kick_player_velocity_transfer,
                kick_y,
            )
        )
        cooldowns.append((team, cooldown))

    if not impulses:
        return

    ball = world.ball

    if len(impulses) >= 2:
        # When both players kick the same ball from opposite sides, averaging
        # the horizontal impulses used to pin the ball between them forever.
        # Head Ball-style contested kicks instead "squirt" the ball upward and
        # recoil both players away from the collision.
        impulse_x = sum(ix for _, ix, _ in impulses) / len(impulses)
        impulse_y = sum(iy for _, _, iy in impulses) / len(impulses)
        ball.vx = (
            ball.vx * config.contested_kick_horizontal_keep
            + impulse_x * 0.35
        )
        if abs(ball.vx) < config.contested_escape_x:
            ball.vx = world.contest_escape_dir * config.contested_escape_x
        ball.vy = min(
            ball.vy * config.kick_keep_ball_velocity + impulse_y,
            -config.contested_kick_pop_y,
        )

        centres = [
            (_player_center(world.players[team], config)[0], team)
            for team, _, _ in impulses
        ]
        centres.sort()
        if len(centres) >= 2:
            left_team = centres[0][1]
            right_team = centres[-1][1]
            world.players[left_team].vx = min(
                world.players[left_team].vx,
                -config.contested_kick_recoil,
            )
            world.players[right_team].vx = max(
                world.players[right_team].vx,
                config.contested_kick_recoil,
            )
    else:
        _, impulse_x, impulse_y = impulses[0]
        ball.vx = ball.vx * config.kick_keep_ball_velocity + impulse_x
        ball.vy = ball.vy * config.kick_keep_ball_velocity + impulse_y

    _limit_ball_speed(ball, config)

    for team, cooldown in cooldowns:
        world.players[team].kick_cd = cooldown

def _apply_jump_intents(world: World, intents: list[Intent], config: GameConfig):
    for team, intent in enumerate(intents):
        if not intent.jump:
            continue
        player = world.players[team]
        if player.on_ground and player.jump_cd <= 0.0:
            player.vy = -config.player_jump_speed
            player.on_ground = False
            player.jump_cd = config.jump_cooldown


def _update_player_horizontal(
    player: Player,
    move_dir: int,
    dt: float,
    config: GameConfig,
):
    if move_dir:
        target = move_dir * config.player_speed
        acceleration = (
            config.player_acceleration
            if player.on_ground
            else config.player_air_acceleration
        )
        player.vx = _move_toward(player.vx, target, acceleration * dt)
        player.face = move_dir
    else:
        deceleration = (
            config.player_deceleration
            if player.on_ground
            else config.player_air_deceleration
        )
        player.vx = _move_toward(player.vx, 0.0, deceleration * dt)


def _integrate_player(
    player: Player,
    move_dir: int,
    dt: float,
    config: GameConfig,
):
    _update_player_horizontal(player, move_dir, dt, config)
    player.vy += config.player_gravity * dt
    player.x += player.vx * dt
    player.y += player.vy * dt

    floor_y = config.ground_y - config.player_height
    if player.y >= floor_y:
        player.y = floor_y
        if player.vy > 0:
            player.vy = 0.0
        player.on_ground = True
    else:
        player.on_ground = False

    # Players stay on the pitch. The goal is a ball-only recessed space.
    player.x = _clamp(
        player.x,
        config.goal_depth,
        config.width - config.goal_depth - config.player_width,
    )


def _resolve_players(world: World, config: GameConfig):
    a, b = world.players
    inset = config.player_collision_inset
    a_left, a_right = a.x + inset, a.x + config.player_width - inset
    b_left, b_right = b.x + inset, b.x + config.player_width - inset
    overlap_x = min(a_right, b_right) - max(a_left, b_left)
    overlap_y = min(
        a.y + config.player_height,
        b.y + config.player_height,
    ) - max(a.y, b.y)

    if overlap_x <= 0 or overlap_y <= 0:
        return

    a_center = a.x + config.player_width / 2
    b_center = b.x + config.player_width / 2
    left, right = (a, b) if a_center <= b_center else (b, a)

    correction = (
        overlap_x / 2
        + config.player_bump_extra_separation
    )
    left.x -= correction
    right.x += correction

    # Equal-mass 1D collision with a small restitution. The old solver set
    # both velocities to their average (usually zero), so two charging bots
    # repeatedly froze nose-to-nose. Now they visibly bump and separate.
    if left.vx > right.vx:
        lv = left.vx
        rv = right.vx
        e = config.player_bump_restitution
        left.vx = ((1.0 - e) * lv + (1.0 + e) * rv) / 2.0
        right.vx = ((1.0 + e) * lv + (1.0 - e) * rv) / 2.0

    for player in (a, b):
        player.x = _clamp(
            player.x,
            config.goal_depth,
            config.width - config.goal_depth - config.player_width,
        )

def _circle_circle_contact(
    cx: float,
    cy: float,
    radius: float,
    ox: float,
    oy: float,
    other_radius: float,
):
    dx, dy = cx - ox, cy - oy
    distance = hypot(dx, dy)
    limit = radius + other_radius
    if distance >= limit:
        return None
    if distance <= 1e-9:
        return 0.0, -1.0, limit
    return dx / distance, dy / distance, limit - distance


def _circle_aabb_contact(
    cx: float,
    cy: float,
    radius: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
):
    nearest_x = _clamp(cx, left, right)
    nearest_y = _clamp(cy, top, bottom)
    dx, dy = cx - nearest_x, cy - nearest_y
    distance = hypot(dx, dy)

    if distance > 1e-9:
        if distance >= radius:
            return None
        return dx / distance, dy / distance, radius - distance

    # Ball centre ended inside the torso. Push it toward the nearest edge.
    choices = [
        (cx - left, -1.0, 0.0),
        (right - cx, 1.0, 0.0),
        (cy - top, 0.0, -1.0),
        (bottom - cy, 0.0, 1.0),
    ]
    edge_distance, nx, ny = min(choices, key=lambda item: item[0])
    return nx, ny, radius + edge_distance


def _best_player_ball_contact(player: Player, ball: Ball, config: GameConfig):
    head_x, head_y = _head_center(player, config)
    head = _circle_circle_contact(
        ball.x,
        ball.y,
        config.ball_radius,
        head_x,
        head_y,
        config.head_radius,
    )
    body = _circle_aabb_contact(
        ball.x,
        ball.y,
        config.ball_radius,
        player.x + config.body_inset_x,
        player.y + config.body_top_offset,
        player.x + config.player_width - config.body_inset_x,
        player.y + config.player_height,
    )

    candidates = []
    if head:
        candidates.append((*head, config.ball_head_restitution))
    if body:
        candidates.append((*body, config.ball_body_restitution))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[2])


def _resolve_player_ball_contacts(world: World, config: GameConfig):
    ball = world.ball

    # Resolve every player contact from one shared ball snapshot, then apply
    # the combined result once. This keeps the simulation side-neutral.
    for _ in range(2):
        base_x, base_y = ball.x, ball.y
        base_vx, base_vy = ball.vx, ball.vy
        corrections = []
        velocity_changes = []
        touching_players = []

        for index, player in enumerate(world.players):
            probe = Ball(base_x, base_y, base_vx, base_vy)
            contact = _best_player_ball_contact(player, probe, config)
            if contact is None:
                continue

            touching_players.append(index)
            nx, ny, penetration, restitution = contact
            corrections.append(
                (
                    nx * (penetration + 0.01),
                    ny * (penetration + 0.01),
                )
            )

            relative_vx = base_vx - player.vx
            relative_vy = base_vy - player.vy
            normal_speed = relative_vx * nx + relative_vy * ny

            dvx = player.vx * config.player_contact_velocity_transfer
            dvy = 0.0

            # A fast side-on run nudges the ball upward instead of bulldozing
            # it along the floor. This creates the quick headers/volleys that
            # make Head Ball-style play readable and prevents ground pinning.
            if (
                abs(nx) > 0.60
                and abs(player.vx) > 120.0
                and base_y > player.y + config.head_center_y
            ):
                dvy -= min(
                    config.running_touch_lift,
                    abs(player.vx) * 0.38,
                )

            if normal_speed < 0:
                impulse = min(
                    config.ball_contact_impulse_cap,
                    -(1.0 + restitution) * normal_speed,
                )
                dvx += impulse * nx
                dvy += impulse * ny

            velocity_changes.append((dvx, dvy))

        if not corrections:
            break

        count = len(corrections)
        ball.x = base_x + sum(dx for dx, _ in corrections) / count
        ball.y = base_y + sum(dy for _, dy in corrections) / count

        if velocity_changes:
            vcount = len(velocity_changes)
            ball.vx = base_vx + sum(dvx for dvx, _ in velocity_changes) / vcount
            ball.vy = base_vy + sum(dvy for _, dvy in velocity_changes) / vcount

        if len(touching_players) >= 2:
            # Two bodies squeezing the ball is an arcade contest, not a static
            # equilibrium. Pop the ball and recoil the players to create space.
            ball.vx *= config.contested_ball_horizontal_keep
            if abs(ball.vx) < config.contested_escape_x:
                ball.vx = world.contest_escape_dir * config.contested_escape_x
            ball.vy = min(ball.vy, -config.contested_ball_pop_y)

            centres = sorted(
                (
                    _player_center(world.players[index], config)[0],
                    index,
                )
                for index in touching_players
            )
            left_index = centres[0][1]
            right_index = centres[-1][1]
            world.players[left_index].vx = min(
                world.players[left_index].vx,
                -config.contested_player_recoil,
            )
            world.players[right_index].vx = max(
                world.players[right_index].vx,
                config.contested_player_recoil,
            )

        _limit_ball_speed(ball, config)

def _resolve_crossbar(ball: Ball, x: float, y: float, config: GameConfig):
    contact = _circle_circle_contact(
        ball.x,
        ball.y,
        config.ball_radius,
        x,
        y,
        config.goal_post_radius,
    )
    if contact is None:
        return

    nx, ny, penetration = contact
    ball.x += nx * (penetration + 0.01)
    ball.y += ny * (penetration + 0.01)
    normal_speed = ball.vx * nx + ball.vy * ny
    if normal_speed < 0:
        impulse = -(1.0 + 0.72) * normal_speed
        ball.vx += impulse * nx
        ball.vy += impulse * ny


def _resolve_goal_roof(ball: Ball, config: GameConfig):
    crossbar_y = config.ground_y - config.goal_height
    r = config.ball_radius
    in_left_recess = r < ball.x < config.goal_depth - config.goal_post_radius
    in_right_recess = (
        config.width - config.goal_depth + config.goal_post_radius
        < ball.x
        < config.width - r
    )

    if (
        (in_left_recess or in_right_recess)
        and ball.y < crossbar_y
        and ball.y + r > crossbar_y
    ):
        ball.y = crossbar_y - r
        if ball.vy > 0:
            ball.vy = -ball.vy * 0.55


def _resolve_ball_environment(
    ball: Ball,
    dt: float,
    config: GameConfig,
    *,
    apply_floor_friction: bool,
):
    r = config.ball_radius
    crossbar_y = config.ground_y - config.goal_height

    if ball.y - r < 0.0:
        ball.y = r
        if ball.vy < 0:
            ball.vy = abs(ball.vy) * config.ball_ceiling_bounce

    if ball.y + r > config.ground_y:
        ball.y = config.ground_y - r
        if ball.vy > 55.0:
            ball.vy = -ball.vy * config.floor_bounce
        else:
            ball.vy = 0.0
        if apply_floor_friction:
            ball.vx *= config.floor_friction ** (dt * 60.0)
            if abs(ball.vx) < config.ball_sleep_speed:
                ball.vx = 0.0

    # Recessed goal back walls. The front is intentionally open below the bar.
    if ball.x - r < 0.0:
        ball.x = r
        if ball.vx < 0:
            ball.vx = abs(ball.vx) * config.ball_wall_bounce
    elif ball.x + r > config.width:
        ball.x = config.width - r
        if ball.vx > 0:
            ball.vx = -abs(ball.vx) * config.ball_wall_bounce

    _resolve_crossbar(ball, config.goal_depth, crossbar_y, config)
    _resolve_crossbar(
        ball,
        config.width - config.goal_depth,
        crossbar_y,
        config,
    )
    _resolve_goal_roof(ball, config)
    _limit_ball_speed(ball, config)


def _integrate_ball(ball: Ball, dt: float, config: GameConfig) -> float:
    previous_x = ball.x
    ball.vy += config.gravity * dt
    ball.x += ball.vx * dt
    ball.y += ball.vy * dt
    ball.vx *= config.horizontal_drag_per_60fps ** (dt * 60.0)
    _resolve_ball_environment(ball, dt, config, apply_floor_friction=True)
    return previous_x


def _detect_goal(world: World, previous_x: float, config: GameConfig):
    ball = world.ball
    r = config.ball_radius
    crossbar_y = config.ground_y - config.goal_height

    # Entire ball must be under the bar and beyond the actual front goal line.
    in_mouth = ball.y - r >= crossbar_y + 0.5

    left_before = previous_x + r
    left_now = ball.x + r
    if (
        in_mouth
        and left_before >= config.goal_depth
        and left_now < config.goal_depth
    ):
        world.score[1] += 1
        world.freeze = config.kickoff_freeze
        return 1

    right_line = config.width - config.goal_depth
    right_before = previous_x - r
    right_now = ball.x - r
    if (
        in_mouth
        and right_before <= right_line
        and right_now > right_line
    ):
        world.score[0] += 1
        world.freeze = config.kickoff_freeze
        return 0

    return None


def _resolve_stall(
    world: World,
    dt: float,
    rng: random.Random,
    config: GameConfig,
):
    """Keep the match alive if the ball gets stuck (goal-roof wedge, asleep on
    the ground, etc.). Escalates: gentle pop first, full kickoff if still dead.
    """
    ball = world.ball
    speed = hypot(ball.vx, ball.vy)

    # A frozen kickoff or a moving ball means nothing is stuck.
    if world.freeze > 0 or speed > config.stall_speed_threshold:
        world.stall_time = 0.0
        world.stall_popped = False
        return

    world.stall_time += dt

    if world.stall_time >= config.stall_kickoff_after:
        # Still dead after the gentle pop: re-drop the ball from the top of the
        # field, exactly like a post-goal restart. The SCORE IS PRESERVED --
        # this only repositions the ball/players, it does not restart the match.
        _kickoff(world, rng, config, initial=True)
        world.stall_time = 0.0
        world.stall_popped = False
    elif world.stall_time >= config.stall_pop_after and not world.stall_popped:
        # One arcade "throw-in": lift the ball and send it toward the center
        # of the pitch (deterministic, so neither side is favored).
        toward_center = 1.0 if ball.x < config.width / 2 else -1.0
        ball.vx = toward_center * config.stall_pop_vx
        ball.vy = -config.stall_pop_vy
        _limit_ball_speed(ball, config)
        world.stall_popped = True


def _frame(world: World) -> dict:
    return {
        "time": round(world.remaining_time, 3),
        "score": list(world.score),
        "players": [
            {
                "x": round(player.x, 3),
                "y": round(player.y, 3),
                "face": player.face,
            }
            for player in world.players
        ],
        "ball": {
            "x": round(world.ball.x, 3),
            "y": round(world.ball.y, 3),
        },
        "debug": world.debug,
    }


def simulate_match(
    blue_strategy: dict,
    red_strategy: dict,
    *,
    seed: int = 1,
    record_frames: bool = True,
    config: GameConfig | None = None,
) -> dict:
    validate_strategy(blue_strategy)
    validate_strategy(red_strategy)
    if config is None:
        config = get_game_config()

    rng = random.Random(seed)
    world = _new_world(rng, config)
    frame_dt = 1.0 / config.physics_fps
    substeps = max(1, int(config.physics_substeps))
    sub_dt = frame_dt / substeps
    record_every = max(1, config.physics_fps // config.record_fps)
    frames = []
    step_index = 0

    while world.remaining_time > 0:
        world.remaining_time = max(0.0, world.remaining_time - frame_dt)

        for player in world.players:
            player.kick_cd = max(0.0, player.kick_cd - frame_dt)
            player.jump_cd = max(0.0, player.jump_cd - frame_dt)

        if world.freeze > 0:
            world.freeze = max(0.0, world.freeze - frame_dt)
            if world.freeze <= 0:
                _kickoff(world, rng, config, initial=True)
        else:
            # Both bots read the exact same world snapshot before either acts.
            states = [
                _sensor_state(world, 0, config),
                _sensor_state(world, 1, config),
            ]
            decisions = [
                _choose_action(blue_strategy, states[0]),
                _choose_action(red_strategy, states[1]),
            ]
            intents = [
                _resolve_intent(decisions[0][1], states[0], 0, config),
                _resolve_intent(decisions[1][1], states[1], 1, config),
            ]

            _apply_jump_intents(world, intents, config)
            _apply_kicks(world, intents, config)

            world.debug = [
                {
                    "rule": decisions[index][0],
                    "action": intents[index].action,
                    "distance_to_ball": round(
                        states[index]["distance_to_ball"],
                        1,
                    ),
                }
                for index in range(2)
            ]

            for _ in range(substeps):
                for team, player in enumerate(world.players):
                    _integrate_player(
                        player,
                        intents[team].move_dir,
                        sub_dt,
                        config,
                    )
                _resolve_players(world, config)

                previous_ball_x = _integrate_ball(world.ball, sub_dt, config)
                _resolve_player_ball_contacts(world, config)
                # Contacts may push the ball into a wall/post, so clamp again.
                _resolve_ball_environment(
                    world.ball,
                    sub_dt,
                    config,
                    apply_floor_friction=False,
                )

                scorer = _detect_goal(world, previous_ball_x, config)
                if scorer is not None:
                    break

            _resolve_stall(world, frame_dt, rng, config)

        if record_frames and step_index % record_every == 0:
            frames.append(_frame(world))
        step_index += 1

    if record_frames:
        frames.append(_frame(world))

    return {
        "score": list(world.score),
        "winner": (
            "draw"
            if world.score[0] == world.score[1]
            else ("blue" if world.score[0] > world.score[1] else "red")
        ),
        "seed": seed,
        "duration": config.match_time,
        "record_fps": config.record_fps,
        "physics_version": PHYSICS_VERSION,
        "frames": frames,
    }


def batch_matches(
    blue_strategy: dict,
    red_strategy: dict,
    *,
    matches: int = DEFAULT_BATCH_MATCHES,
    seed: int = 1,
    config: GameConfig | None = None,
) -> dict:
    validate_strategy(blue_strategy)
    validate_strategy(red_strategy)
    if config is None:
        config = get_game_config()
    matches = max(1, min(int(matches), MAX_BATCH_MATCHES))

    blue_wins = red_wins = draws = blue_goals = red_goals = 0

    for index in range(matches):
        # Every two matches are a mirrored pair with the exact same seed.
        # This cancels kickoff/side variance when comparing strategies.
        match_seed = seed + index // 2
        if index % 2 == 0:
            score = simulate_match(
                blue_strategy,
                red_strategy,
                seed=match_seed,
                record_frames=False,
                config=config,
            )["score"]
        else:
            swapped = simulate_match(
                red_strategy,
                blue_strategy,
                seed=match_seed,
                record_frames=False,
                config=config,
            )["score"]
            score = [swapped[1], swapped[0]]

        blue_goals += score[0]
        red_goals += score[1]
        if score[0] > score[1]:
            blue_wins += 1
        elif score[1] > score[0]:
            red_wins += 1
        else:
            draws += 1

    return {
        "matches": matches,
        "blue_wins": blue_wins,
        "red_wins": red_wins,
        "draws": draws,
        "blue_goals": blue_goals,
        "red_goals": red_goals,
        "blue_goals_per_match": round(blue_goals / matches, 2),
        "red_goals_per_match": round(red_goals / matches, 2),
        "physics_version": PHYSICS_VERSION,
    }
