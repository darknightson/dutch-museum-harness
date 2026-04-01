'use strict';

document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initGallery();
  initModal();
  initScrollEffects();
});

const initNavigation = () => {
  const hamburger = document.querySelector('.header__hamburger');
  const nav = document.querySelector('.header__nav');
  const navLinks = document.querySelectorAll('.header__nav-link');

  if (!hamburger || !nav) return;

  hamburger.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('header__nav--open');
    hamburger.classList.toggle('header__hamburger--active');
    hamburger.setAttribute('aria-expanded', isOpen);
    hamburger.setAttribute('aria-label', isOpen ? '메뉴 닫기' : '메뉴 열기');
  });

  nav.addEventListener('click', (e) => {
    if (e.target.matches('.header__nav-link')) {
      nav.classList.remove('header__nav--open');
      hamburger.classList.remove('header__hamburger--active');
      hamburger.setAttribute('aria-expanded', 'false');
      hamburger.setAttribute('aria-label', '메뉴 열기');
    }
  });

  // 스크롤 시 활성 메뉴 하이라이트
  const sections = document.querySelectorAll('section[id]');
  const onScroll = () => {
    const scrollY = window.scrollY + 80;
    sections.forEach((section) => {
      const top = section.offsetTop;
      const height = section.offsetHeight;
      const id = section.getAttribute('id');
      const link = document.querySelector(`.header__nav-link[href="#${id}"]`);
      if (link) {
        if (scrollY >= top && scrollY < top + height) {
          link.classList.add('header__nav-link--active');
        } else {
          link.classList.remove('header__nav-link--active');
        }
      }
    });
  };
  window.addEventListener('scroll', onScroll);
};

const initGallery = () => {
  const filtersContainer = document.querySelector('.gallery__filters');
  const items = document.querySelectorAll('.gallery__item');

  if (!filtersContainer || items.length === 0) return;

  filtersContainer.addEventListener('click', (e) => {
    if (!e.target.matches('.gallery__filter')) return;

    const filter = e.target.dataset.filter;

    filtersContainer.querySelectorAll('.gallery__filter').forEach((btn) => {
      btn.classList.remove('gallery__filter--active');
      btn.setAttribute('aria-pressed', 'false');
    });
    e.target.classList.add('gallery__filter--active');
    e.target.setAttribute('aria-pressed', 'true');

    items.forEach((item) => {
      if (filter === 'all' || item.dataset.museum === filter) {
        item.classList.remove('gallery__item--hidden');
      } else {
        item.classList.add('gallery__item--hidden');
      }
    });
  });
};

const initModal = () => {
  // TODO: 코딩 에이전트가 구현
};

const initScrollEffects = () => {
  // TODO: 코딩 에이전트가 구현
};
