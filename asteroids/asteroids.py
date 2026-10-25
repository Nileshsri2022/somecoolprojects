"""Terminal Asteroids (Coding Challenges: Build Your Own Asteroids).

All game logic is pure and non-interactive: it works on the
dataclasses below and never touches the terminal, so it is fully
unit-testable.  Only main() imports curses, and only to run the
thin interactive loop over step() and render_frame().

World: WIDTH x HEIGHT cells, float positions, y grows down,
angle 0 points right, -pi/2 points up (the ship's start facing).
"""
import math
import random
import time
from dataclasses import dataclass, field

WIDTH = 80
HEIGHT = 24
SHIP_RADIUS = 1.0
ROTATION = 0.25          # radians turned per tick
THRUST = 0.15            # velocity added per thrust tick
DAMPING = 0.99           # velocity retained per tick (slow decay)
BULLET_SPEED = 2.0
BULLET_LIFE = 50         # ticks a bullet survives
MAX_BULLETS = 4
SAUCER_RADIUS = 2.0
SAUCER_SPEED = 0.4
SAUCER_SCORE = 200
SAUCER_EVERY_TICKS = 600
INVULN_TICKS = 30
START_LIVES = 3
LARGE, MEDIUM, SMALL = 3, 2, 1
ASTEROID_RADIUS = {LARGE: 4.0, MEDIUM: 2.5, SMALL: 1.5}
ASTEROID_SCORE = {LARGE: 20, MEDIUM: 50, SMALL: 100}
ASTEROID_GLYPH = {LARGE: "O", MEDIUM: "o", SMALL: "."}
ASTEROID_SPEED = {LARGE: 0.3, MEDIUM: 0.5, SMALL: 0.8}


@dataclass
class Ship:
    x: float = WIDTH / 2
    y: float = HEIGHT / 2
    vx: float = 0.0
    vy: float = 0.0
    angle: float = -math.pi / 2  # facing up


@dataclass
class Asteroid:
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    size: int = LARGE

    @property
    def radius(self):
        return ASTEROID_RADIUS[self.size]


@dataclass
class Bullet:
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    life: int = BULLET_LIFE


@dataclass
class Saucer:
    x: float = 0.0
    y: float = 0.0
    vx: float = SAUCER_SPEED
    vy: float = 0.0


@dataclass
class Game:
    ship: Ship = field(default_factory=Ship)
    asteroids: list = field(default_factory=list)
    bullets: list = field(default_factory=list)
    saucer: object = None
    score: int = 0
    lives: int = START_LIVES
    level: int = 1
    tick: int = 0
    invulnerable: int = 0
    game_over: bool = False
    high_score: int = 0
    rng: random.Random = field(default_factory=random.Random)


def wrap(value, limit):
    """Toroidal wrap: leaving one edge re-enters on the opposite."""
    return value % limit


def _norm_angle(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def rotate_ship(ship, direction):
    """direction: -1 left, +1 right, 0 none. Returns the ship."""
    ship.angle = _norm_angle(ship.angle + direction * ROTATION)
    return ship


def apply_thrust(ship):
    ship.vx += math.cos(ship.angle) * THRUST
    ship.vy += math.sin(ship.angle) * THRUST
    return ship


def move_ship(ship):
    ship.x = wrap(ship.x + ship.vx, WIDTH)
    ship.y = wrap(ship.y + ship.vy, HEIGHT)
    ship.vx *= DAMPING
    ship.vy *= DAMPING
    return ship


def move_asteroid(asteroid):
    asteroid.x = wrap(asteroid.x + asteroid.vx, WIDTH)
    asteroid.y = wrap(asteroid.y + asteroid.vy, HEIGHT)
    return asteroid


def move_bullet(bullet):
    bullet.x = wrap(bullet.x + bullet.vx, WIDTH)
    bullet.y = wrap(bullet.y + bullet.vy, HEIGHT)
    bullet.life -= 1
    return bullet


def fire_bullet(game):
    """Bullet from the ship's nose, inheriting ship velocity.
    Returns the bullet, or None at the MAX_BULLETS cap."""
    if len(game.bullets) >= MAX_BULLETS:
        return None
    ship = game.ship
    bullet = Bullet(
        x=ship.x + math.cos(ship.angle) * (SHIP_RADIUS + 1),
        y=ship.y + math.sin(ship.angle) * (SHIP_RADIUS + 1),
        vx=ship.vx + math.cos(ship.angle) * BULLET_SPEED,
        vy=ship.vy + math.sin(ship.angle) * BULLET_SPEED,
    )
    game.bullets.append(bullet)
    return bullet


def split_asteroid(asteroid):
    """Two faster children one size smaller; [] for a small rock."""
    if asteroid.size <= SMALL:
        return []
    speed = math.hypot(asteroid.vx, asteroid.vy)
    heading = math.atan2(asteroid.vy, asteroid.vx) if speed > 0 else 0.0
    child_speed = max(speed + 0.3, 0.5)
    children = []
    for sign in (-1, 1):
        ang = heading + sign * 0.7
        children.append(Asteroid(
            x=asteroid.x, y=asteroid.y,
            vx=math.cos(ang) * child_speed,
            vy=math.sin(ang) * child_speed,
            size=asteroid.size - 1,
        ))
    return children


def collides(x1, y1, r1, x2, y2, r2):
    return (x1 - x2) ** 2 + (y1 - y2) ** 2 <= (r1 + r2) ** 2


def spawn_level(game, level):
    """3 + level large asteroids, none near the centre."""
    game.asteroids = []
    for _ in range(3 + level):
        while True:
            x = game.rng.uniform(0, WIDTH)
            y = game.rng.uniform(0, HEIGHT)
            if math.hypot(x - WIDTH / 2, y - HEIGHT / 2) >= 12:
                break
        ang = game.rng.uniform(0, 2 * math.pi)
        game.asteroids.append(Asteroid(
            x=x, y=y,
            vx=math.cos(ang) * ASTEROID_SPEED[LARGE],
            vy=math.sin(ang) * ASTEROID_SPEED[LARGE],
            size=LARGE,
        ))
    return game.asteroids


def spawn_saucer(game):
    """Enters from a random side, crossing horizontally."""
    from_left = game.rng.random() < 0.5
    game.saucer = Saucer(
        x=0.0 if from_left else WIDTH - 1.0,
        y=game.rng.uniform(2, HEIGHT - 2),
        vx=SAUCER_SPEED if from_left else -SAUCER_SPEED,
    )
    return game.saucer


def new_game(seed=None):
    game = Game(rng=random.Random(seed) if seed is not None else random.Random())
    spawn_level(game, 1)
    return game


def _lose_life(game):
    game.lives -= 1
    game.bullets = []
    if game.lives <= 0:
        game.game_over = True
    else:
        game.ship = Ship()  # centre, stopped, facing up
        game.invulnerable = INVULN_TICKS


def step(game, rotate=0, thrust=False, fire=False):
    """Advance one tick. rotate: -1/0/+1; thrust/fire: booleans."""
    if game.game_over:
        return game
    game.tick += 1
    if rotate:
        rotate_ship(game.ship, rotate)
    if thrust:
        apply_thrust(game.ship)
    move_ship(game.ship)
    if game.invulnerable > 0:
        game.invulnerable -= 1
    for asteroid in game.asteroids:
        move_asteroid(asteroid)
    game.bullets = [b for b in (move_bullet(b) for b in game.bullets)
                    if b.life > 0]
    if game.saucer is not None:
        game.saucer.x = wrap(game.saucer.x + game.saucer.vx, WIDTH)
        game.saucer.y = wrap(game.saucer.y + game.saucer.vy, HEIGHT)
    elif game.tick % SAUCER_EVERY_TICKS == 0:
        spawn_saucer(game)
    if fire:
        fire_bullet(game)

    # Bullet vs asteroid: bullet consumed, rock splits or dies.
    dead_bullets, dead_rocks, new_rocks = set(), set(), []
    for bi, bullet in enumerate(game.bullets):
        for ai, rock in enumerate(game.asteroids):
            if ai not in dead_rocks and collides(
                    bullet.x, bullet.y, 0.5, rock.x, rock.y, rock.radius):
                dead_bullets.add(bi)
                dead_rocks.add(ai)
                game.score += ASTEROID_SCORE[rock.size]
                new_rocks.extend(split_asteroid(rock))
                break
    game.bullets = [b for i, b in enumerate(game.bullets)
                    if i not in dead_bullets]
    game.asteroids = [r for i, r in enumerate(game.asteroids)
                      if i not in dead_rocks] + new_rocks

    # Bullet vs saucer.
    if game.saucer is not None:
        for bi, bullet in enumerate(game.bullets):
            if collides(bullet.x, bullet.y, 0.5,
                        game.saucer.x, game.saucer.y, SAUCER_RADIUS):
                game.bullets.pop(bi)
                game.saucer = None
                game.score += SAUCER_SCORE
                break

    # Ship vs asteroid / saucer (invulnerability protects).
    if game.invulnerable == 0:
        hit = any(collides(game.ship.x, game.ship.y, SHIP_RADIUS,
                           rock.x, rock.y, rock.radius)
                  for rock in game.asteroids)
        if not hit and game.saucer is not None:
            hit = collides(game.ship.x, game.ship.y, SHIP_RADIUS,
                           game.saucer.x, game.saucer.y, SAUCER_RADIUS)
        if hit:
            _lose_life(game)

    if game.score > game.high_score:
        game.high_score = game.score
    # Field cleared -> next, harder level (score/lives kept).
    if not game.game_over and not game.asteroids:
        game.level += 1
        spawn_level(game, game.level)
    return game


def ship_glyph(angle):
    """Ship character for the facing octant (y grows down)."""
    glyphs = [">", "\\", "v", "/", "<", "\\", "^", "/"]
    sector = round(math.degrees(_norm_angle(angle)) / 45) % 8
    return glyphs[sector]


def render_frame(game):
    """Pure rendering: HEIGHT rows of WIDTH characters."""
    grid = [[" "] * WIDTH for _ in range(HEIGHT)]

    def put(x, y, ch):
        grid[int(round(y)) % HEIGHT][int(round(x)) % WIDTH] = ch

    for rock in game.asteroids:
        put(rock.x, rock.y, ASTEROID_GLYPH[rock.size])
    for bullet in game.bullets:
        put(bullet.x, bullet.y, "*")
    if game.saucer is not None:
        put(game.saucer.x, game.saucer.y, "U")
    if not game.game_over:
        put(game.ship.x, game.ship.y, ship_glyph(game.ship.angle))
    return ["".join(row) for row in grid]


# --- Thin curses UI (the only terminal-dependent part) ---

def _run(stdscr):
    import curses
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    game = new_game()
    state = "start"  # start | play | over
    while True:
        stdscr.erase()
        if state == "start":
            stdscr.addstr(0, 0, "ASTEROIDS")
            stdscr.addstr(2, 0, "Left/Right: rotate   Up: thrust   Space: fire")
            stdscr.addstr(3, 0, "Press SPACE to start, q to quit")
            if game.high_score:
                stdscr.addstr(4, 0, f"High score: {game.high_score}")
            key = stdscr.getch()
            if key == ord("q"):
                return
            if key == ord(" "):
                game = new_game()
                state = "play"
        elif state == "over":
            stdscr.addstr(0, 0, "GAME OVER")
            stdscr.addstr(2, 0, f"Score: {game.score}   High: {game.high_score}")
            stdscr.addstr(3, 0, "Press SPACE for a new game, q to quit")
            key = stdscr.getch()
            if key == ord("q"):
                return
            if key == ord(" "):
                high = game.high_score
                game = new_game()
                game.high_score = high
                state = "play"
        else:
            key = stdscr.getch()
            if key == ord("q"):
                return
            step(game,
                 rotate=(-1 if key in (curses.KEY_LEFT, ord("a")) else
                         1 if key in (curses.KEY_RIGHT, ord("d")) else 0),
                 thrust=key in (curses.KEY_UP, ord("w")),
                 fire=key == ord(" "))
            stdscr.addstr(0, 0,
                          f"Score: {game.score}  Lives: {game.lives}  "
                          f"Level: {game.level}  High: {game.high_score}")
            for i, row in enumerate(render_frame(game)):
                stdscr.addstr(i + 1, 0, row)
            if game.game_over:
                state = "over"
        stdscr.refresh()
        time.sleep(1 / 15)


def main():
    import curses
    curses.wrapper(_run)


if __name__ == "__main__":
    main()
