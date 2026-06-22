"use client";
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
