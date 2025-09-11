import os
import json
import time
import string
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from rapidfuzz import fuzz, process
from groq import Groq
from langdetect import detect, LangDetectException

app = Flask(__name__)

# Load responses
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

questions_list = list(responses.keys())

# Groq setup
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

SYSTEM_PROMPT = """You are CareConnect, a rural health assistant.
STRICT RULES:
1) Only answer health-related questions: diseases, symptoms, nutrition, hygiene, minor injuries, prevention, treatments.
2) If the question is unrelated to mental or physical health, reply EXACTLY:
'I am here to answer health-related questions only. Please ask health related issues.'
3) Keep answers SHORT, FACTUAL, and TO THE POINT. No extra chit-chat.
4) Use the provided conversation context for follow-ups.
5) Respond ONLY in the language of the user's question.
"""

user_contexts = {}

def clean_text(text):
    """Lowercase and remove punctuation for better matching."""
    return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()

def get_language(text):
    """Detects the language of the input text, limited to 'hi' and 'en'."""
    try:
        lang = detect(text)
        if lang == 'hi':
            return 'hi'
        return 'en'
    except LangDetectException:
        return 'en'

def ask_groq(user_input, context="", lang="en"):
    if not client:
        return "AI engine not working (no API key found)."
    
    # Instruct the AI to respond in the detected language
    prompt_with_lang = f"Respond in {lang}. {context}\n\nUser: {user_input}"
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_with_lang}
            ],
            temperature=0.2,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI request failed: {e}"

@app.route("/", methods=["GET"])
def home():
    return "CareConnect WhatsApp Bot is running!"

# ... (rest of the code is the same) ...

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")
    print("Message from", user_id, ":", incoming_msg)

    resp = MessagingResponse()
    msg = resp.message()

    # --- Language Detection (Always Re-Detect) ---
    user_lang = get_language(incoming_msg)
    cleaned_msg = clean_text(incoming_msg)

    # --- Greeting Check ---
    greetings = {
        "en": ["hi", "hello", "hey", "hii", "helo"],
        "hi": ["namaste", "namaskar"],
    }
    
    current_greetings = greetings.get(user_lang, greetings.get("en", []))

    if cleaned_msg in current_greetings:
        greeting_response = responses.get("greeting", {}).get(user_lang, responses.get("greeting", {}).get("en", "Hello, I am CareConnect. How can I help you?"))
        msg.body(greeting_response)
        print("Replied:", greeting_response)
        return Response(str(resp), mimetype="application/xml")

    # --- Check JSON by keyword ---
    reply = None
    # Iterate through each keyword in your JSON
    for keyword, lang_responses in responses.items():
        # Check if the cleaned incoming message contains this keyword
        if keyword.lower() in cleaned_msg:
            reply = lang_responses.get(user_lang)
            if reply:
                print("Matched keyword:", keyword, "in language:", user_lang, "→ Reply:", reply)
                user_contexts[user_id] = {"last_topic": keyword, "last_update": time.time()}
                break

    # Fallback to Groq if no keyword was matched
    if not reply:
        context = ""
        # Check for context within the 15-minute window
        if user_id in user_contexts:
            last_time = user_contexts[user_id].get("last_update", 0)
            if time.time() - last_time < 900:
                context = "Previous topic: " + user_contexts[user_id].get("last_topic", "")
            else:
                user_contexts.pop(user_id, None)

        # Pass the newly detected language to the AI function
        reply = ask_groq(incoming_msg, context=context, lang=user_lang)
        print("AI reply:", reply)
        user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}

    msg.body(reply)
    print("Sending to", user_id, ":", reply)
    return Response(str(resp), mimetype="application/xml")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

