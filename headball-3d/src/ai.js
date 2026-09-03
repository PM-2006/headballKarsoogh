/**
 * GilBall 3D Smart AI Controller
 * Handles decision-making, ball trajectory prediction, attack & defense positioning.
 */

class SmartBotAI {
  constructor(playerIndex, difficulty = 'normal') {
    this.playerIndex = playerIndex;
    this.difficulty = difficulty; // 'easy', 'normal', 'pro'
    this.reactionTimer = 0;
    this.targetX = 0;
    this.wantsJump = false;
    this.wantsKickLow = false;
    this.wantsKickHigh = false;
    this.wantsSuper = false;
  }

  setDifficulty(level) {
    this.difficulty = level;
  }

  update(physics, dt) {
    const me = physics.players[this.playerIndex];
    const opponent = physics.players[1 - this.playerIndex];
    const ball = physics.ball;
    const isRightTeam = (this.playerIndex === 1);
    const ownGoalX = isRightTeam ? physics.FIELD_RIGHT : physics.FIELD_LEFT;
    const enemyGoalX = isRightTeam ? physics.FIELD_LEFT : physics.FIELD_RIGHT;
    const forwardDir = isRightTeam ? -1 : 1;

    this.reactionTimer -= dt;

    // Reaction rate based on difficulty
    const reactionDelay = this.difficulty === 'pro' ? 0.04 : (this.difficulty === 'normal' ? 0.09 : 0.18);

    if (this.reactionTimer <= 0) {
      this.reactionTimer = reactionDelay + Math.random() * 0.03;
      this.calculateDecision(physics, me, opponent, ball, ownGoalX, enemyGoalX, forwardDir);
    }

    // Apply inputs to player
    me.input.move = 0;
    const moveTolerance = this.difficulty === 'easy' ? 0.4 : 0.15;
    if (this.targetX > me.x + moveTolerance) {
      me.input.move = 1;
    } else if (this.targetX < me.x - moveTolerance) {
      me.input.move = -1;
    }

    me.input.jump = this.wantsJump;
    me.input.kickLow = this.wantsKickLow;
    me.input.kickHigh = this.wantsKickHigh;
    me.input.superShot = this.wantsSuper;

    // Reset one-frame actions
    this.wantsJump = false;
    this.wantsKickLow = false;
    this.wantsKickHigh = false;
    this.wantsSuper = false;
  }

  calculateDecision(physics, me, opponent, ball, ownGoalX, enemyGoalX, forwardDir) {
    const dxToBall = ball.x - me.x;
    const dyToBall = ball.y - me.y;
    const distToBall = Math.hypot(dxToBall, dyToBall);
    const distToOwnGoal = Math.abs(me.x - ownGoalX);
    const isBallHeadingToOwnGoal = (isRightTeam => isRightTeam ? ball.vx > 1.5 : ball.vx < -1.5)(this.playerIndex === 1);

    // Predict where the ball will be in next 0.3s
    const predBallX = ball.x + ball.vx * 0.32;
    const predBallY = Math.max(0, ball.y + ball.vy * 0.32);

    // 1. Defend Goal Emergency: Ball is flying over head towards our net
    if (isBallHeadingToOwnGoal && Math.abs(predBallX - ownGoalX) < 4.5 && ball.y > 2.0) {
      // Retreat back to goal line
      this.targetX = ownGoalX - forwardDir * 2.2;
      if (distToBall < 3.2 && ball.y > 1.8 && me.onGround) {
        this.wantsJump = true;
      }
      return;
    }

    // 2. Attack / Intercept Ball
    // Position slightly behind ball in attack direction
    const offsetBehindBall = -forwardDir * (this.difficulty === 'pro' ? 0.35 : 0.6);
    this.targetX = predBallX + offsetBehindBall;

    // Keep within pitch boundary
    this.targetX = Math.max(physics.FIELD_LEFT + 0.8, Math.min(physics.FIELD_RIGHT - 0.8, this.targetX));

    // 3. Kick & Header Timing
    const canKickDistance = 2.3;
    const isFacingBall = (dxToBall * forwardDir > -0.4);

    if (distToBall < canKickDistance && isFacingBall) {
      // Super Shot Unleash
      if (me.superMeter >= 99 && Math.abs(me.x - enemyGoalX) < 16) {
        this.wantsSuper = true;
        return;
      }

      // Check opponent position to choose High Lob vs Low Drive
      const oppDistance = Math.abs(opponent.x - me.x);
      const isOpponentClose = oppDistance < 4.0;

      if (isOpponentClose && ball.y < 2.0 && Math.random() < 0.6) {
        // Lob over jumping opponent
        this.wantsKickHigh = true;
      } else {
        // Fast ground drive
        this.wantsKickLow = true;
      }

      // Jump kick if ball is in mid-air
      if (ball.y > 1.4 && ball.y < 3.4 && me.onGround) {
        this.wantsJump = true;
      }
    }

    // 4. Header jump when ball is descending
    if (distToBall < 3.0 && ball.y > 2.2 && ball.y < 4.5 && ball.vy < 2.0 && me.onGround) {
      if (Math.abs(dxToBall) < 1.4) {
        this.wantsJump = true;
      }
    }
  }
}

window.SmartBotAI = SmartBotAI;
