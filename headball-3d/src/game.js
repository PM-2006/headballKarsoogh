/**
 * GilBall 3D Main Game Controller & Input Manager
 */

class HeadBallGame {
  constructor() {
    this.container = document.getElementById('game-canvas-container');
    this.physics = new GamePhysics();
    this.graphics = new GameGraphics(this.container);
    this.ai = new SmartBotAI(1, 'normal'); // Red team is AI by default
    this.ai2 = new SmartBotAI(0, 'normal'); // For AI vs AI mode

    this.gameMode = '1p_vs_ai'; // '1p_vs_ai', '2p_local', 'ai_vs_ai'
    this.paused = false;

    // Keys State
    this.keys = {};

    this.initInputs();
    this.initUI();

    // Hook goal callback for celebration
    this.physics.onGoalCallback = (team, score) => this.onGoalScored(team, score);

    // Start Loop
    this.lastTime = performance.now();
    requestAnimationFrame((t) => this.loop(t));
  }

  initInputs() {
    window.addEventListener('keydown', (e) => {
      this.keys[e.code] = true;
      if (e.code === 'KeyP' || e.code === 'Escape') this.togglePause();
    });

    window.addEventListener('keyup', (e) => {
      this.keys[e.code] = false;
    });
  }

  initUI() {
    // Buttons
    document.getElementById('btn-start')?.addEventListener('click', () => this.startMatch());
    document.getElementById('btn-restart')?.addEventListener('click', () => this.restartMatch());
    document.getElementById('btn-pause')?.addEventListener('click', () => this.togglePause());

    // Game Mode select
    document.getElementById('select-mode')?.addEventListener('change', (e) => {
      this.gameMode = e.target.value;
      this.restartMatch();
    });

    // AI Difficulty select
    document.getElementById('select-difficulty')?.addEventListener('change', (e) => {
      this.ai.setDifficulty(e.target.value);
      this.ai2.setDifficulty(e.target.value);
    });

    // Camera view select
    document.getElementById('select-camera')?.addEventListener('change', (e) => {
      this.graphics.cameraMode = e.target.value;
    });

    // Match Duration select
    document.getElementById('select-duration')?.addEventListener('change', (e) => {
      this.physics.resetMatch(parseInt(e.target.value) || 60);
    });

    // Mobile / Touch Virtual Buttons
    const bindTouch = (id, keyName) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('touchstart', (e) => { e.preventDefault(); this.keys[keyName] = true; });
      el.addEventListener('touchend', (e) => { e.preventDefault(); this.keys[keyName] = false; });
      el.addEventListener('mousedown', () => { this.keys[keyName] = true; });
      el.addEventListener('mouseup', () => { this.keys[keyName] = false; });
    };

    bindTouch('btn-left', 'ArrowLeft');
    bindTouch('btn-right', 'ArrowRight');
    bindTouch('btn-jump', 'KeyW');
    bindTouch('btn-kick-low', 'KeyJ');
    bindTouch('btn-kick-high', 'KeyK');
    bindTouch('btn-super', 'KeyL');
  }

  handlePlayerInputs() {
    const p1 = this.physics.players[0];
    const p2 = this.physics.players[1];

    // ─── PLAYER 1 CONTROLS ───
    if (this.gameMode === 'ai_vs_ai') {
      this.ai2.update(this.physics, 1 / 60);
    } else {
      p1.input.move = 0;
      if (this.keys['KeyA'] || this.keys['ArrowLeft']) p1.input.move = -1;
      if (this.keys['KeyD'] || this.keys['ArrowRight']) p1.input.move = 1;

      p1.input.jump = !!(this.keys['KeyW'] || this.keys['Space'] || this.keys['ArrowUp']);
      p1.input.kickLow = !!(this.keys['KeyJ'] || this.keys['KeyX']);
      p1.input.kickHigh = !!(this.keys['KeyK'] || this.keys['KeyC']);
      p1.input.superShot = !!(this.keys['KeyL'] || this.keys['KeyV']);
    }

    // ─── PLAYER 2 CONTROLS ───
    if (this.gameMode === '2p_local') {
      p2.input.move = 0;
      if (this.keys['Numpad4'] || this.keys['KeyJ']) p2.input.move = -1;
      if (this.keys['Numpad6'] || this.keys['KeyL']) p2.input.move = 1;

      p2.input.jump = !!(this.keys['Numpad8'] || this.keys['KeyI']);
      p2.input.kickLow = !!(this.keys['Numpad1'] || this.keys['KeyB']);
      p2.input.kickHigh = !!(this.keys['Numpad2'] || this.keys['KeyN']);
      p2.input.superShot = !!(this.keys['Numpad3'] || this.keys['KeyM']);
    } else {
      // AI controls Player 2
      this.ai.update(this.physics, 1 / 60);
    }
  }

  togglePause() {
    this.paused = !this.paused;
    const pauseOverlay = document.getElementById('pause-modal');
    if (pauseOverlay) {
      pauseOverlay.style.display = this.paused ? 'flex' : 'none';
    }
  }

  restartMatch() {
    const dur = parseInt(document.getElementById('select-duration')?.value) || 60;
    this.physics.resetMatch(dur);
    this.paused = false;
    document.getElementById('pause-modal').style.display = 'none';
    document.getElementById('game-over-modal').style.display = 'none';
    if (window.sound) window.sound.playWhistle(false);
  }

  onGoalScored(team, score) {
    const banner = document.getElementById('goal-banner');
    const teamName = team === 0 ? 'تیم آبی (Blue)' : 'تیم قرمز (Red)';
    const teamColor = team === 0 ? '#2196f3' : '#e6194b';

    if (banner) {
      banner.style.color = teamColor;
      banner.textContent = `⚽ گل برای ${teamName}!`;
      banner.classList.add('active');
      setTimeout(() => banner.classList.remove('active'), 1800);
    }

    // Spawn 3D Confetti at scoring goal
    const goalX = (team === 0 ? 13.0 : -13.0);
    this.graphics.spawnGoalConfetti(goalX);
  }

  updateHUD() {
    const s1 = document.getElementById('score-team1');
    const s2 = document.getElementById('score-team2');
    const timeEl = document.getElementById('match-timer');
    const superBar1 = document.getElementById('super-bar-1');
    const superBar2 = document.getElementById('super-bar-2');

    if (s1) s1.textContent = this.physics.score[0];
    if (s2) s2.textContent = this.physics.score[1];
    if (timeEl) timeEl.textContent = this.physics.matchTime.toFixed(1) + 's';

    // Super Bars
    if (superBar1) {
      const val1 = this.physics.players[0].superMeter;
      superBar1.style.width = val1 + '%';
      superBar1.classList.toggle('ready', val1 >= 99);
    }
    if (superBar2) {
      const val2 = this.physics.players[1].superMeter;
      superBar2.style.width = val2 + '%';
      superBar2.classList.toggle('ready', val2 >= 99);
    }

    // Game Over check
    if (this.physics.state === 'game_over') {
      const overModal = document.getElementById('game-over-modal');
      const winText = document.getElementById('winner-text');
      const finalScore = document.getElementById('final-score-text');

      if (overModal && overModal.style.display !== 'flex') {
        overModal.style.display = 'flex';
        const sc = this.physics.score;
        if (sc[0] > sc[1]) {
          winText.textContent = '🏆 تیم ۱ (آبی) برنده شد!';
          winText.style.color = '#2196f3';
        } else if (sc[1] > sc[0]) {
          winText.textContent = '🏆 تیم ۲ (قرمز) برنده شد!';
          winText.style.color = '#e6194b';
        } else {
          winText.textContent = '🤝 بازی مساوی شد!';
          winText.style.color = '#ffeb3b';
        }
        if (finalScore) finalScore.textContent = `${sc[0]} : ${sc[1]}`;
      }
    }
  }

  loop(currentTime) {
    requestAnimationFrame((t) => this.loop(t));

    const dt = Math.min((currentTime - this.lastTime) * 0.001, 0.05);
    this.lastTime = currentTime;

    if (!this.paused) {
      this.handlePlayerInputs();
      this.physics.update(dt);
    }

    this.graphics.render(this.physics, dt);
    this.updateHUD();
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.game = new HeadBallGame();
});
