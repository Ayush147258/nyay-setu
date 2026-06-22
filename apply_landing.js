const fs = require('fs');

const data = JSON.parse(fs.readFileSync('landing_extracted.json', 'utf8'));

let jsx = data.jsxContent;

// Replace anchor links with Next.js paths where appropriate
jsx = jsx.replace(/"#start"/g, '"/new-case"');
jsx = jsx.replace(/>Sign in</g, ' href="/login">Sign in<'); 
jsx = jsx.replace(/"#"\s+className="nav-signin"/g, '"/login" className="nav-signin"');
jsx = jsx.replace(/"#petition-preview"/g, '"/dashboard"');
jsx = jsx.replace(/href="#" className="link-sm"/g, 'href="/dashboard" className="link-sm"'); 
jsx = jsx.replace(/<a /g, '<Link ');
jsx = jsx.replace(/<\/a>/g, '</Link>');

// Wrap in landing-page div to allow scoping
jsx = `<div className="landing-page">\n${jsx}\n</div>`;

const pageTsx = `import Link from 'next/link';
import LandingScript from '@/components/landing/LandingScript';

export default function LandingPage() {
  return (
    <>
      ${jsx}
      <LandingScript />
    </>
  );
}
`;

fs.writeFileSync('frontend/src/app/page.tsx', pageTsx);

const scriptTsx = `"use client";
import { useEffect } from 'react';

export default function LandingScript() {
  useEffect(() => {
    const nav = document.getElementById('siteNav');
    const onScroll = () => {
      nav?.classList.toggle('is-scrolled', window.scrollY > 8);
    };
    window.addEventListener('scroll', onScroll, { passive: true });

    const burger = document.getElementById('navBurger');
    const onBurgerClick = () => {
      const open = nav?.classList.toggle('menu-open');
      burger?.setAttribute('aria-expanded', open ? 'true' : 'false');
    };
    burger?.addEventListener('click', onBurgerClick);

    const links = document.getElementById('navLinks')?.querySelectorAll('a');
    const onLinkClick = () => {
      nav?.classList.remove('menu-open');
      burger?.setAttribute('aria-expanded', 'false');
    };
    links?.forEach(a => a.addEventListener('click', onLinkClick));

    const reveals = document.querySelectorAll('.reveal');
    if ('IntersectionObserver' in window) {
      const obs = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('in-view');
            obs.unobserve(entry.target);
          }
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
      reveals.forEach(el => obs.observe(el));
    } else {
      reveals.forEach(el => el.classList.add('in-view'));
    }

    return () => {
      window.removeEventListener('scroll', onScroll);
      burger?.removeEventListener('click', onBurgerClick);
      links?.forEach(a => a.removeEventListener('click', onLinkClick));
    };
  }, []);

  return null;
}
`;

if (!fs.existsSync('frontend/src/components/landing')) {
  fs.mkdirSync('frontend/src/components/landing', { recursive: true });
}
fs.writeFileSync('frontend/src/components/landing/LandingScript.tsx', scriptTsx);

let css = data.styleContent;

// Scope root variables to .landing-page to avoid dashboard conflicts
css = css.replace(/:root\s*\{/g, '.landing-page {');
css = css.replace(/body\s*\{([^}]*)\}/g, '.landing-page { $1 min-height: 100vh; }');
css = css.replace(/html\s*\{([^}]*)\}/g, ''); // scroll-behavior is already handled or we can omit it

// Append to globals.css
const globalsPath = 'frontend/src/app/globals.css';
let globals = fs.readFileSync(globalsPath, 'utf8');

// Ensure we don't append multiple times
if (!globals.includes('.landing-page {')) {
  globals += '\n\n/* ============ LANDING PAGE EXTRACTED ============ */\n' + css;
  fs.writeFileSync(globalsPath, globals);
}

console.log('Done generating frontend files for landing page.');
