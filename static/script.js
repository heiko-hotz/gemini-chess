// static/script.js
// Using jQuery for simplicity as chessboard.js requires it
$(document).ready(function() {
    var board = null; // Initialize board variable
    // chess.js is mainly for game_over checks and potentially status display helper
    var game = new Chess();
    var statusEl = $('#status');
    var fenEl = $('#fen');
    var pgnEl = $('#pgn');
    var currentServerFen = null; // Store the last known FEN from the server

    // Function to update the status display elements
    function updateDisplay(fen, pgn, statusText) {
        fenEl.html(fen || 'N/A');
        pgnEl.html(pgn || ''); // PGN might not always be sent

        // Determine status text if not provided directly
        // Use chess.js locally just to parse the state for display purposes
        if (!statusText) {
            if (fen) {
                 try {
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
    }


    // --- Chessboard.js Interaction Callbacks ---

    function onDragStart (source, piece, position, orientation) {
        // Use the FEN we know is correct from the last server update
        var authoritativeFen = currentServerFen;

        if (!authoritativeFen) {
            console.log("Drag prevented: No authoritative FEN available from server yet.");
            return false;
        }

        // --- Parse Active Color directly from the AUTHORITATIVE FEN ---
        console.log("Using Authoritative FEN:", "'" + authoritativeFen + "'");
        var fenParts = authoritativeFen.split(' ');
        var activeColor = 'w'; // Default to white
        if (fenParts.length >= 2) {
            var parsedPart = fenParts[1];
            console.log("Raw fenParts[1]:", "'" + parsedPart + "'"); // Log the specific part with quotes
            if (parsedPart) { // Check if the part exists and is not empty
                 activeColor = parsedPart.trim().toLowerCase(); // Trim whitespace and ensure lowercase
                 console.log("Trimmed & lowercased activeColor:", "'" + activeColor + "'");
            } else {
                 console.warn("Warning: fenParts[1] is empty or undefined in authoritative FEN.");
                 activeColor = 'w'; // Keep default if part is bad
            }
            // Explicitly check if the result is 'w' or 'b'
            if (activeColor !== 'w' && activeColor !== 'b') {
                console.warn("Warning: Parsed active color from authoritative FEN is not 'w' or 'b':", "'" + activeColor + "'. Defaulting to 'w'.");
                activeColor = 'w';
            }
        } else if (authoritativeFen !== 'start') { // 'start' position string has no parts
             console.warn("Warning: Authoritative FEN string does not have enough parts:", authoritativeFen);
             activeColor = 'w'; // Keep default if FEN structure is wrong
        }
        // --- END FEN PARSING ---

        // Determine the color of the piece being dragged ('w' or 'b')
        var pieceColor = piece.startsWith('w') ? 'w' : 'b';

        console.log("--- onDragStart Debug ---");
        console.log("Source Square:", source);
        console.log("Piece:", piece, "(Color:", pieceColor + ")");
        // console.log("Board FEN (visual):", board.fen()); // Optional: Log visual FEN for comparison
        console.log("Final Active Color (from authoritative FEN):", activeColor);


        // Still use the local 'game' object for game_over check, loading the *authoritative* FEN
        try {
            // Use 'start' position string directly if needed, otherwise load FEN
            if (authoritativeFen === 'start') { // chess.js cannot load 'start'
                 game.reset();
            } else {
                 game.load(authoritativeFen); // Load the good FEN here
            }
        } catch (e) {
            console.error("Error loading authoritative FEN into chess.js:", authoritativeFen, e);
            return false; // Prevent drag if local state load fails
        }

        if (game.game_over()) {
            console.log("Drag prevented: Game is over.");
            return false;
        }

        // Now, check if the piece's color matches the final active color variable
        if (pieceColor !== activeColor) {
            console.log("Failing condition check:",
                "Piece Color:", pieceColor,
                "Final Active Color:", activeColor
            );
            console.log("Drag prevented: Not piece's turn (Authoritative FEN check).");
            return false;
        }

        console.log("Drag allowed for " + source);
        return true; // Explicitly return true: drag is allowed
    }


    function onDrop (source, target) {
        console.log("Dropped piece from " + source + " to " + target);

        // Get selected model ID from dropdown
        var selectedModelId = $('#modelSelect').val();

        // Construct the move object for the backend
        var moveData = {
            from: source,
            to: target,
            // Basic promotion handling (always queen for now)
            promotion: 'q',
            model_id: selectedModelId // Add the selected model ID
        };

        // --- Send the move to the backend using fetch API ---
        statusEl.html("Sending move..."); // Give user feedback

        fetch('/move', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(moveData),
        })
        .then(response => {
            // Try to parse JSON regardless of response.ok, as error responses might have JSON bodies
            return response.json().then(data => {
                // Now check response.ok
                if (!response.ok) {
                    // Throw an error with the parsed JSON data
                    throw { status: response.status, data: data };
                }
                // If ok, return the parsed JSON data
                return data;
            });
        })
        .then(data => {
            // --- Update board and status based on successful backend response ---
            console.log("Received from backend (Success):", data);
            if (data.fen) {
                currentServerFen = data.fen; // Store the new authoritative FEN
                board.position(data.fen, false); // Update chessboard visuals (false = don't animate)
                updateDisplay(data.fen, data.pgn, data.status_text); // Update text info
            } else {
                 // This case shouldn't happen if response.ok was true and FEN was expected
                 console.error("Unexpected success response format from backend:", data);
                 statusEl.html("Error: Unexpected success response from server.");
                 // Optionally revert board? Might be confusing.
                 // board.position(currentServerFen || 'start');
            }
        })
        .catch((error) => {
            console.error('Error sending move or processing response:', error);
             // Handle both network errors and bad HTTP responses with JSON bodies
             let errorMessage = "An unknown error occurred.";
             if (error.data && error.data.error) {
                 // Error came from our backend's JSON response
                 errorMessage = "Move rejected: " + error.data.error;
                 // Resync board if backend provided FEN in error response
                 if (error.data.fen) {
                     currentServerFen = error.data.fen; // Update FEN even on error
                     board.position(currentServerFen);
                     updateDisplay(currentServerFen, null, errorMessage); // Update display with error
                 } else {
                    statusEl.html(errorMessage);
                    // If no FEN in error, just revert visually to last known good state
                    board.position(currentServerFen || 'start');
                 }

             } else if (error instanceof Error) {
                 // Network error or non-JSON response parsing error
                 errorMessage = "Network or Server Error: " + error.message;
                 statusEl.html(errorMessage);
                 board.position(currentServerFen || 'start'); // Revert visual
             } else {
                  // Other unexpected error format
                 statusEl.html(errorMessage);
                 board.position(currentServerFen || 'start'); // Revert visual
             }
        });

        // Return null to let the server response dictate the final piece position
         return null;
    }

    // onSnapEnd is not strictly needed anymore
    function onSnapEnd () {
        // console.log("Snap animation ended (visual only).");
    }

    // --- Board Initialization ---
    var config = {
        draggable: true,
        position: 'start', // Will be overridden by fetchInitialState
        onDragStart: onDragStart,
        onDrop: onDrop,
        // onSnapEnd: onSnapEnd, // Can be removed if not needed
        pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png'
    };
    board = Chessboard('myBoard', config); // Initialize the board

    // --- Reset Button ---
    $('#resetButton').on('click', function() {
        console.log("Reset button clicked, calling backend /reset");
        statusEl.html("Resetting game...");
        fetch('/reset')
            .then(response => response.json())
            .then(data => {
                if(data.fen) {
                    currentServerFen = data.fen; // Store reset FEN
                    board.position(data.fen, false); // Update visual board
                    updateDisplay(data.fen, '', 'Game Reset. White to move.'); // Update display
                } else {
                     statusEl.html("Error resetting game.");
                     currentServerFen = 'start'; // Assume start if reset fails?
                     board.start();
                }
            })
            .catch(error => {
                console.error('Error resetting game:', error);
                statusEl.html("Error resetting game: " + error.message);
                currentServerFen = 'start'; // Assume start if reset fails?
                board.start();
            });
    });

    // --- Initial Status ---
    function fetchInitialState() {
         console.log("Fetching initial state from backend...");
         statusEl.html("Loading game state...");
         fetch('/get_fen')
            .then(response => response.json())
            .then(data => {
                if (data.fen) {
                     currentServerFen = data.fen; // Store initial FEN
                     board.position(data.fen); // Set initial position
                     updateDisplay(data.fen);   // Update display elements
                } else {
                     statusEl.html("Error loading initial state.");
                     currentServerFen = 'start'; // Default to start if load fails
                     board.start();
                     updateDisplay('start', null, "Error loading. White to move.");
                }
            })
            .catch(error => {
                 console.error('Error fetching initial state:', error);
                 statusEl.html("Error loading game state: " + error.message);
                 currentServerFen = 'start'; // Default to start if load fails
                 board.start();
                 updateDisplay('start', null, "Error loading. White to move.");
            });
    }

   fetchInitialState(); // Fetch state when page loads

}); // end document ready