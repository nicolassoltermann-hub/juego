#!/usr/bin/env python3
"""
DUNGEON ESCAPE - A roguelike dungeon crawler
Controls: WASD or arrow keys to move, Q to quit
Goal: Collect treasure, defeat monsters, reach the EXIT (E)
"""

import curses
import random
import time

# Symbols
WALL    = '#'
FLOOR   = '.'
PLAYER  = '@'
MONSTER = 'M'
TREASURE= '$'
EXIT    = 'E'
EMPTY   = ' '

# Colors (curses pair IDs)
C_WALL     = 1
C_PLAYER   = 2
C_MONSTER  = 3
C_TREASURE = 4
C_EXIT     = 5
C_UI       = 6
C_DEAD     = 7
C_MSG      = 8


# ── Dungeon generation ────────────────────────────────────────────────────────

def make_dungeon(width, height, num_rooms=8):
    grid = [[WALL] * width for _ in range(height)]
    rooms = []

    for _ in range(num_rooms * 5):
        if len(rooms) >= num_rooms:
            break
        w = random.randint(5, 12)
        h = random.randint(4, 8)
        x = random.randint(1, width  - w - 1)
        y = random.randint(1, height - h - 1)

        # Check overlap (with 1-tile buffer)
        overlaps = any(
            rx - 1 <= x + w and x - 1 <= rx + rw and
            ry - 1 <= y + h and y - 1 <= ry + rh
            for rx, ry, rw, rh in rooms
        )
        if overlaps:
            continue

        for cy in range(y, y + h):
            for cx in range(x, x + w):
                grid[cy][cx] = FLOOR
        rooms.append((x, y, w, h))

    # Connect rooms with corridors
    random.shuffle(rooms)
    for i in range(len(rooms) - 1):
        ax, ay = rooms[i][0] + rooms[i][2] // 2, rooms[i][1] + rooms[i][3] // 2
        bx, by = rooms[i+1][0] + rooms[i+1][2] // 2, rooms[i+1][1] + rooms[i+1][3] // 2
        cx, cy = ax, ay
        while cx != bx:
            grid[cy][cx] = FLOOR
            cx += 1 if bx > cx else -1
        while cy != by:
            grid[cy][cx] = FLOOR
            cy += 1 if by > cy else -1

    return grid, rooms


def random_floor(grid, exclude=None):
    exclude = exclude or set()
    while True:
        y = random.randint(1, len(grid) - 2)
        x = random.randint(1, len(grid[0]) - 2)
        if grid[y][x] == FLOOR and (x, y) not in exclude:
            return x, y


def place_entities(grid, rooms, num_monsters=8, num_treasures=12):
    occupied = set()

    px, py = random_floor(grid)
    occupied.add((px, py))

    # Exit in the farthest room
    ex, ey, ew, eh = rooms[-1]
    exit_x = ex + ew // 2
    exit_y = ey + eh // 2
    occupied.add((exit_x, exit_y))

    monsters  = []
    treasures = []

    for _ in range(num_monsters):
        x, y = random_floor(grid, occupied)
        occupied.add((x, y))
        monsters.append({'x': x, 'y': y, 'hp': 3, 'max_hp': 3})

    for _ in range(num_treasures):
        x, y = random_floor(grid, occupied)
        occupied.add((x, y))
        treasures.append((x, y))

    return (px, py), (exit_x, exit_y), monsters, treasures


# ── Rendering ─────────────────────────────────────────────────────────────────

def render(stdscr, grid, player, exit_pos, monsters, treasures, hp, max_hp, score, message, turn):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    monster_pos  = {(m['x'], m['y']): m for m in monsters}
    treasure_pos = set(treasures)

    # Draw dungeon (leave bottom 3 rows for UI)
    view_h = h - 3

    for y, row in enumerate(grid):
        if y >= view_h:
            break
        for x, cell in enumerate(row):
            if x >= w - 1:
                break
            cx, cy = player
            mx, my = x - cx + w // 2, y - cy + view_h // 2
            if mx < 0 or mx >= w - 1 or my < 0 or my >= view_h:
                continue

            ex, ey = exit_pos
            if (x, y) == (cx, cy):
                attr = curses.color_pair(C_PLAYER) | curses.A_BOLD
                ch   = PLAYER
            elif (x, y) == (ex, ey):
                attr = curses.color_pair(C_EXIT) | curses.A_BOLD
                ch   = EXIT
            elif (x, y) in monster_pos:
                m    = monster_pos[(x, y)]
                attr = curses.color_pair(C_MONSTER) | curses.A_BOLD
                ch   = str(m['hp'])
            elif (x, y) in treasure_pos:
                attr = curses.color_pair(C_TREASURE) | curses.A_BOLD
                ch   = TREASURE
            elif cell == WALL:
                attr = curses.color_pair(C_WALL)
                ch   = WALL
            elif cell == FLOOR:
                attr = curses.color_pair(C_UI)
                ch   = FLOOR
            else:
                continue

            try:
                stdscr.addch(my, mx, ch, attr)
            except curses.error:
                pass

    # UI bar
    ui_y = h - 3
    hp_bar  = '█' * hp + '░' * (max_hp - hp)
    hp_line = f" HP: [{hp_bar}] {hp}/{max_hp}   Score: {score}   Turn: {turn}   Monsters left: {len(monsters)} "
    msg_line = f" {message} "

    try:
        stdscr.addstr(ui_y,     0, '─' * (w - 1), curses.color_pair(C_UI))
        stdscr.addstr(ui_y + 1, 0, hp_line[:w-1],  curses.color_pair(C_UI) | curses.A_BOLD)
        stdscr.addstr(ui_y + 2, 0, msg_line[:w-1],  curses.color_pair(C_MSG))
    except curses.error:
        pass

    stdscr.refresh()


# ── Monster AI ────────────────────────────────────────────────────────────────

def move_monsters(grid, monsters, player_pos, treasures):
    px, py = player_pos
    treasure_set = set(treasures)

    for m in monsters:
        dx = px - m['x']
        dy = py - m['y']
        dist = abs(dx) + abs(dy)

        if dist > 8:
            continue  # Out of aggro range

        steps = []
        if abs(dx) >= abs(dy):
            steps = [(dx // abs(dx) if dx else 0, 0), (0, dy // abs(dy) if dy else 0)]
        else:
            steps = [(0, dy // abs(dy) if dy else 0), (dx // abs(dx) if dx else 0, 0)]

        for sx, sy in steps:
            nx, ny = m['x'] + sx, m['y'] + sy
            if grid[ny][nx] != WALL and (nx, ny) not in treasure_set:
                # Don't stack on other monsters
                if not any(o['x'] == nx and o['y'] == ny for o in monsters if o is not m):
                    m['x'], m['y'] = nx, ny
                    break


# ── Main game loop ────────────────────────────────────────────────────────────

def game_loop(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(100)

    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_WALL,     curses.COLOR_WHITE,  -1)
    curses.init_pair(C_PLAYER,   curses.COLOR_GREEN,  -1)
    curses.init_pair(C_MONSTER,  curses.COLOR_RED,    -1)
    curses.init_pair(C_TREASURE, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_EXIT,     curses.COLOR_CYAN,   -1)
    curses.init_pair(C_UI,       curses.COLOR_WHITE,  -1)
    curses.init_pair(C_DEAD,     curses.COLOR_RED,    -1)
    curses.init_pair(C_MSG,      curses.COLOR_MAGENTA,-1)

    DUNGEON_W, DUNGEON_H = 80, 40

    while True:
        grid, rooms = make_dungeon(DUNGEON_W, DUNGEON_H)
        (px, py), exit_pos, monsters, treasures = place_entities(grid, rooms)

        player   = [px, py]
        hp       = 10
        max_hp   = 10
        score    = 0
        turn     = 0
        message  = "Find the EXIT (E)! Collect $ for points. WASD/arrows to move. Q=quit."
        move_timer = 0

        while True:
            render(stdscr, grid, player, exit_pos, monsters, treasures, hp, max_hp, score, message, turn)

            key = stdscr.getch()

            if key in (ord('q'), ord('Q')):
                return score

            # Movement
            dx, dy = 0, 0
            if   key in (ord('w'), ord('W'), curses.KEY_UP):    dy = -1
            elif key in (ord('s'), ord('S'), curses.KEY_DOWN):  dy =  1
            elif key in (ord('a'), ord('A'), curses.KEY_LEFT):  dx = -1
            elif key in (ord('d'), ord('D'), curses.KEY_RIGHT): dx =  1
            else:
                continue

            nx, ny = player[0] + dx, player[1] + dy

            if grid[ny][nx] == WALL:
                message = "Blocked by wall."
                continue

            # Check monster collision (attack)
            attacked = next((m for m in monsters if m['x'] == nx and m['y'] == ny), None)
            if attacked:
                attacked['hp'] -= 1
                score += 10
                if attacked['hp'] <= 0:
                    monsters.remove(attacked)
                    score += 50
                    message = f"Monster slain! +50 pts. Score: {score}"
                else:
                    message = f"Hit monster! ({attacked['hp']} HP left)"
                turn += 1
                move_monsters(grid, monsters, player, treasures)
                # Monster counterattack if adjacent
                for m in monsters:
                    if abs(m['x'] - player[0]) + abs(m['y'] - player[1]) == 1:
                        hp -= 1
                        message += "  Ouch! Monster hit you!"
                continue

            player[0], player[1] = nx, ny
            turn += 1

            # Treasure
            if (nx, ny) in treasures:
                treasures.remove((nx, ny))
                score += 25
                message = f"Treasure collected! +25 pts. Score: {score}"

            # Exit
            if (nx, ny) == exit_pos:
                bonus = len(treasures) == 0 and 200 or 0
                score += 100 + bonus
                message = f"You escaped! Final score: {score}. Press any key..."
                render(stdscr, grid, player, exit_pos, monsters, treasures, hp, max_hp, score, message, turn)
                stdscr.nodelay(False)
                stdscr.getch()
                break  # New dungeon

            # Monster movement & attacks
            move_monsters(grid, monsters, player, treasures)
            for m in monsters:
                if abs(m['x'] - player[0]) + abs(m['y'] - player[1]) <= 1:
                    hp -= 1
                    if message.startswith("Treasure") or message.startswith("Find"):
                        message = "A monster attacks you! -1 HP"

            if hp <= 0:
                message = f"You died! Score: {score}. Press any key..."
                render(stdscr, grid, player, exit_pos, monsters, treasures, 0, max_hp, score, message, turn)
                stdscr.nodelay(False)
                stdscr.getch()
                return score  # Game over


def show_screen(stdscr, lines, color_pair, wait=True):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    for i, line in enumerate(lines):
        y = h // 2 - len(lines) // 2 + i
        x = max(0, w // 2 - len(line) // 2)
        try:
            stdscr.addstr(y, x, line, color_pair | curses.A_BOLD)
        except curses.error:
            pass
    stdscr.refresh()
    if wait:
        stdscr.nodelay(False)
        stdscr.getch()


def main(stdscr):
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_PLAYER,   curses.COLOR_GREEN,  -1)
    curses.init_pair(C_TREASURE, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_EXIT,     curses.COLOR_CYAN,   -1)
    curses.init_pair(C_MONSTER,  curses.COLOR_RED,    -1)
    curses.init_pair(C_UI,       curses.COLOR_WHITE,  -1)
    curses.curs_set(0)

    title = [
        "╔══════════════════════════════════╗",
        "║       DUNGEON  ESCAPE            ║",
        "║  A Random Roguelike Adventure    ║",
        "╠══════════════════════════════════╣",
        "║  @ = You     M = Monster         ║",
        "║  $ = Treasure ($25 pts)          ║",
        "║  E = Exit   (escape to win!)     ║",
        "║  WASD / Arrow keys to move       ║",
        "║  Attack: walk into monsters      ║",
        "║  Q = Quit                        ║",
        "╚══════════════════════════════════╝",
        "",
        "         Press any key to play",
    ]
    show_screen(stdscr, title, curses.color_pair(C_PLAYER))

    final_score = game_loop(stdscr)

    game_over = [
        "╔══════════════════════════════╗",
        "║         GAME  OVER           ║",
        f"║      Final Score: {str(final_score).center(9)} ║",
        "╚══════════════════════════════╝",
        "",
        "      Press any key to exit",
    ]
    show_screen(stdscr, game_over, curses.color_pair(C_MONSTER))


if __name__ == '__main__':
    curses.wrapper(main)
