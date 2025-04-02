# app.py
import chess
import chess.svg
from flask import Flask, render_template, jsonify, request, Response
import traceback # For more detailed error logging
import random # Needed for placeholder LLM fallback
from google import genai
from dotenv import load_dotenv
import os

load_dotenv()


app = Flask(__name__) # Initialize Flask app

# --- LLM Client Initialization ---
# Initialize the client once when the app starts
try:
    client = genai.Client(
        vertexai=True, project=os.getenv('VERTEXAI_PROJECT'), location=os.getenv('VERTEXAI_LOCATION')
    )
    print("Vertex AI Client initialized successfully.")
except Exception as e:
    print(f"!!! ERROR Initializing Vertex AI Client: {e}")
    print("!!! LLM functionality will likely fail.")
    client = None # Ensure client is None if initialization fails

# --- Game State (Simple In-Memory) ---
# WARNING: This is for demonstration only (single game, resets on server restart)
# A real app would need proper session management or a database.
board = chess.Board()

# --- Placeholder LLM Interaction ---
def get_llm_move(current_fen, model_id='gemini-2.0-flash-001'):
    """
    Placeholder function to get a move from the LLM.
    Replace this with your actual LLM SDK/API call.
    """
    print(f"--- Attempting to get LLM move for FEN: {current_fen} using model: {model_id} ---")

    # *** TODO: Replace this placeholder logic ***
    # 1. Format the prompt for your LLM
    #    - Include rules, current FEN, move history (board.move_stack), desired output format (UCI like 'e7e5').
    #    - Example prompt structure:
    legal_moves_uci = [move.uci() for move in board.legal_moves]
    legal_moves_str = " ".join(legal_moves_uci)

    prompt = (
        "You are a chess engine playing as Black.\n"
        "The current board state in FEN notation is:\n"
        f"{current_fen}\n"
        "History of moves in UCI format: " + " ".join([m.uci() for m in board.move_stack]) + "\n"
        f"LEGAL MOVES available: {legal_moves_str}\n" # Added legal moves
        "Your task is to select the best legal move for Black from the list provided.\n"
        "Respond *only* with the chosen move in UCI notation (e.g., 'g8f6', 'e7e5'). Do not add any other text."
    )
    print(f"LLM Prompt (example):\n{prompt}")

    # Use the globally initialized client
    if not client:
        print("LLM Client is not available. Cannot generate move.")
        llm_response_text = None # Indicate failure
    else:
        try:
            response = client.models.generate_content(
                model=model_id, contents=prompt
            )
            print(response.text)
            llm_response_text = response.text # Ensure it starts as None if LLM call isn't active
        except Exception as e:
             print(f"Error during LLM API call: {e}")
             llm_response_text = None

    if not llm_response_text: # If LLM call fails or is commented out
         print("LLM response failed or is placeholder. Choosing random legal move.")
         try:
             legal_moves = list(board.legal_moves)
             if legal_moves:
                 # Select a random move from the list of legal moves
                 chosen_move = random.choice(legal_moves)
                 llm_response_text = chosen_move.uci()
                 print(f"Random move chosen: {llm_response_text}")
             else:
                 print("No legal moves available for random choice.")
                 llm_response_text = None # No legal moves available
         except Exception as e:
             print(f"Error getting random move: {e}")
             llm_response_text = None
    # **** End of Random Move Placeholder ****

    # 3. Parse the LLM response (basic cleanup)
    if llm_response_text:
         # Basic cleanup - remove quotes, extra text if any (improve this parsing)
         # Takes the first line, removes surrounding quotes/spaces
         cleaned_move_uci = llm_response_text.splitlines()[0].replace('"', '').replace("'", "").strip()
         print(f"LLM Response (cleaned): '{cleaned_move_uci}'")
         # Basic validation: Check if it looks like UCI (e.g., 4 or 5 chars, a-h, 1-8)
         if len(cleaned_move_uci) >= 4 and len(cleaned_move_uci) <= 5:
              # Further regex check could be added here if needed
              return cleaned_move_uci
         else:
              print(f"LLM Response '{cleaned_move_uci}' doesn't look like valid UCI.")
              return None
    else:
         print("LLM failed to provide a valid move string.")
         return None
    # *** End of placeholder section ***


# --- Routes ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/get_fen')
def get_fen():
    """Returns the current board state in FEN format."""
    return jsonify({'fen': board.fen()})

@app.route('/reset')
def reset():
    """Resets the board to the starting position."""
    board.reset()
    print("Board reset")
    return jsonify({'fen': board.fen()}) # Send the starting FEN


@app.route('/move', methods=['POST'])
def handle_move():
    """Handles a player move received from the frontend."""
    try:
        # --- User Move Handling ---
        data = request.get_json()
        if not data or 'from' not in data or 'to' not in data:
            print("Error: Invalid move data received.")
            return jsonify({'error': 'Invalid move data format', 'fen': board.fen()}), 400

        from_square_name = data['from']
        to_square_name = data['to']
        promotion = data.get('promotion') # Optional promotion piece (defaults to None)
        # Get the selected model ID from the request, default if not provided
        selected_model_id = data.get('model_id', 'gemini-2.0-flash-001')
        print(f"Model ID selected by user (or default): {selected_model_id}") # Log selected model

        move_uci = f"{from_square_name}{to_square_name}"
        # Add promotion piece code if present and potentially valid
        # This check prevents adding 'q' to non-promotion moves
        if promotion and len(from_square_name) == 2 and len(to_square_name) == 2:
             try:
                 from_sq = chess.parse_square(from_square_name)
                 to_sq = chess.parse_square(to_square_name)
                 piece = board.piece_at(from_sq)
                 # Check if it's a pawn moving to the back rank
                 if piece and piece.piece_type == chess.PAWN:
                     if (piece.color == chess.WHITE and chess.square_rank(to_sq) == 7) or \
                        (piece.color == chess.BLACK and chess.square_rank(to_sq) == 0):
                          move_uci += promotion.lower() # Ensure promotion piece is lowercase
             except ValueError:
                # Ignore invalid square names here, parse_uci below will handle them
                pass # Let parse_uci handle fundamental errors

        print(f"Received user move attempt (UCI): {move_uci}")

        try:
            # Attempt to parse the user's move using python-chess
            move = board.parse_uci(move_uci)
        except ValueError as e:
             # Handle cases where UCI string is fundamentally invalid
             print(f"Error parsing user UCI '{move_uci}': {e}")
             return jsonify({'error': f'Invalid move format: {move_uci}', 'fen': board.fen()}), 400


        if move in board.legal_moves:
            # Make the user's move
            user_move_san = board.san(move) # Get SAN before pushing the move
            board.push(move)
            print(f"User move successful: {move.uci()}.")


            # --- LLM's Turn Logic ---
            llm_move_san = None
            game_over = board.is_game_over() # Check if user's move ended the game

            # Assuming LLM plays Black (board.turn == chess.BLACK) and game isn't over
            if not game_over and board.turn == chess.BLACK:
                print("--- Triggering LLM Turn ---")
                # Pass the selected model ID to get_llm_move
                llm_move_uci = get_llm_move(board.fen(), selected_model_id) # Pass current FEN and model ID

                if llm_move_uci:
                    try:
                        # Validate the LLM's move string before applying
                        llm_move = board.parse_uci(llm_move_uci)
                        if llm_move in board.legal_moves:
                            llm_move_san = board.san(llm_move) # Get SAN before pushing
                            board.push(llm_move) # Make LLM move
                            print(f"LLM move successful: {llm_move.uci()}")
                            game_over = board.is_game_over() # Check again after LLM move
                        else:
                            print(f"!!! LLM generated illegal move: {llm_move_uci}. Board state: {board.fen()}")
                            llm_move_san = f"[LLM illegal move: {llm_move_uci}]"
                    except ValueError as e:
                        print(f"!!! Error parsing LLM move UCI '{llm_move_uci}': {e}")
                        llm_move_san = f"[LLM invalid format: {llm_move_uci}]"
                else:
                    print("!!! LLM failed to provide a move.")
                    llm_move_san = "[LLM failed]"
            # --- End LLM's Turn Logic ---


            # --- Determine Status Text (incorporating LLM move) ---
            current_turn_color = 'Black' if board.turn == chess.BLACK else 'White'
            status_detail = ""
            # Check game end conditions (after potentially both moves)
            if board.is_checkmate():
                 status_detail = f"CHECKMATE! {'White' if board.turn == chess.BLACK else 'Black'} wins."
                 game_over = True # Ensure game_over is set
            elif board.is_stalemate():
                 status_detail = "STALEMATE! Draw."
                 game_over = True
            elif board.is_insufficient_material():
                 status_detail = "DRAW! Insufficient material."
                 game_over = True
            elif board.is_seventyfive_moves():
                status_detail = "DRAW! 75-move rule."
                game_over = True
            elif board.is_fivefold_repetition():
                status_detail = "DRAW! Fivefold repetition."
                game_over = True
            # elif game_over: # If game_over was set by user move but not specific draw/mate
            #      status_detail = "Game Over." # Optional generic game over
            elif board.is_check():
                 status_detail = f"{current_turn_color} is in CHECK!"
            else:
                 status_detail = f"{current_turn_color} to move."

            # Construct final status message
            if llm_move_san and llm_move_san.startswith("[LLM"): # If LLM failed or made invalid move
                 status_text = f"You played {user_move_san}. {llm_move_san} {status_detail}"
            elif llm_move_san: # If LLM moved successfully
                 status_text = f"You played {user_move_san}. Computer played {llm_move_san}. {status_detail}"
            else: # If it wasn't LLM's turn or user move ended game
                 status_text = f"Move {user_move_san} successful. {status_detail}"


            # --- Send back the FINAL state after both moves (if applicable) ---
            print(f"Sending response: FEN={board.fen()}, GameOver={game_over}")
            return jsonify({
                'fen': board.fen(),
                'pgn': board.epd(), # EPD includes FEN plus move counts etc.
                'status_text': status_text,
                'game_over': game_over # Let frontend know if game is over
            })
        else:
            # User move was illegal
            print(f"Error: Illegal user move - {move_uci}")
            # Return error and current FEN so the frontend can resync
            return jsonify({'error': f'Illegal move: {move_uci}', 'fen': board.fen()}), 400 # Send 400 Bad Request

    except Exception as e:
        # Catch potential errors during processing
        print(f"Error processing move: {e}\n{traceback.format_exc()}")
        # Send a generic server error
        return jsonify({'error': 'An internal server error occurred'}), 500

# --- Main Execution ---
if __name__ == '__main__':
    # Use debug=False and a proper WSGI server (like gunicorn) in production
    # For Cloud Run, gunicorn is typically used via the Procfile or CMD in Dockerfile
    app.run(debug=True, port=5001, host='0.0.0.0') # host='0.0.0.0' makes it accessible on network if needed