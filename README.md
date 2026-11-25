# Szachy z Marcinkiem

A from-scratch Python chess engine, Pygame GUI, and offline evaluation tuner. The project combines a bitwise 0x88 board representation, iterative deepening alpha-beta search, a multiprocess Pygame frontend, and a Ridge regression pipeline for tuning piece-square tables from Lichess evaluation data.

## Features

- **0x88 Bitwise Chess Engine (`chess_board.py`)**
  - 0x88 board representation with bit-packed 29-bit move integers (`start_sq`, `end_sq`, `piece_moved`, `piece_captured`, `promo`, `is_ep`, `is_castle`).
  - Incremental Zobrist hashing with threefold repetition tracking and fifty-move rule detection.
  - Full legal move generation and algebraic notation.
- **Alpha-Beta Search & Tapered Evaluation (`chess_engine.py`)**
  - Iterative deepening Negamax search with Alpha-Beta pruning.
  - Transposition table.
  - Quiescence search
  - Move ordering.
  - Piece-Square Tables.
  - Tapered middlegame/endgame king evaluation based on non-pawn material phase.
- **Pygame Frontend (`chess_main.py`)**
  - Supports **Human vs. Human**, **Human vs. AI**, and **AI vs. AI** modes.
  - Runs engine search in a separate `multiprocessing.Process` so the UI stays responsive while thinking.
  - Smooth piece movement animations, legal move / capture square highlights, interactive pawn promotion overlay, and a scrollable algebraic notation move log.
- **Ridge Regression PST Tuner (`learner.py`)**
  - Fits Piece-Square Tables (Pawns, Knights, Bishops, Rooks, Queens, and Middlegame/Endgame Kings) against Lichess evaluation datasets using closed-form L2-regularized Ridge regression.
  - Filters positions by search depth, centipawn bounds, and quiescence stability before accumulating normal equations in batches.

## Requirements

- Python 3.10+
- `pygame` (for `chess_main.py`)
- `numpy` (for `learner.py`)

```bash
pip install pygame numpy
```

## Usage

### Playing the Game

```bash
python3 chess_main.py
```

#### Controls

| Input | Action |
| :--- | :--- |
| **Left Click** | Select piece / make move / choose promotion piece |
| **Mouse Wheel** (over right panel) | Scroll algebraic notation move log |
| **`Left Arrow`** | Undo last ply |
| **`R`** | Reset the board |
| **`Esc`** | Cancel pending pawn promotion |
| **`E`** | Print raw 0x88 board array to console |

### Tuning Piece-Square Tables

`learner.py` expects a decompressed JSONL file of Lichess position evaluations containing `fen` and `evals` fields. You can download the official evaluation database from the [Lichess Open Database](https://database.lichess.org/#evals) and decompress the `.jsonl.zst` archive (e.g., via `zstd -d lichess_db_eval.jsonl.zst`).

```bash
python3 learner.py [dataset_path] [position_limit] [tag]
```

**Examples:**

```bash
# Default: reads lichess_eval_subset.jsonl, keeps up to 100,000 quiet positions
python3 learner.py

# Tune on 500k positions with a custom output suffix
python3 learner.py lichess_db_eval.jsonl 500k v1

# Process the entire dataset
python3 learner.py lichess_db_eval.jsonl all
```

Tuned weights are saved as Python tuples in `tuned_weights/weights_<timestamp>_kept<N>_a<ALPHA><tag>.py`, ready to be pasted into `chess_engine.py`.

## Project Structure

```text
chess-engine-nnue/
├── chess_main.py
├── chess_board.py
├── chess_engine.py
├── pieces/
│   ├── LICENSE
│   └── ...
├── learner.py
├── tuned_weights/
│   └── ...
├── LICENSE
└── README.md
```

## License

- Source code is licensed under the **GNU General Public License v2.0** (see `LICENSE`).
- Piece graphics in `pieces/` are dedicated to the public domain under **CC0 1.0 Universal** (see `pieces/LICENSE`).
