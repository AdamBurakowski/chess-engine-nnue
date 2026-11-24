# SPDX-License-Identifier: GPL-2.0-only

# Robot doing robot things
from chess_board import (
    PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    WHITE, BLACK, wP, bP, TYPE_MASK,
    move_start, move_end, move_piece, move_captured,
    move_promo, move_is_castle, is_square_attacked,
)
import time
import random

nodes = 0

# Piece-Square Tables from Tomasz Michniewski's Simplified Evaluation Function
piece_value = [0, 100, 320, 330, 500, 900, 0]

white_pawn_pst = (
     0,   0,   0,   0,   0,   0,   0,   0,
    50,  50,  50,  50,  50,  50,  50,  50,
    10,  10,  20,  30,  30,  20,  10,  10,
     5,   5,  10,  25,  25,  10,   5,   5,
     0,   0,   0,  20,  20,   0,   0,   0,
     5,  -5, -10,   0,   0, -10,  -5,   5,
     5,  10,  10, -20, -20,  10,  10,   5,
     0,   0,   0,   0,   0,   0,   0,   0,
)

white_knight_pst = (
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20,   0,   0,   0,   0, -20, -40,
    -30,   0,  10,  15,  15,  10,   0, -30,
    -30,   5,  15,  20,  20,  15,   5, -30,
    -30,   0,  15,  20,  20,  15,   0, -30,
    -30,   5,  10,  15,  15,  10,   5, -30,
    -40, -20,   0,   5,   5,   0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
)

white_bishop_pst = (
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,  10,  10,   5,   0, -10,
    -10,   5,   5,  10,  10,   5,   5, -10,
    -10,   0,  10,  10,  10,  10,   0, -10,
    -10,  10,  10,  10,  10,  10,  10, -10,
    -10,   5,   0,   0,   0,   0,   5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
)

white_rook_pst = (
     0,   0,   0,   0,   0,   0,   0,   0,
     5,  10,  10,  10,  10,  10,  10,   5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
     0,   0,   0,   5,   5,   0,   0,   0,
)

white_queen_pst = (
    -20, -10, -10,  -5,  -5, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,   5,   5,   5,   0, -10,
     -5,   0,   5,   5,   5,   5,   0,  -5,
      0,   0,   5,   5,   5,   5,   0,  -5,
    -10,   5,   5,   5,   5,   5,   0, -10,
    -10,   0,   5,   0,   0,   0,   0, -10,
    -20, -10, -10,  -5,  -5, -10, -10, -20,
)

white_king_mg_pst = (
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
     20,  20,   0,   0,   0,   0,  20,  20,
     20,  30,  10,   0,   0,  10,  30,  20,
)

white_king_eg_pst = (
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10,   0,   0, -10, -20, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -30,   0,   0,   0,   0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
)

def to_0x88_pst(pst_64, flip=False):
    pst = [0] * 128
    for sq64, val in enumerate(pst_64):
        r, c = divmod(sq64, 8)
        if flip:
            r = 7 - r
        pst[(r << 4) | c] = val
    return tuple(pst)

piece_position_scores = [None] * 23

pst_definitions = (
    (PAWN,   white_pawn_pst),
    (KNIGHT, white_knight_pst),
    (BISHOP, white_bishop_pst),
    (ROOK,   white_rook_pst),
    (QUEEN,  white_queen_pst),
    (KING,   white_king_mg_pst),
)

for ptype, grid_64 in pst_definitions:
    piece_position_scores[WHITE | ptype] = to_0x88_pst(grid_64, flip=False)
    piece_position_scores[BLACK | ptype] = to_0x88_pst(grid_64, flip=True)

king_eg_position_scores = [None] * 23
king_eg_position_scores[WHITE | KING] = to_0x88_pst(white_king_eg_pst, flip=False)
king_eg_position_scores[BLACK | KING] = to_0x88_pst(white_king_eg_pst, flip=True)

ENDGAME_MATERIAL_THRESHOLD = 2000

CHECKMATE = 1_000_000
DEPTH = 4
MAX_Q_DEPTH = 8  # Cap quiescence

EXACT = 0
LOWER_BOUND = 1
UPPER_BOUND = 2

TT_MASK = (1 << 20) - 1
transposition_table = {}

def get_search_key(gs):
    return gs.get_search_key()

def score_to_tt(score, ply):
    if score > CHECKMATE - 1000:
        return score + ply
    if score < -CHECKMATE + 1000:
        return score - ply
    return score


def score_from_tt(score, ply):
    if score > CHECKMATE - 1000:
        return score - ply
    if score < -CHECKMATE + 1000:
        return score + ply
    return score

def store_tt_entry(key, depth, score, flag, best_move, ply):
    old_entry = transposition_table.get(key)

    if old_entry is not None:
        if old_entry["depth"] > depth:
            return
        if (
            old_entry["depth"] == depth
            and old_entry["flag"] == EXACT
            and flag != EXACT
        ):
            return

    if len(transposition_table) > TT_MASK and key not in transposition_table:
        transposition_table.pop(next(iter(transposition_table)))

    transposition_table[key] = {
        "depth": depth,
        "score": score_to_tt(score, ply),
        "flag": flag,
        "best_move": best_move,
    }

def score_moves(moves, tt_move=None, pv_move=None):
    scores = []
    for move in moves:
        if move == tt_move:
            scores.append(2_000_000)
        elif move == pv_move:
            scores.append(1_500_000)
        else:
            scores.append(move_priority(move))
    return scores

def pick_next_move(moves, scores, start_idx):
    best_idx = start_idx
    best_score = scores[start_idx]
    for i in range(start_idx + 1, len(moves)):
        if scores[i] > best_score:
            best_score = scores[i]
            best_idx = i

    moves[start_idx], moves[best_idx] = moves[best_idx], moves[start_idx]
    scores[start_idx], scores[best_idx] = scores[best_idx], scores[start_idx]
    return moves[start_idx]

def find_best_move(gs, legal_moves=None, return_queue=None):
    global next_move, nodes, current_root_depth
    nodes = 0

    root_moves = list(legal_moves) if legal_moves is not None else gs.gen_pseudo_legal_moves()
    if not root_moves:
        return None

    next_move = root_moves[0]
    start = time.perf_counter()
    color_multiplier = 1 if gs.white_move else -1

    for depth in range(1, DEPTH + 1):
        current_root_depth = depth
        previous_nodes = nodes
        previous_best_move = next_move

        negamax(
            gs,
            depth,
            -CHECKMATE,
            CHECKMATE,
            color_multiplier,
            ply=0,
            pv_move=previous_best_move,
            root_moves=root_moves,
        )

        print(f"Depth {depth}: {nodes - previous_nodes:,} nodes")

    elapsed = time.perf_counter() - start
    print(f"Nodes: {nodes:,} | Time: {elapsed:.3f}s | NPS: {nodes / elapsed:,.0f}")
    if return_queue is not None:
        return_queue.put(next_move)
    return next_move

def negamax(
    gs, depth, alpha, beta, color_multiplier,
    ply=0, pv_move=None, root_moves=None
):
    global next_move, nodes
    nodes += 1

    original_alpha = alpha
    original_beta = beta

    if (ply > 0 and gs.repetitionCounts.get(gs.zobristHash, 0) >= 2) or gs.half_move_clock >= 100:
        return 0

    position_key = get_search_key(gs)
    tt_entry = transposition_table.get(position_key)
    tt_move = tt_entry["best_move"] if tt_entry is not None else None

    if tt_entry is not None and ply > 0 and tt_entry["depth"] >= depth:
        tt_score = score_from_tt(tt_entry["score"], ply)
        flag = tt_entry["flag"]

        if tt_entry["flag"] == EXACT:
            return tt_score
        elif tt_entry["flag"] == LOWER_BOUND:
            alpha = max(alpha, tt_score)
        elif tt_entry["flag"] == UPPER_BOUND:
            beta = min(beta, tt_score)

        if alpha >= beta:
            return tt_score

    moves = list(root_moves) if root_moves is not None else gs.gen_pseudo_legal_moves()

    if depth == 0:
        return quiescence(
            gs,
            alpha,
            beta,
            color_multiplier,
            ply=ply,
            q_depth=0
        )

    move_scores = score_moves(moves, tt_move=tt_move, pv_move=pv_move)

    max_score = -CHECKMATE
    best_move = None
    legal_moves_searched = 0

    for i in range(len(moves)):
        move = pick_next_move(moves, move_scores, i)

        if not gs.make_move(move):
            continue
        legal_moves_searched += 1

        score = -negamax(
            gs,
            depth - 1,
            -beta,
            -alpha,
            -color_multiplier,
            ply=ply + 1,
        )

        gs.undo_move()

        if score > max_score:
            max_score = score
            best_move = move
            if ply == 0:
                next_move = move

        alpha = max(alpha, max_score)
        if alpha >= beta:
            break

    if legal_moves_searched == 0:
        king_sq = gs.wk_pos if gs.white_move else gs.bk_pos
        enemy_color = BLACK if gs.white_move else WHITE
        if is_square_attacked(gs.board, king_sq, enemy_color):
            return -(CHECKMATE - ply)
        return 0

    if max_score <= original_alpha:
        flag = UPPER_BOUND
    elif max_score >= original_beta:
        flag = LOWER_BOUND
    else:
        flag = EXACT

    store_tt_entry(position_key, depth, max_score, flag, best_move, ply)
    return max_score

def move_priority(move):
    score = 0
    captured = move_captured(move)
    piece_moved = move_piece(move)
    promo = move_promo(move)

    if captured:
        victim = piece_value[captured & TYPE_MASK]
        attacker = piece_value[piece_moved & TYPE_MASK]
        score += 100 * victim - attacker
    if promo:
        if promo == QUEEN:
            score += 900
        elif promo == KNIGHT:
            score += 300
        else:
            score += 100
    if not captured and not promo:
        piece_type = piece_moved & TYPE_MASK
        if piece_type != KING:
            pst = piece_position_scores[piece_moved]
            score += pst[move_end(move)] - pst[move_start(move)]
        if move_is_castle(move):  # Reward AI for castling
            score += 15

    return score

def quiescence(gs, alpha, beta, color_multiplier, ply=0, q_depth=0):
    global nodes
    nodes += 1

    if (ply > 0 and gs.repetitionCounts.get(gs.zobristHash, 0) >= 2) or gs.half_move_clock >= 100:
        return 0

    king_sq = gs.wk_pos if gs.white_move else gs.bk_pos
    enemy_color = BLACK if gs.white_move else WHITE
    in_check = is_square_attacked(gs.board, king_sq, enemy_color)

    if not in_check:
        stand_pat = color_multiplier * score_board(gs)

        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat
        if q_depth >= MAX_Q_DEPTH:
            return stand_pat

        moves = [
            m for m in gs.gen_pseudo_legal_moves()
            if move_captured(m) or move_promo(m)
        ]
    else:
        # Must search evasions when in check to avoid missing checkmate at MAX_Q_DEPTH
        moves = gs.gen_pseudo_legal_moves()

    scores = [move_priority(m) for m in moves]
    legal_moves_searched = 0

    for i in range(len(moves)):
        move = pick_next_move(moves, scores, i)

        # Delta pruning: skip captures that cannot possibly raise alpha
        if not in_check and not move_promo(move):
            captured_val = piece_value[move_captured(move) & TYPE_MASK]
            if stand_pat + captured_val + 150 < alpha:
                continue

        if not gs.make_move(move):
            continue
        legal_moves_searched += 1

        score = -quiescence(
            gs,
            -beta,
            -alpha,
            -color_multiplier,
            ply + 1,
            q_depth + 1
        )

        gs.undo_move()

        if score >= beta:
            return beta
        if score > alpha:
            alpha = score

    if in_check and legal_moves_searched == 0:
        return -(CHECKMATE - ply)

    return alpha

def score_board(gs):
    score = 0
    non_pawn_material = 0

    for sq in gs.white_pieces:
        piece = gs.board[sq]
        piece_type = piece & TYPE_MASK
        if piece_type != KING:
            val = piece_value[piece_type]
            score += val + piece_position_scores[piece][sq]
            if piece_type != PAWN:
                    non_pawn_material += val

    for sq in gs.black_pieces:
        piece = gs.board[sq]
        piece_type = piece & TYPE_MASK
        if piece_type != KING:
            val = piece_value[piece_type]
            score -= val + piece_position_scores[piece][sq]
            if piece_type != PAWN:
                    non_pawn_material += val

    mg_phase = min(non_pawn_material, 6400) / 6400.0
    eg_phase = 1.0 - mg_phase

    wk_score = (
        mg_phase * piece_position_scores[WHITE | KING][gs.wk_pos]
        + eg_phase * king_eg_position_scores[WHITE | KING][gs.wk_pos]
    )
    bk_score = (
        mg_phase * piece_position_scores[BLACK | KING][gs.bk_pos]
        + eg_phase * king_eg_position_scores[BLACK | KING][gs.bk_pos]
    )
    score += int(wk_score - bk_score)

    return score
