import json
import requests
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from rapidfuzz import process
import time
from groq import Groq
import os

app = Flask(__name__)

# Load FAQs from JSON
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

# Groq client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Conversation context
user_contexts = {}

# Strict system prompt (English only)
SYSTEM_PROMPT_TEMPLATE = (
    "You are CareConnect, a rural health assistant in India. STRICT RULES:\n"
    "1) Only answer health-related questions: fever, malaria, dengue, minor injuries, waterborne diseases, nutrition, etc.\n"
    "2) If the question is unrelated, reply EXACTLY:\n"
    "   'I am here to answer health-related questions only. Please ask about fever, malaria, dengue, or other health issues.'\n"
    "3) Keep answers SHORT, FACTUAL, and TO THE POINT. No extra chit-chat.\n"
    "4) Use the provided conversation context for follow-ups.\n\n"
    "Conversation context: {context}\n"
)

# 🔹 Query Groq
def query_groq(user_input, context=""):
    if not client:
        return "AI engine not configured."
    try:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context)
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print("Groq request failed:", e)
        return "Sorry, I couldn’t process your request."

# Fuzzy match for predefined answers
def get_fuzzy_match(user_input):
    match, score, _ = process.extractOne(user_input, responses.keys())
    if score > 80:  
        return match
    return None

#Flask webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")

    resp = MessagingResponse()
    msg = resp.message()

    # Check if first interaction
    if user_id not in user_contexts:
        msg.body("Hello I am CareConnect, your healthbot. How can I help you with health related queries?")
        user_contexts[user_id] = {"last_topic": "", "last_update": time.time(), "introduced": True}
        return Response(str(resp), mimetype="application/xml")

    found = False
    context = ""

    # Add context if recent
    last_time = user_contexts[user_id].get("last_update", 0)
    if time.time() - last_time < 900:  
        context = f"Previous topic: {user_contexts[user_id].get('last_topic','')}"

    # Exact match
    if incoming_msg.lower() in (q.lower() for q in responses.keys()):
        for question, answer in responses.items():
            if question.lower() == incoming_msg.lower():
                msg.body(answer.get("en"))
                user_contexts[user_id] = {"last_topic": question, "last_update": time.time()}
                found = True
                break

    # Fuzzy match
    if not found:
        match_question = get_fuzzy_match(incoming_msg)
        if match_question:
            msg.body(responses[match_question].get("en"))
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}
            found = True

    # AI fallback
    if not found:
        dynamic_answer = query_groq(incoming_msg, context=context)
        msg.body(dynamic_answer)
        user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}

    return Response(str(resp), mimetype="application/xml")

if __name__ == "__main__":
    app.run(port=5000, debug=True)

