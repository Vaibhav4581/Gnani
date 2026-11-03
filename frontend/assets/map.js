// Schematic maps of Kochi (dashboard, volunteer screen): places by their synthetic lat/lng,
// projected flat. No tiles and no library. Hand-drawn backwaters and the sea edge give the eye
// something to hold on to; they are approximate on purpose (see DESIGN.md).
//
//   import { drawMap } from "/assets/map.js";
//   drawMap(svg, places, { duty, routes });                        // the whole city (dashboard)
//   drawMap(svg, places, { focus: { lat, lng, km: 4 }, you: 1 });  // one volunteer's area
//
// `places` is GET /map (or the dashboard board's `map`): kitchens, volunteers, ngos, areas.

const SVGNS = "http://www.w3.org/2000/svg";

// Water as [lat, lng] lines, drawn by hand: the coast, the backwaters west of Edappally and
// Vyttila, and the river past Kakkanad and Thrippunithura.
export const WATER = {
  coast: [[10.12, 76.256], [10.06, 76.260], [10.0, 76.266], [9.94, 76.272], [9.88, 76.278]],
  channels: [
    [[10.08, 76.287], [10.05, 76.289], [10.02, 76.291], [9.995, 76.294], [9.97, 76.298],
     [9.945, 76.302], [9.91, 76.306]],
    [[10.045, 76.378], [10.02, 76.369], [9.995, 76.356], [9.975, 76.344], [9.957, 76.336],
     [9.935, 76.331], [9.90, 76.329]],
  ],
};
const WEST_EDGE = 76.284;  // the whole-city map reaches this far west, so the backwaters show

export function svgEl(tag, attrs = {}, text) {
  const node = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}

// Straight-line distance in km (good enough across a city).
export function km(a, b) {
  const dy = (a.lat - b.lat) * 110.57;
  const dx = (a.lng - b.lng) * 111.32 * Math.cos((a.lat * Math.PI) / 180);
  return Math.hypot(dx, dy);
}

// lat/lng -> SVG x/y: equirectangular, north up, `width` wide and as tall as the points need
// (at most 1.6 times as tall as wide).
export function projector(points, { width = 360, pad = 40 } = {}) {
  const lat0 = points.reduce((s, p) => s + p.lat, 0) / points.length;
  const k = Math.cos((lat0 * Math.PI) / 180);
  const xs = points.map((p) => p.lng * k);
  const ys = points.map((p) => -p.lat);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const scale = (width - 2 * pad) / (maxX - minX || 1);
  const height = Math.round(Math.min((maxY - minY) * scale, 1.6 * width) + 2 * pad);
  const sy = (height - 2 * pad) / (maxY - minY || 1);
  const s = Math.min(scale, sy);
  const offX = (width - (maxX - minX) * s) / 2;
  const offY = (height - (maxY - minY) * s) / 2;
  const round1 = (n) => Math.round(n * 10) / 10;
  return { height, at: (p) => [round1(offX + (p.lng * k - minX) * s), round1(offY + (-p.lat - minY) * s)] };
}

const pt = ([lat, lng]) => ({ lat, lng });

// Draw the places into `svg`. Options:
//   focus   { lat, lng, km }: frame only what is within km of that point (a volunteer's area)
//   duty    Set of on-duty volunteer ids (others are drawn hollow)
//   you     a volunteer id drawn as "you", pulsing gently, labelled `youLabel`
//   routes  [{ stops: [{ lat, lng }], tone }] drawn under the dots (tone: "" | "is-active" | "is-asking")
//   linkable  dots carry data-kind / data-id, and kitchens, shelters and on-duty volunteers take
//             focus (the dashboard lights up their slips)
export function drawMap(svg, places, { width = 360, pad = 40, focus = null, duty = new Set(), you = null,
                                       youLabel = "You", routes = [], linkable = false } = {}) {
  const link = (node, kind, id, name, focusable) => {
    if (!linkable) return node;
    node.classList.add("m-dot");
    node.dataset.kind = kind;
    node.dataset.id = id;
    if (focusable) {
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "img");
      node.setAttribute("aria-label", name);
    }
    return node;
  };
  const all = [...places.kitchens, ...places.volunteers, ...places.ngos, ...places.areas];
  const water = [...WATER.coast, ...WATER.channels.flat()].map(pt);
  const frame = focus
    ? [focus, ...[...all, ...water].filter((p) => km(p, focus) <= focus.km)]
    : [...all, { lat: all.reduce((s, p) => s + p.lat, 0) / all.length, lng: WEST_EDGE }];
  const { at, height } = projector(frame, { width, pad });
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const nodes = [];

  // water first: the sea west of the coast, then the backwater channels
  const coast = WATER.coast.map((p) => at(pt(p)));
  const sea = [...coast, [-200, coast[coast.length - 1][1]], [-200, coast[0][1]]];
  nodes.push(svgEl("polygon", { points: sea.map((p) => p.join(",")).join(" "), class: "m-sea" }));
  nodes.push(svgEl("polyline", { points: coast.map((p) => p.join(",")).join(" "), class: "m-water" }));
  for (const line of WATER.channels) {
    nodes.push(svgEl("polyline", { points: line.map((p) => at(pt(p)).join(",")).join(" "),
                                   class: "m-water" }));
  }
  for (const a of places.areas) {
    const [x, y] = at(a);
    nodes.push(svgEl("circle", { cx: x, cy: y, r: 32, class: "m-area" }));
    nodes.push(svgEl("text", { x, y: y - 40, "text-anchor": "middle", class: "m-area-label" }, a.name));
  }
  for (const r of routes) {
    nodes.push(svgEl("polyline", { points: r.stops.map((s) => at(s).join(",")).join(" "),
                                   class: `m-route ${r.tone || ""}` }));
  }
  for (const v of places.volunteers) {
    if (v.id === you) continue;
    const [x, y] = at(v);
    const on = duty.has(v.id) || v.on_duty;
    const dot = svgEl("circle", { cx: x, cy: y, r: 5.5, class: `m-vol${on ? "" : " is-off"}` });
    dot.append(svgEl("title", {}, `${v.name} (volunteer, ${on ? "on duty" : "off duty"})`));
    nodes.push(link(dot, "vol", v.id, `${v.name}, volunteer on duty`, on));
  }
  for (const n of places.ngos) {
    const [x, y] = at(n);
    const box = svgEl("rect", { x: x - 7.5, y: y - 7.5, width: 15, height: 15, rx: 2, class: "m-ngo" });
    box.append(svgEl("title", {}, `${n.name} (shelter)`));
    nodes.push(link(box, "ngo", n.id, `${n.name}, shelter`, true));
  }
  for (const k of places.kitchens) {
    const [x, y] = at(k);
    const dot = svgEl("circle", { cx: x, cy: y, r: 9, class: "m-kitchen" });
    dot.append(svgEl("title", {}, `${k.name} (kitchen)`));
    nodes.push(link(dot, "kitchen", k.id, `${k.name}, kitchen`, true));
  }
  const me = places.volunteers.find((v) => v.id === you);
  if (me) {
    const [x, y] = at(me);
    nodes.push(svgEl("circle", { cx: x, cy: y, r: 9, class: "m-you-pulse" }));
    const dot = svgEl("circle", { cx: x, cy: y, r: 9, class: "m-you" });
    dot.append(svgEl("title", {}, youLabel));
    nodes.push(dot);
    nodes.push(svgEl("text", { x: x + 14, y: y + 5, class: "m-label" }, youLabel));
  }
  svg.replaceChildren(...nodes);
  return { at, height };
}
