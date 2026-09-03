/**
 * GilBall 3D Physics & Game Mechanics Engine
 * 2.5D Arcade Head-Ball Physics in metric units.
 */

class GamePhysics {
  constructor() {
    // Pitch bounds (metric)
    this.PITCH_HALF_WIDTH = 13.0; // Total pitch = 26m
    this.GOAL_DEPTH = 2.0;       // Goal width = 2m
    this.FIELD_LEFT = -this.PITCH_HALF_WIDTH;
    this.FIELD_RIGHT = this.PITCH_HALF_WIDTH;
    this.CEILING_Y = 11.5;
    this.GROUND_Y = 0.0;
    
    this.GOAL_WIDTH = 2.2;
    this.GOAL_HEIGHT = 3.5;
    this.CROSSBAR_RADIUS = 0.12;

    // Physics constants
    this.GRAVITY = -24.0;
    this.BALL_GRAVITY = -21.0;
    this.PLAYER_SPEED = 8.5;
    this.PLAYER_JUMP_FORCE = 12.8;
    this.BALL_MAX_SPEED = 32.0;

    this.ball = {
      x: 0,
      y: 5.0,
      z: 0,
      vx: 0,
      vy: 0,
      vz: 0,
      radius: 0.42,
      spin: 0,
      isSuper: false,
      superTimer: 0,
      lastHitter: -1
    };

    this.players = [
      this.createPlayer(0, -7.5, 1),  // Team 1 (Left, Blue)
      this.createPlayer(1, 7.5, -1)   // Team 2 (Right, Red)
    ];

    this.score = [0, 0];
    this.matchTime = 60.0;
    this.state = 'playing'; // 'playing', 'goal_scored', 'game_over', 'kickoff'
    this.goalCooldown = 0;
    this.stallTimer = 0;
  }

  createPlayer(id, startX, facing) {
    return {
      id: id,
      startX: startX,
      x: startX,
      y: 0,
      z: 0,
      vx: 0,
      vy: 0,
      facing: facing, // 1 for right, -1 for left
      onGround: true,
      
      // Dimensions
      width: 1.2,
      height: 2.2,
      headRadius: 0.72,
      headOffsetY: 1.45,

      // State & Cooldowns
      jumpCd: 0,
      kickCd: 0,
      kickAnim: 0, // 0 to 1 for visual foot swing
      kickType: null,
      superMeter: 100, // 0 - 100
      isStunned: 0,
      squash: 1.0,

      // Controls buffer
      input: {
        move: 0,   // -1, 0, 1
        jump: false,
        kickLow: false,
        kickHigh: false,
        superShot: false
      }
    };
  }

  resetMatch(duration = 60) {
    this.score = [0, 0];
    this.matchTime = duration;
    this.resetKickoff((Math.random() > 0.5 ? 1 : -1));
    this.state = 'playing';
  }

  resetKickoff(biasSide = 1) {
    this.ball.x = 0;
    this.ball.y = 5.2;
    this.ball.z = 0;
    this.ball.vx = (Math.random() - 0.5) * 1.5 + (biasSide * 0.8);
    this.ball.vy = 2.0;
    this.ball.vz = 0;
    this.ball.spin = 0;
    this.ball.isSuper = false;
    this.ball.superTimer = 0;
    this.stallTimer = 0;

    this.players[0].x = this.players[0].startX;
    this.players[0].y = 0;
    this.players[0].vx = 0;
    this.players[0].vy = 0;
    this.players[0].facing = 1;

    this.players[1].x = this.players[1].startX;
    this.players[1].y = 0;
    this.players[1].vx = 0;
    this.players[1].vy = 0;
    this.players[1].facing = -1;

    this.goalCooldown = 1.2;
  }

  update(dt) {
    if (this.state === 'game_over') return;

    // Time countdown
    if (this.state === 'playing' && this.goalCooldown <= 0) {
      this.matchTime = Math.max(0, this.matchTime - dt);
      if (this.matchTime <= 0) {
        this.state = 'game_over';
        if (window.sound) window.sound.playWhistle(true);
        return;
      }
    }

    if (this.goalCooldown > 0) {
      this.goalCooldown -= dt;
    }

    // 1. Update Players
    this.players.forEach(p => this.updatePlayer(p, dt));

    // 2. Player-Player collisions
    this.resolvePlayerCollisions();

    // 3. Update Ball Physics
    this.updateBall(dt);

    // 4. Ball-Player Interactions & Kicks
    this.resolveBallPlayerInteractions();

    // 5. Goal Checks & Watchdog
    this.checkGoals();
    this.checkStallWatchdog(dt);
  }

  updatePlayer(p, dt) {
    // Super meter passive charge
    p.superMeter = Math.min(100, p.superMeter + dt * 4.0);

    // Stun recovery
    if (p.isStunned > 0) {
      p.isStunned = Math.max(0, p.isStunned - dt);
      p.vx *= 0.85;
      return;
    }

    // Cooldowns
    p.jumpCd = Math.max(0, p.jumpCd - dt);
    p.kickCd = Math.max(0, p.kickCd - dt);
    if (p.kickAnim > 0) p.kickAnim = Math.max(0, p.kickAnim - dt * 4.0);

    // Horizontal Movement
    const targetVx = p.input.move * this.PLAYER_SPEED;
    const accel = p.onGround ? 38.0 : 18.0;
    p.vx += (targetVx - p.vx) * Math.min(1.0, dt * accel);

    // Face direction based on movement or opponent
    if (p.input.move !== 0) {
      p.facing = p.input.move > 0 ? 1 : -1;
    }

    // Jump
    if (p.input.jump && p.onGround && p.jumpCd <= 0) {
      p.vy = this.PLAYER_JUMP_FORCE;
      p.onGround = false;
      p.jumpCd = 0.25;
      p.squash = 1.35;
      if (window.sound) window.sound.playJump();
    }

    // Apply Gravity & Velocity
    p.vy += this.GRAVITY * dt;
    p.x += p.vx * dt;
    p.y += p.vy * dt;

    // Ground check
    if (p.y <= this.GROUND_Y) {
      if (!p.onGround) p.squash = 0.75; // Land squash
      p.y = this.GROUND_Y;
      p.vy = 0;
      p.onGround = true;
    } else {
      p.onGround = false;
    }

    // Smooth squash recovery
    p.squash += (1.0 - p.squash) * dt * 10.0;

    // Pitch Boundaries (Players cannot walk inside back of the goal)
    const minX = this.FIELD_LEFT + 0.6;
    const maxX = this.FIELD_RIGHT - 0.6;
    if (p.x < minX) { p.x = minX; p.vx = 0; }
    if (p.x > maxX) { p.x = maxX; p.vx = 0; }

    // Execute Kicks
    if (p.kickCd <= 0) {
      if (p.input.superShot && p.superMeter >= 99) {
        this.executeKick(p, 'super');
      } else if (p.input.kickHigh) {
        this.executeKick(p, 'high');
      } else if (p.input.kickLow) {
        this.executeKick(p, 'low');
      }
    }
  }

  executeKick(p, type) {
    p.kickCd = 0.32;
    p.kickAnim = 1.0;
    p.kickType = type;

    // Ball distance check
    const dx = this.ball.x - p.x;
    const dy = this.ball.y - (p.y + 0.6);
    const dist = Math.sqrt(dx * dx + dy * dy);
    const kickReach = 2.4;

    // Check if ball is in front of the player (or slightly behind)
    const isFacingBall = (dx * p.facing > -0.6);

    if (dist <= kickReach && isFacingBall) {
      p.kickCd = 0.45;
      this.ball.lastHitter = p.id;

      if (type === 'super') {
        p.superMeter = 0;
        this.ball.isSuper = true;
        this.ball.superTimer = 2.2;
        this.ball.vx = p.facing * 26.0 + p.vx * 0.4;
        this.ball.vy = 4.5;
        this.ball.spin = p.facing * 20;
        if (window.sound) window.sound.playSuperShot();
      } else if (type === 'high') {
        this.ball.vx = p.facing * 14.5 + p.vx * 0.5;
        this.ball.vy = 17.5 + Math.min(0, p.vy * 0.3);
        this.ball.spin = p.facing * 12;
        if (window.sound) window.sound.playKick(1.2);
      } else { // Low shot
        this.ball.vx = p.facing * 19.5 + p.vx * 0.6;
        this.ball.vy = 4.8;
        this.ball.spin = p.facing * 8;
        if (window.sound) window.sound.playKick(0.9);
      }
    }
  }

  resolvePlayerCollisions() {
    const p1 = this.players[0];
    const p2 = this.players[1];
    const dx = p2.x - p1.x;
    const minDist = 1.1;

    if (Math.abs(dx) < minDist) {
      const overlap = (minDist - Math.abs(dx)) * 0.5;
      const sign = dx >= 0 ? 1 : -1;
      p1.x -= sign * overlap;
      p2.x += sign * overlap;

      // Bump velocities
      const avgVx = (p1.vx + p2.vx) * 0.5;
      p1.vx = avgVx - sign * 2.0;
      p2.vx = avgVx + sign * 2.0;
    }
  }

  updateBall(dt) {
    const b = this.ball;

    // Super shot decay
    if (b.isSuper) {
      b.superTimer -= dt;
      if (b.superTimer <= 0) b.isSuper = false;
    }

    // Apply Gravity (lower gravity during super shot)
    const currentGrav = b.isSuper ? this.BALL_GRAVITY * 0.4 : this.BALL_GRAVITY;
    b.vy += currentGrav * dt;

    // Apply Magnus Spin Effect
    b.vy += b.spin * b.vx * 0.003 * dt;
    b.spin *= Math.pow(0.98, dt * 60);

    // Apply Air Drag
    b.vx *= Math.pow(0.998, dt * 60);

    // Update Position
    b.x += b.vx * dt;
    b.y += b.vy * dt;

    // Speed Clamp
    const spd = Math.sqrt(b.vx * b.vx + b.vy * b.vy);
    if (spd > this.BALL_MAX_SPEED) {
      const scale = this.BALL_MAX_SPEED / spd;
      b.vx *= scale;
      b.vy *= scale;
    }

    // 1. Ground Collision
    if (b.y - b.radius <= this.GROUND_Y) {
      b.y = this.GROUND_Y + b.radius;
      b.vy = -b.vy * 0.72; // Elasticity
      b.vx *= 0.96; // Ground friction
      if (Math.abs(b.vy) < 1.2) b.vy = 0;
      if (b.isSuper && Math.abs(b.vy) > 3) b.isSuper = false;
      if (Math.abs(b.vy) > 2.0 && window.sound) window.sound.playHead();
    }

    // 2. Ceiling Collision
    if (b.y + b.radius >= this.CEILING_Y) {
      b.y = this.CEILING_Y - b.radius;
      b.vy = -Math.abs(b.vy) * 0.85;
    }

    // 3. Goal Crossbar Collisions (Left & Right)
    this.checkCrossbarCollision(this.FIELD_LEFT, this.GOAL_HEIGHT);
    this.checkCrossbarCollision(this.FIELD_RIGHT, this.GOAL_HEIGHT);

    // 4. Back of Net / Outer Walls
    const outerLeft = this.FIELD_LEFT - this.GOAL_DEPTH;
    const outerRight = this.FIELD_RIGHT + this.GOAL_DEPTH;

    if (b.x - b.radius <= outerLeft) {
      b.x = outerLeft + b.radius;
      b.vx = Math.abs(b.vx) * 0.55;
    }
    if (b.x + b.radius >= outerRight) {
      b.x = outerRight - b.radius;
      b.vx = -Math.abs(b.vx) * 0.55;
    }

    // Goal Roof Bounce
    if (b.x < this.FIELD_LEFT || b.x > this.FIELD_RIGHT) {
      if (b.y - b.radius <= this.GOAL_HEIGHT && b.y > this.GOAL_HEIGHT - 0.5 && b.vy < 0) {
        b.y = this.GOAL_HEIGHT + b.radius;
        b.vy = Math.abs(b.vy) * 0.65;
      }
    }
  }

  checkCrossbarCollision(postX, postY) {
    const b = this.ball;
    const dx = b.x - postX;
    const dy = b.y - postY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const minDist = b.radius + this.CROSSBAR_RADIUS;

    if (dist < minDist) {
      const nx = dx / (dist || 1);
      const ny = dy / (dist || 1);

      // Reposition
      b.x = postX + nx * (minDist + 0.02);
      b.y = postY + ny * (minDist + 0.02);

      // Reflect velocity
      const dot = b.vx * nx + b.vy * ny;
      b.vx = (b.vx - 2 * dot * nx) * 0.85;
      b.vy = (b.vy - 2 * dot * ny) * 0.85;
      b.spin = (nx > 0 ? 1 : -1) * 15;

      if (window.sound) window.sound.playPost();
    }
  }

  resolveBallPlayerInteractions() {
    const b = this.ball;

    this.players.forEach(p => {
      // 1. Head Collider (Sphere)
      const headX = p.x;
      const headY = p.y + p.headOffsetY;
      const dx = b.x - headX;
      const dy = b.y - headY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const minHeadDist = b.radius + p.headRadius;

      if (dist < minHeadDist) {
        const nx = dx / (dist || 1);
        const ny = dy / (dist || 1);

        // Reposition
        b.x = headX + nx * (minHeadDist + 0.02);
        b.y = headY + ny * (minHeadDist + 0.02);

        // Head bounce physics
        const relVx = b.vx - p.vx;
        const relVy = b.vy - p.vy;
        const normalVel = relVx * nx + relVy * ny;

        if (normalVel < 0) {
          const impulse = -normalVel * 1.55;
          b.vx += nx * impulse + p.vx * 0.45;
          b.vy += ny * impulse + Math.max(0, p.vy * 0.6) + 3.0;
          b.lastHitter = p.id;
          b.isSuper = false;

          // Head touch gain for super meter
          p.superMeter = Math.min(100, p.superMeter + 6.0);
          if (window.sound) window.sound.playHead();
        }
      }

      // 2. Body Knockback from Super-Shot
      if (b.isSuper && b.lastHitter !== p.id) {
        const bodyDist = Math.hypot(b.x - p.x, b.y - (p.y + 1.0));
        if (bodyDist < 1.4) {
          p.isStunned = 0.7;
          p.vx = (b.vx > 0 ? 1 : -1) * 12.0;
          p.vy = 5.0;
        }
      }
    });
  }

  checkGoals() {
    if (this.state !== 'playing' || this.goalCooldown > 0) return;
    const b = this.ball;

    // Left Goal mouth -> Red scores (Team 1)
    if (b.x < this.FIELD_LEFT && b.y < this.GOAL_HEIGHT && b.y > this.GROUND_Y) {
      this.score[1]++;
      this.onGoal(1);
    }
    // Right Goal mouth -> Blue scores (Team 0)
    else if (b.x > this.FIELD_RIGHT && b.y < this.GOAL_HEIGHT && b.y > this.GROUND_Y) {
      this.score[0]++;
      this.onGoal(0);
    }
  }

  onGoal(scoringTeam) {
    this.goalCooldown = 2.4;
    if (window.sound) window.sound.playGoal();
    if (this.onGoalCallback) this.onGoalCallback(scoringTeam, this.score);
    
    // Auto reset after celebrate
    setTimeout(() => {
      if (this.state === 'playing') {
        this.resetKickoff(scoringTeam === 0 ? -1 : 1);
      }
    }, 1800);
  }

  checkStallWatchdog(dt) {
    const spd = Math.hypot(this.ball.vx, this.ball.vy);
    if (spd < 1.0) {
      this.stallTimer += dt;
      if (this.stallTimer > 5.0) {
        // Nudge ball toward center
        this.ball.vx = (this.ball.x > 0 ? -1 : 1) * 8.0;
        this.ball.vy = 12.0;
        this.stallTimer = 0;
      }
    } else {
      this.stallTimer = 0;
    }
  }
}

window.GamePhysics = GamePhysics;
