# Careconnect-Healthbot (Prototype)

CareConnect is a prototype WhatsApp Health Bot designed to provide reliable, quick, and localized health information.
It works using Flask, Twilio WhatsApp API, and an optional AI fallback (Groq / LLM) for complex queries.
The bot can answer health-related questions (like fever, dengue, nutrition, hygiene, etc.) and can be expanded to support multiple languages.

**Features**

1.Predefined responses for common health conditions (e.g., fever, malaria, cough).

2.Fuzzy matching to handle typos and similar queries.

3.Context-aware replies (remembers recent conversation for 15 minutes).

4.AI fallback for queries not found in the dataset.

5.Support for local language responses (via Google Translate API - optional).

6.Ready to integrate with government health/outbreak datasets for real-time updates.

**Project Structure**

careconnect/
 
 ├── app.py                # Main Flask app with chatbot logic
 
 ├── responses.json        # Predefined health responses
 
 ├── requirements.txt      # Dependencies
 
 ├── README.md             # Project documentation

**Installation & Setup**


1.Push your project code to GitHub.

2.Create a new Web Service on Render:

Connect your GitHub repository.

Select Python as environment.

Set build command: pip install -r requirements.txt

Set start command: gunicorn app:app

3.Add environment variables in Render:

TWILIO_ACCOUNT_SID

TWILIO_AUTH_TOKEN

GROQ_API_KEY (optional, for AI fallback)

GOOGLE_APPLICATION_CREDENTIALS (optional, for translation)

4.Once deployed, Render will give you a public URL like:
https://careconnect.onrender.com

5.Go to Twilio WhatsApp Sandbox settings and set the webhook:

https://careconnect.onrender.com/webhook

**Example Queries**

"hello" → Greeting response

"What is malaria?" → Predefined health info

"symptoms of typhoid" → Fuzzy matched response

"Tell me about leukemia and it's treatment" → AI fallback response

**Future Enhancements**

Real-time outbreak info via government datasets

Multi-language support with Google Translate API

Integration with telemedicine services

Analytics dashboard for common queries

**License**

MIT License – feel free to use and improve this project.
