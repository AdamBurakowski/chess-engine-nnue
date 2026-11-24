# SPDX-License-Identifier: GPL-2.0-only

import sys
import json
import time
import numpy as np
import chess_board
import chess_engine
from chess_board import (
    EMPTY, PAWN, KING, WHITE, BLACK, TYPE_MASK,
    wP, wN, wB, wR, wQ, wK, bP, bN, bB, bR, bQ, bK,
    WKS, BKS, WQS, BQS, is_square_attacked,
)

import os
from datetime import datetime

N_FEAT = 7 * 64
BATCH = 8192
ALPHA = 100.0
CP_LIMIT = 1500
QUIET_DIFF = 50
MIN_DEPTH = 15

PIECE_MAP = {
    "P": wP, "N": wN, "B": wB, "R": wR, "Q": wQ, "K": wK,
    "p": bP, "n": bN, "b": bB, "r": bR, "q": bQ, "k": bK,
}

NAMES = (
    "white_pawn_pst",
    "white_knight_pst",
    "white_bishop_pst",
    "white_rook_pst",
    "white_queen_pst",
    "white_king_mg_pst",
    "white_king_eg_pst",
)

def load_fen(gs, fen):
    parts = fen.split()
    if len(parts) < 2:
        return False

    ranks = parts[0].split("/")
    if len(ranks) != 8:
        return False

    gs.board = [EMPTY] * 128
    gs.white_pieces.clear()
    gs.black_pieces.clear()
    gs.wk_pos = -1
    gs.bk_pos = -1

    for r, rank in enumerate(ranks):
        c = 0
        for ch in rank:
            if ch.isdigit():
                c += int(ch)
            else:
                p = PIECE_MAP.get(ch)
                if p is None or c >= 8:
                    return False
                sq = (r << 4) | c
                gs.board[sq] = p
                if p & WHITE:
                    gs.white_pieces.add(sq)
                    if p == wK:
                        gs.wk_pos = sq
                else:
                    gs.black_pieces.add(sq)
                    if p == bK:
                        gs.bk_pos = sq
                c += 1
        if c != 8:
            return False

    if gs.wk_pos == -1 or gs.bk_pos == -1:
        return False

    gs.white_move = (parts[1] == "w")

    castle = parts[2] if len(parts) > 2 else "-"
    gs.castling_rights = (
        (WKS if "K" in castle else 0)
        | (WQS if "Q" in castle else 0)
        | (BKS if "k" in castle else 0)
        | (BQS if "q" in castle else 0)
    )

    ep = parts[3] if len(parts) > 3 else "-"
    if len(ep) == 2:
        c = ord(ep[0]) - ord("a")
        r = 8 - int(ep[1])
        gs.en_passant_possible = (r << 4) | c if (0 <= r < 8 and 0 <= c < 8) else -1
    else:
        gs.en_passant_possible = -1

    gs.half_move_clock = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    gs.move_log.clear()
    gs.en_passant_possible_log = [gs.en_passant_possible]
    gs.castling_rights_log = [gs.castling_rights]
    gs.stateLog.clear()
    gs.checkmate = False
    gs.stalemate = False
    gs.in_check = False

    h = gs.compute_zobrist_hash()
    gs.zobristHash = h
    gs.positionHistory = [h]
    gs.repetitionCounts = {h: 1}
    gs.repetitionSignature = chess_board.repetition_token(h, 1)
    return True

def is_quiet(gs):
    if gs.white_move:
        own_k, opp_k, ally, enemy, sign = gs.wk_pos, gs.bk_pos, WHITE, BLACK, 1
    else:
        own_k, opp_k, ally, enemy, sign = gs.bk_pos, gs.wk_pos, BLACK, WHITE, -1

    if is_square_attacked(gs.board, opp_k, ally):
        return False
    if is_square_attacked(gs.board, own_k, enemy):
        return False

    static = sign * chess_engine.score_board(gs)
    q = chess_engine.quiescence(gs, -chess_engine.CHECKMATE, chess_engine.CHECKMATE, sign)
    return abs(q - static) <= QUIET_DIFF

def extract(gs, x):
    x.fill(0.0)
    mat = 0.0
    npm = 0

    for sq in gs.white_pieces:
        pt = gs.board[sq] & TYPE_MASK
        if pt != KING:
            sq64 = ((sq >> 4) << 3) | (sq & 7)
            x[(pt - 1) * 64 + sq64] += 1.0
            v = chess_engine.piece_value[pt]
            mat += v
            if pt != PAWN:
                npm += v

    for sq in gs.black_pieces:
        pt = gs.board[sq] & TYPE_MASK
        if pt != KING:
            sq64 = ((7 - (sq >> 4)) << 3) | (sq & 7)
            x[(pt - 1) * 64 + sq64] -= 1.0
            v = chess_engine.piece_value[pt]
            mat -= v
            if pt != PAWN:
                npm += v

    mg = min(npm, 6400) / 6400.0
    eg = 1.0 - mg

    wk64 = ((gs.wk_pos >> 4) << 3) | (gs.wk_pos & 7)
    bk64 = ((7 - (gs.bk_pos >> 4)) << 3) | (gs.bk_pos & 7)

    x[5 * 64 + wk64] += mg
    x[5 * 64 + bk64] -= mg
    x[6 * 64 + wk64] += eg
    x[6 * 64 + bk64] -= eg
    return mat

def parse_limit(s):
    s = s.lower()
    if s in ("0", "all"):
        return 0
    if s.endswith("k"):
        return int(s[:-1]) * 1000
    if s.endswith("m"):
        return int(s[:-1]) * 1_000_000
    return int(s)

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "lichess_eval_subset.jsonl"
    limit = parse_limit(sys.argv[2]) if len(sys.argv) > 2 else 100_000
    tag = f"_{sys.argv[3]}" if len(sys.argv) > 3 else ""

    gs = chess_board.GameState()
    XtX = np.zeros((N_FEAT, N_FEAT), dtype=np.float64)
    Xtr = np.zeros(N_FEAT, dtype=np.float64)
    X_buf = np.zeros((BATCH, N_FEAT), dtype=np.float64)
    r_buf = np.zeros(BATCH, dtype=np.float64)

    b = 0
    scanned = 0
    kept = 0
    t0 = time.perf_counter()

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if limit and kept >= limit:
                break
            scanned += 1
            if scanned % 25_000 == 0:
                dt = time.perf_counter() - t0
                print(f"scanned={scanned} kept={kept} ({scanned / dt:.0f} lines/s)")

            rec = json.loads(line)
            evals = rec.get("evals")
            if not evals:
                continue

            best = max(evals, key=lambda e: e.get("depth", 0))
            if best.get("depth", 0) < MIN_DEPTH:
                continue

            pvs = best.get("pvs")
            if not pvs or "cp" not in pvs[0]:
                continue

            cp = pvs[0]["cp"]
            if abs(cp) > CP_LIMIT:
                continue

            fen = rec.get("fen")
            if not fen or not load_fen(gs, fen) or not is_quiet(gs):
                continue

            mat = extract(gs, X_buf[b])
            r_buf[b] = cp - mat
            b += 1
            kept += 1

            if b == BATCH:
                XtX += X_buf.T @ X_buf
                Xtr += X_buf.T @ r_buf
                b = 0

    if b > 0:
        XtX += X_buf[:b].T @ X_buf[:b]
        Xtr += X_buf[:b].T @ r_buf[:b]

    if kept == 0:
        sys.exit("Error: 0 quiet positions kept.")

    w = np.linalg.solve(XtX + ALPHA * np.eye(N_FEAT), Xtr)
    w[0:8] = 0.0
    w[56:64] = 0.0

    os.makedirs("tuned_weights", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"weights_{timestamp}_kept{kept}_a{int(ALPHA)}{tag}.py"
    history_path = os.path.join("tuned_weights", filename)

    header = (
        f"# timestamp={timestamp} kept={kept} "
        f"ALPHA={ALPHA} CP_LIMIT={CP_LIMIT} QUIET_DIFF={QUIET_DIFF} MIN_DEPTH={MIN_DEPTH}\n"
        f"# piece_value={chess_engine.piece_value}\n"
    )

    lines = [header]
    for i, name in enumerate(NAMES):
        grid = w[i * 64 : (i + 1) * 64]
        lines.append(f"{name} = (")
        for r in range(8):
            row = ", ".join(f"{int(round(grid[r * 8 + c])):4d}" for c in range(8))
            lines.append(f"    {row},")
        lines.append(")\n")

    out_text = "\n".join(lines)

    with open(history_path, "w", encoding="utf-8") as out:
        out.write(out_text)

    print(f"\nDone in {time.perf_counter() - t0:.1f}s (kept={kept})")
    print(f"Saved history to: {history_path}\n")
    print(out_text)

if __name__ == "__main__":
    main()
