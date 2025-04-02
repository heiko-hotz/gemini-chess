// --- Chessboard Setup ---
var board = null; // Initialize board variable
var game = new Chess(); // Initialize chess.js
var $status = $('#status'); // Cache the status element

// --- Chessboard Event Handlers ---

function onDragStart (source, piece, position, orientation) {
  // Do not pick up pieces if the game is over
  if (game.isGameOver()) return false;

  // Only pick up pieces for the side to move
  if ((game.turn() === 'w' && piece.search(/^b/) !== -1) ||
      (game.turn() === 'b' && piece.search(/^w/) !== -1)) {
    return false;
  }
}

function onDrop (source, target) {
  // See if the move is legal
  var move = null;
  try {
      move = game.move({
        from: source,
        to: target,
        promotion: 'q' // NOTE: Always promote to a queen for simplicity here
      });
  } catch (e) {
      // Catch exceptions for invalid moves like castling through check, etc.
      // chess.js v1+ throws exceptions for these cases
      console.warn("Invalid move:", e);
      return 'snapback';
  }


  // Illegal move
  if (move === null) return 'snapback';

  updateStatus();

  // If the game isn't over and it's Black's turn, make a random move for Black
  if (!game.isGameOver() && game.turn() === 'b') {
    // Add a small delay for visual effect
    window.setTimeout(makeRandomMove, 250);
  }
}

// --- Computer Move ---

function makeRandomMove () {
  var possibleMoves = game.moves();

  // Game over
  if (possibleMoves.length === 0) return;

  var randomIdx = Math.floor(Math.random() * possibleMoves.length);
  game.move(possibleMoves[randomIdx]);
  board.position(game.fen()); // Update the board position
  updateStatus(); // Update the status after Black's move
}

// Update the board position after the piece snap
// for castling, en passant, pawn promotion
function onSnapEnd () {
  board.position(game.fen());
}

// --- Game Status Update ---

function updateStatus () {
  var status = '';
  var moveColor = (game.turn() === 'b' ? 'Black' : 'White');

  // Checkmate?
  if (game.isCheckmate()) {
    status = 'Game over, ' + moveColor + ' is in checkmate.';
  }
  // Draw?
  else if (game.isDraw()) {
    status = 'Game over, drawn position';
  }
  // Game still on
  else {
    status = moveColor + ' to move';
    // Check?
    if (game.inCheck()) {
      status += ', ' + moveColor + ' is in check';
    }
  }
  $status.html(status);
}

// --- Initialize Chessboard ---

var config = {
  draggable: true,
  position: 'start',
  pieceTheme: 'img/chesspieces/wikipedia/{piece}.png', // Adjust path if needed
  onDragStart: onDragStart,
  onDrop: onDrop,
  onSnapEnd: onSnapEnd
};
board = Chessboard('myBoard', config); // Initialize the board

updateStatus(); // Initial status update
