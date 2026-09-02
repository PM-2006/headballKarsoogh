/**
 * game3d.js — Three.js 3D renderer for GilBall
 * Requires the global THREE object (loaded via CDN <script> tag).
 *
 * Exposes window.Game3D = { init, updateFrame, setTeamColors, resize, dispose, isReady }
 */
(function () {
  'use strict';

  /* ───────── constants ───────── */
  const S  = 0.01;            // 1 game-pixel = 0.01 Three.js units

  /* defaults – overwritten by init(config) */
  let W   = 1500, H  = 860;
  let GY  = 730;              // ground_y
  let GD  = 122;              // goal_depth
  let GH  = 205;              // goal_height
  let BR  = 23;               // ball_radius
  let PW  = 66, PH = 84;     // player w / h

  /* three core */
  let containerEl, scene, camera, renderer;
  let ready = false;

  /* scene objects */
  let groundMesh, groundTex;
  let ballGroup, ballMesh, ballShadow, ballGlow, trailMeshes = [];
  let playerGroups = [];
  let goalGroups   = [];
  let teamHex = ['#2196F3', '#E6194B'];
  let teamColorsThree = [new THREE.Color('#2196F3'), new THREE.Color('#E6194B')];

  /* previous ball pos for trail */
  let prevBallPos = [];

  /* ───────── helpers ───────── */
  function gx(x)   { return x * S; }
  function gy(y)    { return Math.max(0, (GY - y) * S); }      // height above ground
  function gw(v)    { return v * S; }

  function hexToThree(hex) {
    return new THREE.Color(hex.replace('#','#'));
  }

  /* ───────── textures ───────── */
  function makePitchTexture() {
    const c = document.createElement('canvas');
    c.width = 2048; c.height = 1024;
    const ctx = c.getContext('2d');

    /* mowing stripes */
    const stripes = 14, sw = c.width / stripes;
    for (let i = 0; i < stripes; i++) {
      ctx.fillStyle = i % 2 === 0 ? '#2d8c3e' : '#339945';
      ctx.fillRect(i * sw, 0, sw, c.height);
    }

    /* markings */
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 6;
    /* touchlines */
    const mx = 40, my = 30;
    ctx.strokeRect(mx, my, c.width - 2 * mx, c.height - 2 * my);
    /* halfway */
    ctx.beginPath(); ctx.moveTo(c.width / 2, my); ctx.lineTo(c.width / 2, c.height - my); ctx.stroke();
    /* center circle */
    ctx.beginPath(); ctx.arc(c.width / 2, c.height / 2, 80, 0, Math.PI * 2); ctx.stroke();
    /* center spot */
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(c.width / 2, c.height / 2, 6, 0, Math.PI * 2); ctx.fill();
    /* penalty arcs left / right */
    ctx.beginPath(); ctx.arc(mx, c.height / 2, 110, -0.55, 0.55); ctx.stroke();
    ctx.beginPath(); ctx.arc(c.width - mx, c.height / 2, 110, Math.PI - 0.55, Math.PI + 0.55); ctx.stroke();

    const tex = new THREE.CanvasTexture(c);
    tex.anisotropy = 4;
    return tex;
  }

  function makeBallTexture() {
    const c = document.createElement('canvas');
    c.width = 256; c.height = 256;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 256, 256);
    ctx.fillStyle = '#1b2a3d';
    const pent = (cx, cy, r) => {
      ctx.beginPath();
      for (let i = 0; i < 5; i++) {
        const a = -Math.PI / 2 + i * (2 * Math.PI / 5);
        const px = cx + Math.cos(a) * r, py = cy + Math.sin(a) * r;
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      }
      ctx.closePath(); ctx.fill();
    };
    pent(128, 128, 32);
    pent(46, 56, 24); pent(210, 56, 24);
    pent(46, 200, 24); pent(210, 200, 24);
    /* seams */
    ctx.strokeStyle = '#1b2a3d'; ctx.lineWidth = 2;
    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + i * (2 * Math.PI / 5);
      ctx.beginPath();
      ctx.moveTo(128 + Math.cos(a) * 32, 128 + Math.sin(a) * 32);
      ctx.lineTo(128 + Math.cos(a) * 100, 128 + Math.sin(a) * 100);
      ctx.stroke();
    }
    return new THREE.CanvasTexture(c);
  }

  /* ───────── scene builders ───────── */

  function buildGround() {
    groundTex = makePitchTexture();
    const pw = gw(W) * 1.3, pd = 8;
    const geo = new THREE.PlaneGeometry(pw, pd);
    const mat = new THREE.MeshStandardMaterial({ map: groundTex, roughness: 0.75, metalness: 0.05 });
    groundMesh = new THREE.Mesh(geo, mat);
    groundMesh.rotation.x = -Math.PI / 2;
    groundMesh.position.set(gw(W) / 2, -0.001, 0);
    groundMesh.receiveShadow = true;
    scene.add(groundMesh);

    /* surrounding dark floor */
    const outerGeo = new THREE.PlaneGeometry(gw(W) * 3, 20);
    const outerMat = new THREE.MeshStandardMaterial({ color: 0x1a3a1a, roughness: 0.9 });
    const outer = new THREE.Mesh(outerGeo, outerMat);
    outer.rotation.x = -Math.PI / 2;
    outer.position.set(gw(W) / 2, -0.01, 0);
    outer.receiveShadow = true;
    scene.add(outer);
  }

  function buildStands() {
    /* back wall (curved stadium bowl feel) */
    const colors = [0x28324c, 0x313f5e, 0x3a4d72];
    for (let i = 0; i < 3; i++) {
      const h = 1.8 + i * 1.2;
      const geo = new THREE.BoxGeometry(gw(W) * 1.4, h, 0.6);
      const mat = new THREE.MeshStandardMaterial({ color: colors[i], roughness: 0.9 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(gw(W) / 2, h / 2, -4 - i * 0.8);
      scene.add(mesh);
    }

    /* crowd dots on the back stands */
    const dotColors = [0xffd24d, 0x7fe0ff, 0xff90a4, 0x9dffc4, 0xffffff, 0xc9a8ff, 0xffb066];
    const dotGeo = new THREE.SphereGeometry(0.06, 4, 4);
    for (let i = 0; i < 200; i++) {
      const mat = new THREE.MeshBasicMaterial({ color: dotColors[i % dotColors.length] });
      const dot = new THREE.Mesh(dotGeo, mat);
      dot.position.set(
        (Math.random() - 0.5) * gw(W) * 1.3 + gw(W) / 2,
        0.3 + Math.random() * 4.5,
        -3.8 - Math.random() * 2.5
      );
      scene.add(dot);
    }

    /* side walls */
    const sideGeo = new THREE.BoxGeometry(0.5, 3, 8);
    const sideMat = new THREE.MeshStandardMaterial({ color: 0x1c2438, roughness: 0.8 });
    const leftW = new THREE.Mesh(sideGeo, sideMat);
    leftW.position.set(-gw(W) * 0.15, 1.5, 0);
    scene.add(leftW);
    const rightW = new THREE.Mesh(sideGeo, sideMat);
    rightW.position.set(gw(W) * 1.15, 1.5, 0);
    scene.add(rightW);

    /* LED ad boards along the front */
    const adColors = [0x12e0c0, 0xffd23d, 0xff5c8a, 0x4db4ff, 0xa06bff];
    for (let i = 0; i < 10; i++) {
      const adGeo = new THREE.BoxGeometry(gw(W) / 10 - 0.04, 0.2, 0.08);
      const adMat = new THREE.MeshBasicMaterial({ color: adColors[i % adColors.length] });
      const ad = new THREE.Mesh(adGeo, adMat);
      ad.position.set(gw(W) * 0.05 + i * (gw(W) / 10), 0.1, 3.6);
      scene.add(ad);
    }
  }

  function buildFloodlights() {
    const positions = [gw(W) * 0.2, gw(W) * 0.8];
    positions.forEach(function (x) {
      /* pole */
      const poleGeo = new THREE.CylinderGeometry(0.05, 0.06, 7, 6);
      const poleMat = new THREE.MeshStandardMaterial({ color: 0x4a5a78, metalness: 0.3 });
      const pole = new THREE.Mesh(poleGeo, poleMat);
      pole.position.set(x, 3.5, -3.5);
      scene.add(pole);
      /* lamp head */
      const headGeo = new THREE.BoxGeometry(0.8, 0.15, 0.3);
      const headMat = new THREE.MeshStandardMaterial({ color: 0x39496a });
      const head = new THREE.Mesh(headGeo, headMat);
      head.position.set(x, 7.1, -3.5);
      scene.add(head);
      /* glow */
      const spotLight = new THREE.SpotLight(0xfffbe0, 0.4, 20, Math.PI / 4, 0.5);
      spotLight.position.set(x, 7, -3.4);
      spotLight.target.position.set(gw(W) / 2, 0, 0);
      scene.add(spotLight);
      scene.add(spotLight.target);
    });
  }

  function buildGoal(xWorld, isRight) {
    const group = new THREE.Group();
    const depth = gw(GD);
    const height = gw(GH);
    const postRadius = 0.04;
    const halfWidth = 1.2;   // z-spread of the two posts

    const postMat = new THREE.MeshStandardMaterial({ color: 0xffffff, metalness: 0.55, roughness: 0.25 });

    /* front posts */
    const postGeo = new THREE.CylinderGeometry(postRadius, postRadius, height, 8);
    const p1 = new THREE.Mesh(postGeo, postMat);
    p1.position.set(0, height / 2, halfWidth);
    p1.castShadow = true;
    group.add(p1);

    const p2 = new THREE.Mesh(postGeo, postMat);
    p2.position.set(0, height / 2, -halfWidth);
    p2.castShadow = true;
    group.add(p2);

    /* crossbar */
    const barGeo = new THREE.CylinderGeometry(postRadius, postRadius, halfWidth * 2 + postRadius * 2, 8);
    const bar = new THREE.Mesh(barGeo, postMat);
    bar.rotation.x = Math.PI / 2;
    bar.position.set(0, height, 0);
    bar.castShadow = true;
    group.add(bar);

    /* back posts */
    const dir = isRight ? 1 : -1;
    const bp1 = new THREE.Mesh(postGeo, postMat);
    bp1.position.set(dir * depth, height / 2, halfWidth);
    group.add(bp1);
    const bp2 = new THREE.Mesh(postGeo, postMat);
    bp2.position.set(dir * depth, height / 2, -halfWidth);
    group.add(bp2);

    /* top bar back */
    const topBack = new THREE.Mesh(barGeo, postMat);
    topBack.rotation.x = Math.PI / 2;
    topBack.position.set(dir * depth, height, 0);
    group.add(topBack);

    /* connecting bars top */
    const connGeo = new THREE.CylinderGeometry(0.02, 0.02, depth, 4);
    const conn1 = new THREE.Mesh(connGeo, postMat);
    conn1.rotation.z = Math.PI / 2;
    conn1.position.set(dir * depth / 2, height, halfWidth);
    group.add(conn1);
    const conn2 = new THREE.Mesh(connGeo, postMat);
    conn2.rotation.z = Math.PI / 2;
    conn2.position.set(dir * depth / 2, height, -halfWidth);
    group.add(conn2);

    /* net — wireframe planes for the sides, back, and top */
    const netMat = new THREE.MeshBasicMaterial({
      color: 0xffffff, transparent: true, opacity: 0.18,
      side: THREE.DoubleSide, wireframe: true
    });

    /* back net */
    const backNetGeo = new THREE.PlaneGeometry(halfWidth * 2, height, 8, 6);
    const backNet = new THREE.Mesh(backNetGeo, netMat);
    backNet.position.set(dir * depth, height / 2, 0);
    backNet.rotation.y = Math.PI / 2;
    group.add(backNet);

    /* side nets */
    const sideNetGeo = new THREE.PlaneGeometry(depth, height, 4, 6);
    const sn1 = new THREE.Mesh(sideNetGeo, netMat);
    sn1.position.set(dir * depth / 2, height / 2, halfWidth);
    group.add(sn1);
    const sn2 = new THREE.Mesh(sideNetGeo, netMat);
    sn2.position.set(dir * depth / 2, height / 2, -halfWidth);
    group.add(sn2);

    /* top net */
    const topNetGeo = new THREE.PlaneGeometry(depth, halfWidth * 2, 4, 8);
    const topNet = new THREE.Mesh(topNetGeo, netMat);
    topNet.rotation.x = Math.PI / 2;
    topNet.position.set(dir * depth / 2, height, 0);
    group.add(topNet);

    group.position.set(xWorld, 0, 0);
    scene.add(group);
    goalGroups.push(group);
  }

  function buildBall() {
    const radius = gw(BR);
    ballGroup = new THREE.Group();

    const geo = new THREE.SphereGeometry(radius, 20, 20);
    const mat = new THREE.MeshStandardMaterial({
      map: makeBallTexture(), roughness: 0.4, metalness: 0.05
    });
    ballMesh = new THREE.Mesh(geo, mat);
    ballMesh.castShadow = true;
    ballGroup.add(ballMesh);
    scene.add(ballGroup);

    /* ground shadow */
    const shGeo = new THREE.CircleGeometry(radius * 1.3, 16);
    const shMat = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.25, depthWrite: false });
    ballShadow = new THREE.Mesh(shGeo, shMat);
    ballShadow.rotation.x = -Math.PI / 2;
    ballShadow.position.y = 0.005;
    scene.add(ballShadow);

    /* speed glow */
    ballGlow = new THREE.PointLight(0xff6633, 0, 4);
    scene.add(ballGlow);

    /* trail spheres */
    for (let i = 0; i < 8; i++) {
      const tGeo = new THREE.SphereGeometry(radius * (0.7 - i * 0.06), 8, 8);
      const tMat = new THREE.MeshBasicMaterial({ color: 0xff5533, transparent: true, opacity: 0 });
      const tm = new THREE.Mesh(tGeo, tMat);
      tm.visible = false;
      trailMeshes.push(tm);
      scene.add(tm);
    }
    prevBallPos = [];
  }

  function buildPlayer(teamIdx) {
    const group = new THREE.Group();
    const col = teamColorsThree[teamIdx];
    const colDark = col.clone().multiplyScalar(0.7);

    /* head (big, cartoon) */
    const headGeo = new THREE.SphereGeometry(0.32, 16, 12);
    const headMat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.5 });
    const head = new THREE.Mesh(headGeo, headMat);
    head.position.y = 0.78;
    head.castShadow = true;
    group.add(head);
    group.userData.headMat = headMat;

    /* spiky hair */
    const spikeGeo = new THREE.ConeGeometry(0.08, 0.25, 4);
    const spikeMat = new THREE.MeshStandardMaterial({ color: colDark, roughness: 0.6 });
    const offsets = [
      { x: 0, z: 0, ry: 0 },
      { x: 0.12, z: 0.08, ry: 0.3 },
      { x: -0.12, z: 0.08, ry: -0.3 },
      { x: 0.08, z: -0.1, ry: 0.5 },
      { x: -0.08, z: -0.1, ry: -0.5 }
    ];
    offsets.forEach(function (o) {
      const spike = new THREE.Mesh(spikeGeo, spikeMat);
      spike.position.set(o.x, 1.08, o.z);
      spike.rotation.z = o.ry;
      group.add(spike);
    });
    group.userData.spikeMat = spikeMat;

    /* eyes */
    const eyeGeo = new THREE.SphereGeometry(0.06, 8, 8);
    const eyeMat = new THREE.MeshBasicMaterial({ color: 0x202530 });
    const eye1 = new THREE.Mesh(eyeGeo, eyeMat);
    eye1.position.set(0.12, 0.82, 0.25);
    group.add(eye1);
    const eye2 = new THREE.Mesh(eyeGeo, eyeMat);
    eye2.position.set(-0.08, 0.82, 0.25);
    group.add(eye2);

    /* eye whites */
    const ewGeo = new THREE.SphereGeometry(0.04, 8, 8);
    const ewMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const ew1 = new THREE.Mesh(ewGeo, ewMat);
    ew1.position.set(0.13, 0.84, 0.29);
    group.add(ew1);
    const ew2 = new THREE.Mesh(ewGeo, ewMat);
    ew2.position.set(-0.07, 0.84, 0.29);
    group.add(ew2);

    /* smile */
    const smileCurve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(-0.08, 0.68, 0.30),
      new THREE.Vector3(0.03, 0.62, 0.32),
      new THREE.Vector3(0.14, 0.68, 0.30)
    );
    const smileGeo = new THREE.TubeGeometry(smileCurve, 10, 0.015, 4, false);
    const smileMat = new THREE.MeshBasicMaterial({ color: 0x202530 });
    group.add(new THREE.Mesh(smileGeo, smileMat));

    /* body / jersey */
    const bodyGeo = new THREE.BoxGeometry(0.38, 0.3, 0.28, 1, 1, 1);
    const bodyMat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.6 });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.42;
    body.castShadow = true;
    group.add(body);
    group.userData.bodyMat = bodyMat;

    /* jersey V-stripe */
    const stripeGeo = new THREE.PlaneGeometry(0.12, 0.15);
    const stripeMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.7, side: THREE.DoubleSide });
    const stripe = new THREE.Mesh(stripeGeo, stripeMat);
    stripe.position.set(0.02, 0.44, 0.141);
    group.add(stripe);

    /* shorts */
    const shortGeo = new THREE.BoxGeometry(0.34, 0.14, 0.26);
    const shortMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.7 });
    const shorts = new THREE.Mesh(shortGeo, shortMat);
    shorts.position.y = 0.22;
    group.add(shorts);

    /* legs */
    const legGeo = new THREE.CylinderGeometry(0.04, 0.035, 0.18, 6);
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xffccaa, roughness: 0.5 });
    const leg1 = new THREE.Mesh(legGeo, skinMat);
    leg1.position.set(0.08, 0.06, 0);
    group.add(leg1);
    const leg2 = new THREE.Mesh(legGeo, skinMat);
    leg2.position.set(-0.08, 0.06, 0);
    group.add(leg2);

    /* boots */
    const bootGeo = new THREE.BoxGeometry(0.1, 0.05, 0.14);
    const bootMat = new THREE.MeshStandardMaterial({ color: colDark, roughness: 0.3, metalness: 0.2 });
    const boot1 = new THREE.Mesh(bootGeo, bootMat);
    boot1.position.set(0.08, -0.02, 0.02);
    group.add(boot1);
    const boot2 = new THREE.Mesh(bootGeo, bootMat);
    boot2.position.set(-0.08, -0.02, 0.02);
    group.add(boot2);
    group.userData.bootMat = bootMat;

    /* arms */
    const armGeo = new THREE.CylinderGeometry(0.03, 0.025, 0.22, 6);
    const arm1 = new THREE.Mesh(armGeo, skinMat);
    arm1.position.set(0.24, 0.40, 0);
    arm1.rotation.z = -0.6;
    group.add(arm1);
    const arm2 = new THREE.Mesh(armGeo, skinMat);
    arm2.position.set(-0.24, 0.38, 0);
    arm2.rotation.z = 0.8;
    group.add(arm2);

    /* ground shadow (blob) */
    const shGeo = new THREE.CircleGeometry(0.35, 12);
    const shMat = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.2, depthWrite: false });
    const shadow = new THREE.Mesh(shGeo, shMat);
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = 0.005;
    group.add(shadow);
    group.userData.shadow = shadow;

    scene.add(group);
    return group;
  }

  function buildLighting() {
    /* ambient */
    scene.add(new THREE.AmbientLight(0xb0c4de, 0.55));

    /* main directional light (sun / floodlight) */
    const dir = new THREE.DirectionalLight(0xfff8e8, 0.95);
    dir.position.set(gw(W) * 0.5, 12, 6);
    dir.target.position.set(gw(W) * 0.5, 0, 0);
    dir.castShadow = true;
    dir.shadow.camera.left   = -12;
    dir.shadow.camera.right  =  12;
    dir.shadow.camera.top    =  8;
    dir.shadow.camera.bottom = -8;
    dir.shadow.mapSize.width  = 1024;
    dir.shadow.mapSize.height = 1024;
    dir.shadow.bias = -0.001;
    scene.add(dir);
    scene.add(dir.target);

    /* hemisphere for nice sky-ground fill */
    scene.add(new THREE.HemisphereLight(0x87CEEB, 0x2d8c3e, 0.25));
  }

  /* ───────── update team colors on existing meshes ───────── */
  function applyTeamColorToPlayer(group, teamIdx) {
    const c = teamColorsThree[teamIdx];
    const dark = c.clone().multiplyScalar(0.7);
    if (group.userData.headMat)  group.userData.headMat.color.copy(c);
    if (group.userData.spikeMat) group.userData.spikeMat.color.copy(dark);
    if (group.userData.bodyMat)  group.userData.bodyMat.color.copy(c);
    if (group.userData.bootMat)  group.userData.bootMat.color.copy(dark);
  }

  /* ───────── public API ───────── */
  window.Game3D = {

    init: function (container, config) {
      if (ready) return;
      containerEl = container;

      /* apply config overrides */
      if (config) {
        W  = config.width         || W;
        H  = config.height        || H;
        GY = config.ground_y      || GY;
        GD = config.goal_depth    || GD;
        GH = config.goal_height   || GH;
        BR = config.ball_radius   || BR;
        PW = config.player_width  || PW;
        PH = config.player_height || PH;
      }

      /* scene */
      scene = new THREE.Scene();
      scene.background = new THREE.Color(0x72b9e8);
      scene.fog = new THREE.FogExp2(0x72b9e8, 0.018);

      /* camera — angled overhead */
      const aspect = containerEl.clientWidth / (containerEl.clientHeight || 1);
      camera = new THREE.PerspectiveCamera(38, aspect, 0.1, 120);
      camera.position.set(gw(W) / 2, 7.5, 11);
      camera.lookAt(gw(W) / 2, 0.5, 0);

      /* renderer */
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      renderer.setSize(containerEl.clientWidth, containerEl.clientHeight);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.1;
      containerEl.appendChild(renderer.domElement);

      /* build scene */
      buildGround();
      buildStands();
      buildFloodlights();
      buildGoal(gw(GD), false);         // left goal
      buildGoal(gw(W) - gw(GD), true);  // right goal
      buildBall();
      buildLighting();

      /* build two players */
      playerGroups = [ buildPlayer(0), buildPlayer(1) ];

      window.addEventListener('resize', Game3D.resize);

      ready = true;

      /* first render so the idle frame is visible */
      renderer.render(scene, camera);
    },

    /* ── called ~60 fps by playFrames / drawFrame ── */
    updateFrame: function (frame) {
      if (!ready || !frame) return;

      /* players */
      if (frame.players) {
        frame.players.forEach(function (p, idx) {
          if (!playerGroups[idx]) return;
          var grp = playerGroups[idx];
          var x3 = gx(p.x + PW / 2);               // center
          var y3 = Math.max(0, (GY - p.y - PH) * S);
          grp.position.set(x3, y3, 0);

          /* face direction */
          grp.rotation.y = (p.face >= 0) ? 0 : Math.PI;

          /* shadow scales with height */
          if (grp.userData.shadow) {
            var t = Math.min(y3 * 2, 1);
            var sc = 1 - t * 0.5;
            grp.userData.shadow.scale.set(sc, sc, 1);
            grp.userData.shadow.material.opacity = 0.2 * (1 - t * 0.6);
            grp.userData.shadow.position.y = -y3 + 0.005;
          }
        });
      }

      /* ball */
      if (frame.ball && ballGroup) {
        var bx = gx(frame.ball.x);
        var byRaw = (GY - frame.ball.y) * S;
        var by = Math.max(gw(BR), byRaw);

        ballGroup.position.set(bx, by, 0);

        /* rotation from velocity */
        var vx = frame.ball.vx || 0;
        var vy = frame.ball.vy || 0;
        ballMesh.rotation.z -= vx * S * 0.06;
        ballMesh.rotation.x += vy * S * 0.04;

        /* shadow */
        ballShadow.position.set(bx, 0.005, 0);
        var hNorm = Math.min(1, Math.max(0, (by - gw(BR)) / 3));
        var ss = 1 - hNorm * 0.45;
        ballShadow.scale.set(ss, ss, 1);
        ballShadow.material.opacity = 0.25 * (1 - hNorm * 0.55);

        /* speed effects */
        var speed = Math.sqrt(vx * vx + vy * vy);
        var speedFx = Math.max(0, Math.min(1, (speed - 250) / 1050));

        /* glow */
        if (speed > 400) {
          ballGlow.position.set(bx, by, 0);
          ballGlow.intensity = Math.min(2.5, (speed - 400) * 0.004);
          ballGlow.color.setHex(speedFx > 0.6 ? 0xff3322 : 0xff6633);
        } else {
          ballGlow.intensity *= 0.85;
        }

        /* trail */
        prevBallPos.unshift({ x: bx, y: by });
        if (prevBallPos.length > 8) prevBallPos.length = 8;

        for (var i = 0; i < trailMeshes.length; i++) {
          var tm = trailMeshes[i];
          if (speedFx > 0.05 && i < prevBallPos.length) {
            tm.visible = true;
            tm.position.set(prevBallPos[i].x, prevBallPos[i].y, 0);
            tm.material.opacity = speedFx * (1 - i / trailMeshes.length) * 0.35;
          } else {
            tm.material.opacity *= 0.7;
            if (tm.material.opacity < 0.01) tm.visible = false;
          }
        }
      }

      /* render */
      renderer.render(scene, camera);
    },

    setTeamColors: function (c1, c2) {
      teamHex = [c1, c2];
      teamColorsThree = [hexToThree(c1), hexToThree(c2)];
      if (playerGroups[0]) applyTeamColorToPlayer(playerGroups[0], 0);
      if (playerGroups[1]) applyTeamColorToPlayer(playerGroups[1], 1);
    },

    resize: function () {
      if (!ready || !containerEl || !camera || !renderer) return;
      var w = containerEl.clientWidth;
      var h = containerEl.clientHeight;
      if (w < 1 || h < 1) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    },

    dispose: function () {
      if (!ready) return;
      window.removeEventListener('resize', Game3D.resize);
      if (renderer && renderer.domElement && containerEl.contains(renderer.domElement)) {
        containerEl.removeChild(renderer.domElement);
      }
      if (renderer) renderer.dispose();
      ready = false;
      scene = camera = renderer = null;
      playerGroups = [];
      trailMeshes = [];
      prevBallPos = [];
    },

    isReady: function () { return ready; }
  };
})();
