from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
import random

from .validators import validate_strategy

@dataclass(frozen=True)
class GameConfig:
    width: float = 1280.0
    height: float = 720.0
    ground_y: float = 610.0
    gravity: float = 1900.0
    goal_depth: float = 105.0
    goal_height: float = 135.0
    ball_radius: float = 22.0
    ball_max_speed: float = 900.0
    player_width: float = 58.0
    player_height: float = 72.0
    player_speed: float = 390.0
    player_jump_speed: float = 750.0
    jump_cooldown: float = 0.55
    kickoff_freeze: float = 0.80
    match_time: float = 60.0
    physics_fps: int = 60
    record_fps: int = 20
    body_ball_impulse_scale: float = 0.05
    floor_bounce: float = 0.60
    floor_friction: float = 0.90
    horizontal_drag_per_60fps: float = 0.995

CONFIG = GameConfig()

@dataclass
class Player:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    face: int = 1
    on_ground: bool = True
    kick_cd: float = 0.0
    jump_cd: float = 0.0

@dataclass
class Ball:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0

@dataclass
class World:
    players: list[Player]
    ball: Ball
    score: list[int] = field(default_factory=lambda: [0, 0])
    remaining_time: float = CONFIG.match_time
    freeze: float = 0.0
    debug: list[dict] = field(default_factory=lambda: [{}, {}])

def _clamp(value, lo, hi):
    return max(lo, min(hi, value))

def _new_world(rng: random.Random, config: GameConfig = CONFIG) -> World:
    world = World(
        players=[
            Player(255.0, config.ground_y - config.player_height, face=1),
            Player(config.width - 313.0, config.ground_y - config.player_height, face=-1),
        ],
        ball=Ball(config.width / 2, 235.0),
        remaining_time=config.match_time,
    )
    _kickoff(world, rng, config, initial=True)
    return world

def _kickoff(world: World, rng: random.Random, config: GameConfig, initial=False):
    p0, p1 = world.players
    p0.x = 255.0
    p1.x = config.width - 313.0
    for player, face in ((p0, 1), (p1, -1)):
        player.y = config.ground_y - config.player_height
        player.vx = player.vy = 0.0
        player.face = face
        player.on_ground = True
        player.kick_cd = 0.0
        player.jump_cd = 0.0
    direction = rng.choice((-1, 1))
    world.ball.x = config.width / 2
    world.ball.y = 235.0
    world.ball.vx = direction * rng.uniform(110.0, 180.0)
    world.ball.vy = -rng.uniform(80.0, 150.0)
    if not initial:
        world.freeze = config.kickoff_freeze

def _sensor_state(world: World, team: int, config: GameConfig) -> dict:
    me = world.players[team]
    opponent = world.players[1 - team]
    ball = world.ball
    my_x = me.x + config.player_width / 2
    my_y = me.y + config.player_height / 2
    opp_x = opponent.x + config.player_width / 2
    opp_y = opponent.y + config.player_height / 2
    dx, dy = ball.x - my_x, ball.y - my_y
    odx, ody = ball.x - opp_x, ball.y - opp_y
    own_goal_x = 0.0 if team == 0 else config.width
    enemy_goal_x = config.width if team == 0 else 0.0
    own_half = ball.x < config.width / 2 if team == 0 else ball.x > config.width / 2
    t = 0.38
    predicted_x = _clamp(ball.x + ball.vx * t, 0.0, config.width)
    predicted_y = _clamp(ball.y + ball.vy * t + 0.5 * config.gravity * t * t, 0.0, config.ground_y)
    return {
        "my_x": my_x, "opponent_x": opp_x, "ball_x": ball.x, "ball_y": ball.y,
        "ball_vx": ball.vx, "ball_vy": ball.vy, "ball_speed": hypot(ball.vx, ball.vy),
        "distance_to_ball": hypot(dx, dy), "opponent_distance_to_ball": hypot(odx, ody),
        "distance_to_own_goal": abs(my_x - own_goal_x),
        "distance_to_enemy_goal": abs(my_x - enemy_goal_x),
        "ball_distance_to_own_goal": abs(ball.x - own_goal_x),
        "ball_distance_to_enemy_goal": abs(ball.x - enemy_goal_x),
        "predicted_ball_x": predicted_x, "predicted_ball_y": predicted_y,
        "remaining_time": world.remaining_time,
        "my_score": world.score[team], "opponent_score": world.score[1-team],
        "score_difference": world.score[team] - world.score[1-team],
        "can_kick": hypot(dx, dy) < 115.0 and me.kick_cd <= 0.0,
        "on_ground": me.on_ground,
        "ball_in_own_half": own_half, "ball_in_enemy_half": not own_half,
        "ball_above_me": ball.y < me.y + 15.0 and abs(dx) < 130.0,
        "ball_moving_toward_me": ((ball.vx > 0 and ball.x < my_x) or (ball.vx < 0 and ball.x > my_x)),
    }

def _compare(left, operator, right):
    return {
        "<": left < right, "<=": left <= right, ">": left > right,
        ">=": left >= right, "==": left == right, "!=": left != right,
    }.get(operator, False)

def _condition_true(cond: dict, state: dict) -> bool:
    right = state[cond["right"]] if cond["rightType"] == "sensor" else cond["right"]
    return _compare(state[cond["left"]], cond["operator"], right)

def _choose_action(strategy: dict, state: dict) -> tuple[int | str, str]:
    for item in sorted(strategy["rules"], key=lambda row: row["priority"]):
        if all(_condition_true(cond, state) for cond in item["conditions"]):
            return item["priority"], item["action"]
    return "default", strategy.get("default_action", "IDLE")

def _resolve_move(action: str, state: dict, team: int, config: GameConfig) -> str:
    if action == "MOVE_TO_BALL":
        return "MOVE_LEFT" if state["ball_x"] < state["my_x"] else "MOVE_RIGHT"
    if action == "MOVE_TO_GOAL":
        target = config.goal_depth + 45 if team == 0 else config.width - config.goal_depth - 45
        return "MOVE_RIGHT" if state["my_x"] < target else "MOVE_LEFT"
    if action == "MOVE_TO_CENTER":
        target = config.width / 2 + (-80 if team == 0 else 80)
        return "MOVE_RIGHT" if state["my_x"] < target else "MOVE_LEFT"
    return action

def _kick_vector(action: str, team: int):
    direction = 1 if team == 0 else -1
    if action == "KICK_LOW": return direction * 510.0, -120.0, 0.62
    if action == "KICK_HIGH": return direction * 420.0, -410.0, 0.78
    if action == "KICK_CLEAR": return direction * 620.0, -250.0, 0.95
    return None

def _limit_ball_speed(ball: Ball, config: GameConfig):
    speed = hypot(ball.vx, ball.vy)
    if speed > config.ball_max_speed and speed > 0:
        scale = config.ball_max_speed / speed
        ball.vx *= scale
        ball.vy *= scale

def _apply_intents(world: World, states: list[dict], decisions, dt: float, config: GameConfig):
    actual_actions, kick_vectors = [], []
    for team, (_, raw_action) in enumerate(decisions):
        player = world.players[team]
        player.kick_cd = max(0.0, player.kick_cd - dt)
        player.jump_cd = max(0.0, player.jump_cd - dt)
        player.vx = 0.0
        action = _resolve_move(raw_action, states[team], team, config)
        actual_actions.append(action)
        if action == "MOVE_LEFT": player.vx, player.face = -config.player_speed, -1
        elif action == "MOVE_RIGHT": player.vx, player.face = config.player_speed, 1
        elif action == "JUMP" and player.on_ground and player.jump_cd <= 0.0:
            player.vy = -config.player_jump_speed
            player.on_ground = False
            player.jump_cd = config.jump_cooldown
        elif action.startswith("KICK_") and states[team]["can_kick"]:
            kick = _kick_vector(action, team)
            if kick: kick_vectors.append((team, *kick))
    if kick_vectors:
        world.ball.vx = sum(item[1] for item in kick_vectors) / len(kick_vectors)
        world.ball.vy = sum(item[2] for item in kick_vectors) / len(kick_vectors)
        for team, _, _, cooldown in kick_vectors:
            world.players[team].kick_cd = cooldown
        _limit_ball_speed(world.ball, config)
    return actual_actions

def _integrate_player(player: Player, dt: float, config: GameConfig):
    player.vy += config.gravity * dt
    player.x += player.vx * dt
    player.y += player.vy * dt
    if player.y + config.player_height >= config.ground_y:
        player.y = config.ground_y - config.player_height
        player.vy = 0.0
        player.on_ground = True
    player.x = _clamp(player.x, config.goal_depth, config.width - config.goal_depth - config.player_width)

def _resolve_players(world: World, config: GameConfig):
    a, b = world.players
    overlap_x = min(a.x+config.player_width, b.x+config.player_width) - max(a.x,b.x)
    overlap_y = min(a.y+config.player_height, b.y+config.player_height) - max(a.y,b.y)
    if overlap_x > 0 and overlap_y > 0:
        push = overlap_x/2 + 0.1
        a.x = max(config.goal_depth, a.x - push)
        b.x = min(config.width - config.goal_depth - config.player_width, b.x + push)
        if a.vx > 0:
            a.vx = 0.0
        if b.vx < 0:
            b.vx = 0.0

def _resolve_player_ball_contacts(world: World, config: GameConfig):
    ball = world.ball
    base_vx, base_vy = ball.vx, ball.vy
    corr_x = corr_y = dv_x = dv_y = 0.0
    contacts = 0
    for player in world.players:
        nearest_x = _clamp(ball.x, player.x, player.x + config.player_width)
        nearest_y = _clamp(ball.y, player.y, player.y + config.player_height)
        dx, dy = ball.x - nearest_x, ball.y - nearest_y
        distance = hypot(dx, dy)
        if distance < config.ball_radius:
            nx, ny = ((0.0, -1.0) if distance == 0 else (dx/distance, dy/distance))
            penetration = config.ball_radius - distance
            contacts += 1
            corr_x += nx * penetration
            corr_y += ny * penetration
            closing = (base_vx-player.vx)*nx + (base_vy-player.vy)*ny
            if closing < 0:
                impulse = -config.body_ball_impulse_scale * closing
                dv_x += impulse * nx
                dv_y += impulse * ny
    if contacts:
        ball.x += corr_x / contacts
        ball.y += corr_y / contacts
        ball.vx += dv_x
        ball.vy += dv_y

def _crossbar_contact(ball: Ball, px: float, py: float, config: GameConfig):
    dx,dy=ball.x-px,ball.y-py; distance=hypot(dx,dy); radius=config.ball_radius+7.0
    if distance >= radius: return
    nx,ny=((1.0,0.0) if distance==0 else (dx/distance,dy/distance))
    penetration=radius-distance; ball.x += nx*penetration; ball.y += ny*penetration
    projection=ball.vx*nx+ball.vy*ny
    if projection < 0:
        ball.vx -= 1.25*projection*nx; ball.vy -= 1.25*projection*ny

def _integrate_ball(world: World, dt: float, config: GameConfig):
    ball = world.ball
    ball.vy += config.gravity * dt
    ball.x += ball.vx * dt
    ball.y += ball.vy * dt
    ball.vx *= config.horizontal_drag_per_60fps ** (dt * 60.0)

    in_left_goal = ball.x < config.goal_depth
    in_right_goal = ball.x > config.width - config.goal_depth
    if not (in_left_goal or in_right_goal) and ball.y + config.ball_radius > config.ground_y:
        ball.y = config.ground_y - config.ball_radius
        ball.vy *= -config.floor_bounce
        ball.vx *= config.floor_friction

    if ball.y - config.ball_radius < 0:
        ball.y = config.ball_radius
        ball.vy = abs(ball.vy) * 0.75

    # A goal is counted only after the ball crosses the back line inside the goal height.
    if ball.x - config.ball_radius < 0:
        if ball.y > config.ground_y - config.goal_height:
            world.score[1] += 1
            world.freeze = config.kickoff_freeze
            return 1
        ball.x = config.ball_radius
        ball.vx = abs(ball.vx) * 0.8

    if ball.x + config.ball_radius > config.width:
        if ball.y > config.ground_y - config.goal_height:
            world.score[0] += 1
            world.freeze = config.kickoff_freeze
            return 0
        ball.x = config.width - config.ball_radius
        ball.vx = -abs(ball.vx) * 0.8

    crossbar_y = config.ground_y - config.goal_height
    _crossbar_contact(ball, config.goal_depth, crossbar_y, config)
    _crossbar_contact(ball, config.width - config.goal_depth, crossbar_y, config)
    _limit_ball_speed(ball, config)
    return None

def _frame(world: World) -> dict:
    return {
        "time": round(world.remaining_time,3), "score": list(world.score),
        "players": [{"x":round(p.x,3),"y":round(p.y,3),"face":p.face} for p in world.players],
        "ball": {"x":round(world.ball.x,3),"y":round(world.ball.y,3)},
        "debug": world.debug,
    }

def simulate_match(blue_strategy: dict, red_strategy: dict, *, seed: int=1, record_frames: bool=True, config: GameConfig=CONFIG) -> dict:
    validate_strategy(blue_strategy); validate_strategy(red_strategy)
    rng=random.Random(seed); world=_new_world(rng,config); dt=1.0/config.physics_fps
    record_every=max(1,config.physics_fps//config.record_fps); frames=[]; step_index=0
    while world.remaining_time > 0:
        world.remaining_time=max(0.0,world.remaining_time-dt)
        if world.freeze > 0:
            world.freeze=max(0.0,world.freeze-dt)
            if world.freeze <= 0: _kickoff(world,rng,config,initial=True)
        else:
            states=[_sensor_state(world,0,config),_sensor_state(world,1,config)]
            decisions=[_choose_action(blue_strategy,states[0]),_choose_action(red_strategy,states[1])]
            actual=_apply_intents(world,states,decisions,dt,config)
            world.debug=[{"rule":decisions[i][0],"action":actual[i],"distance_to_ball":round(states[i]["distance_to_ball"],1)} for i in range(2)]
            for p in world.players: _integrate_player(p,dt,config)
            _resolve_players(world,config)
            _resolve_player_ball_contacts(world, config)
            _integrate_ball(world,dt,config)
        if record_frames and step_index % record_every == 0: frames.append(_frame(world))
        step_index += 1
    if record_frames: frames.append(_frame(world))
    return {
        "score":list(world.score),
        "winner":"draw" if world.score[0]==world.score[1] else ("blue" if world.score[0]>world.score[1] else "red"),
        "seed":seed,"duration":config.match_time,"record_fps":config.record_fps,"frames":frames,
    }

def batch_matches(blue_strategy: dict, red_strategy: dict, *, matches: int=100, seed: int=1, config: GameConfig=CONFIG) -> dict:
    validate_strategy(blue_strategy); validate_strategy(red_strategy); matches=max(1,min(int(matches),250))
    bw=rw=draws=bg=rg=0
    for index in range(matches):
        match_seed=seed+index
        if index%2==0:
            score=simulate_match(blue_strategy,red_strategy,seed=match_seed,record_frames=False,config=config)["score"]
        else:
            q=simulate_match(red_strategy,blue_strategy,seed=match_seed,record_frames=False,config=config)["score"]
            score=[q[1],q[0]]
        bg+=score[0]; rg+=score[1]
        if score[0]>score[1]: bw+=1
        elif score[1]>score[0]: rw+=1
        else: draws+=1
    return {
        "matches":matches,"blue_wins":bw,"red_wins":rw,"draws":draws,
        "blue_goals":bg,"red_goals":rg,
        "blue_goals_per_match":round(bg/matches,2),"red_goals_per_match":round(rg/matches,2),
    }
