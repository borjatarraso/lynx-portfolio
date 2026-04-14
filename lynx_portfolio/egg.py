"""
Nothing to see here. Move along.
"""

import io
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave

# ---------------------------------------------------------------------------
# Lynx ASCII art frames
# ---------------------------------------------------------------------------

_LYNX_FRAMES = [
    r"""
        /\_/\
       ( o.o )
        > ^ <
       /|   |\
      (_|   |_)
    """,
    r"""
        /\_/\
       ( -.o )
        > ^ <
       /|   |\
      (_|   |_)
    """,
    r"""
        /\_/\
       ( o.- )
        > ^ <
       /|   |\
      (_|   |_)
    """,
    r"""
        /\_/\
       ( ^.^ )
        > ^ <
       /|   |\
      (_|   |_)
    """,
]

_LYNX_WALK = [
    r"""
              /\_/\
             ( o.o )  ~
              > ^ <
             /     \___
            /  |  |    \
           (___|  |___)
    """,
    r"""
               /\_/\
              ( o.o )   ~
               > ^ <
              /     \___
             /   |  |   \
            (___ |  |___)
    """,
    r"""
                /\_/\
               ( o.o )    ~
                > ^ <
               /     \___
              /  |  |    \
             (___|  |___)
    """,
    r"""
                 /\_/\
                ( o.o )     ~
                 > ^ <
                /     \___
               /   |  |   \
              (___ |  |___)
    """,
]

_LYNX_BIG = r"""
                                  ╱╲_╱╲
                                 ╱      ╲
                                │  ●  ●  │
                                │   ╲╱   │
                                 ╲  ──  ╱
                           ╱╲    │╲    ╱│    ╱╲
                          ╱  ╲───╯ ╲──╱ ╰───╱  ╲
                         │    ╲             ╱    │
                         │     ╲───────────╱     │
                          ╲     │         │     ╱
                           ╲    │         │    ╱
                            ╰───╯         ╰───╯
"""

_ROCKET = [
    r"""
        *
       /|\
      / | \
     /  |  \
    |   |   |
    |  LPM  |
    |       |
    |_______|
      /   \
     / ~~~ \
    /~~~~~~~\
       |||
       |||
    """,
    r"""
        *
       /|\
      / | \
     /  |  \
    |   |   |
    |  LPM  |
    |       |
    |_______|
      /   \
     /~~~~~\
    /~~~~~~~\
      |||||
      |||||
     ~~~~~~~
    """,
    r"""
        *
       /|\
      / | \
     /  |  \
    |   |   |
    |  LPM  |
    |       |
    |_______|
      /   \
     /~~~~~\
    /~~~~~~~\
     |||||||
     |||||||
    ~~~~~~~~~
    ~~~~ ~~~~
    """,
]

_BULL = r"""
               /|            |\
              / |    ____    | \
             /  |   /    \   |  \
            /   |  |  $$  |  |   \
                |  |  $$  |  |
                 \ |      | /
                  \|______|/
                   |      |
                  /|      |\
                 / |      | \
                /  |      |  \
                   |  ||  |
                   |  ||  |
                  /|      |\
                 /_|      |_\
"""

_CHART_UP = r"""

    $$$                           ╱
    $$$                         ╱
    $$$                       ╱
    $$$                     ╱
    $$$                   ╱
    $$$                 ╱   ╲
    $$$     ╱╲        ╱       ╲ ╱
    $$$   ╱    ╲    ╱
    $$$ ╱        ╲╱
    ───────────────────────────────
     JAN FEB MAR APR MAY JUN JUL
"""

_FIREWORKS = [
    """
          .  *  .
        .    *    .
       *  . * .  *
        '   *   '
          . * .
    """,
    """
        . * . * .
      *   . * .   *
     .  *  . .  *  .
      *   . * .   *
        . * . * .
          * . *
    """,
    """
      *  . * . *  .
    .  *  .   .  *  .
   *  . *  . .  * .  *
    .  *  .   .  *  .
      *  . * . *  .
        *  . .  *
          . * .
    """,
    """
          . * .
        *  . .  *
      .  *     *  .
        *  . .  *
          . * .
    """,
]

_SPARKLES = "✦✧★☆⚡💎🔥💰📈🚀🐂💹🏆🎯🎰"

_BANNER = r"""
 ██╗     ██╗   ██╗███╗   ██╗██╗  ██╗
 ██║     ╚██╗ ██╔╝████╗  ██║╚██╗██╔╝
 ██║      ╚████╔╝ ██╔██╗ ██║ ╚███╔╝
 ██║       ╚██╔╝  ██║╚██╗██║ ██╔██╗
 ███████╗   ██║   ██║ ╚████║██╔╝ ██╗
 ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝
"""

_BANNER2 = r"""
 ╔═══════════════════════════════════════════════╗
 ║  LYNX PORTFOLIO — TO THE MOON! 🚀🌕         ║
 ╚═══════════════════════════════════════════════╝
"""

_MOON = r"""
                    *       .        *
           .              *               .
       *          🌕🌕🌕🌕🌕
              🌕🌕🌕🌕🌕🌕🌕🌕          *
     .     🌕🌕🌕🌕🌕🌕🌕🌕🌕🌕
          🌕🌕🌕🌕🌕🌕🌕🌕🌕🌕🌕     .
    *     🌕🌕🌕🌕🌕🌕🌕🌕🌕🌕🌕
           🌕🌕🌕🌕🌕🌕🌕🌕🌕🌕    *
     .       🌕🌕🌕🌕🌕🌕🌕🌕
                  🌕🌕🌕🌕            .
        *                        *
"""


# ---------------------------------------------------------------------------
# Sound synthesis — generate a short chiptune melody as WAV
# ---------------------------------------------------------------------------

def _note_freq(name: str) -> float:
    """Return frequency in Hz for a note name like 'C4', 'A#5'."""
    _NOTES = {
        'C': -9, 'C#': -8, 'Db': -8, 'D': -7, 'D#': -6, 'Eb': -6,
        'E': -5, 'F': -4, 'F#': -3, 'Gb': -3, 'G': -2, 'G#': -1,
        'Ab': -1, 'A': 0, 'A#': 1, 'Bb': 1, 'B': 2,
    }
    if name[-1].isdigit():
        octave = int(name[-1])
        note_name = name[:-1]
    else:
        octave = 4
        note_name = name
    semitone = _NOTES[note_name] + (octave - 4) * 12
    return 440.0 * (2 ** (semitone / 12.0))


def _generate_tone(freq: float, duration: float, sample_rate: int = 22050,
                   volume: float = 0.3, wave_type: str = "square") -> bytes:
    """Generate raw PCM samples for a tone."""
    n_samples = int(sample_rate * duration)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        if wave_type == "square":
            val = volume if math.sin(2 * math.pi * freq * t) >= 0 else -volume
        elif wave_type == "triangle":
            period = 1.0 / freq
            phase = (t % period) / period
            val = volume * (4 * abs(phase - 0.5) - 1)
        elif wave_type == "sawtooth":
            period = 1.0 / freq
            phase = (t % period) / period
            val = volume * (2 * phase - 1)
        else:  # sine
            val = volume * math.sin(2 * math.pi * freq * t)

        # Fade out last 10% to avoid clicks
        fade_start = int(n_samples * 0.9)
        if i > fade_start:
            val *= (n_samples - i) / (n_samples - fade_start)
        # Fade in first 2%
        fade_in_end = int(n_samples * 0.02)
        if i < fade_in_end and fade_in_end > 0:
            val *= i / fade_in_end

        samples.append(int(val * 32767))
    return struct.pack(f"<{len(samples)}h", *samples)


def _generate_melody_wav() -> bytes:
    """Generate a chiptune victory fanfare as WAV bytes."""
    sample_rate = 22050

    # Victory fanfare melody (inspired by classic game victory themes)
    melody = [
        # Intro flourish
        ("C5", 0.10, "square"),
        ("E5", 0.10, "square"),
        ("G5", 0.10, "square"),
        ("C6", 0.20, "square"),
        (None, 0.05, None),     # rest
        ("G5", 0.10, "square"),
        ("C6", 0.35, "square"),
        (None, 0.08, None),

        # Main theme
        ("E5", 0.12, "square"),
        ("E5", 0.12, "square"),
        ("E5", 0.12, "square"),
        (None, 0.04, None),
        ("C5", 0.12, "triangle"),
        ("E5", 0.15, "square"),
        ("G5", 0.30, "square"),
        (None, 0.06, None),
        ("G4", 0.30, "triangle"),
        (None, 0.10, None),

        # Second phrase
        ("C5", 0.15, "square"),
        (None, 0.04, None),
        ("G4", 0.15, "triangle"),
        (None, 0.04, None),
        ("E4", 0.15, "square"),
        (None, 0.06, None),
        ("A4", 0.12, "square"),
        ("B4", 0.12, "square"),
        (None, 0.04, None),
        ("Bb4", 0.08, "triangle"),
        ("A4", 0.15, "square"),
        (None, 0.06, None),

        # Triplet run
        ("G4", 0.10, "square"),
        ("E5", 0.10, "square"),
        ("G5", 0.10, "square"),
        ("A5", 0.15, "square"),
        (None, 0.04, None),
        ("F5", 0.12, "square"),
        ("G5", 0.12, "square"),
        (None, 0.04, None),
        ("E5", 0.15, "square"),
        (None, 0.04, None),
        ("C5", 0.12, "triangle"),
        ("D5", 0.12, "triangle"),
        ("B4", 0.12, "triangle"),
        (None, 0.10, None),

        # Grand finale
        ("G5", 0.08, "square"),
        ("F#5", 0.08, "square"),
        ("F5", 0.08, "square"),
        ("D#5", 0.12, "square"),
        (None, 0.04, None),
        ("E5", 0.12, "square"),
        (None, 0.04, None),
        ("G#4", 0.08, "triangle"),
        ("A4", 0.08, "triangle"),
        ("C5", 0.08, "square"),
        (None, 0.04, None),
        ("A4", 0.10, "triangle"),
        ("C5", 0.10, "square"),
        ("D5", 0.10, "square"),
        (None, 0.06, None),

        # Final chord (arpeggiated)
        ("C5", 0.08, "square"),
        ("E5", 0.08, "square"),
        ("G5", 0.08, "square"),
        ("C6", 0.60, "square"),
    ]

    all_samples = b""
    for note, dur, wtype in melody:
        if note is None:
            # Silence
            n = int(sample_rate * dur)
            all_samples += struct.pack(f"<{n}h", *([0] * n))
        else:
            freq = _note_freq(note)
            all_samples += _generate_tone(freq, dur, sample_rate, 0.25, wtype)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(all_samples)
    return buf.getvalue()


def _play_sound_async():
    """Play the melody in a background thread."""
    def _play():
        wav_data = _generate_melody_wav()
        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            os.write(fd, wav_data)
            os.close(fd)
            for player in ["pw-play", "paplay", "aplay", "ffplay -nodisp -autoexit"]:
                cmd = player.split() + [path]
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=15)
                    break
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    t = threading.Thread(target=_play, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Terminal (CLI / Interactive) easter egg
# ---------------------------------------------------------------------------

def _clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _move_cursor(row: int, col: int):
    sys.stdout.write(f"\033[{row};{col}H")
    sys.stdout.flush()


def _color(text: str, code: int) -> str:
    return f"\033[{code}m{text}\033[0m"


def _rainbow(text: str, offset: int = 0) -> str:
    colors = [31, 33, 32, 36, 34, 35]  # red, yellow, green, cyan, blue, magenta
    out = []
    ci = offset
    for ch in text:
        if ch.strip():
            out.append(f"\033[1;{colors[ci % len(colors)]}m{ch}\033[0m")
            ci += 1
        else:
            out.append(ch)
    return "".join(out)


def _get_terminal_size():
    try:
        cols, rows = os.get_terminal_size()
        return rows, cols
    except OSError:
        return 24, 80


def _center(text: str, width: int) -> str:
    lines = text.split("\n")
    return "\n".join(line.center(width) for line in lines)


def run_terminal_egg():
    """The full terminal easter egg show."""
    rows, cols = _get_terminal_size()
    sound_thread = _play_sound_async()

    _clear_screen()
    sys.stdout.write("\033[?25l")  # hide cursor
    sys.stdout.flush()

    try:
        # Phase 1: Lynx blinking eyes
        for i in range(8):
            _clear_screen()
            frame = _LYNX_FRAMES[i % len(_LYNX_FRAMES)]
            centered = _center(frame, cols)
            _move_cursor(rows // 2 - 3, 1)
            for line in centered.split("\n"):
                print(_color(line, 36))  # cyan
            time.sleep(0.25)

        # Phase 2: Banner reveal with rainbow
        _clear_screen()
        for i in range(6):
            _move_cursor(2, 1)
            for line in _BANNER.split("\n"):
                print(_rainbow(line.center(cols), i))
            time.sleep(0.15)

        time.sleep(0.3)

        # Phase 3: Lynx walks across screen
        _clear_screen()
        _move_cursor(2, 1)
        print(_color(_BANNER2.center(cols), 33))
        for i in range(min(6, (cols - 30) // 8)):
            _move_cursor(6, 1)
            frame = _LYNX_WALK[i % len(_LYNX_WALK)]
            padded = " " * (i * 8) + frame
            for line in padded.split("\n"):
                print(_color(line, 36))
            time.sleep(0.3)

        time.sleep(0.3)

        # Phase 4: Bull market!
        _clear_screen()
        _move_cursor(1, 1)
        bull_centered = _center(_BULL, cols)
        for line in bull_centered.split("\n"):
            print(_color(line, 32))  # green
        _move_cursor(rows // 2 + 5, 1)
        print(_color("    📈 BULL MARKET DETECTED! 📈".center(cols), 32))
        time.sleep(0.8)

        # Phase 5: Chart going up
        _clear_screen()
        chart_centered = _center(_CHART_UP, cols)
        _move_cursor(3, 1)
        for line in chart_centered.split("\n"):
            print(_color(line, 32))
            time.sleep(0.08)
        time.sleep(0.5)

        # Phase 6: Rocket launch
        for i in range(len(_ROCKET)):
            _clear_screen()
            rocket_y = rows - 2 - (i * 4)
            if rocket_y < 1:
                rocket_y = 1
            _move_cursor(rocket_y, 1)
            rocket = _center(_ROCKET[i], cols)
            for line in rocket.split("\n"):
                c = 33 if "~" in line or "|" in line else 37
                print(_color(line, c))
            time.sleep(0.4)

        # Phase 7: To the moon!
        _clear_screen()
        _move_cursor(1, 1)
        moon_centered = _center(_MOON, cols)
        for line in moon_centered.split("\n"):
            print(line)
        _move_cursor(rows // 2 + 4, 1)
        msg = "🚀  TO THE MOON!  🚀"
        print(_color(msg.center(cols), 33))
        time.sleep(0.8)

        # Phase 8: Fireworks
        for i in range(8):
            _clear_screen()
            _move_cursor(1, 1)
            fw = _FIREWORKS[i % len(_FIREWORKS)]
            # Place firework at random-ish position
            xoff = (i * 17 + 5) % (cols - 30)
            centered_fw = "\n".join((" " * xoff) + line for line in fw.split("\n"))
            colors = [31, 33, 32, 36, 34, 35]
            for line in centered_fw.split("\n"):
                print(_color(line, colors[i % len(colors)]))
            _move_cursor(rows - 3, 1)
            sparkle_line = " ".join(
                _SPARKLES[(i + j) % len(_SPARKLES)]
                for j in range(cols // 3)
            )
            print(sparkle_line.center(cols))
            time.sleep(0.25)

        # Phase 9: Big lynx + credits
        _clear_screen()
        _move_cursor(2, 1)
        for line in _LYNX_BIG.split("\n"):
            print(_color(line.center(cols), 36))
        _move_cursor(rows // 2 + 4, 1)
        print(_color("Lynx Portfolio".center(cols), 1))
        print()
        print(_color("Your portfolio is watching. Always.".center(cols), 36))
        print()

        # Phase 10: Final rainbow banner
        _move_cursor(rows - 5, 1)
        for i in range(12):
            _move_cursor(rows - 5, 1)
            final_msg = "★  L Y N X   P O R T F O L I O  ★"
            print(_rainbow(final_msg.center(cols), i))
            time.sleep(0.15)

        time.sleep(1.0)

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h")  # show cursor
        sys.stdout.flush()
        sound_thread.join(timeout=2)
        _clear_screen()


# ---------------------------------------------------------------------------
# GUI (tkinter) easter egg
# ---------------------------------------------------------------------------

def run_gui_egg(parent=None):
    """A tkinter animation easter egg."""
    import tkinter as tk

    sound_thread = _play_sound_async()

    root = tk.Toplevel(parent) if parent else tk.Tk()
    root.title("")
    root.configure(bg="#000000")
    root.attributes("-fullscreen", False)

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w, h = min(sw - 100, 900), min(sh - 100, 700)
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.resizable(False, False)

    canvas = tk.Canvas(root, bg="#000000", highlightthickness=0,
                       width=w, height=h)
    canvas.pack(fill="both", expand=True)

    phase = [0]
    frame_counter = [0]

    # Star field
    import random
    stars = []
    for _ in range(80):
        sx = random.randint(0, w)
        sy = random.randint(0, h)
        size = random.choice([1, 1, 1, 2, 2, 3])
        speed = random.uniform(0.5, 2.5)
        stars.append([sx, sy, size, speed])

    # Colors
    _RAINBOW = ["#FF0000", "#FF8800", "#FFFF00", "#00FF00", "#00FFFF",
                "#0088FF", "#8800FF", "#FF00FF"]

    def _draw_stars():
        for s in stars:
            c = random.choice(["#FFFFFF", "#AAAAAA", "#FFFF88", "#88FFFF"])
            canvas.create_oval(s[0]-s[2], s[1]-s[2], s[0]+s[2], s[1]+s[2],
                               fill=c, outline="")
            s[1] += s[3]
            if s[1] > h:
                s[1] = 0
                s[0] = random.randint(0, w)

    def _draw_text(text, y_pos, size=24, color="#00FFFF", font="Courier"):
        canvas.create_text(w // 2, y_pos, text=text, fill=color,
                           font=(font, size, "bold"), anchor="center")

    def animate():
        canvas.delete("all")
        _draw_stars()
        p = phase[0]
        fc = frame_counter[0]

        if p == 0:
            # Lynx face
            frame_text = _LYNX_FRAMES[fc % len(_LYNX_FRAMES)]
            _draw_text(frame_text, h // 2 - 30, size=16, color="#00FFFF",
                       font="Courier")
            _draw_text("🐱", h // 2 + 80, size=40)
            if fc > 10:
                phase[0] = 1
                frame_counter[0] = 0

        elif p == 1:
            # Banner
            rainbow_idx = fc % len(_RAINBOW)
            _draw_text("L Y N X", h // 3, size=60,
                       color=_RAINBOW[rainbow_idx])
            _draw_text("P O R T F O L I O", h // 3 + 70, size=36,
                       color=_RAINBOW[(rainbow_idx + 3) % len(_RAINBOW)])
            if fc > 15:
                phase[0] = 2
                frame_counter[0] = 0

        elif p == 2:
            # Bull
            _draw_text("📈 BULL MARKET! 📈", h // 3, size=40,
                       color="#00FF00")
            bull_text = _BULL
            _draw_text(bull_text, h // 2 + 20, size=10, color="#00FF00",
                       font="Courier")
            if fc > 12:
                phase[0] = 3
                frame_counter[0] = 0

        elif p == 3:
            # Rocket
            rocket_y = h - fc * 15
            if rocket_y < -100:
                rocket_y = -100
            rocket_text = _ROCKET[min(fc // 4, len(_ROCKET) - 1)]
            _draw_text(rocket_text, rocket_y, size=10,
                       color="#FF8800", font="Courier")
            _draw_text("🚀", rocket_y - 80, size=50)
            if fc > 25:
                phase[0] = 4
                frame_counter[0] = 0

        elif p == 4:
            # Moon
            _draw_text("🌕", h // 3 - 40, size=80)
            _draw_text("TO THE MOON!", h // 2 + 40, size=48,
                       color="#FFD700")
            # Sparkles
            for i in range(8):
                angle = (fc * 0.15 + i * 0.785)
                sx = int(w // 2 + 200 * math.cos(angle))
                sy = int(h // 3 + 200 * math.sin(angle))
                canvas.create_text(sx, sy, text="✦",
                                   fill=_RAINBOW[i % len(_RAINBOW)],
                                   font=("", 20))
            if fc > 20:
                phase[0] = 5
                frame_counter[0] = 0

        elif p == 5:
            # Fireworks
            for i in range(5):
                cx = (i * 180 + fc * 7) % w
                cy = h // 3 + int(50 * math.sin(fc * 0.2 + i))
                color = _RAINBOW[(fc + i) % len(_RAINBOW)]
                for j in range(12):
                    angle = j * (math.pi * 2 / 12) + fc * 0.1
                    r = 30 + fc * 2
                    ex = cx + int(r * math.cos(angle))
                    ey = cy + int(r * math.sin(angle))
                    canvas.create_oval(ex-3, ey-3, ex+3, ey+3,
                                       fill=color, outline="")

            _draw_text("★ LYNX PORTFOLIO ★", h - 100, size=32,
                       color=_RAINBOW[fc % len(_RAINBOW)])
            _draw_text("Your portfolio is watching. Always.", h - 50,
                       size=16, color="#888888")

            if fc > 30:
                phase[0] = 6
                frame_counter[0] = 0

        elif p == 6:
            # Final — big lynx
            _draw_text(_LYNX_BIG, h // 2 - 50, size=12,
                       color=_RAINBOW[fc % len(_RAINBOW)], font="Courier")
            _draw_text("Lynx Portfolio", h // 2 + 100, size=36,
                       color="#00FFFF")
            sparkle_text = " ".join(
                _SPARKLES[(fc + i) % len(_SPARKLES)]
                for i in range(12)
            )
            _draw_text(sparkle_text, h - 60, size=18)
            if fc > 25:
                root.after(1500, root.destroy)
                return

        frame_counter[0] += 1
        root.after(80, animate)

    root.bind("<Escape>", lambda _: root.destroy())
    root.bind("<space>", lambda _: root.destroy())
    root.after(100, animate)

    if parent:
        root.grab_set()
        root.focus_force()
        root.wait_window()
    else:
        root.mainloop()

    sound_thread.join(timeout=2)
