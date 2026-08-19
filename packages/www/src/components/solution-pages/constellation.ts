/**
 * Build-time layout solver for the solution constellation.
 *
 * Geometry is deterministic polar math from each page's `role` in
 * `SOLUTION_PAGES`: three verb anchors (Copy / Test / Recover) sit on an
 * ellipse around an empty centre, each arm's pages hang off its anchor as a
 * CHAIN along the arc (adjacent short hops, a few long reaches - not a spoke
 * fan, which would read as a sunburst), and the five `property` pages sit as
 * an inner ring around the centre. The centre stays empty on purpose: it is
 * the permanent landing zone for the popover, which is why this design never
 * needs CSS anchor positioning.
 *
 * Everything here runs in Astro frontmatter, so the solver ships zero bytes.
 * The SVG edges and the HTML node positions are derived from the SAME arrays,
 * so they cannot drift.
 *
 * RTL: `x <- W - x` is applied ONCE here, at build time, to nodes and edges
 * together. Node positions are consumed as physical left/top percentages with
 * PRE-MIRRORED coordinates - do not "improve" that to inset-inline-start, or
 * the mirror applies twice and Arabic silently flips back to LTR.
 */
import { SOLUTION_PAGES, type SolutionRole } from '../../config/solution-pages';

export type ConstellationPreset = 'full' | 'compact';

interface CxPlaced {
  kind: 'centre' | 'anchor' | 'solution';
  /** For anchors: the arm role. For solutions: the page's role. */
  role: SolutionRole | null;
  /** Solution slug (solution nodes only). */
  slug: string | null;
  /** ViewBox coordinates. */
  x: number;
  y: number;
  /** Percent coordinates for the HTML layer, 2dp. */
  px: number;
  py: number;
  /** Bottom-half nodes render their label above the dot so it stays in frame. */
  flip: boolean;
}

interface CxEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Line length, for the build-time stroke-dash draw-in. */
  len: number;
}

export interface CxLayout {
  width: number;
  height: number;
  centre: CxPlaced;
  anchors: CxPlaced[];
  /** Solution nodes grouped by arm role, in chain order. */
  arms: Record<SolutionRole, CxPlaced[]>;
  edges: CxEdge[];
}

const DEG = Math.PI / 180;

interface Geometry {
  width: number;
  height: number;
  rx: number;
  ry: number;
  /** Arc step between adjacent arm nodes, degrees. */
  step: Record<'copy' | 'test' | 'recover', number>;
  /** Radial reach of arm nodes: base + alternating stagger (the "scatter"). */
  reach: Record<'copy' | 'test' | 'recover', number>;
  stagger: Record<'copy' | 'test' | 'recover', number>;
  /** Property ring reach as a fraction of rx / ry. */
  ringX: number;
  ringY: number;
  /** Centre exclusion ellipse half-axes (the headline's footprint). */
  holeA: number;
  holeB: number;
}

const GEOMETRY: Record<ConstellationPreset, Geometry> = {
  full: {
    width: 1440,
    height: 800,
    rx: 470,
    ry: 250,
    step: { copy: 21, test: 16, recover: 19 },
    reach: { copy: 1.34, test: 1.34, recover: 1.28 },
    stagger: { copy: 0.12, test: 0.12, recover: 0.1 },
    ringX: 0.85,
    ringY: 0.9,
    /* Half-axes of the ellipse the centre headline occupies; centre-radiating
       edges start OUTSIDE it so no hairline crosses the text. */
    holeA: 205,
    holeB: 112,
  },
  compact: {
    width: 1440,
    height: 580,
    rx: 470,
    ry: 172,
    step: { copy: 20, test: 21, recover: 20 },
    reach: { copy: 1.35, test: 1.32, recover: 1.38 },
    stagger: { copy: 0.1, test: 0.13, recover: 0.09 },
    ringX: 0.85,
    ringY: 0.95,
    holeA: 140,
    holeB: 55,
  },
};

/** Anchor bearings, degrees. Clockwise reading order in LTR: copy, test, recover. */
const ANCHOR_THETA: Record<'copy' | 'test' | 'recover', number> = {
  copy: 150,
  test: 30,
  recover: 270,
};

/** Property ring bearings: one at 12 o'clock, four in the diagonal gaps the
 * three anchors leave free (anchors sit at 150/30/270). */
const RING_PSI = [90, -22, -60, -120, -158] as const;

/** Keep node CENTRES far enough inside the box that a ~150px label survives. */
const MARGIN_X = 88;
const MARGIN_Y = 46;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function place(
  g: Geometry,
  kind: CxPlaced['kind'],
  role: SolutionRole | null,
  slug: string | null,
  x: number,
  y: number,
  rtl: boolean
): CxPlaced {
  const cx = clamp(x, MARGIN_X, g.width - MARGIN_X);
  const cy = clamp(y, MARGIN_Y, g.height - MARGIN_Y);
  const mx = rtl ? g.width - cx : cx;
  return {
    kind,
    role,
    slug,
    x: mx,
    y: cy,
    px: Number(((mx / g.width) * 100).toFixed(2)),
    py: Number(((cy / g.height) * 100).toFixed(2)),
    flip: cy > g.height * 0.55,
  };
}

/** Object-key order of SOLUTION_PAGES is the canonical arm order. */
export function slugsForRole(role: SolutionRole): string[] {
  return Object.keys(SOLUTION_PAGES).filter((slug) => SOLUTION_PAGES[slug].role === role);
}

/**
 * Solve the layout.
 *
 * @param preset  'full' (the /solutions page, all 21) or 'compact' (a filtered
 *                node set in a shorter frame - hero slot, explore/related slots).
 * @param include solution slugs to render. Empty array = anchors + centre only
 *                (the 4-object hero density). Order within an arm always follows
 *                config key order regardless of the caller's order.
 * @param rtl     mirror the whole coordinate field once.
 */
export function buildConstellation(
  preset: ConstellationPreset,
  include: readonly string[],
  rtl: boolean
): CxLayout {
  const g = GEOMETRY[preset];
  const cx = g.width / 2;
  const cy = g.height / 2;
  const wanted = new Set(include);

  const centre = place(g, 'centre', null, null, cx, cy, rtl);
  const anchors: CxPlaced[] = [];
  const arms: Record<SolutionRole, CxPlaced[]> = { copy: [], test: [], recover: [], property: [] };
  const edges: CxEdge[] = [];

  const edge = (a: CxPlaced, b: CxPlaced) => {
    let sx = a.x;
    let sy = a.y;
    // Edges radiating from the centre start at the rim of the headline's
    // exclusion ellipse, so no hairline runs under the text.
    if (a.kind === 'centre') {
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      // The point where the centre->b ray leaves the exclusion ellipse is
      // exactly (dx, dy) / norm from the centre. Only trim when b is outside
      // the ellipse (norm > 1), otherwise the edge would invert.
      const norm = Math.hypot(dx / g.holeA, dy / g.holeB);
      if (norm > 1) {
        sx = a.x + dx / norm;
        sy = a.y + dy / norm;
      }
    }
    edges.push({
      x1: Math.round(sx),
      y1: Math.round(sy),
      x2: Math.round(b.x),
      y2: Math.round(b.y),
      len: Math.round(Math.hypot(sx - b.x, sy - b.y)),
    });
  };

  for (const role of ['copy', 'test', 'recover'] as const) {
    const theta = ANCHOR_THETA[role];
    const anchor = place(
      g,
      'anchor',
      role,
      null,
      cx + g.rx * Math.cos(theta * DEG),
      cy - g.ry * Math.sin(theta * DEG),
      rtl
    );
    anchors.push(anchor);
    edge(centre, anchor);

    const armSlugs = slugsForRole(role).filter((s) => wanted.has(s));
    const n = armSlugs.length;
    let prev = anchor;
    armSlugs.forEach((slug, i) => {
      const phi = theta + (i - (n - 1) / 2) * g.step[role];
      const s = g.reach[role] + (i % 2) * g.stagger[role];
      const node = place(
        g,
        'solution',
        role,
        slug,
        cx + g.rx * s * Math.cos(phi * DEG),
        cy - g.ry * s * Math.sin(phi * DEG),
        rtl
      );
      arms[role].push(node);
      edge(prev, node);
      prev = node;
    });
  }

  slugsForRole('property')
    .filter((s) => wanted.has(s))
    .forEach((slug, i) => {
      const psi = RING_PSI[i % RING_PSI.length];
      const node = place(
        g,
        'solution',
        'property',
        slug,
        cx + g.rx * g.ringX * Math.cos(psi * DEG),
        cy - g.ry * g.ringY * Math.sin(psi * DEG),
        rtl
      );
      arms.property.push(node);
      edge(centre, node);
    });

  return { width: g.width, height: g.height, centre, anchors, arms, edges };
}

/**
 * Where each page's short label and blurb lived before the harvest: the page's
 * OWN entry in its `explore.solutions[]` array (deleted by the consolidated
 * i18n pass; see the w9 harvest artifact). Until `pages.solutionPages.<key>.label`
 * and `.blurb` land in the catalogs, the component falls back to reading these
 * paths so every locale keeps its already-naturalized short titles. After the
 * harvest lands, the primary keys win and these paths no longer resolve, which
 * is harmless: the fallback is only consulted when the primary key is absent.
 *
 * `data-sovereignty` is the one slug NO explore array references (0 of 180),
 * so its label/blurb are net-new English pending the operator's wording.
 */
export const LEGACY_EXPLORE_SOURCE: Record<string, { ck: string; idx: number }> = {
  'environment-cloning': { ck: 'environmentCloning', idx: 0 },
  'infrastructure-costs': { ck: 'infrastructureCosts', idx: 2 },
  'production-parity': { ck: 'productionParity', idx: 1 },
  integrations: { ck: 'integrations', idx: 3 },
  'immutable-backups': { ck: 'immutableBackups', idx: 0 },
  'migration-safety': { ck: 'migrationSafety', idx: 2 },
  'instant-recovery': { ck: 'instantRecovery', idx: 2 },
  'safe-os-testing': { ck: 'safeOsTesting', idx: 2 },
  'retention-compliance': { ck: 'retentionCompliance', idx: 1 },
  'cloud-outage-protection': { ck: 'cloudOutageProtection', idx: 0 },
  'failover-testing': { ck: 'failoverTesting', idx: 2 },
  'backup-verification': { ck: 'backupVerification', idx: 0 },
  'vulnerability-management': { ck: 'vulnerabilityManagement', idx: 2 },
  'ai-pentesting': { ck: 'aiPentesting', idx: 0 },
  encryption: { ck: 'encryption', idx: 0 },
  'continuous-security-testing': { ck: 'continuousSecurityTesting', idx: 1 },
  'audit-trail': { ck: 'auditTrail', idx: 1 },
  'rapid-recovery': { ck: 'rapidRecovery', idx: 1 },
  'kubernetes-cluster-mobility': { ck: 'kubernetesClusterMobility', idx: 0 },
  'vendor-lock-in': { ck: 'vendorLockIn', idx: 1 },
};

/** English-only last resort, used when neither the new key nor the legacy path resolves. */
export const EN_FALLBACK: Record<string, { label: string; blurb: string }> = {
  'data-sovereignty': {
    label: 'Data Sovereignty',
    blurb: 'Your servers, your keys, your jurisdiction.',
  },
};
