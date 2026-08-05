/** Deterministic circle-pile physics for Heap Ore — DOM-free, no rotation. */

export const HEAP_SIM_DT_MS = 8;
export const HEAP_GRAVITY = 0.0012;
export const HEAP_RESTITUTION = 0.2;
export const HEAP_FRICTION = 0.4;
export const HEAP_LINEAR_DAMPING = 0.999;
export const HEAP_REST_SPEED = 0.002;
export const HEAP_CONTACT_ITERATIONS = 4;
export const HEAP_SETTLE_MAX_STEPS = 2000;
export const HEAP_SPAWN_JITTER_PX = 10;
export const HEAP_SPAWN_VX_MIN = -0.06;
export const HEAP_SPAWN_VX_MAX = -0.02;

export interface HeapBin {
  readonly floorY: number;
  readonly westX: number;
  readonly eastX: number;
  readonly ceilingY: number;
}

export interface HeapBody {
  readonly id: number;
  readonly radius: number;
  readonly x: number;
  readonly y: number;
  readonly vx: number;
  readonly vy: number;
}

export interface HeapPileSimOptions {
  readonly bin: HeapBin;
  readonly seed: number;
  readonly startMs?: number;
}

export interface HeapPileSim {
  readonly bodies: readonly HeapBody[];
  readonly nowMs: number;
  spawn(radius: number, x: number, y: number, vx: number, vy: number): number;
  spawnJittered(radius: number, x: number, y: number): number;
  removeGrabbed(grabX: number, grabY: number): number | null;
  stepTo(nowMs: number): void;
  settle(): void;
  clear(): void;
}

interface MutableBody {
  id: number;
  radius: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function freezeBody(body: MutableBody): HeapBody {
  return {
    id: body.id,
    radius: body.radius,
    x: body.x,
    y: body.y,
    vx: body.vx,
    vy: body.vy,
  };
}

function resolveBodyBody(a: MutableBody, b: MutableBody): void {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  let dist = Math.hypot(dx, dy);
  const minDist = a.radius + b.radius;
  if (dist >= minDist) {
    return;
  }

  let nx: number;
  let ny: number;
  if (dist === 0) {
    nx = 1;
    ny = 0;
    dist = 0;
  } else {
    nx = dx / dist;
    ny = dy / dist;
  }

  const overlap = minDist - dist;
  const half = overlap * 0.5;
  a.x -= nx * half;
  a.y -= ny * half;
  b.x += nx * half;
  b.y += ny * half;

  const rvx = b.vx - a.vx;
  const rvy = b.vy - a.vy;
  const vn = rvx * nx + rvy * ny;
  if (vn >= 0) {
    return;
  }

  const vtx = rvx - vn * nx;
  const vty = rvy - vn * ny;
  const newVn = -HEAP_RESTITUTION * vn;
  const newVtx = vtx * HEAP_FRICTION;
  const newVty = vty * HEAP_FRICTION;

  const dvx = newVn * nx + newVtx - rvx;
  const dvy = newVn * ny + newVty - rvy;
  a.vx -= dvx * 0.5;
  a.vy -= dvy * 0.5;
  b.vx += dvx * 0.5;
  b.vy += dvy * 0.5;
}

function resolveBodyWall(body: MutableBody, bin: HeapBin): void {
  const minX = bin.westX + body.radius;
  const maxX = bin.eastX - body.radius;
  const minY = bin.floorY + body.radius;
  const maxY = bin.ceilingY - body.radius;

  if (body.x < minX) {
    body.x = minX;
    body.vx = -body.vx * HEAP_RESTITUTION;
    body.vy *= HEAP_FRICTION;
  } else if (body.x > maxX) {
    body.x = maxX;
    body.vx = -body.vx * HEAP_RESTITUTION;
    body.vy *= HEAP_FRICTION;
  }

  if (body.y < minY) {
    body.y = minY;
    body.vy = -body.vy * HEAP_RESTITUTION;
    body.vx *= HEAP_FRICTION;
  } else if (body.y > maxY) {
    body.y = maxY;
    body.vy = -body.vy * HEAP_RESTITUTION;
    body.vx *= HEAP_FRICTION;
  }
}

function bodyAtRest(body: MutableBody): boolean {
  return (
    Math.abs(body.vx) < HEAP_REST_SPEED &&
    Math.abs(body.vy) < HEAP_REST_SPEED
  );
}

export function createHeapPileSim(options: HeapPileSimOptions): HeapPileSim {
  const bin = options.bin;
  const bodies: MutableBody[] = [];
  let nowMs = options.startMs ?? 0;
  let accumulatorMs = 0;
  let nextId = 1;
  const rng = mulberry32(options.seed);

  function sortedBodies(): readonly HeapBody[] {
    return [...bodies]
      .sort((a, b) => a.id - b.id)
      .map(freezeBody);
  }

  function integrateStep(): void {
    const ordered = [...bodies].sort((a, b) => a.id - b.id);

    for (const body of ordered) {
      body.vy -= HEAP_GRAVITY * HEAP_SIM_DT_MS;
      body.vx *= HEAP_LINEAR_DAMPING;
      body.vy *= HEAP_LINEAR_DAMPING;
      body.x += body.vx * HEAP_SIM_DT_MS;
      body.y += body.vy * HEAP_SIM_DT_MS;
    }

    for (let pass = 0; pass < HEAP_CONTACT_ITERATIONS; pass++) {
      for (let i = 0; i < ordered.length; i++) {
        for (let j = i + 1; j < ordered.length; j++) {
          resolveBodyBody(ordered[i]!, ordered[j]!);
        }
      }
      for (const body of ordered) {
        resolveBodyWall(body, bin);
      }
    }
  }

  function spawnInternal(
    radius: number,
    x: number,
    y: number,
    vx: number,
    vy: number,
  ): number {
    const id = nextId++;
    const body: MutableBody = { id, radius, x, y, vx, vy };
    bodies.push(body);

    const ordered = [...bodies].sort((a, b) => a.id - b.id);
    for (let pass = 0; pass < HEAP_CONTACT_ITERATIONS; pass++) {
      for (let i = 0; i < ordered.length; i++) {
        for (let j = i + 1; j < ordered.length; j++) {
          resolveBodyBody(ordered[i]!, ordered[j]!);
        }
      }
      for (const b of ordered) {
        resolveBodyWall(b, bin);
      }
    }

    return id;
  }

  const api: HeapPileSim = {
    get bodies() {
      return sortedBodies();
    },
    get nowMs() {
      return nowMs;
    },
    spawn(radius, x, y, vx, vy) {
      return spawnInternal(radius, x, y, vx, vy);
    },
    spawnJittered(radius, x, y) {
      const jitter = (rng() * 2 - 1) * HEAP_SPAWN_JITTER_PX;
      const vx =
        HEAP_SPAWN_VX_MIN +
        rng() * (HEAP_SPAWN_VX_MAX - HEAP_SPAWN_VX_MIN);
      return spawnInternal(radius, x + jitter, y, vx, 0);
    },
    removeGrabbed(grabX, grabY) {
      if (bodies.length === 0) {
        return null;
      }

      let best = bodies[0]!;
      let bestDistSq =
        (best.x - grabX) * (best.x - grabX) +
        (best.y - grabY) * (best.y - grabY);
      for (const body of bodies) {
        const distSq =
          (body.x - grabX) * (body.x - grabX) +
          (body.y - grabY) * (body.y - grabY);
        if (distSq < bestDistSq || (distSq === bestDistSq && body.id < best.id)) {
          best = body;
          bestDistSq = distSq;
        }
      }

      const removedId = best.id;
      const index = bodies.findIndex((b) => b.id === removedId);
      bodies.splice(index, 1);
      return removedId;
    },
    stepTo(targetMs) {
      if (targetMs < nowMs) {
        throw new Error(
          `stepTo: nowMs cannot decrease (${nowMs} -> ${targetMs})`,
        );
      }
      if (targetMs === nowMs) {
        return;
      }

      const deltaMs = targetMs - nowMs;
      accumulatorMs += deltaMs;
      while (accumulatorMs >= HEAP_SIM_DT_MS) {
        integrateStep();
        accumulatorMs -= HEAP_SIM_DT_MS;
      }
      nowMs = targetMs;
    },
    settle() {
      for (let step = 0; step < HEAP_SETTLE_MAX_STEPS; step++) {
        if (bodies.every(bodyAtRest)) {
          return;
        }
        integrateStep();
      }
    },
    clear() {
      bodies.length = 0;
    },
  };

  return api;
}
