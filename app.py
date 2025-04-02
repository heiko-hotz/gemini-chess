import chess
import chess.svg
from flask import Flask, render_template, jsonify, request, Response
import traceback # For more detailed error logging
import random # Needed for placeholder LLM fallback
from google import genai
from dotenv import load_dotenv
import os
import re # Import regex for better move parsing

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
def get_llm_move(current_fen, last_player_move_uci=None, model_id='gemini-2.0-flash-001'):
    """
    Gets a move and thoughts from the LLM using a chat session to handle potential illegal moves.
    Returns a dictionary: {'thoughts': str, 'move': str (UCI) or None}
    """
    print(f"--- Attempting to get LLM move/thoughts for FEN: {current_fen} using model: {model_id} ---")

    legal_moves_uci = [move.uci() for move in board.legal_moves]
    legal_moves_str = " ".join(legal_moves_uci)
    move_history_uci = " ".join([m.uci() for m in board.move_stack])

    # No LLM client available
    if not client:
        print("LLM Client is not available. Cannot generate move.")
        return get_random_move_with_thoughts()

    # *** MODIFIED PROMPT ***
    initial_prompt = (
        "You are a chess engine playing as Black, analyzing the position and deciding your next move.\n"
        "The current board state in FEN notation is:\n"
        f"{current_fen}\n"
        f"History of moves in UCI format: {move_history_uci}\n"
        f"The last move played by White (your opponent) was: {last_player_move_uci if last_player_move_uci else 'N/A (Start of game)'}\n"
        f"LEGAL MOVES available for you (Black): {legal_moves_str}\n\n" 
        "Your task:\n"
        "1. Briefly analyze the current situation. Consider the opponent's last move, threats, opportunities, and your general strategy.\n"
        "2. Choose the best legal move for Black from the list provided.\n"
        "3. Respond with your analysis/thoughts first (keep it concise, 1-3 sentences).\n"
        "4. On the VERY LAST LINE, provide *ONLY* your chosen move in UCI notation (e.g., 'g8f6', 'e7e5'). Do not include any other text or formatting on this last line."
        "\n\nExample Response Format:\n"
        "White's last move opened the center, but leaves their knight vulnerable. I should develop my piece and prepare to castle.\n"
        "e7e5" # Note: actual move should be from LEGAL MOVES
    )
    print(f"LLM Prompt (example):\n{initial_prompt}")

    try:
        # Create a chat session
        chat = client.chats.create(model=model_id)
        
        # Send the initial prompt
        response = chat.send_message(initial_prompt)
        llm_response_text = response.text
        print(f"LLM Raw Response:\n{llm_response_text}")
        
        # Parse the response to extract thoughts and move
        llm_thoughts, llm_move_uci = parse_llm_response(llm_response_text)
        
        # Check if the move is legal
        max_retries = 3
        retries = 0
        
        while retries < max_retries:
            # Check if we have a move and if it's valid
            if llm_move_uci:
                try:
                    move = board.parse_uci(llm_move_uci)
                    if move in board.legal_moves:
                        print(f"LLM provided legal move: {llm_move_uci}")
                        return {'thoughts': llm_thoughts, 'move': llm_move_uci}
                except ValueError:
                    pass  # Move format is invalid, will be handled below
            
            # If we get here, the move was either illegal, invalid format, or None
            retries += 1
            print(f"LLM provided invalid or illegal move: {llm_move_uci}. Retry {retries}/{max_retries}")
            
            correction_prompt = (
                f"Your selected move '{llm_move_uci}' is illegal or invalid. "
                f"Please choose a different move from these legal moves: {legal_moves_str}\n"
                "Keep your same analysis/thoughts, but select a different legal move."
                "Respond with your thoughts followed by ONLY the chosen move in UCI notation on the last line."
            )
            
            response = chat.send_message(correction_prompt)
            llm_response_text = response.text
            print(f"LLM Retry Response {retries}:\n{llm_response_text}")
            
            # Parse the new response
            llm_thoughts, llm_move_uci = parse_llm_response(llm_response_text)
        
        # If we've exhausted retries, fall back to random move but keep thoughts
        print(f"LLM failed to provide a legal move after {max_retries} attempts. Using random move instead.")
        random_result = get_random_move_with_thoughts(llm_thoughts)
        return random_result
        
    except Exception as e:
        print(f"Error during LLM chat: {e}")
        return get_random_move_with_thoughts()

def parse_llm_response(response_text):
    """Parse the LLM response to extract thoughts and move."""
    llm_thoughts = "AI analysis not available."
    llm_move_uci = None

    if response_text:
        lines = response_text.strip().splitlines()
        if len(lines) >= 1:
            # Assume the last non-empty line is the move
            potential_move = lines[-1].strip()
            # Basic validation: Check if it looks like UCI (4 or 5 chars, a-h, 1-8, optional promotion)
            if re.fullmatch(r"^[a-h][1-8][a-h][1-8][qnrb]?$", potential_move):
                 llm_move_uci = potential_move
                 print(f"Parsed LLM Move (UCI): '{llm_move_uci}'")
                 # If there were lines before the move, join them as thoughts
                 if len(lines) > 1:
                      llm_thoughts = "\n".join(lines[:-1]).strip()
                 else:
                      llm_thoughts = "(No thoughts provided, only move)"
                 print(f"Parsed LLM Thoughts:\n{llm_thoughts}")
            else:
                print(f"LLM Response's last line '{potential_move}' doesn't look like valid UCI. Treating whole response as thoughts.")
                llm_thoughts = response_text.strip()
                llm_move_uci = None # Explicitly set move to None
        else:
             print("LLM response was empty or only whitespace.")
             llm_thoughts = "(LLM response was empty)"

    return llm_thoughts, llm_move_uci

def get_random_move_with_thoughts(existing_thoughts=None):
    """Get a random legal move when LLM fails, with appropriate thoughts."""
    thoughts = existing_thoughts or "AI analysis not available."
    thoughts += " (AI failed to provide a valid move, choosing randomly.)"
    
    try:
        legal_moves = list(board.legal_moves)
        if legal_moves:
            chosen_move = random.choice(legal_moves)
            random_move_uci = chosen_move.uci()
            print(f"Random move chosen: {random_move_uci}")
            return {'thoughts': thoughts, 'move': random_move_uci}
        else:
            print("No legal moves available for random choice.")
            return {'thoughts': thoughts + " (No legal moves available!)", 'move': None}
    except Exception as e:
        print(f"Error getting random move: {e}")
        return {'thoughts': thoughts + f" (Error during random move fallback: {e})", 'move': None}

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
        selected_model_id = data.get('model_id', 'gemini-2.0-flash-001') # Get selected model ID
        print(f"Model ID selected by user (or default): {selected_model_id}")

        move_uci = f"{from_square_name}{to_square_name}"
        if promotion and len(from_square_name) == 2 and len(to_square_name) == 2:
             try:
                 from_sq = chess.parse_square(from_square_name)
                 to_sq = chess.parse_square(to_square_name)
                 piece = board.piece_at(from_sq)
                 if piece and piece.piece_type == chess.PAWN:
                     if (piece.color == chess.WHITE and chess.square_rank(to_sq) == 7) or \
                        (piece.color == chess.BLACK and chess.square_rank(to_sq) == 0):
                          move_uci += promotion.lower()
             except ValueError:
                pass

        print(f"Received user move attempt (UCI): {move_uci}")

        try:
            move = board.parse_uci(move_uci)
        except ValueError as e:
             print(f"Error parsing user UCI '{move_uci}': {e}")
             return jsonify({'error': f'Invalid move format: {move_uci}', 'fen': board.fen()}), 400


        if move in board.legal_moves:
            user_move_san = board.san(move) # Get SAN *before* pushing the move
            user_move_uci_for_llm = move.uci() # Get UCI *before* pushing
            board.push(move)
            print(f"User move successful: {move.uci()}.")

            # --- LLM's Turn Logic ---
            llm_move_san = None
            game_over = board.is_game_over()
            llm_thoughts_for_frontend = None # Initialize thoughts variable

            if not game_over and board.turn == chess.BLACK:
                print("--- Triggering LLM Turn ---")
                # Pass the user's last move UCI to the LLM function
                llm_result = get_llm_move(board.fen(), user_move_uci_for_llm, selected_model_id) # Pass current FEN, last user move, model ID

                llm_thoughts_for_frontend = llm_result.get('thoughts', "AI provided no thoughts.") # Get thoughts for frontend
                llm_move_uci = llm_result.get('move') # Get move UCI

                if llm_move_uci:
                    try:
                        llm_move = board.parse_uci(llm_move_uci)
                        if llm_move in board.legal_moves:
                            llm_move_san = board.san(llm_move) # Get SAN before pushing
                            board.push(llm_move)
                            print(f"LLM move successful: {llm_move.uci()}")
                            game_over = board.is_game_over()
                        else:
                            print(f"!!! LLM generated illegal move: {llm_move_uci}. Board state: {board.fen()}")
                            llm_move_san = f"[LLM illegal move: {llm_move_uci}]"
                            # Keep the thoughts from the result even if the move was illegal
                    except ValueError as e:
                        print(f"!!! Error parsing LLM move UCI '{llm_move_uci}': {e}")
                        llm_move_san = f"[LLM invalid format: {llm_move_uci}]"
                        # Keep the thoughts
                else:
                    print("!!! LLM failed to provide a move (might be included in thoughts).")
                    llm_move_san = "[LLM failed to move]"
                    # Thoughts might contain the reason for failure if parsing failed earlier

            # --- Determine Status Text ---
            current_turn_color = 'Black' if board.turn == chess.BLACK else 'White'
            status_detail = ""
            if board.is_checkmate():
                 status_detail = f"CHECKMATE! {'White' if board.turn == chess.BLACK else 'Black'} wins."
                 game_over = True
            elif board.is_stalemate():
                 status_detail = "STALEMATE! Draw."
                 game_over = True
            elif board.is_insufficient_material():
                 status_detail = "DRAW! Insufficient material."
                 game_over = True
            # Add other draw conditions if needed (75-move, fivefold)
            elif board.is_check():
                 status_detail = f"{current_turn_color} is in CHECK!"
            elif not game_over:
                 status_detail = f"{current_turn_color} to move."
            else:
                 status_detail = "Game Over." # Generic game over if needed


            # Construct final status message (remains largely the same)
            if llm_move_san and llm_move_san.startswith("[LLM"):
                 status_text = f"You played {user_move_san}. {llm_move_san} {status_detail}"
            elif llm_move_san:
                 status_text = f"You played {user_move_san}. Computer played {llm_move_san}. {status_detail}"
            else: # Only user moved or user move ended game
                 status_text = f"Move {user_move_san} successful. {status_detail}"


            # --- Send back the FINAL state including LLM thoughts ---
            print(f"Sending response: FEN={board.fen()}, GameOver={game_over}")
            return jsonify({
                'fen': board.fen(),
                # 'pgn': board.epd(), # EPD can be complex, FEN is usually enough for state
                'status_text': status_text,
                'game_over': game_over,
                'llm_thoughts': llm_thoughts_for_frontend # ADDED thoughts to response
            })
        else:
            # User move was illegal
            print(f"Error: Illegal user move - {move_uci}")
            return jsonify({'error': f'Illegal move: {move_uci}', 'fen': board.fen()}), 400

    except Exception as e:
        print(f"Error processing move: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'An internal server error occurred'}), 500

# --- Main Execution ---
if __name__ == '__main__':
    # Use debug=False and a proper WSGI server in production
    app.run(debug=True, port=5001, host='0.0.0.0')
