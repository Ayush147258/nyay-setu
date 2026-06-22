# NyaySetu 10-Minute Live Demo Runbook

This script is designed for a strict 10-minute presentation window. It demonstrates the multi-lingual intake, the autonomous LangGraph agent debate, and the generated PDF petition. 

## Prerequisites & Setup (T-Minus 5 minutes)
1. Ensure both `.env` files are populated and services are running (`docker-compose up`).
2. Run the seed script: `python backend/app/data/seed.py`.
3. Open a browser window in Incognito mode to `http://localhost:3000`.
4. Ensure your microphone is connected and authorized in the browser.

---

## 0:00 - 1:30 | The Hook & Landing Page
**Action:** Share screen. Keep the browser on the `http://localhost:3000` landing page.
**Talk Track:**
> "There are over 54 million cases pending in Indian courts. The primary barrier to justice isn't just backlogs—it's access. The legal system is complex, expensive, and predominantly operates in English, alienating the majority of citizens.
> 
> Meet NyaySetu: India's first autonomous legal rights navigator. It's not a chatbot. It's a team of AI legal agents that triage complaints in 22 regional languages, debate the merits of a case, cite actual Indian legal precedents, and draft court-ready petitions. Let me show you."

**Action:** Click **"Get started free"** and sign in using the Google OAuth demo account (`demo@nyaysetu.in`).
**Action:** The app redirects to the Dashboard.

## 1:30 - 3:30 | Multilingual Voice Intake
**Action:** On the Dashboard, briefly point out the stats, then click **"File your first case"** to navigate to `/new-case`.
**Talk Track:**
> "We're dropping right into the Intake flow. We know our users aren't typing out legal briefs. They are using their phones, speaking in their mother tongues. NyaySetu is powered by Sarvam AI to handle raw, emotional voice input."

**Action:** Select **Hindi** from the language dropdown.
**Action:** Click the Microphone icon. Speak the following phrase clearly:
> *"पुलिस मेरी FIR दर्ज नहीं कर रही है। मेरे पड़ोसी ने कल रात मेरी गाड़ी तोड़ दी और जब मैं थाने गया तो इंस्पेक्टर ने मुझे भगा दिया।"* 
> *(Translation: The police is not registering my FIR. My neighbor vandalized my car last night and when I went to the station, the inspector chased me away.)*

**Action:** Click Stop. Wait for the Sarvam transcription to populate the text box.
**Talk Track:**
> "The voice is instantly transcribed and translated into English for our backend agents. I'll hit submit, and this is where the magic happens."

**Action:** Click **Submit**. You will be redirected to the Agent Arena (`/cases/[id]`).

## 3:30 - 7:00 | The Agent Arena (Live Debate)
**Action:** The Agent Arena page loads. Let the SSE stream begin pushing agent bubbles.
**Talk Track:**
> "What you are seeing here isn't a single LLM generating a response. This is our Agent Arena—a LangGraph-orchestrated debate. 
> 
> 1. First, the **Intake Agent** structures the facts.
> 2. Then, the **Advocate Agent** takes those facts and drafts an initial petition. In this case, an application under Section 156(3) of the CrPC to force the FIR registration.
> 3. But here is the differentiator: the **Adversarial Agent**. Its entire prompt is designed to attack the Advocate's draft. It acts as the opposing counsel, looking for missing dates, unmentioned jurisdictions, or weak legal basis."

**Action:** Wait for the Adversarial and Mediator bubbles to appear. 
**Talk Track:**
> "Finally, the **Mediator Agent** acts as the judge. It reviews the Advocate's draft against the Adversary's critique. If the draft is weak, the Mediator rejects it, forcing a Round 2. 
> 
> Watch how it handles our case..." *(Read out the Mediator's feedback if it rejects the draft for missing details).* "...Because we didn't specify the exact date or police station name in our voice note, the Mediator is forcing the Advocate to add placeholders for those critical details."

## 7:00 - 8:30 | The Hardened Petition
**Action:** Once the Mediator approves (Status changes to `petition_ready`), the right-hand panel illuminates with the final draft. 
**Talk Track:**
> "The debate has concluded. What emerges is a hardened, battle-tested petition. It has survived adversarial scrutiny. 
> Notice how it correctly formats the plea for the Judicial Magistrate First Class, cites the relevant sections of the CrPC, and leaves perfectly formatted blanks for the user to fill in their personal details."

**Action:** Click the **"Download PDF"** button. Open the PDF to show the WeasyPrint-generated court document.
**Talk Track:**
> "This isn't just text on a screen. It's a properly formatted PDF, ready to be printed, signed, and filed. In 4 minutes, we went from a frustrated Hindi voice note to a legally sound court document."

## 8:30 - 10:00 | Case Library & Wrap Up
**Action:** Click the **Back to Dashboard** button, then navigate to the **Case Library** (`/cases`).
**Talk Track:**
> "NyaySetu tracks everything. Here in the Case Library, we can see other cases we've processed—domestic violence, crop insurance claims in Bhojpuri, land disputes in Tamil. 
> 
> Justice in India shouldn't be gated by language, wealth, or access to top-tier lawyers. NyaySetu bridges that gap autonomously."

**Action:** Conclude presentation and open for Q&A.

---

## 🚨 Fallback Plan (If Live Demo Fails)
Live LLM calls and API endpoints (Sarvam, Anthropic) can experience latency or timeouts during live demos. **Do not panic.** 

**If the voice transcription fails:**
1. Apologize briefly ("It seems our speech-to-text API is hitting a rate limit").
2. Simply paste the Hindi text into the fallback text box and click Submit.
   - Text: `पुलिस मेरी FIR दर्ज नहीं कर रही है। मेरे पड़ोसी ने कल रात मेरी गाड़ी तोड़ दी...`

**If the Agent Stream stalls or errors out:**
1. Do not wait longer than 15 seconds. Say: *"Since we are hitting live LLM endpoints, we sometimes see latency. Let me show you a case that processed just a moment ago."*
2. Navigate back to the **Case Library** (`/cases`).
3. Click on the **"Phishing Scam via SMS (Electricity Bill)"** case.
4. **Why this case?** The seed script (`seed.py`) deliberately inserted this case with a `debate_round: 1` status and pre-populated the `agent_runs` table. 
5. The UI will instantly load the Agent Arena, showing a completed Round 1 where the Mediator *rejected* the Advocate's draft. You can use this to perfectly explain the adversarial critique mechanism without waiting for a live run.
