# SPDX-License-Identifier: GPL-2.0-only

# Frontend stuff

from multiprocessing import Process, Queue
import time
import math

from chess_board import (
    BISHOP, BLACK, COLOR_MASK, EMPTY, KING, KNIGHT, QUEEN, ROOK, WHITE,
    bB, bK, bN, bP, bQ, bR,
    create_game_state, gen_legal_moves, get_game_outcome, make_move, undo_move,
    move_end, move_is_ep, move_piece, move_promo, move_start, move_to_san,
    wB, wK, wN, wP, wQ, wR,
)
import chess_engine

BOARD_SIZE = 1024
LOG_PANEL_WIDTH = 336
WINDOW_WIDTH = BOARD_SIZE + LOG_PANEL_WIDTH
WINDOW_HEIGHT = BOARD_SIZE
TILE_SIZE = BOARD_SIZE // 8
FPS = 30
ANIM_SECS = 0.16
DRAG_DELAY_SECS = 0.10

LIGHT_TILE = (255, 255, 255)
DARK_TILE = (245, 220, 247)

SELECTED_TILE = (0, 0, 255, 75)
HOVER_TILE = (0, 0, 255, 40)
MOVE_INDICATOR = (0, 0, 192, 75)
LAST_MOVE_TILE = (106, 106, 255, 75)

HIGHLIGHT_TILE = (235, 100, 80, 255)
ARROW_COLOR = (255, 80, 185, 255)

PROMOTION_CHOICES = (QUEEN, ROOK, BISHOP, KNIGHT)
PIECE_FILENAMES = {
    bR: "bR", bN: "bN", bB: "bB", bQ: "bQ", bK: "bK", bP: "bP",
    wR: "wR", wN: "wN", wB: "wB", wQ: "wQ", wK: "wK", wP: "wP",
}

# Pre-game player selection layout
MENU_PANEL = (132, 220, 760, 584)
WHITE_HUMAN_BTN = (220, 440, 250, 82)
WHITE_AI_BTN = (220, 540, 250, 82)
BLACK_HUMAN_BTN = (554, 440, 250, 82)
BLACK_AI_BTN = (554, 540, 250, 82)
CONFIRM_BTN = (397, 680, 230, 76)

def load_sprites(p):
    sprites = {}
    for piece_code, file_name in PIECE_FILENAMES.items():
        raw = p.image.load(f"pieces/{file_name}.png").convert_alpha()
        sprites[piece_code] = p.transform.scale(raw, (TILE_SIZE, TILE_SIZE))
    return sprites

def load_fonts(p):
    return {
        "log": p.font.SysFont("Arial", 32),
        "menu_title": p.font.SysFont("Arial", 48, bold=True),
        "menu_btn": p.font.SysFont("Arial", 28, bold=True),
        "confirm": p.font.SysFont("Arial", 30, bold=True),
        "banner": p.font.SysFont("Bebas Neue", 68, bold=True),
    }

def sq_to_xy(sq):
    return (sq & 7) * TILE_SIZE, (sq >> 4) * TILE_SIZE

def xy_to_sq(pos):
    col = pos[0] // TILE_SIZE
    row = pos[1] // TILE_SIZE
    if 0 <= col < 8 and 0 <= row < 8:
        return (row << 4) | col
    return None

def is_human_ply(ui):
    return ui["human_white"] if ui["gs"]["white_move"] else ui["human_black"]

def engine_worker(task_q, res_q):
    while True:
        job = task_q.get()
        if job is None:
            break
        job_id, gs, legal_moves = job
        best_move = chess_engine.find_best_move(gs, legal_moves)
        res_q.put((job_id, best_move))

def start_engine(ui):
    if ui["engine_process"] is not None and ui["engine_process"].is_alive():
        return
    task_q = Queue()
    res_q = Queue()
    proc = Process(target=engine_worker, args=(task_q, res_q), daemon=True)
    proc.start()
    ui["engine_process"] = proc
    ui["engine_task_q"] = task_q
    ui["engine_res_q"] = res_q
    ui["engine_busy"] = False

def kill_engine(ui, restart=False):
    proc = ui["engine_process"]
    if proc is not None:
        if proc.is_alive():
            if ui["engine_busy"]:
                proc.terminate()
            else:
                ui["engine_task_q"].put(None)
            proc.join(timeout=0.1)
        ui["engine_process"] = None
        ui["engine_task_q"] = None
        ui["engine_res_q"] = None
        ui["engine_busy"] = False

    if restart:
        start_engine(ui)

def deselect_sq(ui):
    ui["selected_sq"] = None
    ui["selected_moves"] = []
    ui["dragging_sq"] = None
    ui["drag_start_time"] = 0

def select_sq(ui, sq):
    if sq is None:
        deselect_sq(ui)
        return

    ally_mask = WHITE if ui["gs"]["white_move"] else BLACK
    if ui["gs"]["board"][sq] & ally_mask:
        ui["selected_sq"] = sq
        ui["selected_moves"] = [m for m in ui["legal_moves"] if move_start(m) == sq]
    else:
        deselect_sq(ui)

def exec_ply(p, screen, clock, sprites, fonts, ui, move, animate=True):
    gs = ui["gs"]
    snapshot = render_board_snapshot(p, gs["board"], sprites, exclude_sq=move_start(move), highlight_move=move) if animate else None
    make_move(gs, move)
    if animate:
        play_move_animation(p, screen, clock, sprites, fonts, ui, move, snapshot)

    ui["legal_moves"] = gen_legal_moves(gs)
    deselect_sq(ui)
    ui["pending_promo"] = None
    ui["engine_paused"] = False
    ui["log_scroll"] = max_log_scroll(gs, fonts["log"])

def reset_board(ui):
    kill_engine(ui, restart=True)
    ui["gs"] = create_game_state()
    ui["legal_moves"] = gen_legal_moves(ui["gs"])
    deselect_sq(ui)
    ui["pending_promo"] = None
    ui["engine_paused"] = False
    ui["log_scroll"] = 0
    clear_annotations(ui)

def undo_ply(fonts, ui):
    if ui["pending_promo"] is not None:
        ui["pending_promo"] = None
        deselect_sq(ui)
        return

    if not ui["gs"]["move_log"]:
        return

    kill_engine(ui, restart=True)
    undo_move(ui["gs"])
    ui["legal_moves"] = gen_legal_moves(ui["gs"])
    deselect_sq(ui)
    ui["engine_paused"] = not is_human_ply(ui)
    ui["log_scroll"] = max_log_scroll(ui["gs"], fonts["log"])

def handle_event(p, screen, clock, sprites, fonts, ui, event):
    if event.type == p.QUIT:
        ui["running"] = False
        return

    if event.type == p.MOUSEWHEEL and not ui["menu_open"]:
        mx, _ = p.mouse.get_pos()
        if mx >= BOARD_SIZE:
            ui["log_scroll"] -= event.y * 60
        return

    if event.type == p.MOUSEBUTTONDOWN:
        if not ui["menu_open"] and event.button in (4, 5):
            if event.pos[0] >= BOARD_SIZE:
                ui["log_scroll"] += -60 if event.button == 4 else 60
            return

        if event.button == 1:
            on_lmb(p, screen, clock, sprites, fonts, ui, event.pos)
        elif event.button == 3:
            on_rmb(ui, event.pos)
        return

    if event.type == p.MOUSEBUTTONUP:
        if event.button == 1:
            on_lmb_up(p, screen, clock, sprites, fonts, ui, event.pos)
        elif event.button == 3:
            on_rmb_up(ui, event.pos)
        return

    if event.type == p.KEYDOWN and not ui["menu_open"]:
        if event.key == p.K_ESCAPE and ui["pending_promo"] is not None:
            ui["pending_promo"] = None
            deselect_sq(ui)
        elif event.key == p.K_LEFT:
            undo_ply(fonts, ui)
        elif event.key == p.K_SPACE and not is_human_ply(ui):
            ui["engine_paused"] = not ui["engine_paused"]
        elif event.key == p.K_r:
            reset_board(ui)
        elif event.key == p.K_e:
            print(ui["gs"]["board"])

def is_valid_arrow(src, dst):
    if src is None or dst is None or src == dst:
        return False
    dr = abs((dst >> 4) - (src >> 4))
    dc = abs((dst & 7) - (src & 7))
    is_slider = (dr == 0) or (dc == 0) or (dr == dc)
    is_knight = (dr, dc) in ((1, 2), (2, 1))
    return is_slider or is_knight

def on_rmb(ui, pos):
    if ui["menu_open"] or ui["pending_promo"] is not None:
        return
    ui["rmb_start_sq"] = xy_to_sq(pos)

def on_rmb_up(ui, pos):
    start_sq = ui["rmb_start_sq"]
    ui["rmb_start_sq"] = None
    if start_sq is None or ui["menu_open"] or ui["pending_promo"] is not None:
        return

    end_sq = xy_to_sq(pos)
    if end_sq is None:
        return

    if end_sq == start_sq:
        if start_sq in ui["highlights"]:
            ui["highlights"].remove(start_sq)
        else:
            ui["highlights"].add(start_sq)
    elif is_valid_arrow(start_sq, end_sq):
        arrow = (start_sq, end_sq)
        if arrow in ui["arrows"]:
            ui["arrows"].remove(arrow)
        else:
            ui["arrows"].add(arrow)

def on_lmb(p, screen, clock, sprites, fonts, ui, pos):
    if ui["menu_open"]:
        if p.Rect(WHITE_HUMAN_BTN).collidepoint(pos):
            ui["human_white"] = True
        elif p.Rect(WHITE_AI_BTN).collidepoint(pos):
            ui["human_white"] = False

        if p.Rect(BLACK_HUMAN_BTN).collidepoint(pos):
            ui["human_black"] = True
        elif p.Rect(BLACK_AI_BTN).collidepoint(pos):
            ui["human_black"] = False

        if p.Rect(CONFIRM_BTN).collidepoint(pos):
            ui["menu_open"] = False
            ui["engine_paused"] = False
            deselect_sq(ui)
        return

    clear_annotations(ui)

    if ui["pending_promo"] is not None:
        choice = pick_promo_choice(p, pos, ui["pending_promo"])
        if choice is not None:
            src = move_start(ui["pending_promo"])
            dst = move_end(ui["pending_promo"])
            for move in ui["legal_moves"]:
                if move_start(move) == src and move_end(move) == dst and move_promo(move) == choice:
                    exec_ply(p, screen, clock, sprites, fonts, ui, move, animate=True)
                    break
        return

    if get_game_outcome(ui["gs"]) is not None or not is_human_ply(ui):
        return

    clicked_sq = xy_to_sq(pos)
    if clicked_sq is None:
        deselect_sq(ui)
        return

    if ui["selected_sq"] is not None:
        candidates = [m for m in ui["selected_moves"] if move_end(m) == clicked_sq]
        if candidates:
            if move_promo(candidates[0]):
                ui["pending_promo"] = candidates[0]
            else:
                exec_ply(p, screen, clock, sprites, fonts, ui, candidates[0], animate=True)
            return

    select_sq(ui, clicked_sq)
    if ui["selected_sq"] is not None:
        ui["dragging_sq"] = clicked_sq
        ui["drag_start_time"] = time.perf_counter()

def on_lmb_up(p, screen, clock, sprites, fonts, ui, pos):
    was_dragging = is_actively_dragging(ui)
    drag_sq = ui["dragging_sq"]
    ui["dragging_sq"] = None
    ui["drag_start_time"] = 0

    if not was_dragging or drag_sq is None:
        return

    drop_sq = xy_to_sq(pos)
    if drop_sq is None or drop_sq == drag_sq:
        return

    candidates = [m for m in ui["selected_moves"] if move_end(m) == drop_sq]
    if candidates:
        if move_promo(candidates[0]):
            ui["pending_promo"] = candidates[0]
        else:
            exec_ply(p, screen, clock, sprites, fonts, ui, candidates[0], animate=False)

def is_actively_dragging(ui):
    return (
        ui["dragging_sq"] is not None
        and (time.perf_counter() - ui["drag_start_time"]) >= DRAG_DELAY_SECS
    )

def clear_annotations(ui):
    ui["highlights"].clear()
    ui["arrows"].clear()
    ui["rmb_start_sq"] = None

def poll_engine(p, screen, clock, sprites, fonts, ui):
    if ui["menu_open"] or get_game_outcome(ui["gs"]) is not None or is_human_ply(ui) or ui["engine_paused"]:
        return

    if ui["engine_process"] is None or not ui["engine_process"].is_alive():
        start_engine(ui)

    if not ui["engine_busy"]:
        ui["engine_job_id"] += 1
        ui["engine_busy"] = True
        ui["engine_task_q"].put((ui["engine_job_id"], ui["gs"], ui["legal_moves"]))
        return

    if ui["engine_res_q"].empty():
        return
    job_id, chosen = ui["engine_res_q"].get()

    ui["engine_busy"] = False
    if job_id != ui["engine_job_id"]:
        return

    if chosen is None and ui["legal_moves"]:
        chosen = ui["legal_moves"][0]
    if chosen is not None:
        exec_ply(p, screen, clock, sprites, fonts, ui, chosen, animate=True)

# RENDERING

def draw_tiles(p, surface):
    for idx in range(64):
        row, col = divmod(idx, 8)
        color = LIGHT_TILE if (row + col) % 2 == 0 else DARK_TILE
        p.draw.rect(surface, color, (col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE))

def draw_pieces(surface, board, sprites, exclude_sq=None):
    for row in range(8):
        rank_offset = row << 4
        for col in range(8):
            sq = rank_offset | col
            if sq == exclude_sq:
                continue
            piece = board[sq]
            if piece != EMPTY:
                surface.blit(sprites[piece], (col * TILE_SIZE, row * TILE_SIZE))

def render_board_snapshot(p, board, sprites, exclude_sq=None, highlight_move=None):
    snapshot = p.Surface((BOARD_SIZE, BOARD_SIZE))
    draw_tiles(p, snapshot)
    if highlight_move is not None:
        draw_move_squares(p, snapshot, highlight_move)
    draw_pieces(snapshot, board, sprites, exclude_sq=exclude_sq)
    return snapshot

def play_move_animation(p, screen, clock, sprites, fonts, ui, move, snapshot):
    sx, sy = sq_to_xy(move_start(move))
    ex, ey = sq_to_xy(move_end(move))
    sprite = sprites[move_piece(move)]

    t0 = time.perf_counter()
    while True:
        progress = min(1.0, (time.perf_counter() - t0) / ANIM_SECS)
        eased = 1.0 - (1.0 - progress) ** 3
        cx = sx + (ex - sx) * eased
        cy = sy + (ey - sy) * eased

        screen.blit(snapshot, (0, 0))
        screen.blit(sprite, (cx, cy))
        draw_move_log(p, screen, fonts["log"], ui)
        p.display.flip()

        if progress >= 1.0:
            break
        clock.tick(FPS)

def sq_center(sq):
    x, y = sq_to_xy(sq)
    return x + TILE_SIZE // 2, y + TILE_SIZE // 2

def draw_arrow_segment(p, surface, start, end, color, is_head):
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length == 0:
        return

    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    shaft_half = TILE_SIZE * 0.11
    head_len = TILE_SIZE * 0.36
    head_half = TILE_SIZE * 0.25

    if not is_head:
        ext_ex = ex + ux * shaft_half
        ext_ey = ey + uy * shaft_half
        pts = [
            (sx + px * shaft_half, sy + py * shaft_half),
            (sx - px * shaft_half, sy - py * shaft_half),
            (ext_ex - px * shaft_half, ext_ey - py * shaft_half),
            (ext_ex + px * shaft_half, ext_ey + py * shaft_half),
        ]
        p.draw.polygon(surface, color, pts)
        return

    neck_x = ex - ux * head_len
    neck_y = ey - uy * head_len
    pts = [
        (sx + px * shaft_half, sy + py * shaft_half),
        (sx - px * shaft_half, sy - py * shaft_half),
        (neck_x - px * shaft_half, neck_y - py * shaft_half),
        (neck_x - px * head_half, neck_y - py * head_half),
        (ex, ey),
        (neck_x + px * head_half, neck_y + py * head_half),
        (neck_x + px * shaft_half, neck_y + py * shaft_half),
    ]
    p.draw.polygon(surface, color, pts)

def draw_single_arrow(p, surface, src, dst, color):
    sx, sy = sq_center(src)
    ex, ey = sq_center(dst)
    dr = (dst >> 4) - (src >> 4)
    dc = (dst & 7) - (src & 7)

    start_trim = TILE_SIZE * 0.22
    end_trim = TILE_SIZE * 0.18

    if (abs(dr), abs(dc)) in ((1, 2), (2, 1)):
        if abs(dc) == 2:
            elbow = (ex, sy)
            sx += math.copysign(start_trim, dc)
            ey -= math.copysign(end_trim, dr)
        else:
            elbow = (sx, ey)
            sy += math.copysign(start_trim, dr)
            ex -= math.copysign(end_trim, dc)

        draw_arrow_segment(p, surface, (sx, sy), elbow, color, is_head=False)
        draw_arrow_segment(p, surface, elbow, (ex, ey), color, is_head=True)
    else:
        angle = math.atan2(ey - sy, ex - sx)
        ux, uy = math.cos(angle), math.sin(angle)
        start = (sx + ux * start_trim, sy + uy * start_trim)
        end = (ex - ux * end_trim, ey - uy * end_trim)
        draw_arrow_segment(p, surface, start, end, color, is_head=True)

def draw_highlight_annotations(p, screen, ui):
    start_sq = ui["rmb_start_sq"]
    preview_sq = xy_to_sq(p.mouse.get_pos()) if start_sq is not None else None
    has_preview = (
        start_sq is not None
        and preview_sq == start_sq
        and start_sq not in ui["highlights"]
    )

    if not ui["highlights"] and not has_preview:
        return

    overlay = p.Surface((BOARD_SIZE, BOARD_SIZE), p.SRCALPHA)

    for sq in ui["highlights"]:
        x, y = sq_to_xy(sq)
        p.draw.rect(overlay, HIGHLIGHT_TILE, (x, y, TILE_SIZE, TILE_SIZE))

    if has_preview:
        x, y = sq_to_xy(start_sq)
        p.draw.rect(overlay, HIGHLIGHT_TILE, (x, y, TILE_SIZE, TILE_SIZE))

    screen.blit(overlay, (0, 0))


def draw_arrow_annotations(p, screen, ui):
    start_sq = ui["rmb_start_sq"]
    preview_sq = xy_to_sq(p.mouse.get_pos()) if start_sq is not None else None
    has_preview = (
        start_sq is not None
        and is_valid_arrow(start_sq, preview_sq)
        and (start_sq, preview_sq) not in ui["arrows"]
    )

    if not ui["arrows"] and not has_preview:
        return

    overlay = p.Surface((BOARD_SIZE, BOARD_SIZE), p.SRCALPHA)

    for src, dst in ui["arrows"]:
        draw_single_arrow(p, overlay, src, dst, ARROW_COLOR)

    if has_preview:
        draw_single_arrow(p, overlay, start_sq, preview_sq, ARROW_COLOR)

    screen.blit(overlay, (0, 0))

def draw_move_squares(p, surface, move):
    tile = p.Surface((TILE_SIZE, TILE_SIZE), p.SRCALPHA)
    tile.fill(LAST_MOVE_TILE)
    for sq in (move_start(move), move_end(move)):
        surface.blit(tile, sq_to_xy(sq))

def draw_last_move(p, screen, ui):
    if ui["gs"]["move_log"]:
        draw_move_squares(p, screen, ui["gs"]["move_log"][-1])

def draw_move_hints(p, screen, ui):
    selected_sq = ui["selected_sq"]
    if selected_sq is None:
        return

    overlay = p.Surface((BOARD_SIZE, BOARD_SIZE), p.SRCALPHA)

    sx, sy = sq_to_xy(selected_sq)
    p.draw.rect(overlay, SELECTED_TILE, (sx, sy, TILE_SIZE, TILE_SIZE))

    mx, my = p.mouse.get_pos()
    board = ui["gs"]["board"]
    corner = int(TILE_SIZE * 0.23)
    dot_radius = int(TILE_SIZE * 0.13)

    seen_targets = set()
    for move in ui["selected_moves"]:
        target_sq = move_end(move)
        if target_sq in seen_targets:
            continue
        seen_targets.add(target_sq)

        tx, ty = sq_to_xy(target_sq)
        is_hovered = tx <= mx < tx + TILE_SIZE and ty <= my < ty + TILE_SIZE

        if is_hovered:
            p.draw.rect(overlay, HOVER_TILE, (tx, ty, TILE_SIZE, TILE_SIZE))
            continue

        is_capture = board[target_sq] != EMPTY or move_is_ep(move)
        if is_capture:
            right, bottom = tx + TILE_SIZE, ty + TILE_SIZE
            triangles = [
                [(tx, ty), (tx + corner, ty), (tx, ty + corner)],
                [(right, ty), (right - corner, ty), (right, ty + corner)],
                [(tx, bottom), (tx + corner, bottom), (tx, bottom - corner)],
                [(right, bottom), (right - corner, bottom), (right, bottom - corner)],
            ]
            for triangle in triangles:
                p.draw.polygon(overlay, MOVE_INDICATOR, triangle)
        else:
            center = (tx + TILE_SIZE // 2, ty + TILE_SIZE // 2)
            p.draw.circle(overlay, MOVE_INDICATOR, center, dot_radius)

    screen.blit(overlay, (0, 0))

def promo_rects(p, move):
    step = 1 if (move_piece(move) & WHITE) else -1
    dst = move_end(move)
    end_row, end_col = dst >> 4, dst & 7
    return [
        (piece, p.Rect(end_col * TILE_SIZE, (end_row + i * step) * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        for i, piece in enumerate(PROMOTION_CHOICES)
    ]

def pick_promo_choice(p, pos, move):
    for piece, rect in promo_rects(p, move):
        if rect.collidepoint(pos):
            return piece
    return None

def draw_promo_overlay(p, screen, sprites, move):
    dim = p.Surface((BOARD_SIZE, BOARD_SIZE), p.SRCALPHA)
    dim.fill((0, 0, 0, 120))
    screen.blit(dim, (0, 0))

    side = move_piece(move) & COLOR_MASK
    cursor = p.mouse.get_pos()

    for piece, rect in promo_rects(p, move):
        hovered = rect.collidepoint(cursor)
        fill = (92, 145, 112) if hovered else (240, 240, 245)
        border = (190, 235, 198) if hovered else (54, 59, 69)
        p.draw.rect(screen, fill, rect)
        p.draw.rect(screen, border, rect, 3)
        screen.blit(sprites[side | piece], rect)

def draw_toggle_btn(p, screen, font, bounds, caption, active):
    rect = p.Rect(bounds)
    fill = (92, 145, 112) if active else (54, 59, 69)
    border = (190, 235, 198) if active else (125, 130, 140)
    p.draw.rect(screen, fill, rect)
    p.draw.rect(screen, border, rect, 4 if active else 2)
    text = font.render(caption, True, (255, 255, 255))
    screen.blit(text, text.get_rect(center=rect.center))

def draw_menu_overlay(p, screen, sprites, fonts, ui):
    dim = p.Surface((BOARD_SIZE, BOARD_SIZE), p.SRCALPHA)
    dim.fill((0, 0, 0, 155))
    screen.blit(dim, (0, 0))

    panel = p.Rect(MENU_PANEL)
    p.draw.rect(screen, (35, 38, 46), panel)
    p.draw.rect(screen, (205, 205, 215), panel, 3)

    title = fonts["menu_title"].render("Choose players", True, (255, 255, 255))
    screen.blit(title, title.get_rect(center=(BOARD_SIZE // 2, 285)))

    white_icon = p.transform.smoothscale(sprites[wK], (96, 96))
    black_icon = p.transform.smoothscale(sprites[bK], (96, 96))
    screen.blit(white_icon, white_icon.get_rect(center=(345, 365)))
    screen.blit(black_icon, black_icon.get_rect(center=(679, 365)))

    draw_toggle_btn(p, screen, fonts["menu_btn"], WHITE_HUMAN_BTN, "HUMAN", ui["human_white"])
    draw_toggle_btn(p, screen, fonts["menu_btn"], WHITE_AI_BTN, "AI", not ui["human_white"])
    draw_toggle_btn(p, screen, fonts["menu_btn"], BLACK_HUMAN_BTN, "HUMAN", ui["human_black"])
    draw_toggle_btn(p, screen, fonts["menu_btn"], BLACK_AI_BTN, "AI", not ui["human_black"])

    confirm = p.Rect(CONFIRM_BTN)
    p.draw.rect(screen, (75, 105, 155), confirm)
    p.draw.rect(screen, (190, 210, 245), confirm, 3)
    label = fonts["confirm"].render("CONFIRM", True, (255, 255, 255))
    screen.blit(label, label.get_rect(center=confirm.center))

def max_log_scroll(gs, log_font):
    pair_count = (len(gs["move_log"]) + 1) // 2
    padding = 10
    row_height = log_font.get_linesize() + 4
    viewport_h = WINDOW_HEIGHT - 2 * padding
    return max(0, pair_count * row_height - viewport_h)

def draw_move_log(p, screen, log_font, ui):
    panel = p.Rect(BOARD_SIZE, 0, LOG_PANEL_WIDTH, WINDOW_HEIGHT)
    p.draw.rect(screen, (0, 0, 0), panel)

    moves = ui["gs"]["move_log"]
    rows = [
        f"{i // 2 + 1}. {move_to_san(moves[i])}"
        + (f" {move_to_san(moves[i + 1])}" if i + 1 < len(moves) else "")
        for i in range(0, len(moves), 2)
    ]

    padding = 10
    bar_w = 10
    row_h = log_font.get_linesize() + 4
    viewport_h = WINDOW_HEIGHT - 2 * padding
    content_h = len(rows) * row_h
    max_scroll = max(0, content_h - viewport_h)
    ui["log_scroll"] = max(0, min(ui["log_scroll"], max_scroll))

    text_w = LOG_PANEL_WIDTH - 2 * padding - (bar_w + 6 if max_scroll > 0 else 0)
    clip_rect = p.Rect(BOARD_SIZE + padding, padding, text_w, viewport_h)

    prev_clip = screen.get_clip()
    screen.set_clip(clip_rect)
    for idx, line in enumerate(rows):
        surf = log_font.render(line, True, (255, 255, 255))
        screen.blit(surf, (BOARD_SIZE + padding, padding + idx * row_h - ui["log_scroll"]))
    screen.set_clip(prev_clip)

    if max_scroll > 0:
        track = p.Rect(BOARD_SIZE + LOG_PANEL_WIDTH - padding - bar_w, padding, bar_w, viewport_h)
        p.draw.rect(screen, (65, 65, 65), track, border_radius=5)

        thumb_h = max(35, int(viewport_h * viewport_h / content_h))
        thumb_y = padding + int((ui["log_scroll"] / max_scroll) * (viewport_h - thumb_h))
        p.draw.rect(screen, (190, 190, 190), (track.x, thumb_y, bar_w, thumb_h), border_radius=5)

def draw_outcome_banner(p, screen, banner_font, message):
    label = banner_font.render(message, True, (255, 255, 255))
    box_w = max(460, label.get_width() + 80)
    box_h = label.get_height() + 48
    box = p.Rect(0, 0, box_w, box_h)
    box.center = (BOARD_SIZE // 2, BOARD_SIZE // 2)

    card = p.Surface((box_w, box_h), p.SRCALPHA)
    card.fill((28, 31, 38, 225))
    screen.blit(card, box.topleft)
    p.draw.rect(screen, (205, 205, 215), box, 3)
    screen.blit(label, label.get_rect(center=box.center))

def render_frame(p, screen, sprites, fonts, ui):
    dragging = is_actively_dragging(ui)
    draw_tiles(p, screen)
    draw_last_move(p, screen, ui)
    draw_highlight_annotations(p, screen, ui)
    draw_move_hints(p, screen, ui)
    draw_pieces(
        screen,
        ui["gs"]["board"],
        sprites,
        exclude_sq=ui["dragging_sq"] if dragging else None,
    )
    draw_arrow_annotations(p, screen, ui)

    draw_move_log(p, screen, fonts["log"], ui)

    if dragging:
        piece = ui["gs"]["board"][ui["dragging_sq"]]
        if piece != EMPTY:
            mx, my = p.mouse.get_pos()
            mx = max(0, min(mx, BOARD_SIZE))
            my = max(0, min(my, BOARD_SIZE))
            screen.blit(sprites[piece], (mx - TILE_SIZE // 2, my - TILE_SIZE // 2))

    if ui["pending_promo"] is not None:
        draw_promo_overlay(p, screen, sprites, ui["pending_promo"])
    if ui["menu_open"]:
        draw_menu_overlay(p, screen, sprites, fonts, ui)

    outcome = get_game_outcome(ui["gs"])
    if outcome is not None:
        draw_outcome_banner(p, screen, fonts["banner"], outcome)

    p.display.flip()

def main():
    import pygame as p

    p.init()
    screen = p.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    p.display.set_caption("Szachy z Marcinkiem")
    p.display.set_icon(p.image.load("pieces/bK.png"))
    clock = p.time.Clock()

    sprites = load_sprites(p)
    fonts = load_fonts(p)
    gs = create_game_state()

    ui = {
        "gs": gs,
        "legal_moves": gen_legal_moves(gs),
        "human_white": True,
        "human_black": False,
        "menu_open": True,
        "selected_sq": None,
        "dragging_sq": None,
        "drag_start_time": 0.0,
        "selected_moves": [],
        "highlights": set(),
        "arrows": set(),
        "rmb_start_sq": None,
        "pending_promo": None,
        "log_scroll": 0,
        "engine_process": None,
        "engine_task_q": None,
        "engine_res_q": None,
        "engine_busy": False,
        "engine_job_id": 0,
        "engine_paused": False,
        "running": True,
    }

    while ui["running"]:
        for event in p.event.get():
            handle_event(p, screen, clock, sprites, fonts, ui, event)

        poll_engine(p, screen, clock, sprites, fonts, ui)
        render_frame(p, screen, sprites, fonts, ui)
        clock.tick(FPS)

    kill_engine(ui, restart=False)
    p.quit()

if __name__ == "__main__":
    main()
