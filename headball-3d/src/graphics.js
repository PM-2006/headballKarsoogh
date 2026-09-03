/**
 * GilBall 3D High-End Graphics Engine (Three.js)
 * Full 3D Stadium, Animated Characters, Dynamic Lighting & Particles.
 */

class GameGraphics {
  constructor(container) {
    this.container = container;
    this.width = container.clientWidth || window.innerWidth;
    this.height = container.clientHeight || window.innerHeight;

    // Three.js Core
    this.scene = new THREE.Scene();
    this.camera = null;
    this.renderer = null;

    // Visual Objects
    this.ballMesh = null;
    this.ballShadow = null;
    this.ballFireTrail = [];
    this.ballGlowLight = null;
    this.superAura = null;

    this.playerMeshes = [];
    this.crowdParticles = [];
    this.confettiParticles = [];
    this.netMeshes = [];

    // Camera settings
    this.cameraMode = 'broadcast'; // 'broadcast', 'follow', 'side'
    this.cameraShake = 0;
    this.nightMode = true;

    this.init();
  }

  init() {
    // 1. Scene & Environment
    this.scene.background = new THREE.Color(0x0a1226);
    this.scene.fog = new THREE.FogExp2(0x0a1226, 0.012);

    // 2. Camera Setup
    const aspect = this.width / this.height;
    this.camera = new THREE.PerspectiveCamera(40, aspect, 0.1, 300);
    this.camera.position.set(0, 9.5, 23.0);
    this.camera.lookAt(0, 3.2, 0);

    // 3. WebGL Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;
    this.container.appendChild(this.renderer.domElement);

    // 4. Build 3D World
    this.buildLighting();
    this.buildPitch();
    this.buildStadium();
    this.buildGoals();
    this.buildBall();
    this.buildPlayers();
    this.buildConfettiSystem();

    // 5. Handle Resize
    window.addEventListener('resize', () => this.onResize());
  }

  onResize() {
    this.width = this.container.clientWidth || window.innerWidth;
    this.height = this.container.clientHeight || window.innerHeight;
    this.camera.aspect = this.width / this.height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(this.width, this.height);
  }

  // ════════════════════════ LIGHTING & ENVIRONMENT ════════════════════════
  buildLighting() {
    // Ambient light
    this.ambientLight = new THREE.AmbientLight(0x7090c0, 0.6);
    this.scene.add(this.ambientLight);

    // Hemisphere sky-ground fill
    const hemiLight = new THREE.HemisphereLight(0x8bc34a, 0x1a237e, 0.45);
    this.scene.add(hemiLight);

    // Main Sun / Main Floodlight
    this.dirLight = new THREE.DirectionalLight(0xfff8ee, 1.2);
    this.dirLight.position.set(0, 24, 18);
    this.dirLight.castShadow = true;
    this.dirLight.shadow.mapSize.width = 2048;
    this.dirLight.shadow.mapSize.height = 2048;
    this.dirLight.shadow.camera.near = 0.5;
    this.dirLight.shadow.camera.far = 60;
    this.dirLight.shadow.camera.left = -22;
    this.dirLight.shadow.camera.right = 22;
    this.dirLight.shadow.camera.top = 18;
    this.dirLight.shadow.camera.bottom = -4;
    this.dirLight.shadow.bias = -0.0005;
    this.scene.add(this.dirLight);

    // Stadium Floodlight Towers
    this.floodlights = [];
    const lightPositions = [
      { x: -17, z: -10 },
      { x: 17, z: -10 },
      { x: -17, z: 12 },
      { x: 17, z: 12 }
    ];

    lightPositions.forEach(pos => {
      // Tower Pole
      const poleGeo = new THREE.CylinderGeometry(0.2, 0.35, 18, 8);
      const poleMat = new THREE.MeshStandardMaterial({ color: 0x37474f, metalness: 0.8, roughness: 0.3 });
      const pole = new THREE.Mesh(poleGeo, poleMat);
      pole.position.set(pos.x, 9, pos.z);
      this.scene.add(pole);

      // Light Rack
      const rackGeo = new THREE.BoxGeometry(3.2, 1.4, 0.6);
      const rackMat = new THREE.MeshStandardMaterial({ color: 0x263238 });
      const rack = new THREE.Mesh(rackGeo, rackMat);
      rack.position.set(pos.x, 18, pos.z);
      rack.lookAt(0, 0, 0);
      this.scene.add(rack);

      // Spot Light
      const spot = new THREE.SpotLight(0xfffae0, 0.8, 45, Math.PI / 4, 0.4);
      spot.position.set(pos.x, 18, pos.z);
      spot.target.position.set(0, 1.5, 0);
      this.scene.add(spot);
      this.scene.add(spot.target);
      this.floodlights.push(spot);
    });
  }

  // ════════════════════════ PITCH & FIELD ════════════════════════
  buildPitch() {
    // Generate High-Res Procedural Grass Canvas Texture
    const canvas = document.createElement('canvas');
    canvas.width = 2048;
    canvas.height = 1024;
    const ctx = canvas.getContext('2d');

    // Striped turf lawn
    const stripes = 16;
    const stripeW = canvas.width / stripes;
    for (let i = 0; i < stripes; i++) {
      ctx.fillStyle = i % 2 === 0 ? '#2e7d32' : '#388e3c';
      ctx.fillRect(i * stripeW, 0, stripeW, canvas.height);
    }

    // Grass fiber noise texture
    for (let i = 0; i < 40000; i++) {
      ctx.fillStyle = Math.random() > 0.5 ? 'rgba(255,255,255,0.025)' : 'rgba(0,0,0,0.035)';
      ctx.fillRect(Math.random() * canvas.width, Math.random() * canvas.height, 2, 4);
    }

    // White Pitch Markings
    ctx.strokeStyle = 'rgba(255,255,255,0.92)';
    ctx.lineWidth = 10;
    const marginX = 80;
    const marginY = 60;
    const pW = canvas.width - 2 * marginX;
    const pH = canvas.height - 2 * marginY;

    // Outer boundary
    ctx.strokeRect(marginX, marginY, pW, pH);

    // Halfway Line
    ctx.beginPath();
    ctx.moveTo(canvas.width / 2, marginY);
    ctx.lineTo(canvas.width / 2, canvas.height - marginY);
    ctx.stroke();

    // Center Circle & Spot
    ctx.beginPath();
    ctx.arc(canvas.width / 2, canvas.height / 2, 140, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(canvas.width / 2, canvas.height / 2, 12, 0, Math.PI * 2);
    ctx.fill();

    // Penalty Boxes Left & Right
    const boxW = 240, boxH = 460;
    ctx.strokeRect(marginX, (canvas.height - boxH) / 2, boxW, boxH);
    ctx.strokeRect(canvas.width - marginX - boxW, (canvas.height - boxH) / 2, boxW, boxH);

    // Penalty Arcs
    ctx.beginPath();
    ctx.arc(marginX + boxW, canvas.height / 2, 90, -0.65, 0.65);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(canvas.width - marginX - boxW, canvas.height / 2, 90, Math.PI - 0.65, Math.PI + 0.65);
    ctx.stroke();

    const grassTex = new THREE.CanvasTexture(canvas);
    grassTex.anisotropy = 16;

    // Pitch Ground Mesh
    const pitchGeo = new THREE.PlaneGeometry(32.0, 15.0);
    const pitchMat = new THREE.MeshStandardMaterial({
      map: grassTex,
      roughness: 0.8,
      metalness: 0.05
    });
    const pitch = new THREE.Mesh(pitchGeo, pitchMat);
    pitch.rotation.x = -Math.PI / 2;
    pitch.position.set(0, 0, 0);
    pitch.receiveShadow = true;
    this.scene.add(pitch);

    // Dark Stadium Apron Outer Floor
    const outerGeo = new THREE.PlaneGeometry(120, 80);
    const outerMat = new THREE.MeshStandardMaterial({ color: 0x0a160a, roughness: 0.95 });
    const outer = new THREE.Mesh(outerGeo, outerMat);
    outer.rotation.x = -Math.PI / 2;
    outer.position.set(0, -0.02, 0);
    outer.receiveShadow = true;
    this.scene.add(outer);
  }

  // ════════════════════════ STADIUM & CROWD ════════════════════════
  buildStadium() {
    // 1. Grandstand Tiers (Back Stand)
    const tiers = [
      { color: 0x1a2744, h: 3.5, z: -8.5, w: 42 },
      { color: 0x223358, h: 6.0, z: -11.5, w: 46 },
      { color: 0x2a3e6c, h: 9.0, z: -14.5, w: 50 }
    ];

    tiers.forEach(tier => {
      const geo = new THREE.BoxGeometry(tier.w, tier.h, 2.5);
      const mat = new THREE.MeshStandardMaterial({ color: tier.color, roughness: 0.85 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(0, tier.h / 2, tier.z);
      mesh.receiveShadow = true;
      this.scene.add(mesh);
    });

    // 2. Animated 3D Crowd Spectators
    const crowdGeo = new THREE.BoxGeometry(0.24, 0.4, 0.24);
    const teamColors = [0x2196f3, 0xe6194b, 0xffeb3b, 0xffffff, 0x4caf50, 0xff9800];

    for (let i = 0; i < 450; i++) {
      const mat = new THREE.MeshBasicMaterial({ color: teamColors[i % teamColors.length] });
      const spectator = new THREE.Mesh(crowdGeo, mat);
      
      const x = (Math.random() - 0.5) * 38;
      const tierChoice = Math.floor(Math.random() * 3);
      const y = tiers[tierChoice].h + 0.2;
      const z = tiers[tierChoice].z + (Math.random() - 0.5) * 1.5;

      spectator.position.set(x, y, z);
      spectator.userData = { baseY: y, phase: Math.random() * Math.PI * 2, speed: 3 + Math.random() * 4 };
      this.crowdParticles.push(spectator);
      this.scene.add(spectator);
    }

    // 3. Side Walls
    const sideWallGeo = new THREE.BoxGeometry(1.2, 8, 22);
    const sideWallMat = new THREE.MeshStandardMaterial({ color: 0x172138, roughness: 0.8 });

    const leftWall = new THREE.Mesh(sideWallGeo, sideWallMat);
    leftWall.position.set(-18, 4, 0);
    this.scene.add(leftWall);

    const rightWall = new THREE.Mesh(sideWallGeo, sideWallMat);
    rightWall.position.set(18, 4, 0);
    this.scene.add(rightWall);

    // 4. Animated LED Advertising Boards along Touchline
    const ledMat = new THREE.MeshBasicMaterial({ color: 0x00e5ff });
    this.ledBoards = [];

    const adColors = [0x00e5ff, 0xff0055, 0xffeb3b, 0x00e676, 0x7c4dff];
    for (let i = 0; i < 12; i++) {
      const bGeo = new THREE.BoxGeometry(2.6, 0.65, 0.15);
      const bMat = new THREE.MeshBasicMaterial({ color: adColors[i % adColors.length] });
      const board = new THREE.Mesh(bGeo, bMat);
      board.position.set(-14.5 + i * 2.65, 0.32, -6.8);
      this.scene.add(board);
      this.ledBoards.push(board);
    }
  }

  // ════════════════════════ 3D GOALS WITH NETS ════════════════════════
  buildGoals() {
    const goalHeight = 3.5;
    const goalDepth = 2.0;
    const postRadius = 0.08;
    const halfGoalZ = 2.0; // Goal width along Z

    const postMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      metalness: 0.75,
      roughness: 0.2
    });

    [-13.0, 13.0].forEach((postX, isRight) => {
      const dir = isRight === 1 ? 1 : -1;
      const group = new THREE.Group();

      // Front Posts
      [-halfGoalZ, halfGoalZ].forEach(z => {
        const post = new THREE.Mesh(new THREE.CylinderGeometry(postRadius, postRadius, goalHeight, 16), postMat);
        post.position.set(0, goalHeight / 2, z);
        post.castShadow = true;
        group.add(post);

        // Back Post
        const backPost = new THREE.Mesh(new THREE.CylinderGeometry(postRadius * 0.7, postRadius * 0.7, goalHeight, 16), postMat);
        backPost.position.set(dir * goalDepth, goalHeight / 2, z);
        group.add(backPost);
      });

      // Front Crossbar
      const bar = new THREE.Mesh(new THREE.CylinderGeometry(postRadius, postRadius, halfGoalZ * 2 + postRadius * 2, 16), postMat);
      bar.rotation.x = Math.PI / 2;
      bar.position.set(0, goalHeight, 0);
      bar.castShadow = true;
      group.add(bar);

      // Back Top Crossbar
      const backBar = new THREE.Mesh(new THREE.CylinderGeometry(postRadius * 0.7, postRadius * 0.7, halfGoalZ * 2, 16), postMat);
      backBar.rotation.x = Math.PI / 2;
      backBar.position.set(dir * goalDepth, goalHeight, 0);
      group.add(backBar);

      // Connecting Roof Bars
      [-halfGoalZ, halfGoalZ].forEach(z => {
        const conn = new THREE.Mesh(new THREE.CylinderGeometry(postRadius * 0.5, postRadius * 0.5, goalDepth, 8), postMat);
        conn.rotation.z = Math.PI / 2;
        conn.position.set(dir * goalDepth / 2, goalHeight, z);
        group.add(conn);
      });

      // 3D Hex Netting (Back, Top, Sides)
      const netMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.28,
        wireframe: true,
        side: THREE.DoubleSide
      });

      // Back Net
      const backNet = new THREE.Mesh(new THREE.PlaneGeometry(halfGoalZ * 2, goalHeight, 14, 10), netMat);
      backNet.rotation.y = Math.PI / 2;
      backNet.position.set(dir * goalDepth, goalHeight / 2, 0);
      group.add(backNet);

      // Top Net
      const topNet = new THREE.Mesh(new THREE.PlaneGeometry(goalDepth, halfGoalZ * 2, 8, 14), netMat);
      topNet.rotation.x = Math.PI / 2;
      topNet.position.set(dir * goalDepth / 2, goalHeight, 0);
      group.add(topNet);

      // Side Nets
      [-halfGoalZ, halfGoalZ].forEach(z => {
        const sideNet = new THREE.Mesh(new THREE.PlaneGeometry(goalDepth, goalHeight, 8, 10), netMat);
        sideNet.position.set(dir * goalDepth / 2, goalHeight / 2, z);
        group.add(sideNet);
      });

      group.position.set(postX, 0, 0);
      this.scene.add(group);
      this.netMeshes.push(backNet);
    });
  }

  // ════════════════════════ 3D SOCCER BALL ════════════════════════
  buildBall() {
    const ballRadius = 0.42;

    // Classic Pentagon Texture
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 512, 512);
    ctx.fillStyle = '#1a2332';

    const drawPentagon = (cx, cy, r) => {
      ctx.beginPath();
      for (let i = 0; i < 5; i++) {
        const a = -Math.PI / 2 + i * (2 * Math.PI / 5);
        const px = cx + Math.cos(a) * r;
        const py = cy + Math.sin(a) * r;
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      }
      ctx.closePath();
      ctx.fill();
    };

    drawPentagon(256, 256, 68);
    drawPentagon(90, 110, 52);
    drawPentagon(422, 110, 52);
    drawPentagon(90, 410, 52);
    drawPentagon(422, 410, 52);

    // Seams
    ctx.strokeStyle = '#1a2332';
    ctx.lineWidth = 5;
    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + i * (2 * Math.PI / 5);
      ctx.beginPath();
      ctx.moveTo(256 + Math.cos(a) * 68, 256 + Math.sin(a) * 68);
      ctx.lineTo(256 + Math.cos(a) * 210, 256 + Math.sin(a) * 210);
      ctx.stroke();
    }

    const ballTex = new THREE.CanvasTexture(canvas);

    // Ball Mesh
    const ballGeo = new THREE.SphereGeometry(ballRadius, 24, 24);
    const ballMat = new THREE.MeshStandardMaterial({
      map: ballTex,
      roughness: 0.35,
      metalness: 0.05
    });
    this.ballMesh = new THREE.Mesh(ballGeo, ballMat);
    this.ballMesh.castShadow = true;
    this.scene.add(this.ballMesh);

    // Dynamic Blob Shadow on Ground
    const shadowGeo = new THREE.CircleGeometry(ballRadius * 1.5, 18);
    const shadowMat = new THREE.MeshBasicMaterial({
      color: 0x000000,
      transparent: true,
      opacity: 0.35,
      depthWrite: false
    });
    this.ballShadow = new THREE.Mesh(shadowGeo, shadowMat);
    this.ballShadow.rotation.x = -Math.PI / 2;
    this.ballShadow.position.y = 0.01;
    this.scene.add(this.ballShadow);

    // Ball Point Light (Glow on high speed)
    this.ballGlowLight = new THREE.PointLight(0xff5500, 0, 8);
    this.scene.add(this.ballGlowLight);

    // Fireball Trail Spheres
    for (let i = 0; i < 14; i++) {
      const trGeo = new THREE.SphereGeometry(ballRadius * (0.85 - i * 0.05), 8, 8);
      const trMat = new THREE.MeshBasicMaterial({
        color: 0xff3d00,
        transparent: true,
        opacity: 0
      });
      const trMesh = new THREE.Mesh(trGeo, trMat);
      trMesh.visible = false;
      this.ballFireTrail.push(trMesh);
      this.scene.add(trMesh);
    }
  }

  // ════════════════════════ 3D CHARACTERS ════════════════════════
  buildPlayers() {
    const teamColors = [0x2196f3, 0xe6194b];

    for (let i = 0; i < 2; i++) {
      const group = new THREE.Group();
      const color = teamColors[i];
      const darkColor = (new THREE.Color(color)).multiplyScalar(0.65).getHex();
      const skinColor = 0xffccaa;

      // 1. Head (Big Head Stylized)
      const headGeo = new THREE.SphereGeometry(0.72, 24, 18);
      const headMat = new THREE.MeshStandardMaterial({ color: skinColor, roughness: 0.45 });
      const head = new THREE.Mesh(headGeo, headMat);
      head.position.y = 1.45;
      head.castShadow = true;
      group.add(head);

      // 2. Cool Spiky Hair
      const hairMat = new THREE.MeshStandardMaterial({ color: darkColor, roughness: 0.6 });
      const hairSpikes = [
        { x: 0, y: 2.15, z: 0, s: 0.28, rz: 0 },
        { x: 0.25, y: 2.05, z: 0.15, s: 0.22, rz: 0.35 },
        { x: -0.25, y: 2.05, z: 0.15, s: 0.22, rz: -0.35 },
        { x: 0.18, y: 2.0, z: -0.22, s: 0.24, rz: 0.5 },
        { x: -0.18, y: 2.0, z: -0.22, s: 0.24, rz: -0.5 }
      ];
      hairSpikes.forEach(sp => {
        const spike = new THREE.Mesh(new THREE.ConeGeometry(sp.s, 0.55, 5), hairMat);
        spike.position.set(sp.x, sp.y, sp.z);
        spike.rotation.z = sp.rz;
        group.add(spike);
      });

      // 3. Expressive 3D Eyes (Ball Tracking)
      const eyeMat = new THREE.MeshBasicMaterial({ color: 0x111111 });
      const eyeWhiteMat = new THREE.MeshBasicMaterial({ color: 0xffffff });

      const eyeGroup = new THREE.Group();
      [-0.22, 0.22].forEach(ex => {
        // Eye White
        const eyeWhite = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 12), eyeWhiteMat);
        eyeWhite.position.set(ex, 1.55, 0.58);
        eyeWhite.scale.set(1, 1.2, 0.5);
        eyeGroup.add(eyeWhite);

        // Pupil
        const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8), eyeMat);
        pupil.position.set(ex, 1.55, 0.68);
        eyeGroup.add(pupil);
      });
      group.add(eyeGroup);
      group.userData.eyeGroup = eyeGroup;

      // 4. Jersey Torso
      const torsoGeo = new THREE.BoxGeometry(0.85, 0.75, 0.65);
      const torsoMat = new THREE.MeshStandardMaterial({ color: color, roughness: 0.5 });
      const torso = new THREE.Mesh(torsoGeo, torsoMat);
      torso.position.y = 0.65;
      torso.castShadow = true;
      group.add(torso);

      // Jersey Stripe / Number
      const numGeo = new THREE.PlaneGeometry(0.35, 0.35);
      const numMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide });
      const num = new THREE.Mesh(numGeo, numMat);
      num.position.set(0, 0.65, 0.33);
      group.add(num);

      // 5. Cleats / Boots (Animated on kick)
      const bootGeo = new THREE.BoxGeometry(0.32, 0.22, 0.55);
      const bootMat = new THREE.MeshStandardMaterial({ color: darkColor, roughness: 0.3, metalness: 0.3 });

      const footL = new THREE.Mesh(bootGeo, bootMat);
      footL.position.set(-0.25, 0.11, 0.05);
      group.add(footL);

      const footR = new THREE.Mesh(bootGeo, bootMat);
      footR.position.set(0.25, 0.11, 0.05);
      group.add(footR);

      group.userData.footR = footR;
      group.userData.footL = footL;

      // 6. Ground Shadow
      const pShadow = new THREE.Mesh(
        new THREE.CircleGeometry(0.95, 16),
        new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.32, depthWrite: false })
      );
      pShadow.rotation.x = -Math.PI / 2;
      pShadow.position.y = 0.01;
      group.add(pShadow);
      group.userData.shadow = pShadow;

      this.scene.add(group);
      this.playerMeshes.push(group);
    }
  }

  // ════════════════════════ CONFETTI & PARTICLES ════════════════════════
  buildConfettiSystem() {
    this.confettiGroup = new THREE.Group();
    const confColors = [0x2196f3, 0xe6194b, 0xffd600, 0x00e676, 0xff4081, 0xffffff];
    const geo = new THREE.PlaneGeometry(0.18, 0.28);

    for (let i = 0; i < 180; i++) {
      const mat = new THREE.MeshBasicMaterial({
        color: confColors[i % confColors.length],
        side: THREE.DoubleSide
      });
      const piece = new THREE.Mesh(geo, mat);
      piece.visible = false;
      this.confettiParticles.push(piece);
      this.confettiGroup.add(piece);
    }
    this.scene.add(this.confettiGroup);
  }

  spawnGoalConfetti(scoringTeamX) {
    this.cameraShake = 0.65;
    this.confettiParticles.forEach(p => {
      p.visible = true;
      p.position.set(scoringTeamX + (Math.random() - 0.5) * 4, 3 + Math.random() * 4, (Math.random() - 0.5) * 4);
      p.userData = {
        vx: (Math.random() - 0.5) * 14,
        vy: 8 + Math.random() * 12,
        vz: (Math.random() - 0.5) * 14,
        rotSpeedX: Math.random() * 10,
        rotSpeedY: Math.random() * 10
      };
    });
  }

  // ════════════════════════ FRAME RENDER & UPDATE ════════════════════════
  render(physics, dt) {
    // 1. Update Ball Position & Rotation
    const b = physics.ball;
    this.ballMesh.position.set(b.x, b.y, b.z);
    
    // Rotate ball with velocity
    this.ballMesh.rotation.z -= b.vx * dt * 3.5;
    this.ballMesh.rotation.x += b.vy * dt * 2.0;

    // Ball Shadow
    this.ballShadow.position.set(b.x, 0.01, b.z);
    const heightNorm = Math.min(1.0, b.y / 7.0);
    this.ballShadow.scale.setScalar(1.0 - heightNorm * 0.5);
    this.ballShadow.material.opacity = 0.35 * (1.0 - heightNorm * 0.6);

    // Ball Speed Effects
    const speed = Math.hypot(b.vx, b.vy);
    const isFast = speed > 16.0 || b.isSuper;

    if (isFast) {
      this.ballGlowLight.intensity = Math.min(4.0, (speed - 12.0) * 0.35);
      this.ballGlowLight.position.set(b.x, b.y, b.z);
      this.ballGlowLight.color.setHex(b.isSuper ? 0x00e5ff : 0xff3d00);

      // Update Fire trail
      for (let i = this.ballFireTrail.length - 1; i > 0; i--) {
        this.ballFireTrail[i].position.copy(this.ballFireTrail[i - 1].position);
        this.ballFireTrail[i].material.opacity = this.ballFireTrail[i - 1].material.opacity * 0.72;
        this.ballFireTrail[i].visible = this.ballFireTrail[i].material.opacity > 0.05;
      }
      this.ballFireTrail[0].visible = true;
      this.ballFireTrail[0].position.set(b.x, b.y, b.z);
      this.ballFireTrail[0].material.opacity = 0.75;
      this.ballFireTrail[0].material.color.setHex(b.isSuper ? 0x00e5ff : 0xff3d00);
    } else {
      this.ballGlowLight.intensity *= 0.85;
      this.ballFireTrail.forEach(tr => {
        tr.material.opacity *= 0.7;
        if (tr.material.opacity < 0.02) tr.visible = false;
      });
    }

    // 2. Update Players
    physics.players.forEach((p, idx) => {
      const mesh = this.playerMeshes[idx];
      mesh.position.set(p.x, p.y, p.z);

      // Squash and stretch
      mesh.scale.set(1.0 / Math.sqrt(p.squash), p.squash, 1.0);

      // Facing orientation
      mesh.rotation.y = (p.facing === 1) ? Math.PI / 2 : -Math.PI / 2;

      // Foot Kick Animation
      if (mesh.userData.footR) {
        if (p.kickAnim > 0) {
          mesh.userData.footR.rotation.x = -p.kickAnim * Math.PI * 0.65;
          mesh.userData.footR.position.z = 0.05 + p.kickAnim * 0.45;
        } else {
          mesh.userData.footR.rotation.x = 0;
          mesh.userData.footR.position.z = 0.05;
        }
      }

      // Ground Shadow scaling
      if (mesh.userData.shadow) {
        const shadowFade = Math.min(1.0, p.y / 4.0);
        mesh.userData.shadow.scale.setScalar(1.0 - shadowFade * 0.4);
        mesh.userData.shadow.material.opacity = 0.32 * (1.0 - shadowFade * 0.7);
        mesh.userData.shadow.position.y = -p.y + 0.01;
      }

      // Eye tracking the ball
      if (mesh.userData.eyeGroup) {
        const dx = b.x - p.x;
        const dy = b.y - (p.y + 1.55);
        mesh.userData.eyeGroup.rotation.y = Math.atan2(dx, 6.0) * 0.5;
        mesh.userData.eyeGroup.rotation.x = -Math.atan2(dy, 6.0) * 0.5;
      }
    });

    // 3. Crowd Animation (Bouncing/Cheering)
    const time = performance.now() * 0.001;
    this.crowdParticles.forEach(sp => {
      sp.position.y = sp.userData.baseY + Math.abs(Math.sin(time * sp.userData.speed + sp.userData.phase)) * 0.35;
    });

    // 4. Confetti Particles Update
    this.confettiParticles.forEach(p => {
      if (p.visible) {
        p.userData.vy -= 22.0 * dt; // gravity
        p.position.x += p.userData.vx * dt;
        p.position.y += p.userData.vy * dt;
        p.position.z += p.userData.vz * dt;
        p.rotation.x += p.userData.rotSpeedX * dt;
        p.rotation.y += p.userData.rotSpeedY * dt;

        if (p.position.y < 0) p.visible = false;
      }
    });

    // 5. Dynamic Camera Behavior
    this.updateCamera(physics, dt);

    // 6. Final WebGL Render
    this.renderer.render(this.scene, this.camera);
  }

  updateCamera(physics, dt) {
    const ball = physics.ball;

    let targetCamX = 0;
    let targetCamY = 9.5;
    let targetCamZ = 23.0;

    if (this.cameraMode === 'follow') {
      // Dynamic camera smoothly follows the ball and action
      targetCamX = ball.x * 0.45;
      targetCamY = 7.5 + ball.y * 0.25;
      targetCamZ = 20.0;
    }

    // Apply Screen Shake
    if (this.cameraShake > 0) {
      targetCamX += (Math.random() - 0.5) * this.cameraShake * 1.5;
      targetCamY += (Math.random() - 0.5) * this.cameraShake * 1.5;
      this.cameraShake = Math.max(0, this.cameraShake - dt * 2.2);
    }

    // Smooth Lerp
    this.camera.position.x += (targetCamX - this.camera.position.x) * dt * 4.0;
    this.camera.position.y += (targetCamY - this.camera.position.y) * dt * 4.0;
    this.camera.position.z += (targetCamZ - this.camera.position.z) * dt * 4.0;
    this.camera.lookAt(targetCamX * 0.3, 2.8, 0);
  }
}

window.GameGraphics = GameGraphics;
