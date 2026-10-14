// The hero's one 3D piece: a grid of tiles, each one attempt of the same test case. Scrolling
// through the hero flips a share of them from pass to fail, as a regression would appear.
// Loaded only by hero-visual.tsx, with a dynamic import, after it has decided the device can
// take it. Unlit basic materials: every pixel is a flat token colour, with no light, fog or
// post-processing. Nothing here evaluates strings, so the strict CSP holds.
import {
  BoxGeometry,
  BufferGeometry,
  Color,
  EdgesGeometry,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  LineBasicMaterial,
  LineSegments,
  MeshBasicMaterial,
  Object3D,
  PerspectiveCamera,
  PlaneGeometry,
  Scene,
  WebGLRenderer,
} from "three";

const COLS = 20;
const ROWS = 15; // 4:3, the box's own ratio
const TILE = 0.4; // of the 1-unit pitch: mostly gaps, so the outlined headline over it still reads
/** The share of attempts that end up failing. */
const FAIL_SHARE = 0.3;
/** Each flip takes this much of the hero's scroll progress. */
const FLIP = 0.15;
const MAX_TILT = (3 * Math.PI) / 180; // mouse parallax, at most 3 degrees
const BASE_TILT = { x: -0.38, y: 0.26 };

// A fixed hash, not Math.random: the same tiles fail in the same order on every visit.
const hash = (i: number) => {
  const x = Math.sin(i * 12.9898) * 43758.5453;
  return x - Math.floor(x);
};

/** DESIGN.md's fail mark: a square with a knocked-out cross, as four triangles. */
function failMark(size: number) {
  const h = size / 2;
  const d = h * 0.24; // the cross's half-width, measured along the axis
  const top = [-(h - d), h, 0, 0, d, 0, h - d, h, 0];
  const out: number[] = [];
  for (let q = 0; q < 4; q++) {
    const [c, s] = [Math.cos((q * Math.PI) / 2), Math.sin((q * Math.PI) / 2)];
    for (let v = 0; v < 9; v += 3) out.push(top[v] * c - top[v + 1] * s, top[v] * s + top[v + 1] * c, 0);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(out, 3));
  return geometry;
}

const token = (name: string) => new Color(getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim());

type Options = {
  /** A canvas that already holds the WebGL2 context the probe made, reused rather than made twice. */
  canvas: HTMLCanvasElement;
  context: WebGL2RenderingContext;
  /** Where the canvas goes; it fills it. */
  host: HTMLElement;
  /** The element whose scroll drives the flips and whose pointer drives the parallax. */
  track: HTMLElement;
};

/**
 * Renders the grid into `host` and returns the teardown. Frames run only while `host` is on
 * screen and the tab is visible, and draw only when something moved.
 */
export function mountScene({ canvas, context, host, track }: Options) {
  const renderer = new WebGLRenderer({ canvas, context });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(token("surface-1"));

  const scene = new Scene();
  // Narrow and far: little perspective distortion, and the frame sits inside the box with a margin.
  const camera = new PerspectiveCamera(24, 4 / 3, 1, 100);
  camera.position.set(0, 0, 50);
  const grid = new Group();
  scene.add(grid);

  const tile = new PlaneGeometry(TILE, TILE);
  const mark = failMark(TILE);
  const passMaterial = new MeshBasicMaterial({ color: token("accent") });
  const failMaterial = new MeshBasicMaterial({ color: token("fail") });
  const count = COLS * ROWS;
  const pass = new InstancedMesh(tile, passMaterial, count);
  const fail = new InstancedMesh(mark, failMaterial, count);
  grid.add(pass, fail);

  const box = new BoxGeometry(COLS + 1, ROWS + 1, 3);
  const edges = new EdgesGeometry(box);
  const frameMaterial = new LineBasicMaterial({ color: token("hairline-strong") });
  grid.add(new LineSegments(edges, frameMaterial));

  // When each failing attempt starts to flip, as a share of the hero's scroll; -1 never flips.
  const flipAt = Array.from({ length: count }, (_, i) => (hash(i) < FAIL_SHARE ? hash(i + count) * (1 - FLIP) : -1));

  const dummy = new Object3D();
  function place(mesh: InstancedMesh, i: number, angle: number, shown: boolean) {
    dummy.position.set((i % COLS) - (COLS - 1) / 2, Math.floor(i / COLS) - (ROWS - 1) / 2, 0);
    dummy.rotation.set(angle, 0, 0);
    dummy.scale.setScalar(shown ? 1 : 0);
    dummy.updateMatrix();
    mesh.setMatrixAt(i, dummy.matrix);
  }
  function flip(progress: number) {
    for (let i = 0; i < count; i++) {
      const start = flipAt[i];
      const angle = start < 0 ? 0 : Math.PI * Math.min(Math.max((progress - start) / FLIP, 0), 1);
      // A split-flap: the pass face turns away, then the fail face turns in from edge-on.
      place(pass, i, angle, angle < Math.PI / 2);
      place(fail, i, angle - Math.PI, angle >= Math.PI / 2);
    }
    pass.instanceMatrix.needsUpdate = true;
    fail.instanceMatrix.needsUpdate = true;
  }

  const tilt = { x: 0, y: 0, toX: 0, toY: 0 };
  let progress = -1;
  let dirty = true;

  function resize() {
    const { width, height } = host.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    dirty = true;
  }

  function draw() {
    const rect = track.getBoundingClientRect();
    const next = Math.min(Math.max(-rect.top / (rect.height * 0.75), 0), 1);
    if (next !== progress) {
      progress = next;
      flip(progress);
      dirty = true;
    }
    tilt.x += (tilt.toX - tilt.x) * 0.12;
    tilt.y += (tilt.toY - tilt.y) * 0.12;
    if (Math.abs(tilt.toX - tilt.x) + Math.abs(tilt.toY - tilt.y) > 1e-4) dirty = true;
    if (!dirty) return;
    grid.rotation.set(BASE_TILT.x + tilt.x, BASE_TILT.y + tilt.y, 0);
    renderer.render(scene, camera);
    dirty = false;
  }

  let raf = 0;
  let onScreen = false;
  const frame = () => {
    raf = 0;
    draw();
    run();
  };
  const run = () => {
    if (!raf && onScreen && !document.hidden) raf = requestAnimationFrame(frame);
  };

  const onPointer = (e: PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    const rect = track.getBoundingClientRect();
    tilt.toY = ((e.clientX - rect.left) / rect.width - 0.5) * 2 * MAX_TILT;
    tilt.toX = ((e.clientY - rect.top) / rect.height - 0.5) * 2 * MAX_TILT;
  };
  const onLeave = () => {
    tilt.toX = 0;
    tilt.toY = 0;
  };
  const visibility = new IntersectionObserver(([entry]) => {
    onScreen = entry.isIntersecting;
    if (!onScreen) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
    run();
  });
  const sizes = new ResizeObserver(resize);

  canvas.className = "absolute inset-0 block size-full";
  host.append(canvas);
  resize();
  draw(); // the first frame now, so the canvas never shows empty over the static figure
  visibility.observe(host);
  sizes.observe(host);
  track.addEventListener("pointermove", onPointer);
  track.addEventListener("pointerleave", onLeave);
  document.addEventListener("visibilitychange", run);

  return () => {
    cancelAnimationFrame(raf);
    visibility.disconnect();
    sizes.disconnect();
    track.removeEventListener("pointermove", onPointer);
    track.removeEventListener("pointerleave", onLeave);
    document.removeEventListener("visibilitychange", run);
    pass.dispose();
    fail.dispose();
    for (const disposable of [tile, mark, box, edges, passMaterial, failMaterial, frameMaterial]) disposable.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    canvas.remove();
  };
}
