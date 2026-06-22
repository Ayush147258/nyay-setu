import asyncio
import uuid
import logging
from datetime import datetime, timezone

from app.db.neon_client import get_pool, close_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def seed_data():
    pool = await get_pool()
    
    # 1. Ensure Demo User Exists
    demo_user_id = "00000000-0000-0000-0000-000000000001"
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (id, email, name, role, preferred_lang)
            VALUES ($1, 'demo@nyaysetu.in', 'Demo Judge', 'admin', 'hi')
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name;
        """, demo_user_id)
        logger.info(f"Demo user ensured: {demo_user_id}")

        # Clear existing demo cases (optional, but good for repeatability)
        await conn.execute("DELETE FROM cases WHERE user_id = $1", demo_user_id)
        
        # 2. Prepare Demo Cases
        cases = [
            {
                "id": str(uuid.uuid4()),
                "case_type": "fir",
                "raw_input": "पुलिस मेरी FIR दर्ज नहीं कर रही है। मेरे पड़ोसी ने कल रात मेरी गाड़ी तोड़ दी और जब मैं थाने गया तो इंस्पेक्टर ने मुझे भगा दिया।",
                "detected_language": "hi",
                "status": "filed",
                "title": "Refusal to Register FIR against Neighbor",
                "description": "Complainant alleges that the local police station refused to register an FIR regarding vandalism of their vehicle by a neighbor.",
                "district": "Lucknow",
                "state": "Uttar Pradesh",
                "debate_round": 1
            },
            {
                "id": str(uuid.uuid4()),
                "case_type": "domestic_violence",
                "raw_input": "मेरे पति रोज़ शराब पीकर मुझे मारते हैं। मैं अपने बच्चों के साथ घर छोड़कर अपनी माँ के पास आ गई हूँ। मुझे सुरक्षा और गुज़ारा भत्ता चाहिए।",
                "detected_language": "hi",
                "status": "petition_ready",
                "title": "Protection Order against Abusive Husband",
                "description": "Wife seeking protection order, residence, and maintenance under the Domestic Violence Act due to habitual physical abuse.",
                "district": "Patna",
                "state": "Bihar",
                "debate_round": 2
            },
            {
                "id": str(uuid.uuid4()),
                "case_type": "crop_insurance",
                "raw_input": "हमर फसल बाढ़ में डूब गइल बा। बीमा कंपनी वाला लोग पईसा देवे से मना करत बाड़ें।",
                "detected_language": "bho",
                "status": "resolved",
                "title": "Denial of Crop Insurance Claim Due to Flood",
                "description": "Farmer's crop insurance claim under PMFBY unjustly denied by the insurance company following severe flood damage.",
                "district": "Chapra",
                "state": "Bihar",
                "debate_round": 1
            },
            {
                "id": str(uuid.uuid4()),
                "case_type": "land_dispute",
                "raw_input": "என் நிலத்தை என் அண்ணன் போலி ஆவணங்கள் மூலம் அபகரித்துவிட்டார். தாசில்தார் அலுவலகத்தில் புகார் செய்தும் நடவடிக்கை இல்லை.",
                "detected_language": "ta",
                "status": "intake",
                "title": "Fraudulent Transfer of Ancestral Land",
                "description": "Complainant's brother allegedly forged documents to transfer ancestral land into his name. Revenue authorities unresponsive.",
                "district": "Madurai",
                "state": "Tamil Nadu",
                "debate_round": 0
            },
            {
                "id": str(uuid.uuid4()),
                "case_type": "cyber_fraud",
                "raw_input": "I clicked on a link in an SMS claiming my electricity bill was pending, and Rs 45,000 was deducted from my bank account. The bank says it's my fault.",
                "detected_language": "en",
                "status": "advocating", # Mid-debate
                "title": "Phishing Scam via SMS (Electricity Bill)",
                "description": "Victim lost Rs 45,000 to a phishing scam. Seeking RBI ombudsman intervention against the bank for failing to freeze the account.",
                "district": "Bangalore",
                "state": "Karnataka",
                "debate_round": 1
            },
            {
                "id": str(uuid.uuid4()),
                "case_type": "consumer",
                "raw_input": "I bought a refrigerator online and it was delivered completely damaged. The company is refusing to replace it or refund my money.",
                "detected_language": "en",
                "status": "intake",
                "title": "Damaged Appliance Delivered, Refund Refused",
                "description": "E-commerce consumer dispute regarding delivery of defective goods and refusal of seller to honor the return policy.",
                "district": "Mumbai",
                "state": "Maharashtra",
                "debate_round": 0
            },
            {
                "id": str(uuid.uuid4()),
                "case_type": "flood_relief",
                "raw_input": "My shop was destroyed in the recent floods. The district administration has not included my name in the relief compensation list.",
                "detected_language": "en",
                "status": "filed",
                "title": "Omission from Disaster Relief Compensation List",
                "description": "Small business owner erroneously excluded from the state government's flood relief compensation register.",
                "district": "Ernakulam",
                "state": "Kerala",
                "debate_round": 1
            },
            {
                "id": str(uuid.uuid4()),
                "case_type": "wage_theft",
                "raw_input": "ठेकेदार ने हमें 3 महीने से दिहाड़ी नहीं दी है। जब भी पैसे मांगते हैं तो वह गालियां देता है और भगा देता है।",
                "detected_language": "hi",
                "status": "petition_ready",
                "title": "Non-payment of Minimum Wages by Contractor",
                "description": "Group of daily wage laborers seeking recovery of 3 months' unpaid wages from a construction contractor under the Minimum Wages Act.",
                "district": "Gurgaon",
                "state": "Haryana",
                "debate_round": 2
            }
        ]

        mid_debate_case_id = cases[4]["id"] # The cyber fraud case

        for c in cases:
            await conn.execute("""
                INSERT INTO cases (id, user_id, case_type, raw_input, detected_language, status, title, description, district, state, debate_round)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """, c["id"], demo_user_id, c["case_type"], c["raw_input"], c["detected_language"], c["status"], c["title"], c["description"], c["district"], c["state"], c["debate_round"])
            logger.info(f"Inserted case: {c['title']}")

        # 3. Insert Agent Runs (Debate Turns) for the mid-debate case
        debate_turns = [
            {
                "case_id": mid_debate_case_id,
                "agent_name": "Intake",
                "round_number": 1,
                "input_summary": "Extracted facts from voice input regarding Rs 45,000 phishing scam.",
                "output_summary": "Classified as Cyber Fraud. Identified jurisdiction as Consumer Court / Banking Ombudsman. Sent to Advocate for drafting.",
                "score": None
            },
            {
                "case_id": mid_debate_case_id,
                "agent_name": "Advocate",
                "round_number": 1,
                "input_summary": "Drafted initial petition focusing on consumer protection.",
                "output_summary": "Drafted complaint against the Bank emphasizing RBI circulars on zero liability of customers in unauthorized electronic transactions.",
                "score": None
            },
            {
                "case_id": mid_debate_case_id,
                "agent_name": "Adversarial",
                "round_number": 1,
                "input_summary": "Critiquing the Advocate's draft.",
                "output_summary": "The draft fails to mention if the victim reported the fraud to the bank within the mandatory 3-day window stipulated by RBI. Without this, zero liability does not automatically apply.",
                "score": None
            },
            {
                "case_id": mid_debate_case_id,
                "agent_name": "Mediator",
                "round_number": 1,
                "input_summary": "Reviewing Advocate draft vs Adversarial critique.",
                "output_summary": "Adversarial agent is correct. The petition must explicitly state the exact timeline of reporting the fraud to the bank and the National Cyber Crime Reporting Portal. Draft REJECTED. Returning to Advocate for Round 2.",
                "score": 45
            }
        ]

        for turn in debate_turns:
            await conn.execute("""
                INSERT INTO agent_runs (id, case_id, agent_name, round_number, input_summary, output_summary, score)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, str(uuid.uuid4()), turn["case_id"], turn["agent_name"], turn["round_number"], turn["input_summary"], turn["output_summary"], turn["score"])
        
        logger.info(f"Inserted mid-debate turns for case: {mid_debate_case_id}")

    await close_pool()
    logger.info("Database seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed_data())
