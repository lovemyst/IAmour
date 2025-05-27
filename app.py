from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time

# Configuration Flask
app = Flask(__name__)
CORS(app)

# Variables d’environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SYSTEM_PROMPT_PREMIUM = os.getenv("SYSTEM_PROMPT_PREMIUM")

# Connexion à OpenAI
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Dictionnaire temporaire de threads par utilisateur (en mémoire uniquement pour test)
user_threads = {}

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    user_id = data.get("user_id")

    if not user_id or not user_message:
        return jsonify({"error": "user_id and message are required"}), 400

    # ⚡ Forcé : tous les utilisateurs sont traités comme premium
    is_premium = True
    assistant_id = ASSISTANT_ID_PREMIUM
    system_prompt = SYSTEM_PROMPT_PREMIUM

    print("🧠 Assistant utilisé :", assistant_id)
    print("👤 user_id :", user_id)
    print("📜 Prompt injecté :", system_prompt)

    # Vérifie si un thread existe déjà (en mémoire pour tests)
    if user_id in user_threads:
        thread_id = user_threads[user_id]
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id
        user_threads[user_id] = thread_id

        # Injecte le style calibré IAmour dès le début
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=f"[STYLE IAmour ACTIVÉ]\n{system_prompt}"
        )

    # Envoie le message réel de l'utilisateur
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    # Lance l'exécution de l'assistant
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # Attente de complétion
    max_attempts = 30
    attempts = 0
    while attempts < max_attempts:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            break
        elif run_status.status == "failed":
            return jsonify({"error": "L'assistant a échoué."}), 500
        time.sleep(1)
        attempts += 1

    if attempts == max_attempts:
        return jsonify({"error": "Temps d’attente dépassé."}), 504

    # Récupère la réponse
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last_message = messages.data[0].content[0].text.value

    print("💬 Réponse brute de l’IA :", last_message)

    return jsonify({"response": last_message})

# Lancement de l'application (compatible Railway)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
