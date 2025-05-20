from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
from supabase import create_client, Client

# Initialisation de Flask
app = Flask(__name__)
CORS(app)

# Clés d'environnement
openai.api_key = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")

# Connexion à Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    user_id = data.get("user_id")
    is_premium = data.get("isPremium", False)

    if not user_id or not user_message:
        return jsonify({"error": "user_id and message are required"}), 400

    assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE

    # Vérifie si un thread existe déjà pour cet utilisateur
    response = supabase.table("threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data:
        thread_id = response.data[0]["thread_id"]
    else:
        # Crée un nouveau thread
        thread = openai.beta.threads.create()
        thread_id = thread.id

        # Enregistre le thread dans Supabase
        supabase.table("threads").insert({
            "user_id": user_id,
            "thread_id": thread_id
        }).execute()

    # Envoie le message de l'utilisateur
    openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    # Lance l’assistant
    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # Attend la fin du traitement avec timeout
    max_attempts = 30
    attempts = 0
    while attempts < max_attempts:
        run_status = openai.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break
        elif run_status.status == "failed":
            return jsonify({"error": "L'assistant a échoué."}), 500
        time.sleep(1)
        attempts += 1

    if attempts == max_attempts:
        return jsonify({"error": "Temps d’attente dépassé."}), 504

    # Récupère la dernière réponse
    messages = openai.beta.threads.messages.list(thread_id=thread_id)
    last_message = messages.data[0].content[0].text.value

    return jsonify({"response": last_message})


# Ce bloc permet d’exécuter en local seulement
if __name__ == '__main__':
    if os.getenv("RAILWAY_ENVIRONMENT") is None:
        app.run(debug=True)
