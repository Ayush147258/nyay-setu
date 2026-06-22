import Link from 'next/link';
import LandingScript from '@/components/landing/LandingScript';

export default function LandingPage() {
  return (
    <>
      <div className="landing-page">
<header className="site-nav" id="siteNav">
  <div className="nav-row">
    <Link href="#" className="brand" aria-label="NyaySetu home">
      <span className="brand-seal" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M5 8h14M12 8v11M7 19h10" stroke="#B23A2E" strokeWidth="2" strokeLinecap="round"/>
          <circle cx="5" cy="11" r="2.4" stroke="#B8965A" strokeWidth="1.4"/>
          <circle cx="19" cy="11" r="2.4" stroke="#B8965A" strokeWidth="1.4"/>
        </svg>
      </span>
      <span className="brand-text">NyaySetu<small className="devanagari">न्यायसेतु · legal rights navigator</small></span>
    </Link>

    <nav className="nav-links" id="navLinks">
      <Link href="#how-it-works">How it works</Link>
      <Link href="#case-types">Case types</Link>
      <Link href="/dashboard">Petitions</Link>
      <Link href="#about">About</Link>
    </nav>

    <div className="nav-actions">
      <Link href="/login" className="nav-signin">Sign in</Link>
      <Link href="/new-case" className="btn btn-stamp btn-sm">Get started free</Link>
      <button className="nav-burger" id="navBurger" aria-label="Toggle menu" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>
    </div>
  </div>
</header>

<main>

  {/*  ============ HERO ============  */}
  <section className="hero" id="start">
    <div className="wrap hero-grid">
      <div className="reveal in-view">
        <p className="eyebrow hero-eyebrow"><span className="dot"></span> Powered by Sarvam AI &nbsp;·&nbsp; Built for Bharat</p>
        <h1 className="hero-title">Justice shouldn't depend on <em>who you know.</em></h1>
        <p className="hero-sub">NyaySetu is an autonomous multi-agent legal navigator that drafts petitions, researches precedents, and guides you through India's legal system — in your own language.</p>
        <div className="hero-cta">
          <Link href="#how-it-works" className="btn btn-stamp">Start voice triage</Link>
          <Link href="/dashboard" className="btn btn-ghost">Upload a document</Link>
        </div>
        <p className="hero-micro">No lawyer required · Available 24/7 · Hindi, English, and 12 regional languages</p>
      </div>

      <div className="doc-stage reveal in-view" id="petition-preview">
        <div className="tape-row" aria-hidden="true">
          <div className="tape tape-left"><span className="tape-text">OFFICIAL · SEALED · OFFICIAL · SEALED · OFFICIAL ·</span></div>
          <div className="tape tape-right"><span className="tape-text">SEALED · OFFICIAL · SEALED · OFFICIAL · SEALED ·</span></div>
        </div>
        <div className="seal-stamp" aria-hidden="true"><span>✓<br />FILED</span></div>

        <div className="doc-card">
          <div className="doc-kicker">
            <span>Section 156(3) CrPC</span>
            <span className="live"><span className="live-dot"></span> Live draft</span>
          </div>
          <p className="doc-heading">Petition draft · Judicial Magistrate First Class</p>
          <div className="doc-body">
            TO,<br />
            The Judicial Magistrate First Class,<br />
            Bhagalpur (District)<br /><br />
            <strong>SUBJECT:</strong> Application under Section 156(3) of CrPC seeking direction to register FIR and investigate the cognizable offence...<br /><br />
            The applicant respectfully submits that on [date], the respondent(s) committed acts constituting [offence under IPC Section...]
          </div>
          <p className="doc-foot">Drafted in 4 minutes · Checkpointed on Neon Postgres</p>
        </div>

        <div className="pipeline-row">
          <span className="pipeline-label">Pipeline</span>
          <span className="chip">Intake</span><span className="chip-arrow">→</span>
          <span className="chip">Research</span><span className="chip-arrow">→</span>
          <span className="chip">Advocate</span><span className="chip-arrow">→</span>
          <span className="chip">Mediator</span><span className="chip-arrow">→</span>
          <span className="chip">Override</span>
        </div>
      </div>
    </div>
  </section>

  {/*  ============ STATS ============  */}
  <section className="stats-section">
    <div className="wrap stats-grid">
      <div className="stat-cell reveal">
        <div className="stat-num">54M+</div>
        <div className="stat-label">Cases pending across India</div>
      </div>
      <div className="stat-cell reveal">
        <div className="stat-num">1.4B+</div>
        <div className="stat-label">People we aim to reach</div>
      </div>
      <div className="stat-cell reveal">
        <div className="stat-num">125K+</div>
        <div className="stat-label">Petitions drafted</div>
      </div>
      <div className="stat-cell reveal">
        <div className="stat-num">640+</div>
        <div className="stat-label">Districts covered</div>
      </div>
    </div>
  </section>

  {/*  ============ HOW IT WORKS ============  */}
  <section id="how-it-works">
    <div className="wrap">
      <div className="section-head reveal">
        <p className="eyebrow">How it works</p>
        <h2>Seven agents, one petition — in 4 minutes</h2>
        <p>Our autonomous pipeline takes your voice input and produces a court-ready legal document without any back-and-forth.</p>
      </div>

      <div className="process-grid">
        <div className="process-step reveal">
          <div className="stamp-num">1</div>
          <h3>Speak your problem</h3>
          <p>Describe your issue in Hindi or any regional language. The intake agent classifies and normalises your complaint automatically.</p>
          <span className="step-tag">Sarvam AI · 98% accuracy</span>
        </div>
        <div className="process-step reveal">
          <div className="stamp-num">2</div>
          <h3>Research runs in parallel</h3>
          <p>The research agent cross-references IndianKanoon and cached precedents to find the strongest legal arguments for your case.</p>
          <span className="step-tag">pgvector · 125K+ archived petitions</span>
        </div>
        <div className="process-step reveal">
          <div className="stamp-num">3</div>
          <h3>Advocate and adversarial check</h3>
          <p>A petition draft is created, then stress-tested by the bureaucrat agent to find and eliminate weak points before you even review it.</p>
          <span className="step-tag">Zero hallucination design</span>
        </div>
        <div className="process-step reveal">
          <div className="stamp-num">4</div>
          <h3>Final petition, ready to file</h3>
          <p>The filing agent assembles a hardened, court-ready document that can be printed and submitted directly to the magistrate's office.</p>
          <span className="step-tag">Drafted in under 4 minutes</span>
        </div>
      </div>
    </div>
  </section>

  {/*  ============ FEATURES / CLAUSES ============  */}
  <section className="light-section">
    <div className="wrap">
      <div className="section-head reveal">
        <p className="eyebrow">Built different</p>
        <h2>Not a chatbot. Not a template.</h2>
        <p>A production-grade autonomous legal pipeline built from first principles.</p>
      </div>

      <div className="clause-grid reveal">
        <div className="clause">
          <span className="clause-num">CLAUSE 01</span>
          <h3>Multi-agent pipeline</h3>
          <p>Seven specialised agents — intake, research, advocate, bureaucrat, mediator, override, and filing — each handling a precise step in the legal workflow.</p>
        </div>
        <div className="clause">
          <span className="clause-num">CLAUSE 02</span>
          <h3>Zero hallucination design</h3>
          <p>Every claim is grounded in IndianKanoon precedents and cross-validated by an adversarial check before the petition is finalised.</p>
        </div>
        <div className="clause">
          <span className="clause-num">CLAUSE 03</span>
          <h3>Voice-first, multilingual</h3>
          <p>Describe your case in Hindi, Bengali, Tamil, or 12 other languages. Sarvam AI handles transcription and intent extraction at 98% accuracy.</p>
        </div>
        <div className="clause">
          <span className="clause-num">CLAUSE 04</span>
          <h3>Institutional memory</h3>
          <p>pgvector stores 125,000+ petitions district-by-district so every new case benefits from the pattern of every past one.</p>
        </div>
        <div className="clause">
          <span className="clause-num">CLAUSE 05</span>
          <h3>Privacy first</h3>
          <p>Your data is encrypted at rest and in transit. Never sold, never shared. Explainable decisions so you always know why a choice was made.</p>
        </div>
        <div className="clause">
          <span className="clause-num">CLAUSE 06</span>
          <h3>Free tier, always</h3>
          <p>Deployed on Vercel, Hugging Face, Neon, Twilio, and Sarvam AI — entirely on free tiers so cost never blocks a citizen from legal help.</p>
        </div>
      </div>
    </div>
  </section>

  {/*  ============ CASE TYPES ============  */}
  <section id="case-types">
    <div className="wrap">
      <div className="section-head reveal">
        <p className="eyebrow">Case types</p>
        <h2>Every legal matter, handled</h2>
        <p>NyaySetu drafts petitions across civil, criminal, consumer, and cyber law — covering the cases citizens face most.</p>
      </div>

      <div className="case-grid">
        <div className="case-card reveal">
          <span className="case-file-no">FILE NO. 156/CrPC</span>
          <h3>FIR not registered</h3>
          <p className="case-act">Section 156(3) CrPC</p>
          <span className="case-stamp">Draft generated</span>
        </div>
        <div className="case-card reveal">
          <span className="case-file-no">FILE NO. PWDVA</span>
          <h3>Domestic violence complaint</h3>
          <p className="case-act">Protection of Women from DV Act</p>
          <span className="case-stamp">Under review</span>
        </div>
        <div className="case-card reveal">
          <span className="case-file-no">FILE NO. 144/CrPC</span>
          <h3>Land dispute resolution</h3>
          <p className="case-act">Section 144 CrPC</p>
          <span className="case-stamp">Mediator review</span>
        </div>
        <div className="case-card reveal">
          <span className="case-file-no">FILE NO. CPA</span>
          <h3>Consumer court claim</h3>
          <p className="case-act">Consumer Protection Act</p>
          <span className="case-stamp">Ready to file</span>
        </div>
        <div className="case-card reveal">
          <span className="case-file-no">FILE NO. 66D/IT</span>
          <h3>Cyber fraud complaint</h3>
          <p className="case-act">IT Act, Section 66D</p>
          <span className="case-stamp">Draft generated</span>
        </div>
      </div>
    </div>
  </section>

  {/*  ============ TESTIMONIAL + MISSION ============  */}
  <section id="about">
    <div className="wrap testimonial-wrap">
      <div className="reveal">
        <span className="quote-mark" aria-hidden="true">"</span>
        <p className="stars">★★★★★</p>
        <blockquote>I had been trying to get an FIR filed for three months. NyaySetu drafted the Section 156(3) petition in minutes and the magistrate accepted it on the first day.</blockquote>
        <div className="cite">
          <span className="cite-avatar">RK</span>
          <div>
            <p className="cite-name">Ravi Kumar</p>
            <p className="cite-role">Farmer, Bhagalpur District</p>
          </div>
        </div>
      </div>

      <div className="mission-card reveal">
        <p className="eyebrow" style={{"color":"var(--brass)","marginBottom":"16px"}}>Our mission</p>
        <p className="mission-line">"Justice delayed is justice denied. NyaySetu ensures justice is not denied."</p>
        <p className="mission-sig">— NyaySetu</p>
      </div>
    </div>
  </section>

  {/*  ============ FINAL CTA ============  */}
  <section className="final-cta">
    <div className="wrap reveal">
      <p className="eyebrow" style={{"color":"var(--tape-dark)","marginBottom":"16px"}}>Get started</p>
      <h2>Your legal rights, in your hands</h2>
      <p>Describe your problem in your own words. NyaySetu handles the rest — from research to a court-ready petition.</p>
      <div className="hero-cta">
        <Link href="/new-case" className="btn btn-stamp">Start voice triage — it's free</Link>
        <Link href="/dashboard" className="btn btn-dark" style={{"background":"transparent","borderColor":"#241F1A33","color":"var(--charcoal)"}}>View the dashboard demo</Link>
      </div>
    </div>
  </section>

</main>

<footer>
  <div className="wrap">
    <div className="footer-top">
      <div className="footer-brand">
        <Link href="#" className="brand" aria-label="NyaySetu home">
          <span className="brand-seal" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M5 8h14M12 8v11M7 19h10" stroke="#B23A2E" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="5" cy="11" r="2.4" stroke="#B8965A" strokeWidth="1.4"/>
              <circle cx="19" cy="11" r="2.4" stroke="#B8965A" strokeWidth="1.4"/>
            </svg>
          </span>
          <span className="brand-text">NyaySetu</span>
        </Link>
        <p>India's Autonomous Legal Rights Navigator. Bridging the justice gap with AI. Built for Bharat, deployed on free tiers, open source at heart.</p>
      </div>

      <div className="footer-col">
        <h4>Product</h4>
        <ul>
          <li><Link href="/new-case">Voice triage</Link></li>
          <li><Link href="/dashboard">Petition generator</Link></li>
          <li><Link href="#how-it-works">Legal research</Link></li>
          <li><Link href="/dashboard">Document upload</Link></li>
        </ul>
      </div>

      <div className="footer-col">
        <h4>Case types</h4>
        <ul>
          <li><Link href="#case-types">Criminal (FIR)</Link></li>
          <li><Link href="#case-types">Domestic violence</Link></li>
          <li><Link href="#case-types">Land disputes</Link></li>
          <li><Link href="#case-types">Consumer cases</Link></li>
          <li><Link href="#case-types">Cyber fraud</Link></li>
        </ul>
      </div>

      <div className="footer-col">
        <h4>Company</h4>
        <ul>
          <li><Link href="#about">About</Link></li>
          <li><Link href="#">Privacy policy</Link></li>
          <li><Link href="#">Terms of service</Link></li>
          <li><Link href="#">Open source</Link></li>
        </ul>
      </div>
    </div>

    <div className="footer-bottom">
      <p>© 2025 NyaySetu · Made in India 🇮🇳 · Powered by Open Source</p>
      <div className="pill-row">
        <span className="pill">Built for Bharat</span>
        <span className="pill">Privacy First</span>
        <span className="pill">Always Available</span>
      </div>
    </div>
  </div>
</footer>
</div>
      <LandingScript />
    </>
  );
}
