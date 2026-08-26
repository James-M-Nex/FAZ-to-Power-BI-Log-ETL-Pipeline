import sys
import msvcrt
import time
import random as r

# ANSI Colors
colors = {
    "RED": "\033[0;31m",
    "YELLOW": "\033[93m",
    "GREEN": "\033[0;32m",
    "CYAN": "\033[96m",
    "BLUE": "\033[0;34m",
    "PURPLE": "\033[0;35m",
    "BYELLOW": "\033[1;33m",
    "BRED": "\033[1;31m",
    "RESET": "\033[0m"
}

# Cursor Control for Flicker-Free Rendering
HOME = "\033[H"            # Move cursor to top-left (overwrites without erasing)
HIDE_CURSOR = "\033[?25l"  # Hide blinking cursor
SHOW_CURSOR = "\033[?25h"  # Show cursor when quitting
CLEAR_ONCE = "\033[2J"     # Clear screen once at start

GRID_SIZE = 20
character_head = [GRID_SIZE/2, GRID_SIZE/2]
character_body = []
direction = [0, 0]  # [dx, dy]

def spawn_apple():
    while True:
        pos = [r.randint(0, GRID_SIZE - 1), r.randint(0, GRID_SIZE - 1)]
        if pos != character_head and pos not in character_body:
            return pos

apple = spawn_apple()
apple_flag = False
game_over = False
k = 0

# Hide cursor and clear terminal once at startup
print(HIDE_CURSOR + CLEAR_ONCE, end="")

try:
    while True:
        # Non-blocking input handling
        while msvcrt.kbhit():
            key = msvcrt.getwch().lower()
            if key == "w" and direction != [0, 1]:
                direction = [0, -1]
            elif key == "s" and direction != [0, -1]:
                direction = [0, 1]
            elif key == "a" and direction != [1, 0]:
                direction = [-1, 0]
            elif key == "d" and direction != [-1, 0]:
                direction = [1, 0]
            elif key in ("x", "q"):
                game_over = True
                break

        if game_over:
            break

        # Move snake if moving
        if direction != [0, 0]:
            old_head = list(character_head)
            new_head = [character_head[0] + direction[0], character_head[1] + direction[1]]

            # Check boundary collision
            if new_head[0] < 0 or new_head[0] >= GRID_SIZE or new_head[1] < 0 or new_head[1] >= GRID_SIZE:
                game_over = True
            # Check self collision
            elif new_head in character_body[1:]:
                game_over = True
            else:
                character_head = new_head
                if character_head == apple:
                    character_body.insert(0, old_head)
                    apple = spawn_apple()
                    apple_flag = True
                elif character_body:
                    character_body = [old_head] + character_body[:-1]

        # Build the entire frame string in memory first (double buffering)
        frame = [HOME, f"{colors["YELLOW"]}Use WASD to move. Press 'x' or 'q' to quit.{colors["RESET"]}\n\n"]

        for i in range(GRID_SIZE):
            for j in range(GRID_SIZE):
                if j == character_head[0] and i == character_head[1]:
                    frame.append(f"{colors['BYELLOW']}<>{colors['RESET']}")
                elif j == apple[0] and i == apple[1]:
                    frame.append(f"{colors['BRED']}@*{colors["RESET"]}")
                elif any(j == seg[0] and i == seg[1] for seg in character_body):
                    frame.append(f"{colors['BYELLOW']}{{}}{colors['RESET']}")
                else:
                    if apple_flag:
                        colors_list = list(colors.values())[:-3]
                        if k < len(colors_list):
                            frame.append(f"{colors_list[k]}',{colors['RESET']}")
                        else:
                            k = 0
                            apple_flag = False
                    else:
                        frame.append(f"{colors['GREEN']}',{colors['RESET']}")
            frame.append("\n")

        if apple_flag:
            k += 1

        if game_over:
            frame.append(f"\n{colors['BRED']}GAME OVER! Final Score: {len(character_body)}{colors['RESET']}\n")

        # Output the complete frame in one single call (zero flickering)
        sys.stdout.write("".join(frame))
        sys.stdout.flush()

        if game_over:
            break

        scale = (1 + (len(character_body) * 0.25))

        time.sleep(0.4 / scale)
finally:
    # Always restore blinking cursor when exiting
    print(SHOW_CURSOR, end="")