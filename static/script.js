// Using jQuery for simplicity as chessboard.js requires it
$(document).ready(function() {
    var board = null; // Initialize board variable
    var game = new Chess(); // For local validation/status checks
    var statusEl = $('#status');
    var fenEl = $('#fen');
    // var pgnEl = $('#pgn'); // PGN element removed from default HTML, commenting out
    var thoughtsEl = $('#aiThoughts'); // Get the new thoughts element
    var currentServerFen = null; // Store the last known FEN from the server

    // Function to update the status display elements
    // ADDED llmThoughts parameter
    function updateDisplay(fen, pgn, statusText, llmThoughts) {
        fenEl.html(fen || 'N/A');
        // pgnEl.html(pgn || ''); // Commented out as element removed
        thoughtsEl.html(llmThoughts || ''); // Update thoughts, clear if null/undefined

        // Determine status text if not provided directly by server
        if (!statusText) {
            if (fen) {
                 try {
                     // Use 'start' position string directly if needed for reset
                     if (fen === 'start') { game.reset(); } else { game.load(fen); }
                     var moveColor = (game.turn() === 'b' ? 'Black' : 'White');

                     if (game.game_over()) {
                         if (game.in_checkmate()) {
                             statusText = 'Game over, ' + moveColor + ' is in checkmate.';
                         } else if (game.in_draw()) {
                             statusText = 'Game over, drawn position';
                         } else {
                             statusText = 'Game over';
                         }
                     } else {
                         statusText = moveColor + ' to move';
                         if (game.in_check()) {
                             statusText += ', ' + moveColor + ' is in check';
                         }
                     }
                 } catch (e) {
                    console.error("Error loading FEN in updateDisplay:", fen, e);
                    statusText = "Error parsing state.";
                 }
            } else {
                statusText = "Waiting for server...";
            }
        }
        statusEl.html(statusText);
        console.log("Display updated. Status: " + statusText + " FEN: " + fen);
        // Don't log thoughts here as they can be long
    }


    // --- Chessboard.js Interaction Callbacks ---

    function onDragStart (source, piece, position, orientation) {
        var authoritativeFen = currentServerFen;
        if (!authoritativeFen) return false; // Need server state

        // Reload game state from authoritative FEN for checks
        try {
            if (authoritativeFen === 'start') { game.reset(); } else { game.load(authoritativeFen); }
        } catch (e) {
            console.error("Error loading authoritative FEN into chess.js:", authoritativeFen, e);
            return false;
        }

        // Basic checks: game over, whose turn is it?
        if (game.game_over()) {
            console.log("Drag prevented: Game is over.");
            return false;
        }
        var pieceColor = piece.startsWith('w') ? 'w' : 'b';
        if (pieceColor !== game.turn()) {
            console.log("Drag prevented: Not piece's turn.");
            return false;
        }

        console.log("Drag allowed for " + source);
        return true;
    }


    function onDrop (source, target) {
        console.log("Dropped piece from " + source + " to " + target);
        var selectedModelId = $('#modelSelect').val();
        var moveData = {
            from: source,
            to: target,
            promotion: 'q', // Assume queen promotion for simplicity
            model_id: selectedModelId
        };

        statusEl.html("Sending move..."); // User feedback
        thoughtsEl.html("Waiting for AI response..."); // Clear old thoughts

        fetch('/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(moveData),
        })
        .then(response => {
            return response.json().then(data => {
                if (!response.ok) { throw { status: response.status, data: data }; }
                return data;
            });
        })
        .then(data => {
            console.log("Received from backend (Success):", data);
            if (data.fen) {
                currentServerFen = data.fen;
                board.position(data.fen, false);
                // Call updateDisplay WITH thoughts
                updateDisplay(data.fen, data.pgn, data.status_text, data.llm_thoughts);
            } else {
                 console.error("Unexpected success response format from backend:", data);
                 statusEl.html("Error: Unexpected success response from server.");
                 thoughtsEl.html("Error receiving data."); // Update thoughts area too
                 // Optionally revert board?
                 // board.position(currentServerFen || 'start');
            }
        })
        .catch((error) => {
            console.error('Error sending move or processing response:', error);
             let errorMessage = "An unknown error occurred.";
             let serverFenOnError = currentServerFen; // Keep track of FEN before potential update
             if (error.data && error.data.error) {
                 errorMessage = "Move rejected: " + error.data.error;
                 if (error.data.fen) {
                     serverFenOnError = error.data.fen; // Backend provided FEN even on error
                     currentServerFen = error.data.fen; // Update authoritative FEN
                     board.position(currentServerFen);
                 } else {
                     board.position(currentServerFen || 'start'); // Revert visual if no FEN provided
                 }
                 updateDisplay(serverFenOnError, null, errorMessage, "Error processing move."); // Update display, clear thoughts
             } else if (error instanceof Error) {
                 errorMessage = "Network or Server Error: " + error.message;
                 statusEl.html(errorMessage);
                 thoughtsEl.html("Network/Server error.");
                 board.position(currentServerFen || 'start'); // Revert visual
             } else {
                  statusEl.html(errorMessage);
                  thoughtsEl.html("Unknown error.");
                  board.position(currentServerFen || 'start'); // Revert visual
             }
        });

         // Let the server response dictate the final position
         return null;
    }

    // --- Board Initialization ---
    var config = {
        draggable: true,
        position: 'start',
        onDragStart: onDragStart,
        onDrop: onDrop,
        pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png' // Make sure this path is correct
        // pieceTheme: 'static/img/chesspieces/wikipedia/{piece}.png' // Alt path if relative to static needed
    };
    board = Chessboard('myBoard', config);

    // --- Reset Button ---
    $('#resetButton').on('click', function() {
        console.log("Reset button clicked, calling backend /reset");
        statusEl.html("Resetting game...");
        thoughtsEl.html(''); // Clear thoughts on reset
        fetch('/reset')
            .then(response => response.json())
            .then(data => {
                if(data.fen) {
                    currentServerFen = data.fen;
                    board.position(data.fen, false);
                    // Clear thoughts explicitly on reset success
                    updateDisplay(data.fen, '', 'Game Reset. White to move.', '');
                } else {
                     statusEl.html("Error resetting game.");
                     thoughtsEl.html("Reset error.");
                     currentServerFen = 'start';
                     board.start();
                }
            })
            .catch(error => {
                console.error('Error resetting game:', error);
                statusEl.html("Error resetting game: " + error.message);
                thoughtsEl.html("Reset error.");
                currentServerFen = 'start';
                board.start();
            });
    });

    // --- Initial Status ---
    function fetchInitialState() {
         console.log("Fetching initial state from backend...");
         statusEl.html("Loading game state...");
         thoughtsEl.html(''); // Clear thoughts on initial load
         fetch('/get_fen')
            .then(response => response.json())
            .then(data => {
                if (data.fen) {
                     currentServerFen = data.fen;
                     board.position(data.fen);
                     // Clear thoughts explicitly on initial load success
                     updateDisplay(data.fen, null, null, ''); // Let updateDisplay figure out status text
                } else {
                     statusEl.html("Error loading initial state.");
                     thoughtsEl.html("Load error.");
                     currentServerFen = 'start';
                     board.start();
                     updateDisplay('start', null, "Error loading. White to move.", '');
                }
            })
            .catch(error => {
                 console.error('Error fetching initial state:', error);
                 statusEl.html("Error loading game state: " + error.message);
                 thoughtsEl.html("Load error.");
                 currentServerFen = 'start';
                 board.start();
                 updateDisplay('start', null, "Error loading. White to move.", '');
            });
    }

   fetchInitialState(); // Fetch state when page loads

}); // end document ready
