# SPDX-License-Identifier: GPL-2.0-only

# Backend Stuff
import random

# Deterministic keys: the same program run always uses the same Zobrist table.
zobrist_rng = random.Random(0xC0FFEE)

EMPTY = 0
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6
WHITE, BLACK = 8, 16
TYPE_MASK = 7
COLOR_MASK = 24

wP, wN, wB, wR, wQ, wK = WHITE | PAWN, WHITE | KNIGHT, WHITE | BISHOP, WHITE | ROOK, WHITE | QUEEN, WHITE | KING
bP, bN, bB, bR, bQ, bK = BLACK | PAWN, BLACK | KNIGHT, BLACK | BISHOP, BLACK | ROOK, BLACK | QUEEN, BLACK | KING

PIECES = (wP, wR, wN, wB, wQ, wK, bP, bR, bN, bB, bQ, bK)

ZOBRIST_PIECES = [
    [zobrist_rng.getrandbits(64) for _ in range(128)] if p in PIECES else [0] * 128 for p in range(23)]
ZOBRIST_SIDE = zobrist_rng.getrandbits(64)
ZOBRIST_CASTLING = [zobrist_rng.getrandbits(64) for _ in range(16)]
ZOBRIST_EP = [zobrist_rng.getrandbits(64) for _ in range(8)]

DIRECTIONS = (-16, -1, 16, 1, -17, -15, 15, 17)
ROOK_DIRECTIONS = (-16, -1, 16, 1)
BISHOP_DIRECTIONS = (-17, -15, 15, 17)
KNIGHT_OFFSETS = (-33, -31, -18, -14, 14, 18, 31, 33)
KING_OFFSETS = (-17, -16, -15, -1, 1, 15, 16, 17)

WKS = 1  # 0001
BKS = 2  # 0010
WQS = 4  # 0100
BQS = 8  # 1000
CASTLING_RIGHTS = WKS | BKS | WQS | BQS

def repetition_token(position_hash, count):
    """
    Deterministic 64-bit token for a position occurring once or twice.

    Counts above two are deliberately treated as two, matching the
    previous min(count, 2) implementation.
    """
    x = (position_hash ^ (count * 0x9E3779B97F4A7C15)) & 0xFFFFFFFFFFFFFFFF

    x ^= x >> 30
    x = (x * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 27
    x = (x * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 31

    return x


def create_game_state():
    board = [
        bR, bN, bB, bQ, bK, bB, bN, bR,  0, 0, 0, 0, 0, 0, 0, 0,
        bP, bP, bP, bP, bP, bP, bP, bP,  0, 0, 0, 0, 0, 0, 0, 0,
         0,  0,  0,  0,  0,  0,  0,  0,  0, 0, 0, 0, 0, 0, 0, 0,
         0,  0,  0,  0,  0,  0,  0,  0,  0, 0, 0, 0, 0, 0, 0, 0,
         0,  0,  0,  0,  0,  0,  0,  0,  0, 0, 0, 0, 0, 0, 0, 0,
         0,  0,  0,  0,  0,  0,  0,  0,  0, 0, 0, 0, 0, 0, 0, 0,
        wP, wP, wP, wP, wP, wP, wP, wP,  0, 0, 0, 0, 0, 0, 0, 0,
        wR, wN, wB, wQ, wK, wB, wN, wR,  0, 0, 0, 0, 0, 0, 0, 0]

    gs = {
        "board": board,
        "white_pieces": {
            (row << 4) | col
            for row in range(8)
            for col in range(8)
            if board[(row << 4) | col] & WHITE
        },
        "black_pieces": {
            (row << 4) | col
            for row in range(8)
            for col in range(8)
            if board[(row << 4) | col] & BLACK
        },
        "white_move": True,
        "move_log": [],
        "wk_pos": 0x74,
        "bk_pos": 0x04,
        "checkmate": False,
        "stalemate": False,
        "in_check": False,
        "en_passant_possible": -1,
        "en_passant_possible_log": [-1],
        "castling_rights": CASTLING_RIGHTS,
        "castling_rights_log": [CASTLING_RIGHTS],
        "state_log": [],
        "half_move_clock": 0,
        "zobrist_hash": 0,
        "position_history": [],
        "repetition_counts": {},
        "repetition_signature": 0,
    }

    # Zobrist Hash
    zobrist_hash = compute_zobrist_hash(gs)
    gs["zobrist_hash"] = zobrist_hash
    gs["position_history"] = [zobrist_hash]
    gs["repetition_counts"] = {zobrist_hash: 1}
    gs["repetition_signature"] = repetition_token(zobrist_hash, 1)
    return gs


def verify_zobrist_hash(gs):
    calculated = compute_zobrist_hash(gs)

    if calculated != gs["zobrist_hash"]:
        raise AssertionError(
            f"Zobrist mismatch: "
            f"stored={gs['zobrist_hash']:#018x}, "
            f"calculated={calculated:#018x}"
        )


def compute_zobrist_hash(gs):
    """
    Full recomputation. Used for initialization and debugging,
    NOT during normal search.
    """
    board = gs["board"]
    h = 0
    for row in range(8):
        for col in range(8):
            sq = (row << 4) | col
            piece = board[sq]
            if piece:
                h ^= ZOBRIST_PIECES[piece][sq]
    if not gs["white_move"]:
        h ^= ZOBRIST_SIDE
    h ^= ZOBRIST_CASTLING[gs["castling_rights"]]
    if gs["en_passant_possible"] != -1:
        h ^= ZOBRIST_EP[gs["en_passant_possible"] & 7]
    return h


def get_position_key(gs):
    return gs["zobrist_hash"]


def get_search_key(gs):
    return (
        gs["zobrist_hash"],
        gs["repetition_signature"],
        min(gs["half_move_clock"], 100),
    )


def is_threefold_repetition(gs):
    return gs["repetition_counts"].get(gs["zobrist_hash"], 0) >= 3


def update_repetition_history(gs, position_hash):
    rep_counts = gs["repetition_counts"]
    old_count = rep_counts.get(position_hash, 0)
    new_count = old_count + 1
    if old_count:
        gs["repetition_signature"] ^= repetition_token(
            position_hash, min(old_count, 2)
        )
    gs["repetition_signature"] ^= repetition_token(
        position_hash, min(new_count, 2)
    )
    rep_counts[position_hash] = new_count


def get_game_outcome(gs):
    if gs["checkmate"]:
        return "Black wins by checkmate" if gs["white_move"] else "White wins by checkmate"
    if gs["stalemate"]:
        return "Stalemate"
    if is_threefold_repetition(gs):
        return "Draw by threefold repetition"
    if gs["half_move_clock"] >= 100:
        return "Draw by fifty-move rule"
    return None


def make_move(gs, move):
    board = gs["board"]
    gs["state_log"].append((
        gs["zobrist_hash"],
        gs["repetition_signature"],
        gs["half_move_clock"],
    ))

    old_castling_rights = gs["castling_rights"]
    old_enpassant = gs["en_passant_possible"]
    old_white_move = gs["white_move"]

    start_sq = move & 0x7F
    end_sq = (move >> 7) & 0x7F
    piece_moved = (move >> 14) & 0x1F
    piece_captured = (move >> 19) & 0x1F
    promo = (move >> 24) & 0x7
    is_ep = (move >> 27) & 1
    is_castle = (move >> 28) & 1

    changed_squares = {start_sq, end_sq}

    if is_ep:
        changed_squares.add((start_sq & 0x70) | (end_sq & 7))

    if is_castle:
        if end_sq - start_sq == 2:
            changed_squares.add(end_sq + 1)
            changed_squares.add(end_sq - 1)
        else:
            changed_squares.add(end_sq - 2)
            changed_squares.add(end_sq + 1)

    old_square_contents = {
        square: board[square] for square in changed_squares
    }

    # MOVE LOGIC
    board[start_sq] = EMPTY
    board[end_sq] = piece_moved

    moving_pieces = gs["white_pieces"] if piece_moved & WHITE else gs["black_pieces"]
    moving_pieces.remove(start_sq)
    moving_pieces.add(end_sq)

    if piece_captured and not is_ep:
        captured_pieces = gs["white_pieces"] if piece_captured & WHITE else gs["black_pieces"]
        captured_pieces.remove(end_sq)

    gs["move_log"].append(move)

    if (piece_moved & TYPE_MASK) == PAWN or piece_captured:
        gs["half_move_clock"] = 0
    else:
        gs["half_move_clock"] += 1

    gs["white_move"] = not gs["white_move"]

    if piece_moved == wK:
        gs["wk_pos"] = end_sq
    elif piece_moved == bK:
        gs["bk_pos"] = end_sq

    if promo:
        board[end_sq] = (piece_moved & COLOR_MASK) | promo

    # En passant
    if is_ep:
        ep_cp_sq = (start_sq & 0x70) | (end_sq & 7)
        board[ep_cp_sq] = EMPTY
        captured_pieces = gs["white_pieces"] if piece_captured & WHITE else gs["black_pieces"]
        captured_pieces.remove(ep_cp_sq)

    # Update en passant target
    if (piece_moved & TYPE_MASK) == PAWN and abs(start_sq - end_sq) == 32:
        gs["en_passant_possible"] = (start_sq + end_sq) >> 1
    else:
        gs["en_passant_possible"] = -1

    gs["en_passant_possible_log"].append(gs["en_passant_possible"])

    if is_castle:
        if end_sq - start_sq == 2:
            # Kingside
            rook_start, rook_end = end_sq + 1, end_sq - 1
        else:
            # Queenside
            rook_start, rook_end = end_sq - 2, end_sq + 1

        board[rook_end] = board[rook_start]
        board[rook_start] = EMPTY
        moving_pieces.remove(rook_start)
        moving_pieces.add(rook_end)

    # Update castling rights
    update_castling_rights(gs, move)
    gs["castling_rights_log"].append(gs["castling_rights"])

    # ZOBRIST HASH UPDATE
    zobrist = gs["zobrist_hash"]
    zobrist ^= ZOBRIST_CASTLING[old_castling_rights]
    if old_enpassant != -1:
        zobrist ^= ZOBRIST_EP[old_enpassant & 7]
    if not old_white_move:
        zobrist ^= ZOBRIST_SIDE

    for sq, old_piece in old_square_contents.items():
        zobrist ^= ZOBRIST_PIECES[old_piece][sq]
        zobrist ^= ZOBRIST_PIECES[board[sq]][sq]

    zobrist ^= ZOBRIST_CASTLING[gs["castling_rights"]]
    if gs["en_passant_possible"] != -1:
        zobrist ^= ZOBRIST_EP[gs["en_passant_possible"] & 7]
    if not gs["white_move"]:
        zobrist ^= ZOBRIST_SIDE

    gs["zobrist_hash"] = zobrist
    gs["position_history"].append(zobrist)
    update_repetition_history(gs, zobrist)

    if gs["white_move"]:
        moved_king_sq = gs["bk_pos"]
        opponent_color = WHITE
    else:
        moved_king_sq = gs["wk_pos"]
        opponent_color = BLACK

    if is_square_attacked(board, moved_king_sq, opponent_color):
        undo_move(gs)
        return False

    return True


def update_castling_rights(gs, move):
    start_sq = move & 0x7F
    end_sq = (move >> 7) & 0x7F
    piece_moved = (move >> 14) & 0x1F
    piece_captured = (move >> 19) & 0x1F

    # If the king moves
    if piece_moved == wK:
        gs["castling_rights"] &= ~(WKS | WQS)
    elif piece_moved == bK:
        gs["castling_rights"] &= ~(BKS | BQS)
    # If a rook moves from its original square
    elif piece_moved == wR:
        if start_sq == 0x70:
            gs["castling_rights"] &= ~WQS
        elif start_sq == 0x77:
            gs["castling_rights"] &= ~WKS
    elif piece_moved == bR:
        if start_sq == 0x00:
            gs["castling_rights"] &= ~BQS
        elif start_sq == 0x07:
            gs["castling_rights"] &= ~BKS
    # If a rook is captured on its original square
    if piece_captured == wR:
        if end_sq == 0x70:
            gs["castling_rights"] &= ~WQS
        elif end_sq == 0x77:
            gs["castling_rights"] &= ~WKS
    elif piece_captured == bR:
        if end_sq == 0x00:
            gs["castling_rights"] &= ~BQS
        elif end_sq == 0x07:
            gs["castling_rights"] &= ~BKS


def undo_move(gs):
    if gs["move_log"]:
        board = gs["board"]
        move = gs["move_log"].pop()
        prev_hash, prev_rep_sig, prev_half_move = gs["state_log"].pop()
        current_hash = gs["zobrist_hash"]
        rep_counts = gs["repetition_counts"]
        count = rep_counts[current_hash]

        if count == 1:
            del rep_counts[current_hash]
        else:
            rep_counts[current_hash] = count - 1

        gs["position_history"].pop()
        gs["half_move_clock"] = prev_half_move

        start_sq = move & 0x7F
        end_sq = (move >> 7) & 0x7F
        piece_moved = (move >> 14) & 0x1F
        piece_captured = (move >> 19) & 0x1F
        is_ep = (move >> 27) & 1
        is_castle = (move >> 28) & 1

        board[start_sq] = piece_moved
        board[end_sq] = piece_captured

        # Restore piece position sets
        moving_pieces = gs["white_pieces"] if piece_moved & WHITE else gs["black_pieces"]
        moving_pieces.remove(end_sq)
        moving_pieces.add(start_sq)

        # Restore captured piece
        if piece_captured and not is_ep:
            captured_pieces = gs["white_pieces"] if piece_captured & WHITE else gs["black_pieces"]
            captured_pieces.add(end_sq)

        gs["white_move"] = not gs["white_move"]
        if piece_moved == wK:
            gs["wk_pos"] = start_sq
        elif piece_moved == bK:
            gs["bk_pos"] = start_sq

        # Undo en passant move
        if is_ep:
            ep_cp_sq = (start_sq & 0x70) | (end_sq & 7)
            board[end_sq] = EMPTY
            board[ep_cp_sq] = piece_captured
            captured_pieces = gs["white_pieces"] if piece_captured & WHITE else gs["black_pieces"]
            captured_pieces.add(ep_cp_sq)

        gs["en_passant_possible_log"].pop()
        gs["en_passant_possible"] = gs["en_passant_possible_log"][-1]

        # Undo castling rights
        gs["castling_rights_log"].pop()
        gs["castling_rights"] = gs["castling_rights_log"][-1]

        # Undo castling move
        if is_castle:
            if end_sq - start_sq == 2:
                rook_start, rook_end = end_sq - 1, end_sq + 1
            else:
                rook_start, rook_end = end_sq + 1, end_sq - 2
            board[rook_end] = board[rook_start]
            board[rook_start] = EMPTY
            moving_pieces.remove(rook_start)
            moving_pieces.add(rook_end)

        gs["zobrist_hash"] = prev_hash
        gs["repetition_signature"] = prev_rep_sig

    gs["checkmate"] = False
    gs["stalemate"] = False


def gen_pseudo_legal_moves(gs):
    moves = []
    board = gs["board"]
    white_move = gs["white_move"]
    if white_move:
        ally_color, pieces, king_sq = WHITE, gs["white_pieces"], gs["wk_pos"]
    else:
        ally_color, pieces, king_sq = BLACK, gs["black_pieces"], gs["bk_pos"]

    for sq in pieces:
        ptype = board[sq] & TYPE_MASK
        if ptype == PAWN:
            gen_pawn_moves(board, sq, white_move, gs["en_passant_possible"], moves)
        elif ptype == KNIGHT:
            gen_step_moves(board, sq, KNIGHT_OFFSETS, ally_color, moves)
        elif ptype == BISHOP:
            gen_slider_moves(board, sq, BISHOP_DIRECTIONS, ally_color, moves)
        elif ptype == ROOK:
            gen_slider_moves(board, sq, ROOK_DIRECTIONS, ally_color, moves)
        elif ptype == QUEEN:
            gen_slider_moves(board, sq, DIRECTIONS, ally_color, moves)
        elif ptype == KING:
            gen_step_moves(board, sq, KING_OFFSETS, ally_color, moves)

    gen_castle_moves(board, king_sq, white_move, gs["castling_rights"], moves)
    return moves


def gen_legal_moves(gs):
    white_move = gs["white_move"]
    enemy_color = BLACK if white_move else WHITE
    king_sq = gs["wk_pos"] if white_move else gs["bk_pos"]
    gs["in_check"] = is_square_attacked(gs["board"], king_sq, enemy_color)

    legal_moves = []
    for move in gen_pseudo_legal_moves(gs):
        if make_move(gs, move):
            undo_move(gs)
            legal_moves.append(move)

    gs["checkmate"] = gs["in_check"] and not legal_moves
    gs["stalemate"] = not gs["in_check"] and not legal_moves
    return legal_moves


def is_square_attacked(board, sq, by_color):
    # Pawn attacks
    pawn_src_step = 16 if by_color == WHITE else -16
    enemy_pawn = by_color | PAWN
    for dc in (-1, 1):
        target = sq + pawn_src_step + dc
        if not (target & 0x88) and board[target] == enemy_pawn:
            return True

    # Knight attacks
    enemy_knight = by_color | KNIGHT
    for offset in KNIGHT_OFFSETS:
        target = sq + offset
        if not (target & 0x88) and board[target] == enemy_knight:
            return True

    # King attacks
    enemy_king = by_color | KING
    for offset in KING_OFFSETS:
        target = sq + offset
        if not (target & 0x88) and board[target] == enemy_king:
            return True

    # Orthogonal sliders
    for d in ROOK_DIRECTIONS:
        target = sq + d
        while not (target & 0x88):
            piece = board[target]
            if piece:
                if (piece & by_color) and (piece & TYPE_MASK) in (ROOK, QUEEN):
                    return True
                break
            target += d

    # Diagonal sliders
    for d in BISHOP_DIRECTIONS:
        target = sq + d
        while not (target & 0x88):
            piece = board[target]
            if piece:
                if (piece & by_color) and (piece & TYPE_MASK) in (BISHOP, QUEEN):
                    return True
                break
            target += d

    return False


def add_pawn_move(start_sq, end_sq, pawn, captured, moves):
    end_rank = end_sq >> 4
    if end_rank == 0 or end_rank == 7:
        for promo in (QUEEN, ROOK, BISHOP, KNIGHT):
            moves.append(encode_move(start_sq, end_sq, pawn, captured, promo=promo))
    else:
        moves.append(encode_move(start_sq, end_sq, pawn, captured))


def gen_pawn_moves(board, sq, white_move, ep_sq, moves):
    """Shared generator for Pawns."""
    if white_move:
        step, start_rank, enemy_color = -16, 6, BLACK
    else:
        step, start_rank, enemy_color = 16, 1, WHITE

    pawn = board[sq]
    one_step = sq + step
    if not board[one_step]:
        add_pawn_move(sq, one_step, pawn, EMPTY, moves)
        two_step = sq + (step << 1)
        if (sq >> 4) == start_rank and not board[two_step]:
            moves.append(encode_move(sq, two_step, pawn))

    for dc in (-1, 1):
        target = sq + step + dc
        if target & 0x88:
            continue
        target_piece = board[target]
        if target_piece & enemy_color:
            add_pawn_move(sq, target, pawn, target_piece, moves)
        elif target == ep_sq:
            moves.append(encode_move(sq, target, pawn, enemy_color | PAWN, is_ep=1))


def gen_step_moves(board, sq, offsets, ally_color, moves):
    """Shared generator for Knights and Kings."""
    piece = board[sq]
    for offset in offsets:
        target = sq + offset
        if not (target & 0x88):
            target_piece = board[target]
            if not (target_piece & ally_color):
                moves.append(encode_move(sq, target, piece, target_piece))


def gen_slider_moves(board, sq, directions, ally_color, moves):
    """Shared generator for Rooks, Bishops, and Queens."""
    piece = board[sq]
    for d in directions:
        target = sq + d
        while not (target & 0x88):
            target_piece = board[target]
            if not target_piece:
                moves.append(encode_move(sq, target, piece))
            else:
                if not (target_piece & ally_color):
                    moves.append(encode_move(sq, target, piece, target_piece))
                break
            target += d


def gen_castle_moves(board, king_sq, white_move, castling_rights, moves):
    enemy_color = BLACK if white_move else WHITE
    if is_square_attacked(board, king_sq, enemy_color):
        return

    king = board[king_sq]
    ks_flag = WKS if white_move else BKS
    qs_flag = WQS if white_move else BQS

    if (castling_rights & ks_flag) and not board[king_sq + 1] and not board[king_sq + 2]:
        if (
            not is_square_attacked(board, king_sq + 1, enemy_color)
            and not is_square_attacked(board, king_sq + 2, enemy_color)
        ):
            moves.append(encode_move(king_sq, king_sq + 2, king, is_castle=1))

    if (castling_rights & qs_flag) and not board[king_sq - 1] and not board[king_sq - 2] and not board[king_sq - 3]:
        if (
            not is_square_attacked(board, king_sq - 1, enemy_color)
            and not is_square_attacked(board, king_sq - 2, enemy_color)
        ):
            moves.append(encode_move(king_sq, king_sq - 2, king, is_castle=1))

COLS_TO_FILES = ("a", "b", "c", "d", "e", "f", "g", "h")
ROWS_TO_RANKS = ("8", "7", "6", "5", "4", "3", "2", "1")
PIECE_SYMBOLS = {PAWN: "P", KNIGHT: "N", BISHOP: "B", ROOK: "R", QUEEN: "Q", KING: "K"}

#     MOVE ENCODING / DECODING
# BITS   0-6: start_sq       (0x7F)
# BITS  7-13: end_sq         (0x7F)
# BITS 14-18: piece_moved    (0x1F)
# BITS 19-23: piece_captured (0x1F)
# BITS 24-26: promo          (0x07)
# BIT     27: is_ep          (1)
# BIT     28: is_castle      (1)

def encode_move(start_sq, end_sq, piece_moved, piece_captured=0, promo=0, is_ep=0, is_castle=0):
    return (
        start_sq
        | (end_sq << 7)
        | (piece_moved << 14)
        | (piece_captured << 19)
        | (promo << 24)
        | (is_ep << 27)
        | (is_castle << 28)
    )

def move_start(move):
    return move & 0x7F

def move_end(move):
    return (move >> 7) & 0x7F

def move_piece(move):
    return (move >> 14) & 0x1F

def move_captured(move):
    return (move >> 19) & 0x1F

def move_promo(move):
    return (move >> 24) & 0x7

def move_is_ep(move):
    return (move >> 27) & 1

def move_is_castle(move):
    return (move >> 28) & 1

def sq_to_algebraic(sq):
    return COLS_TO_FILES[sq & 7] + ROWS_TO_RANKS[sq >> 4]

def move_to_uci(move):
    promo = PIECE_SYMBOLS[move_promo(move)].lower() if move_promo(move) else ""
    return sq_to_algebraic(move_start(move)) + sq_to_algebraic(move_end(move)) + promo

def move_to_san(move):
    start_sq = move_start(move)
    end_sq = move_end(move)
    piece_moved = move_piece(move)
    captured = move_captured(move)
    promo = move_promo(move)

    if move_is_castle(move):
        return "O-O" if (end_sq & 7) == 6 else "O-O-O"

    end_square = sq_to_algebraic(end_sq)

    if (piece_moved & TYPE_MASK) == PAWN:
        promo_str = f"={PIECE_SYMBOLS[promo]}" if promo else ""
        if captured:
            return f"{COLS_TO_FILES[start_sq & 7]}x{end_square}{promo_str}"
        return f"{end_square}{promo_str}"

    piece_str = PIECE_SYMBOLS[piece_moved & TYPE_MASK]
    if captured:
        piece_str += "x"
    return piece_str + end_square

