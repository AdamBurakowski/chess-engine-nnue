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


class GameState():
    def __init__(self):
        self.board = [
            bR, bN, bB, bQ, bK, bB, bN, bR,  0, 0, 0, 0, 0, 0, 0, 0,
            bP, bP, bP, bP, bP, bP, bP, bP,  0, 0, 0, 0, 0, 0, 0, 0,
             0,  0,  0,  0,  0,  0,  0,  0,  0, 0, 0, 0, 0, 0, 0, 0,
             0,  0,  0,  0,  0,  0,  0,  0,  0, 0, 0, 0, 0, 0, 0, 0,
             0,  0,  0,  0,  0,  0,  0,  0,  0, 0, 0, 0, 0, 0, 0, 0,
             0,  0,  0,  0,  0,  0,  0,  0,  0, 0, 0, 0, 0, 0, 0, 0,
            wP, wP, wP, wP, wP, wP, wP, wP,  0, 0, 0, 0, 0, 0, 0, 0,
            wR, wN, wB, wQ, wK, wB, wN, wR,  0, 0, 0, 0, 0, 0, 0, 0]

        self.white_pieces = {
            (row << 4) | col
            for row in range(8)
            for col in range(8)
            if self.board[row << 4 | col] & WHITE
        }

        self.black_pieces = {
            (row << 4) | col
            for row in range(8)
            for col in range(8)
            if self.board[row << 4 | col] & BLACK
        }

        self.white_move = True
        self.move_log = []
        self.wk_pos = 0x74
        self.bk_pos = 0x04
        self.checkmate = False
        self.stalemate = False
        self.in_check = False
        self.en_passant_possible = -1
        self.en_passant_possible_log = [-1]
        self.castling_rights = CASTLING_RIGHTS
        self.castling_rights_log = [self.castling_rights]
        self.stateLog = []

        self.half_move_clock = 0

        # Zobrist Hash
        self.zobristHash = self.compute_zobrist_hash()
        self.positionHistory = [self.zobristHash]
        self.repetitionCounts = {
            self.zobristHash: 1
        }
        self.repetitionSignature = repetition_token(
            self.zobristHash, 1
        )

    def verify_zobrist_hash(self):
        calculated = self.compute_zobrist_hash()

        if calculated != self.zobristHash:
            raise AssertionError(
                f"Zobrist mismatch: "
                f"stored={self.zobristHash:#018x}, "
                f"calculated={calculated:#018x}"
            )

    def compute_zobrist_hash(self):
        """
        Full recomputation. Used for initialization and debugging,
        NOT during normal search.
        """
        h = 0
        for row in range(8):
            for col in range(8):
                sq = row << 4 | col
                piece = self.board[sq]
                if piece:
                    h ^= ZOBRIST_PIECES[piece][sq]
        if not self.white_move:
            h ^= ZOBRIST_SIDE
        h ^= ZOBRIST_CASTLING[self.castling_rights]
        if self.en_passant_possible != -1:
            h ^= ZOBRIST_EP[self.en_passant_possible & 7]
        return h

    def get_position_key(self):
        return self.zobristHash

    def get_search_key(self):
        return (
            self.zobristHash,
            self.repetitionSignature,
            min(self.half_move_clock, 100)
        )

    def is_threefold_repetition(self):
        return self.repetitionCounts.get(self.zobristHash, 0) >= 3

    def update_repetition_history(self, position_hash):
        old_count = self.repetitionCounts.get(position_hash, 0)
        new_count = old_count + 1
        if old_count:
            self.repetitionSignature ^= repetition_token(
                position_hash, min(old_count, 2))
        self.repetitionSignature ^= repetition_token(
            position_hash, min(new_count, 2))
        self.repetitionCounts[position_hash] = new_count

    @property
    def game_outcome(self):
        if self.checkmate:
            return "Black wins by checkmate" if self.white_move else "White wins by checkmate"
        if self.stalemate:
            return "Stalemate"
        if self.is_threefold_repetition():
            return "Draw by threefold repetition"
        if self.half_move_clock >= 100:
            return "Draw by fifty-move rule"
        return None

    def make_move(self, move):
        self.stateLog.append((
            self.zobristHash,
            self.repetitionSignature,
            self.half_move_clock
        ))

        old_castling_rights = self.castling_rights
        old_enpassant = self.en_passant_possible
        old_white_move = self.white_move

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
            square: self.board[square] for square in changed_squares}

        # MOVE LOGIC
        self.board[start_sq] = EMPTY
        self.board[end_sq] = piece_moved

        movingPieces = self.white_pieces if piece_moved & WHITE else self.black_pieces
        movingPieces.remove(start_sq)
        movingPieces.add(end_sq)

        if piece_captured and not is_ep:
            capturedPieces = self.white_pieces if piece_captured & WHITE else self.black_pieces
            capturedPieces.remove(end_sq)

        self.move_log.append(move)

        if piece_moved & TYPE_MASK == PAWN or piece_captured:
            self.half_move_clock = 0
        else:
            self.half_move_clock += 1

        self.white_move = not self.white_move

        if piece_moved == wK:
            self.wk_pos = end_sq
        elif piece_moved == bK:
            self.bk_pos = end_sq

        if promo:
            self.board[end_sq] = (piece_moved & COLOR_MASK) | promo

        # En passant
        if is_ep:
            ep_cp_sq = (start_sq & 0x70) | (end_sq & 7)
            self.board[ep_cp_sq] = EMPTY
            capturedPieces = self.white_pieces if piece_captured & WHITE else self.black_pieces
            capturedPieces.remove(ep_cp_sq)

        # Update en passant target
        if piece_moved & TYPE_MASK == PAWN and abs(start_sq - end_sq) == 32:
            self.en_passant_possible = ((start_sq + end_sq) >> 1)
        else:
            self.en_passant_possible = -1

        self.en_passant_possible_log.append(self.en_passant_possible)

        if is_castle:
            if end_sq - start_sq == 2:
                # Kingside
                rook_start, rook_end = end_sq + 1, end_sq - 1
            else:
                # Queenside
                rook_start, rook_end = end_sq - 2, end_sq + 1

            self.board[rook_end] = self.board[rook_start]
            self.board[rook_start] = EMPTY
            movingPieces.remove(rook_start)
            movingPieces.add(rook_end)

        # Update castling rights
        self.update_castling_rights(move)
        self.castling_rights_log.append(self.castling_rights)

        # ZOBRIST HASH UPDATE
        self.zobristHash ^= ZOBRIST_CASTLING[old_castling_rights]
        if old_enpassant != -1:
            self.zobristHash ^= ZOBRIST_EP[old_enpassant & 7]
        if not old_white_move:
            self.zobristHash ^= ZOBRIST_SIDE

        for sq, old_piece in old_square_contents.items():
            self.zobristHash ^= ZOBRIST_PIECES[old_piece][sq]
            self.zobristHash ^= ZOBRIST_PIECES[self.board[sq]][sq]

        self.zobristHash ^= ZOBRIST_CASTLING[self.castling_rights]
        if self.en_passant_possible != -1:
            self.zobristHash ^= ZOBRIST_EP[self.en_passant_possible & 7]
        if not self.white_move:
            self.zobristHash ^= ZOBRIST_SIDE

        self.positionHistory.append(self.zobristHash)
        self.update_repetition_history(self.zobristHash)

        if self.white_move:
            moved_king_sq = self.bk_pos
            opponent_color = WHITE
        else:
            moved_king_sq = self.wk_pos
            opponent_color = BLACK

        if is_square_attacked(self.board, moved_king_sq, opponent_color):
            self.undo_move()
            return False

        return True

    def update_castling_rights(self, move):
        start_sq = move & 0x7F
        end_sq = (move >> 7) & 0x7F
        piece_moved = (move >> 14) & 0x1F
        piece_captured = (move >> 19) & 0x1F

        # If the king moves
        if piece_moved == wK:
            self.castling_rights &= ~(WKS | WQS)
        elif piece_moved == bK:
            self.castling_rights &= ~(BKS | BQS)
        # If a rook moves from its original square
        elif piece_moved == wR:
            if start_sq == 0x70:
                self.castling_rights &= ~WQS
            elif start_sq == 0x77:
                    self.castling_rights &= ~WKS
        elif piece_moved == bR:
            if start_sq == 0x00:
                self.castling_rights &= ~BQS
            elif start_sq == 0x07:
                self.castling_rights &= ~BKS
        # If a rook is captured on its original square
        if piece_captured == wR:
            if end_sq == 0x70:
                self.castling_rights &= ~WQS
            elif end_sq == 0x77:
                self.castling_rights &= ~WKS
        elif piece_captured == bR:
            if end_sq == 0x00:
                self.castling_rights &= ~BQS
            elif end_sq == 0x07:
                self.castling_rights &= ~BKS

    def undo_move(self):
        if self.move_log:
            move = self.move_log.pop()
            prev_hash, prev_rep_sig, prev_half_move = self.stateLog.pop()
            current_hash = self.zobristHash
            count = self.repetitionCounts[current_hash]

            if count == 1:
                del self.repetitionCounts[current_hash]
            else:
                self.repetitionCounts[current_hash] = count - 1

            self.positionHistory.pop()
            self.half_move_clock = prev_half_move

            start_sq = move & 0x7F
            end_sq = (move >> 7) & 0x7F
            piece_moved = (move >> 14) & 0x1F
            piece_captured = (move >> 19) & 0x1F
            is_ep = (move >> 27) & 1
            is_castle = (move >> 28) & 1

            self.board[start_sq] = piece_moved
            self.board[end_sq] = piece_captured

            # Restore piece position sets
            movingPieces = self.white_pieces if piece_moved & WHITE else self.black_pieces
            movingPieces.remove(end_sq)
            movingPieces.add(start_sq)

            # Restore captured piece
            if piece_captured and not is_ep:
                capturedPieces = self.white_pieces if piece_captured & WHITE else self.black_pieces
                capturedPieces.add(end_sq)

            self.white_move = not self.white_move
            if piece_moved == wK:
                self.wk_pos = start_sq
            elif piece_moved == bK:
                self.bk_pos = start_sq

            # Undo en passant move
            if is_ep:
                ep_cp_sq = (start_sq & 0x70) | (end_sq & 7)
                self.board[end_sq] = EMPTY
                self.board[ep_cp_sq] = piece_captured
                capturedPieces = self.white_pieces if piece_captured & WHITE else self.black_pieces
                capturedPieces.add(ep_cp_sq)

            self.en_passant_possible_log.pop()
            self.en_passant_possible = self.en_passant_possible_log[-1]

            # Undo castling rights
            self.castling_rights_log.pop()
            self.castling_rights = self.castling_rights_log[-1]

            # Undo castling move
            if is_castle:
                if end_sq - start_sq == 2:
                    rook_start, rook_end = end_sq - 1, end_sq + 1
                else:
                    rook_start, rook_end = end_sq + 1, end_sq - 2
                self.board[rook_end] = self.board[rook_start]
                self.board[rook_start] = EMPTY
                movingPieces.remove(rook_start)
                movingPieces.add(rook_end)

            self.zobristHash = prev_hash
            self.repetitionSignature = prev_rep_sig

        self.checkmate = False
        self.stalemate = False

    def gen_pseudo_legal_moves(self):
        moves = []
        board = self.board
        if self.white_move:
            ally_color, pieces, king_sq = WHITE, self.white_pieces, self.wk_pos
        else:
            ally_color, pieces, king_sq = BLACK, self.black_pieces, self.bk_pos

        for sq in pieces:
            ptype = board[sq] & TYPE_MASK
            if ptype == PAWN:
                gen_pawn_moves(board, sq, self.white_move, self.en_passant_possible, moves)
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

        gen_castle_moves(board, king_sq, self.white_move, self.castling_rights, moves)
        return moves

    def gen_legal_moves(self):
        enemy_color = BLACK if self.white_move else WHITE
        king_sq = self.wk_pos if self.white_move else self.bk_pos
        self.in_check = is_square_attacked(self.board, king_sq, enemy_color)

        legal_moves = []
        for move in self.gen_pseudo_legal_moves():
            if self.make_move(move):
                self.undo_move()
                legal_moves.append(move)

        self.checkmate = self.in_check and not legal_moves
        self.stalemate = not self.in_check and not legal_moves
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

