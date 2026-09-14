import { useEffect, useState } from "react";
import { ArrowRight, BookOpen, FileText, Globe2, Layers3, Search, Scale } from "lucide-react";
import { Link } from "react-router-dom";
import Logo from "../components/common/Logo";

const modes = [
  {
    icon: FileText,
    title: "Document research",
    text: "Ask questions grounded in the PDFs you upload.",
    context: "Uploaded PDFs",
    evidence: "Relevant passages, with available document and page details.",
  },
  {
    icon: Globe2,
    title: "Web research",
    text: "Explore current information from the open web.",
    context: "Current web results",
    evidence: "Links and previews from the sources returned for your question.",
  },
  {
    icon: Layers3,
    title: "Hybrid research",
    text: "Bring document context and web results together in one answer.",
    context: "Documents + web",
    evidence: "Document and web material presented together for review.",
  },
];

export default function Landing() {
  const [activeMode, setActiveMode] = useState(0);

  useEffect(() => {
    const sections = document.querySelectorAll(".landing .reveal");
    if (!window.IntersectionObserver) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  const mode = modes[activeMode];
  const ModeIcon = mode.icon;

  return (
    <div className="landing">
      <header className="site-header">
        <Logo />
        <nav className="site-nav" aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <Link to="/login">Sign in</Link>
          <Link className="primary-button" to="/signup" aria-label="Start researching"><span className="nav-cta-label">Start researching</span><span className="nav-cta-short">Start</span><ArrowRight size={15}/></Link>
        </nav>
      </header>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <span className="eyebrow">A clearer way to research law</span>
            <h1 className="serif">Legal research,<br/>grounded in evidence.</h1>
            <p>Ask a question. Explore your documents, current web sources, or both. Get a considered answer with the evidence alongside it.</p>
            <div className="hero-actions">
              <Link className="primary-button" to="/signup">Start Researching <ArrowRight size={16}/></Link>
              <a className="text-link" href="#how-it-works">Explore AskLAW</a>
            </div>
            <p className="hero-note">Built for thoughtful legal research. Always review the underlying sources.</p>
          </div>
          <div className="preview" aria-label="Illustrative AskLAW research workflow">
            <div className="preview-top"><span className="brand preview-brand"><Scale size={16}/> AskLAW</span><span>Research preview</span></div>
            <div className="preview-body">
              <div className="preview-question"><span className="preview-caption">Question</span>How does Article 32 protect fundamental rights?</div>
              <div className="preview-flow"><span>Researching relevant material</span><span className="preview-flow-line"/></div>
              <div className="preview-evidence"><span><BookOpen size={13}/> Document evidence</span><span><Globe2 size={13}/> Web evidence</span></div>
              <div className="preview-answer"><span className="preview-caption">Answer</span><h3>An answer, with a trail back to its sources.</h3><p>AskLAW organizes the answer around the material it finds, so you can assess the underlying evidence as you read.</p></div>
            </div>
          </div>
        </section>
        <section id="how-it-works" className="landing-section reveal">
          <span className="eyebrow">The research flow</span><h2>From question to grounded answer.</h2>
          <div className="process">
            <div className="process-card"><b>01 / ASK</b><h3>Your question</h3><p>Start with a legal question in plain language.</p></div>
            <div className="process-card"><b>02 / ROUTE</b><h3>Research path</h3><p>AskLAW selects documents, the web, or both.</p></div>
            <div className="process-card"><b>03 / EXAMINE</b><h3>Evidence</h3><p>Relevant material becomes the basis for the response.</p></div>
            <div className="process-card"><b>04 / UNDERSTAND</b><h3>Answer</h3><p>Read the explanation with its available sources.</p></div>
          </div>
        </section>
        <section className="landing-section reveal">
          <span className="eyebrow">One question, the right context</span><h2>Research across the material that matters.</h2>
          <div className="mode-grid" aria-label="Research capabilities">
            {modes.map(({ icon: Icon, title, text }, index) => <button type="button" className={`mode-card ${index === activeMode ? "active" : ""}`} key={title} aria-pressed={index === activeMode} onClick={() => setActiveMode(index)}><Icon size={24} strokeWidth={1.6}/><h3>{title}</h3><p>{text}</p></button>)}
          </div>
          <div className="mode-detail" aria-live="polite" key={mode.title}>
            <div className="mode-detail-label"><ModeIcon size={17}/> {mode.title}</div>
            <div className="mode-diagram"><span>Question</span><ArrowRight size={15}/><span>{mode.context}</span><ArrowRight size={15}/><span>Evidence</span><ArrowRight size={15}/><span>Answer</span></div>
            <p>{mode.evidence}</p>
          </div>
        </section>
        <section className="landing-section closing reveal"><div className="closing-inner"><Search size={27}/><h2>Begin with a better question.</h2><p>Bring your curiosity and the material you trust. AskLAW helps make the research path clearer.</p><Link className="primary-button" to="/signup">Start Researching <ArrowRight size={16}/></Link></div></section>
      </main>
      <footer className="site-footer"><span>© {new Date().getFullYear()} AskLAW</span><span>Research support, not legal advice.</span></footer>
    </div>
  );
}
