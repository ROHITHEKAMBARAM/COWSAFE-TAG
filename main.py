"""CowSafe Tag: smart neck tag logic and simulation (pure Python, no extra libraries).

Run:  python main.py

What it shows:
  Act 1  Virtual boundary: light vibration first, then a mild pulse. The cow trains itself.
  Act 2  Plastic Guard: red zone at a garbage pile, sniffing and chewing alert, vet flag.
  Act 3  Health monitoring: eating, chewing, water, temperature and activity.

Safety note: every number below is a placeholder. Pulse strength, the daily limit and the
health limits must be set with a veterinarian before any use on a real animal.
"""

import math
from dataclasses import dataclass, field

EARTH_RADIUS_M = 6371000.0


# --------------------------------------------------------------------------- geo
def distance_m(a, b):
    """Distance in metres between two (lat, lon) points."""
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    dla, dlo = la2 - la1, math.radians(b[1] - a[1])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def offset_m(origin, east_m, north_m):
    """Point that is east_m / north_m metres away from origin."""
    lat = origin[0] + math.degrees(north_m / EARTH_RADIUS_M)
    lon = origin[1] + math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(origin[0]))))
    return (lat, lon)


def inside_polygon(poly, p):
    """True if point p is inside the polygon (ray casting)."""
    if len(poly) < 3:
        return False
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if (yi > p[0]) != (yj > p[0]) and p[1] < (xj - xi) * (p[0] - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def edge_distance_m(poly, p):
    """Shortest distance in metres from p to the polygon's edge."""
    def local(q):
        return ((q[1] - p[1]) * math.radians(1) * EARTH_RADIUS_M * math.cos(math.radians(p[0])),
                (q[0] - p[0]) * math.radians(1) * EARTH_RADIUS_M)

    best = float("inf")
    for i in range(len(poly)):
        ax, ay = local(poly[i])
        bx, by = local(poly[(i + 1) % len(poly)])
        dx, dy = bx - ax, by - ay
        len2 = dx * dx + dy * dy
        t = 0.0 if len2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / len2))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


# --------------------------------------------------------------------------- tag
SAFE, WARN, VIOLATION = "SAFE", "WARN", "VIOLATION"
PULSE_HARD_CAP_PCT = 40  # PLACEHOLDER: set with a veterinarian


@dataclass
class Config:
    warn_distance_m: float = 10.0       # start warning this close to an edge or red zone
    vibration_ms: int = 500
    pulse_ms: int = 200
    pulse_strength_pct: int = 20        # never above PULSE_HARD_CAP_PCT
    max_pulses_per_day: int = 5         # pulses switch off after this many
    vibration_repeat_s: int = 15
    pulse_interval_s: int = 10          # minimum gap after any vibration or pulse
    head_down_pitch_deg: float = -30.0
    chew_min_hz: float = 0.5
    chew_max_hz: float = 2.0
    sniff_chew_dwell_s: int = 10
    vet_flag_visits: int = 3


@dataclass
class RedZone:
    name: str
    center: tuple
    radius_m: float
    visits: int = 0


@dataclass
class Stats:
    vibrations: int = 0
    pulses: int = 0
    boundary_breaks: int = 0
    red_zone_entries: int = 0
    plastic_alerts: int = 0
    turned_back: int = 0
    escalated: int = 0


@dataclass
class Tag:
    boundary: list
    red_zones: list = field(default_factory=list)
    cfg: Config = field(default_factory=Config)
    on_vibrate: callable = None
    on_pulse: callable = None
    on_alert: callable = None   # message to the farmer's phone

    def __post_init__(self):
        self.cfg.pulse_strength_pct = max(0, min(self.cfg.pulse_strength_pct, PULSE_HARD_CAP_PCT))
        self.stats = Stats()
        self.state = SAFE
        self.episode = False
        self.escalated_now = False
        self.last_vibe = None
        self.last_stim = None
        self.pulses_today = 0
        self.limit_alerted = False
        self.was_outside = False
        self.was_in_red = False
        self.dwell = 0
        self.plastic_alerted = False
        self.last_t = None

    # -- helpers
    def _alert(self, msg):
        if self.on_alert:
            self.on_alert(msg)

    def _vibrate(self, now):
        if self.on_vibrate:
            self.on_vibrate(self.cfg.vibration_ms)
        self.stats.vibrations += 1
        self.last_vibe = self.last_stim = now

    def _pulse(self, now):
        if self.last_stim is not None and now - self.last_stim < self.cfg.pulse_interval_s:
            return
        if self.pulses_today >= self.cfg.max_pulses_per_day:      # automatic switch-off
            if not self.limit_alerted:
                self.limit_alerted = True
                self._alert("Daily pulse limit reached: pulses switched off for today")
            return
        if self.on_pulse:
            self.on_pulse(self.cfg.pulse_strength_pct, self.cfg.pulse_ms)
        self.pulses_today += 1
        self.stats.pulses += 1
        self.last_stim = now

    def new_day(self):
        self.pulses_today = 0
        self.limit_alerted = False

    def training_score(self):
        """Percent of finished warnings where the cow turned back on vibration alone."""
        done = self.stats.turned_back + self.stats.escalated
        return None if done == 0 else 100.0 * self.stats.turned_back / done

    # -- main update, call about once per second
    def update(self, now, pos, head_pitch_deg=0.0, chew_hz=0.0):
        c = self.cfg
        dt = 0 if self.last_t is None else max(0, now - self.last_t)
        self.last_t = now

        inside = inside_polygon(self.boundary, pos) if len(self.boundary) >= 3 else True
        edge_d = edge_distance_m(self.boundary, pos) if (inside and len(self.boundary) >= 3) else 1e9

        zone, gap = None, 1e9
        for z in self.red_zones:
            g = distance_m(z.center, pos) - z.radius_m
            if g < gap:
                zone, gap = z, g
        in_red = zone is not None and gap <= 0
        near_red = zone is not None and gap <= c.warn_distance_m

        if not inside or in_red:
            st = VIOLATION
        elif edge_d <= c.warn_distance_m or near_red:
            st = WARN
        else:
            st = SAFE

        # 1. warning episode starts with a light vibration
        if st != SAFE:
            if not self.episode:
                self.episode, self.escalated_now = True, False
                self._alert(f"Warning: cow is close to red zone '{zone.name}'" if near_red
                            else "Warning: cow is close to the boundary edge")
                self._vibrate(now)
            elif st == WARN and now - self.last_vibe >= c.vibration_repeat_s:
                self._vibrate(now)
        elif self.episode:
            self.episode = False
            if self.escalated_now:
                self.stats.escalated += 1
            else:
                self.stats.turned_back += 1

        # 2. entry alerts for the farmer
        if not inside and not self.was_outside:
            self.stats.boundary_breaks += 1
            self._alert("Cow is OUTSIDE the safe boundary")
        if in_red and not self.was_in_red:
            zone.visits += 1
            self.stats.red_zone_entries += 1
            self._alert(f"Cow entered red zone '{zone.name}' (visit {zone.visits})")
            if c.vet_flag_visits and zone.visits == c.vet_flag_visits:
                self._alert(f"Vet check suggested: cow keeps going to '{zone.name}'")
        self.was_outside, self.was_in_red = (not inside), in_red

        # 3. crossed the line after a warning: mild pulse (rate limited)
        if st == VIOLATION:
            self.escalated_now = True
            self._pulse(now)

        # 4. Plastic Guard: head down + chewing near a red zone
        if near_red:
            pattern = head_pitch_deg <= c.head_down_pitch_deg and c.chew_min_hz <= chew_hz <= c.chew_max_hz
            self.dwell = self.dwell + dt if pattern else 0
            if self.dwell >= c.sniff_chew_dwell_s and not self.plastic_alerted:
                self.plastic_alerted = True
                self.stats.plastic_alerts += 1
                self._alert(f"PLASTIC RISK: cow is sniffing and chewing near '{zone.name}'")
        else:
            self.dwell, self.plastic_alerted = 0, False

        self.state = st
        return st


# ------------------------------------------------------------------------ health
ACTIVITIES = ("resting", "walking", "eating", "ruminating", "drinking")


def classify(head_pitch_deg, chew_hz, speed_mps, at_water_point=False):
    """Simple rule-based activity guess from the motion sensor and GPS."""
    head_down, chewing = head_pitch_deg <= -30, chew_hz >= 0.5
    if speed_mps > 0.3:
        return "walking"
    if head_down and at_water_point:
        return "drinking"
    if head_down and chewing:
        return "eating"
    if chewing:
        return "ruminating"
    return "resting"


class HealthMonitor:
    """Compares today with the cow's own normal day (all numbers are placeholders)."""

    def __init__(self):
        self.normal = {"eating": 240.0, "ruminating": 420.0, "walking": 120.0, "drinks": 8.0}  # minutes / visits
        self.fever_c, self.low, self.water_low, self.high_activity, self.alpha = 39.5, 0.6, 0.5, 1.5, 0.2
        self._reset()

    def _reset(self):
        self.sec = dict.fromkeys(ACTIVITIES, 0)
        self.drinks, self.temps, self._last = 0, [], None

    def add(self, activity, seconds, temp_c=None):
        self.sec[activity] += seconds
        if activity == "drinking" and self._last != "drinking":
            self.drinks += 1
        self._last = activity
        if temp_c is not None:
            self.temps.append(temp_c)

    def alerts(self, day_fraction=1.0):
        n, f, out = self.normal, max(0.0, min(1.0, day_fraction)), []
        if len(self.temps) >= 3 and sum(self.temps) / len(self.temps) >= self.fever_c:
            out.append("possible fever (high body temperature)")
        if self.sec["eating"] / 60 < n["eating"] * f * self.low:
            out.append("eating much less than normal")
        if self.sec["ruminating"] / 60 < n["ruminating"] * f * self.low:
            out.append("chewing cud much less than normal")
        if self.drinks < n["drinks"] * f * self.water_low:
            out.append("drinking much less than normal")
        if self.sec["walking"] / 60 > n["walking"] * f * self.high_activity:
            out.append("unusually high activity (possible heat or restlessness)")
        return out

    def summary(self):
        avg = sum(self.temps) / len(self.temps) if self.temps else 0.0
        return (f"eat {self.sec['eating'] // 60} min | rumination {self.sec['ruminating'] // 60} min | "
                f"walk {self.sec['walking'] // 60} min | water visits {self.drinks} | temp {avg:.1f} C")

    def end_day(self):
        """Close the day. Learns only from healthy days, so a sick day never becomes 'normal'."""
        out = self.alerts()
        if not out:
            a, n = self.alpha, self.normal
            for key, val in (("eating", self.sec["eating"] / 60), ("ruminating", self.sec["ruminating"] / 60),
                             ("walking", self.sec["walking"] / 60), ("drinks", self.drinks)):
                n[key] = (1 - a) * n[key] + a * val
        self._reset()
        return out


# -------------------------------------------------------------------- simulation
ORIGIN = (20.0, 78.0)   # sample field centre
clock = 0               # seconds since 06:00


def stamp():
    s = 6 * 3600 + clock
    return f"{(s // 3600) % 24:02d}:{(s // 60) % 60:02d}:{s % 60:02d}"


def build_tag():
    field_corners = [offset_m(ORIGIN, x, y) for x, y in ((-100, -100), (100, -100), (100, 100), (-100, 100))]
    tag = Tag(
        boundary=field_corners,
        red_zones=[RedZone("garbage pile", offset_m(ORIGIN, -60, 60), 15.0)],
        cfg=Config(max_pulses_per_day=4, vet_flag_visits=2),   # low limits so the demo shows them
        on_vibrate=lambda ms: print(f"[{stamp()}]   vibrate {ms} ms (light warning)"),
        on_pulse=lambda pct, ms: print(f"[{stamp()}]   MILD PULSE {pct}% for {ms} ms"),
        on_alert=lambda m: print(f"[{stamp()}] > phone alert: {m}"),
    )
    return tag


def tick(tag, x, y, pitch=-5.0, chew=0.0):
    global clock
    tag.update(clock, offset_m(ORIGIN, x, y), pitch, chew)
    clock += 1


def walk(tag, x0, y0, x1, y1, speed):
    n = max(1, int(math.hypot(x1 - x0, y1 - y0) / speed))
    for i in range(1, n + 1):
        f = i / n
        tick(tag, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)


def graze(tag, x, y, seconds):
    for _ in range(seconds):
        tick(tag, x, y, pitch=-45.0, chew=1.0)   # head down, chewing about once a second


def rest(seconds):
    global clock
    clock += seconds


def health_day(h, eat, rum, walk_min, drinks, temp):
    for _ in range(24):
        h.add("resting", 0, temp)                # one temperature reading every hour
    h.add("eating", eat * 60)
    h.add("ruminating", rum * 60)
    h.add("walking", walk_min * 60)
    for _ in range(drinks):
        h.add("drinking", 30)
        h.add("resting", 60)


def main():
    tag = build_tag()
    print("CowSafe Tag simulation")
    print("Field 200 m x 200 m, garbage pile 15 m radius, warning distance 10 m\n")

    print("=== Act 1: virtual boundary and self-training ===")
    print("-- Trip 1 (east edge): the cow ignores the vibration and crosses")
    walk(tag, 0, 0, 104, 0, 0.8)
    walk(tag, 104, 0, 0, 0, 1.5)
    rest(600)
    print("-- Trip 2 (east edge): the cow turns back after the vibration")
    walk(tag, 0, 0, 95, 0, 0.8)
    walk(tag, 95, 0, 0, 0, 1.0)
    rest(600)
    print("-- Trip 3 (north edge): the cow turns back again")
    walk(tag, 0, 0, 0, 95, 0.8)
    walk(tag, 0, 95, 0, 0, 1.0)
    print(f"\nTraining score: {tag.training_score():.0f}% of warnings ended with the cow "
          "turning back on vibration alone\n")

    print("=== Act 2: Plastic Guard at the garbage pile ===")
    rest(1200)
    print("-- Visit 1: the cow walks to the pile and starts sniffing and chewing")
    walk(tag, 0, 0, -60, 60, 0.8)
    graze(tag, -60, 60, 14)
    walk(tag, -60, 60, 0, 0, 1.0)
    rest(900)
    print("-- Visit 2: the cow goes back to the pile")
    walk(tag, 0, 0, -60, 60, 0.8)
    graze(tag, -60, 60, 14)
    walk(tag, -60, 60, 0, 0, 1.0)
    s = tag.stats
    print(f"\nTag totals: vibrations {s.vibrations}, pulses {s.pulses}, boundary breaks {s.boundary_breaks}, "
          f"red-zone entries {s.red_zone_entries}, plastic alerts {s.plastic_alerts}\n")

    print("=== Act 3: health monitoring ===")
    h = HealthMonitor()
    for label, args in (("Day 1", (250, 430, 115, 8, 38.6)), ("Day 2", (235, 410, 125, 9, 38.7)),
                        ("Day 3", (110, 190, 40, 3, 39.9)), ("Day 4", (240, 420, 260, 8, 38.7))):
        health_day(h, *args)
        print(f"{label}: {h.summary()}")
        alerts = h.end_day()
        print("   -> all normal" if not alerts else "\n".join(f"   -> ALERT: {a}" for a in alerts))
    print("\nSimulation complete.")


if __name__ == "__main__":
    main()
