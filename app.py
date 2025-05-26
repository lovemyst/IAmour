from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
from supabase import create_client, Client

# Configuration Flask
app = Flask(__name__)
CORS(app)

# Récupération des variables d’environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SYSTEM_PROMPT_FREE = os.getenv("SYSTEM_PROMPT_FREE")
SYSTEM_PROMPT_PREMIUM = os.getenv("SYSTEM_PROMPT_PREMIUM")

# Connexions aux services
client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Vérifie si un utilisateur est premium
def get_is_premium(user_id: str) -> bool:
    try:
        response = supabase.table("users").select("is_premium").eq("id", user_id).single().execute()
        return response.data and response.data.get("is_premium", False)
    except Exception as e:
        print(f"Erreur Supabase (vérif premium) : {e}")
        return False

# Rend un utilisateur premium manuellement
def make_user_premium(user_id: str):
    try:
        response = supabase.table("users").upsert({
            "id": user_id,
            "is_premium": True
        }).execute()
        print(f"✅ Utilisateur {user_id} activé en premium.")
    except Exception as e:
        print(f"❌ Erreur lors de l'activation premium : {e}")

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    user_id = data.get("user_id")

    if not user_id or not user_message:
        return jsonify({"error": "user_id and message are required"}), 400

    # Vérifie le statut premium depuis Supabase
    is_premium = get_is_premium(user_id)
    assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE
    system_prompt = SYSTEM_PROMPT_PREMIUM if is_premium else SYSTEM_PROMPT_FREE

    print("🧠 Assistant utilisé :", assistant_id)
    print("📜 Prompt injecté :", system_prompt)

    # Vérifie si un thread existe pour cet utilisateur
    response = supabase.table("threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data:
        thread_id = response.data[0]["thread_id"]
    else:
        # Crée un nouveau thread
        thread = client.beta.threads.create()
        thread_id = thread.id

        # Sauvegarde le thread
        supabase.table("threads").insert({
            "user_id": user_id,
            "thread_id": thread_id
        }).execute()

        # Injecte le prompt calibré (debug initial)
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=f"[STYLE IAmour ACTIVÉ]\n{system_prompt}"
        )

    # Message utilisateur
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    # Lance l'exécution
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

# Test : activer ton propre compte premium (désactivable ensuite)
make_user_premium("user_1747692922028")  # ← Remplace par ton user_id réel si besoin

# Lancement correct sur Railway (ou en local)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
